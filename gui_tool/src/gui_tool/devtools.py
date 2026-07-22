from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import http.client
import json
import locale
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from . import cleanup


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
EventSink = Callable[[str, object], None]

# Chrome은 127.0.0.1이 이미 점유되어 있으면 IPv6 loopback으로 물러나 바인딩한다.
# 두 주소를 모두 확인해야 "띄웠는데 응답이 없다"는 오진을 피할 수 있다.
LOOPBACK_HOSTS = ("127.0.0.1", "[::1]")


def _port(values: Mapping[str, object], key: str, label: str) -> int:
    raw = values.get(key, "")
    # bool은 int의 하위형이라 int(True)가 1로 통과한다. YAML의 ``on:``/``yes:``가
    # 포트 1로 둔갑하지 않도록 먼저 막는다.
    if isinstance(raw, bool):
        raise ValueError(f"{label}은 정수여야 합니다.")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}은 정수여야 합니다.") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{label}은 1~65535 범위여야 합니다.")
    return value


def _optional_port(values: Mapping[str, object], key: str, label: str) -> int:
    value = str(values.get(key, "")).strip()
    # 빈 값은 0으로 저장되고 YAML에도 0으로 남는다. 0을 다시 "미설정"으로 읽지
    # 않으면 앱이 자기가 쓴 프로파일을 두 번 다시 열지 못한다.
    if not value or value == "0":
        return 0
    return _port(values, key, label)


@dataclass(frozen=True, slots=True)
class DevToolsConfig:
    backend_host: str
    backend_port: int
    ssh_target: str
    chrome_debug_port: int
    remote_debug_port: int
    chrome_profile: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "DevToolsConfig":
        return cls(
            backend_host=str(values.get("backend_host", "")).strip(),
            backend_port=_optional_port(values, "backend_port", "백엔드 웹 포트"),
            ssh_target=str(values.get("ssh_target", "")).strip(),
            chrome_debug_port=_port(values, "chrome_debug_port", "이 PC Chrome 포트"),
            remote_debug_port=_optional_port(values, "remote_debug_port", "원격 DevTools 포트"),
            chrome_profile=str(values.get("chrome_profile", "")).strip(),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "backend_host": self.backend_host,
            "backend_port": self.backend_port,
            "ssh_target": self.ssh_target,
            "chrome_debug_port": self.chrome_debug_port,
            "remote_debug_port": self.remote_debug_port,
            "chrome_profile": self.chrome_profile,
        }

    @property
    def demo_url(self) -> str:
        if self.backend_host and self.backend_port:
            return f"http://{self.backend_host}:{self.backend_port}/"
        return "about:blank"

    @property
    def launch_url(self) -> str:
        return self.demo_url

    @property
    def chrome_profile_path(self) -> Path:
        if self.chrome_profile:
            expanded = os.path.expandvars(os.path.expanduser(self.chrome_profile))
            return Path(expanded)
        return Path(tempfile.gettempdir()) / f"ready-chromedev-chrome-{self.chrome_debug_port}"


def find_chrome() -> Path:
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    executable = shutil.which("chrome.exe") or shutil.which("chrome")
    if executable:
        return Path(executable)
    raise FileNotFoundError("Google Chrome 실행 파일을 찾을 수 없습니다.")


def build_chrome_command(config: DevToolsConfig, chrome: Path | str) -> list[str]:
    return [
        str(chrome),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={config.chrome_debug_port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={config.chrome_profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        config.launch_url,
    ]


def build_ssh_command(config: DevToolsConfig, ssh: str = "ssh.exe") -> list[str]:
    if not config.ssh_target:
        raise ValueError("SSH 대상 별칭 또는 user@host를 입력하세요.")
    if not config.remote_debug_port:
        raise ValueError("원격 DevTools 포트를 입력하세요.")
    remote_forward = (
        f"127.0.0.1:{config.remote_debug_port}:"
        f"127.0.0.1:{config.chrome_debug_port}"
    )
    return [
        ssh,
        "-NT",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-R",
        remote_forward,
        config.ssh_target,
    ]


# 시스템 프록시가 설정되어 있으면 기본 opener는 loopback 요청까지 프록시로
# 보낸다. CDP 확인은 언제나 직접 연결이어야 한다.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe_devtools(host: str, port: int, timeout: float = 2.0) -> dict[str, object] | None:
    try:
        with _DIRECT_OPENER.open(
            f"http://{host}:{port}/json/version", timeout=timeout
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, http.client.HTTPException, json.JSONDecodeError):
        return None
    # DevTools 응답에는 항상 Browser 키가 있다. 이 확인이 없으면 포트를 점유한
    # 다른 JSON 서비스를 Chrome으로 오인한다.
    if isinstance(payload, dict) and "Browser" in payload:
        return payload
    return None


def find_devtools(port: int, timeout: float = 2.0) -> tuple[str, dict[str, object]] | None:
    """CDP가 응답하는 loopback 주소와 그 응답을 찾는다."""
    for host in LOOPBACK_HOSTS:
        payload = probe_devtools(host, port, timeout)
        if payload is not None:
            return host, payload
    return None


def get_devtools_version(port: int, timeout: float = 2.0) -> dict[str, object] | None:
    found = find_devtools(port, timeout)
    return found[1] if found else None


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """127.0.0.1:port를 바인딩할 수 있는지 본다.

    Windows에서는 SO_REUSEADDR를 켜면 남의 소켓을 가로챌 수 있으므로 켜지 않는다.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        return False
    return True


def suggest_free_port(start: int, attempts: int = 50) -> int | None:
    for candidate in range(start + 1, min(start + attempts, 65535) + 1):
        if is_port_free(candidate):
            return candidate
    return None


class PortInUseError(RuntimeError):
    """CDP 포트를 다른 프로세스가 점유해 Chrome을 띄울 수 없는 상황.

    사용자에게는 세 가지가 필요하다: 누가 잡고 있는지, 그것이 앱 소유인지,
    그리고 지금 당장 쓸 수 있는 대안 포트가 무엇인지.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self.owner = cleanup.port_owner(port)
        self.owned_by_app = self._is_owned_by_app()
        self.suggested_port = suggest_free_port(port)
        super().__init__(self._build_message())

    def _is_owned_by_app(self) -> bool:
        if self.owner is None:
            return False
        pid, image = self.owner
        for state in cleanup.read_session_states():
            for item in state.processes:
                if item.pid == pid and item.image == image and item.still_ours:
                    return True
        identity = cleanup.process_identity(pid)
        if identity is None or identity[0] != "chrome.exe":
            return False
        # 세션 기록이 없어도, 해당 포트의 전용 프로파일 폴더를 그 pid가 쓰고
        # 있으면 앱이 시작한 Chrome이다.
        profile = cleanup.temp_root() / f"{cleanup.PROFILE_PREFIX}{self.port}"
        if profile.is_dir():
            return any(item.pid == pid for item in cleanup.processes_using_profile(profile))
        return False

    def _build_message(self) -> str:
        if self.owner is None:
            lines = [f"127.0.0.1:{self.port}을 다른 프로세스가 이미 사용 중입니다."]
        else:
            pid, image = self.owner
            lines = [f"127.0.0.1:{self.port}은 {image}(pid {pid})가 사용 중입니다."]
        if self.owned_by_app:
            lines.append("이전 실행이 남긴 앱 소유 Chrome으로 확인되었습니다. '남은 프로세스 정리'로 치울 수 있습니다.")
        else:
            lines.append("앱이 시작한 프로세스가 아니므로 이 앱은 종료하지 않습니다.")
        if self.suggested_port is not None:
            lines.append(f"비어 있는 포트: {self.suggested_port}")
        return "\n".join(lines)


def decode_process_output(data: bytes) -> str:
    try:
        return data.decode("utf-8").rstrip()
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace").rstrip()


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount",
        "WriteOperationCount",
        "OtherOperationCount",
        "ReadTransferCount",
        "WriteTransferCount",
        "OtherTransferCount",
    )]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJob:
    """Own a Windows process tree and kill it when the job is closed."""

    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    def __init__(self) -> None:
        self.handle: object | None = None
        if os.name != "nt":
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        limits = _JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if self.handle is None:
            return
        process_handle = getattr(process, "_handle", None)
        if not process_handle:
            # Win32 호출을 하지 않았으므로 get_last_error()는 여기서 무의미하다.
            raise OSError("프로세스 핸들을 얻지 못해 Job Object에 넣을 수 없습니다.")
        if not self._kernel32.AssignProcessToJobObject(self.handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle is None:
            return
        handle = self.handle
        self.handle = None
        if os.name == "nt":
            self._kernel32.TerminateJobObject(handle, 1)
            self._kernel32.CloseHandle(handle)


class DevToolsRunner:
    def __init__(self) -> None:
        self._ssh_process: subprocess.Popen[bytes] | None = None
        self._ssh_job: _WindowsJob | None = None
        self._chrome_process: subprocess.Popen[bytes] | None = None
        self._chrome_job: _WindowsJob | None = None
        self._owns_chrome = False
        self._session_port: int | None = None
        self._devtools_host = "127.0.0.1"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        """세션이 살아 있는지. 기존 Chrome을 빌려 쓰는 경우도 실행 중이다."""
        if not self._stop_event.is_set() and self._session_port is not None:
            return True
        with self._lock:
            processes = [self._ssh_process, self._chrome_process]
        return any(p is not None and p.poll() is None for p in processes)

    @property
    def devtools_host(self) -> str:
        """CDP가 실제로 응답한 loopback 주소."""
        return self._devtools_host

    @property
    def owns_chrome(self) -> bool:
        """이번 세션의 Chrome을 앱이 시작했는가. 빌려 쓰는 중이면 False."""
        return self._owns_chrome

    def run_local(self, config: DevToolsConfig, emit: EventSink) -> int:
        self._stop_event.clear()
        try:
            devtools = self._prepare_devtools(config, emit, steps=2)
            if self._stop_event.is_set():
                return 0
            emit("log", f"[2/2] Chrome DevTools 확인: {devtools.get('Browser', 'unknown')}")
            emit("log", f"      로컬 주소: http://{self._devtools_host}:{config.chrome_debug_port}")
            emit("state", "로컬 DevTools 실행 중")
            return self._wait_for_stop()
        finally:
            self._close_all()

    def run_tunnel(self, config: DevToolsConfig, emit: EventSink) -> int:
        self._stop_event.clear()
        try:
            return self._run_tunnel(config, emit)
        finally:
            self._close_all()

    def _prepare_devtools(
        self, config: DevToolsConfig, emit: EventSink, *, steps: int
    ) -> dict[str, object]:
        port = config.chrome_debug_port
        self._session_port = port
        found = find_devtools(port)

        if found:
            # 앱이 시작하지 않은 Chrome이다. 규칙상 중지해도 종료하지 않으므로
            # 그 사실을 로그에 남긴다.
            self._devtools_host, devtools = found
            self._owns_chrome = False
            emit("log", f"[1/{steps}] 기존 Chrome DevTools를 사용합니다: {self._devtools_host}:{port}")
            emit("log", "      앱이 시작한 Chrome이 아니므로 중지해도 이 Chrome은 종료하지 않습니다.")
            self._save_session(config)
            return devtools

        if not self._wait_port_free(port):
            if self._stop_event.is_set():
                return {}
            raise PortInUseError(port)

        chrome = find_chrome()
        command = build_chrome_command(config, chrome)
        emit("log", f"[1/{steps}] Chrome DevTools를 {port} 포트로 실행합니다.")
        emit("log", f"      프로필: {config.chrome_profile_path}")
        emit("log", f"      시작 URL: {config.launch_url}")
        self._launch_chrome(command)
        self._owns_chrome = True
        self._save_session(config)

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self._stop_event.is_set():
            found = find_devtools(port)
            if found:
                self._devtools_host, devtools = found
                self._save_session(config)
                return devtools
            with self._lock:
                process = self._chrome_process
            if process is not None and process.poll() is not None:
                # Chrome이 곧바로 끝났다면 대개 같은 프로필을 쓰는 Chrome이 이미
                # 있어서 명령줄만 넘기고 물러난 것이다. 20초를 더 기다릴 이유가 없다.
                raise RuntimeError(
                    f"Chrome이 즉시 종료했습니다(exit code={process.returncode}). "
                    f"같은 프로필 폴더({config.chrome_profile_path})를 쓰는 Chrome이 "
                    "이미 실행 중일 수 있습니다."
                )
            time.sleep(0.5)

        if self._stop_event.is_set():
            return {}
        raise RuntimeError(
            f"Chrome DevTools가 {port} 포트에서 20초 안에 응답하지 않았습니다."
        )

    def _wait_port_free(self, port: int, timeout: float = 3.0) -> bool:
        """중지 직후 재시작이면 이전 소켓의 반납이 끝나지 않았을 수 있다.

        일시적 점유는 잠깐 기다리면 풀리므로, 바로 실패시키지 않고 짧게 재시도한다.
        """
        deadline = time.monotonic() + timeout
        while True:
            if is_port_free(port):
                return True
            if self._stop_event.is_set() or time.monotonic() >= deadline:
                return False
            time.sleep(0.3)

    def _save_session(self, config: DevToolsConfig) -> None:
        """다음 실행이 이 프로세스들을 되찾을 수 있도록 소유권 증거를 남긴다."""
        with self._lock:
            chrome, ssh = self._chrome_process, self._ssh_process
        tracked = []
        for kind, process in (("chrome", chrome), ("ssh", ssh)):
            if process is None or process.poll() is not None:
                continue
            item = cleanup.TrackedProcess.capture(kind, process.pid)
            if item is not None:
                tracked.append(item)
        state = cleanup.SessionState(
            port=config.chrome_debug_port,
            owner_pid=os.getpid(),
            user_data_dir=str(config.chrome_profile_path),
            owns_chrome=self._owns_chrome,
            processes=tuple(tracked),
        )
        try:
            cleanup.write_session_state(state)
        except OSError:
            # 세션 파일은 편의 기능이다. 쓰지 못한다고 실행을 막지 않는다.
            pass

    def _run_tunnel(self, config: DevToolsConfig, emit: EventSink) -> int:
        devtools = self._prepare_devtools(config, emit, steps=3)
        if self._stop_event.is_set():
            return 0

        emit("log", f"[2/3] Chrome DevTools 확인: {devtools.get('Browser', 'unknown')}")
        emit("log", f"      시작 URL: {config.launch_url}")

        ssh = shutil.which("ssh.exe") or shutil.which("ssh")
        if not ssh:
            raise FileNotFoundError("OpenSSH Client의 ssh 실행 파일을 찾을 수 없습니다.")
        command = build_ssh_command(config, ssh)
        emit(
            "log",
            f"[3/3] 원격 127.0.0.1:{config.remote_debug_port} -> "
            f"이 PC 127.0.0.1:{config.chrome_debug_port}",
        )
        emit("log", f"      SSH 대상: {config.ssh_target}")

        # stop()이 이 창 안에 들어오면 아직 _ssh_process가 없어 아무것도 죽이지
        # 못한다. 그 상태로 ssh를 띄우면 누구도 회수할 수 없는 프로세스가 된다.
        if self._stop_event.is_set():
            return 0

        process, job = self._spawn_tracked(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self._ssh_process = process
            self._ssh_job = job
        if self._stop_event.is_set():
            # 등록과 stop()이 교차했다면 여기서 직접 회수한다.
            self._close_ssh()
            return 0
        self._save_session(config)
        emit("state", "실행 중")

        try:
            assert process.stdout is not None
            for raw_line in iter(process.stdout.readline, b""):
                line = decode_process_output(raw_line)
                if line:
                    emit("log", line)
            return process.wait()
        finally:
            self._close_ssh()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_all()

    def _wait_for_stop(self) -> int:
        while not self._stop_event.wait(0.25):
            with self._lock:
                process = self._chrome_process
            if process and process.poll() is not None:
                return process.returncode or 0
        return 0

    def _spawn_tracked(
        self, command: list[str], **kwargs: object
    ) -> tuple[subprocess.Popen[bytes], _WindowsJob | None]:
        """자식 프로세스를 Job Object에 넣어 띄운다.

        Job Object에 KILL_ON_JOB_CLOSE가 걸려 있으므로, 앱이 어떤 방식으로 죽든
        (정상 종료, 크래시, 작업 관리자 강제 종료) 자식 트리가 함께 정리된다.
        """
        job: _WindowsJob | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            job = _WindowsJob()
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, **kwargs)
            try:
                job.assign(process)
            except OSError:
                # Job Object를 사용할 수 없는 환경에서는 주 프로세스만 정리한다.
                job.close()
                job = None
            return process, job
        except Exception:
            if job:
                job.close()
            if process and process.poll() is None:
                process.terminate()
            raise

    def _launch_chrome(self, command: list[str]) -> None:
        process, job = self._spawn_tracked(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_PROCESS_GROUP,
        )
        with self._lock:
            self._chrome_process = process
            self._chrome_job = job

    def _close_all(self) -> None:
        self._close_ssh()
        self._close_chrome()
        port, self._session_port = self._session_port, None
        self._owns_chrome = False
        if port is not None:
            cleanup.clear_session_state(port)

    def _close_ssh(self) -> None:
        with self._lock:
            process = self._ssh_process
            job = self._ssh_job
            self._ssh_process = None
            self._ssh_job = None
        self._terminate(process, job)

    def _close_chrome(self) -> None:
        with self._lock:
            process = self._chrome_process
            job = self._chrome_job
            self._chrome_process = None
            self._chrome_job = None
        self._terminate(process, job)

    @staticmethod
    def _terminate(
        process: subprocess.Popen[bytes] | None, job: _WindowsJob | None
    ) -> None:
        if job:
            # TerminateJobObject가 프로세스 트리 전체를 함께 끝낸다.
            job.close()
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
