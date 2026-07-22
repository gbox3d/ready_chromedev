"""앱이 시작한 Chrome·ssh 프로세스를 재실행 시점에 되찾아 정리한다.

앱이 소유하지 않은 Chrome은 절대 건드리지 않는다는 규칙을 지키려면, 먼저
"무엇이 앱 소유인지"에 대한 증거를 남겨야 한다. 실행 중에 세션 파일을 써 두고,
다음 실행에서 그 파일에 적힌 pid가 아직 **같은 프로세스**인지 확인한 뒤에만
종료 대상으로 삼는다. pid는 Windows에서 빠르게 재사용되므로 pid만으로는
증거가 되지 못한다. 그래서 이미지 이름과 생성 시각을 함께 기록하고 대조한다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


SESSION_PREFIX = "ready-chromedev-session-"
PROFILE_PREFIX = "ready-chromedev-chrome-"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_MORE_DATA = 234


def temp_root() -> Path:
    return Path(tempfile.gettempdir())


def session_path(port: int) -> Path:
    return temp_root() / f"{SESSION_PREFIX}{port}.json"


class _FileTime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


def _kernel32() -> ctypes.WinDLL | None:
    if os.name != "nt":
        return None
    return ctypes.WinDLL("kernel32", use_last_error=True)


def process_identity(pid: int) -> tuple[str, int] | None:
    """살아 있는 pid의 (이미지 이름, 생성 시각)을 돌려준다. 죽었으면 None.

    생성 시각은 100ns 단위 FILETIME 정수다. pid 재사용을 걸러내는 지문으로만
    쓰므로 사람이 읽을 수 있는 형식으로 바꾸지 않는다.
    """
    kernel32 = _kernel32()
    if kernel32 is None or pid <= 0:
        return None

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None

    try:
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        image = Path(buffer.value).name.lower()

        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        created, exited, kernel_time, user_time = (_FileTime() for _ in range(4))
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return image, stamp
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)


def is_alive(pid: int) -> bool:
    return process_identity(pid) is not None


class _MibTcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class _MibTcp6RowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


def port_owner(port: int) -> tuple[int, str] | None:
    """loopback 포트를 LISTEN 중인 프로세스의 (pid, 이미지 이름)을 찾는다.

    "포트가 사용 중"이라는 오류에 점유자가 누구인지를 함께 밝히기 위한 것이다.
    이름이 없으면 사용자는 앱이 자기 프로세스와 충돌한다고 오해할 수밖에 없다.
    """
    if os.name != "nt":
        return None
    iphlpapi = ctypes.WinDLL("iphlpapi")
    TCP_TABLE_OWNER_PID_LISTENER = 3
    for family, row_type in ((2, _MibTcpRowOwnerPid), (23, _MibTcp6RowOwnerPid)):
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(
            None, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_LISTENER, 0
        )
        if not size.value:
            continue
        buffer = ctypes.create_string_buffer(size.value)
        if iphlpapi.GetExtendedTcpTable(
            buffer, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_LISTENER, 0
        ):
            continue
        count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
        rows = ctypes.cast(
            ctypes.byref(buffer, ctypes.sizeof(wintypes.DWORD)),
            ctypes.POINTER(row_type * count),
        ).contents
        for row in rows:
            # dwLocalPort는 하위 16비트가 network byte order다.
            if ((row.dwLocalPort & 0xFF) << 8) | ((row.dwLocalPort >> 8) & 0xFF) != port:
                continue
            pid = int(row.dwOwningPid)
            identity = process_identity(pid)
            return pid, identity[0] if identity else "unknown"
    return None


class _RmUniqueProcess(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", wintypes.DWORD),
        ("ProcessStartTime", _FileTime),
    ]


class _RmProcessInfo(ctypes.Structure):
    _fields_ = [
        ("Process", _RmUniqueProcess),
        ("strAppName", ctypes.c_wchar * 256),
        ("strServiceShortName", ctypes.c_wchar * 64),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wintypes.ULONG),
        ("TSSessionId", wintypes.DWORD),
        ("bRestartable", wintypes.BOOL),
    ]


def pids_with_open_handles(paths: list[Path]) -> set[int]:
    """주어진 파일에 핸들을 열어 둔 프로세스의 pid 집합 (Restart Manager).

    세션 파일이 없는 옛 실행의 Chrome을 되찾는 마지막 수단이다. 전용 프로파일
    폴더 안의 파일을 잡고 있는 프로세스는 그 폴더를 쓰는 Chrome뿐이다.
    """
    if os.name != "nt" or not paths:
        return set()
    try:
        rstrtmgr = ctypes.WinDLL("rstrtmgr")
    except OSError:
        return set()
    handle = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(33)
    if rstrtmgr.RmStartSession(ctypes.byref(handle), 0, key):
        return set()
    try:
        names = (ctypes.c_wchar_p * len(paths))(*[str(path) for path in paths])
        if rstrtmgr.RmRegisterResources(handle.value, len(paths), names, 0, None, 0, None):
            return set()
        needed = ctypes.c_uint(0)
        count = ctypes.c_uint(0)
        reasons = wintypes.DWORD()
        result = rstrtmgr.RmGetList(
            handle.value, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons)
        )
        while result == ERROR_MORE_DATA:
            count = ctypes.c_uint(needed.value)
            infos = (_RmProcessInfo * count.value)()
            result = rstrtmgr.RmGetList(
                handle.value, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons)
            )
            if result == 0:
                return {int(infos[i].Process.dwProcessId) for i in range(count.value)}
        return set()
    finally:
        rstrtmgr.RmEndSession(handle.value)


# Chrome이 user-data-dir 안에서 계속 핸들을 쥐고 있을 법한 파일들.
_PROFILE_LOCK_CANDIDATES = (
    "Local State",
    "DevToolsActivePort",
    "lockfile",
    "Default/History",
    "Default/Cookies",
    "Default/Network/Cookies",
    "Default/Local Storage/leveldb/LOCK",
)


def processes_using_profile(path: Path) -> tuple[TrackedProcess, ...]:
    """전용 프로파일 폴더를 실제로 사용 중인 chrome.exe들을 찾는다.

    세션 파일이 없어도(구버전 실행, 세션 기록 실패) 폴더 이름 자체가 앱의
    마커이므로, 그 폴더를 쓰는 Chrome은 앱이 시작한 것으로 판정할 수 있다.
    """
    candidates = [path / relative for relative in _PROFILE_LOCK_CANDIDATES]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    found = []
    for pid in sorted(pids_with_open_handles(existing)):
        if pid == os.getpid():
            continue
        tracked = TrackedProcess.capture("chrome", pid)
        if tracked is not None and tracked.image == "chrome.exe":
            found.append(tracked)
    return tuple(found)


@dataclass(frozen=True, slots=True)
class TrackedProcess:
    """세션 파일에 기록하는 프로세스 한 건."""

    kind: str  # "chrome" | "ssh"
    pid: int
    image: str
    created_at: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "pid": self.pid,
            "image": self.image,
            "created_at": self.created_at,
        }

    @classmethod
    def capture(cls, kind: str, pid: int) -> "TrackedProcess | None":
        identity = process_identity(pid)
        if identity is None:
            return None
        image, created_at = identity
        return cls(kind=kind, pid=pid, image=image, created_at=created_at)

    @classmethod
    def from_mapping(cls, values: object) -> "TrackedProcess | None":
        if not isinstance(values, dict):
            return None
        try:
            return cls(
                kind=str(values["kind"]),
                pid=int(values["pid"]),
                image=str(values["image"]),
                created_at=int(values["created_at"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def still_ours(self) -> bool:
        """기록한 그 프로세스가 아직 살아 있는지. pid 재사용이면 False."""
        identity = process_identity(self.pid)
        return identity is not None and identity == (self.image, self.created_at)


@dataclass(frozen=True, slots=True)
class SessionState:
    """실행 중 남기는 소유권 증거."""

    port: int
    owner_pid: int
    user_data_dir: str
    owns_chrome: bool
    processes: tuple[TrackedProcess, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "version": 1,
            "port": self.port,
            "owner_pid": self.owner_pid,
            "user_data_dir": self.user_data_dir,
            "owns_chrome": self.owns_chrome,
            "processes": [item.to_mapping() for item in self.processes],
        }

    @classmethod
    def from_mapping(cls, values: object) -> "SessionState | None":
        if not isinstance(values, dict):
            return None
        try:
            port = int(values["port"])
            owner_pid = int(values["owner_pid"])
        except (KeyError, TypeError, ValueError):
            return None
        tracked = []
        raw = values.get("processes")
        if isinstance(raw, list):
            for item in raw:
                parsed = TrackedProcess.from_mapping(item)
                if parsed is not None:
                    tracked.append(parsed)
        return cls(
            port=port,
            owner_pid=owner_pid,
            user_data_dir=str(values.get("user_data_dir", "")),
            owns_chrome=bool(values.get("owns_chrome", False)),
            processes=tuple(tracked),
        )


def write_session_state(state: SessionState) -> None:
    path = session_path(state.port)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(state.to_mapping(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def clear_session_state(port: int) -> None:
    session_path(port).unlink(missing_ok=True)


def read_session_states() -> list[SessionState]:
    states = []
    try:
        candidates = sorted(temp_root().glob(f"{SESSION_PREFIX}*.json"))
    except OSError:
        return states
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        state = SessionState.from_mapping(payload)
        if state is None:
            path.unlink(missing_ok=True)
        else:
            states.append(state)
    return states


@dataclass(frozen=True, slots=True)
class Leftover:
    """이전 실행이 남긴, 정리해도 되는 것들."""

    port: int
    processes: tuple[TrackedProcess, ...]
    profile_dir: Path | None

    @property
    def is_empty(self) -> bool:
        return not self.processes and self.profile_dir is None

    def describe(self) -> str:
        parts = []
        for item in self.processes:
            parts.append(f"{item.image} (pid {item.pid})")
        if self.profile_dir is not None:
            parts.append(f"프로파일 폴더 {self.profile_dir.name}")
        return f"포트 {self.port}: " + ", ".join(parts)


def find_leftovers(owner_is_alive: object = None) -> list[Leftover]:
    """죽은 실행이 남긴 프로세스와 폴더를 찾는다.

    세션을 만든 GUI 프로세스가 아직 살아 있으면 그 세션은 건드리지 않는다.
    현재 실행 중인 자기 자신도, 두 번째로 띄운 다른 창도 여기에 걸린다 —
    창을 하나 더 열었다는 이유로 먼저 열린 창의 Chrome을 죽이면 안 된다.
    """
    alive_check = owner_is_alive if callable(owner_is_alive) else is_alive

    leftovers = []
    claimed_ports = set()
    for state in read_session_states():
        claimed_ports.add(state.port)
        if alive_check(state.owner_pid):
            # 소유자가 살아 있다. 정리 대상이 아니다.
            continue
        alive = tuple(item for item in state.processes if item.still_ours)
        profile_dir = _reclaimable_profile_dir(state)
        leftover = Leftover(port=state.port, processes=alive, profile_dir=profile_dir)
        if leftover.is_empty:
            # 남은 것이 없다. 세션 파일만 치운다.
            clear_session_state(state.port)
            continue
        leftovers.append(leftover)

    for path in _orphan_profile_dirs(claimed_ports):
        # 세션 파일이 없어도 폴더를 쓰는 Chrome이 남아 있을 수 있다(구버전 실행 등).
        leftovers.append(
            Leftover(
                port=_port_of_dir(path),
                processes=processes_using_profile(path),
                profile_dir=path,
            )
        )
    return leftovers


def _reclaimable_profile_dir(state: SessionState) -> Path | None:
    if not state.owns_chrome or not state.user_data_dir:
        return None
    path = Path(state.user_data_dir)
    if path.name.startswith(PROFILE_PREFIX) and path.is_dir():
        return path
    return None


def _port_of_dir(path: Path) -> int:
    suffix = path.name[len(PROFILE_PREFIX):]
    return int(suffix) if suffix.isdigit() else 0


def _orphan_profile_dirs(known_ports: set[int]) -> list[Path]:
    """세션 파일이 없는 전용 프로파일 폴더. 매 실행마다 쌓이므로 같이 치운다."""
    orphans = []
    try:
        candidates = sorted(temp_root().glob(f"{PROFILE_PREFIX}*"))
    except OSError:
        return orphans
    for path in candidates:
        if path.is_dir() and _port_of_dir(path) not in known_ports:
            orphans.append(path)
    return orphans


def terminate_tree(pid: int) -> bool:
    """프로세스와 그 자식들을 종료한다.

    이미 돌고 있는 프로세스를 새 Job Object에 넣어도 **이미 태어난** 자식은
    소급해서 딸려오지 않는다. 그래서 여기서는 Job Object를 쓰지 않고 트리 종료를
    지원하는 taskkill을 쓴다.
    """
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def remove_profile_dir(path: Path) -> bool:
    try:
        shutil.rmtree(path, ignore_errors=False)
    except OSError:
        # Chrome이 lockfile 핸들을 아직 쥐고 있으면 지워지지 않는다. 다음 실행에서
        # 다시 시도하면 되므로 실패를 치명적으로 다루지 않는다.
        return False
    return True


def clean_leftovers(leftovers: list[Leftover], log: object = None) -> tuple[int, int]:
    """검증된 잔존 프로세스를 종료하고 남은 폴더를 지운다. (프로세스 수, 폴더 수)"""

    def emit(message: str) -> None:
        if callable(log):
            log(message)

    killed = 0
    removed = 0
    for leftover in leftovers:
        for item in leftover.processes:
            # 종료 직전에 한 번 더 확인한다. 스캔과 정리 사이에 pid가 재사용되었을
            # 수 있고, 그 경우 남의 프로세스를 죽이게 된다.
            if not item.still_ours:
                emit(f"건너뜀: {item.image} pid {item.pid}는 이미 종료되었거나 다른 프로세스입니다.")
                continue
            if terminate_tree(item.pid):
                killed += 1
                emit(f"종료함: {item.image} (pid {item.pid}, 포트 {leftover.port})")
            else:
                emit(f"종료 실패: {item.image} (pid {item.pid})")
        if leftover.profile_dir is not None:
            if remove_profile_dir(leftover.profile_dir):
                removed += 1
                emit(f"삭제함: {leftover.profile_dir}")
            else:
                emit(f"삭제 보류: {leftover.profile_dir} (사용 중)")
        clear_session_state(leftover.port)
    return killed, removed
