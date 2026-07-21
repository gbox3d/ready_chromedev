from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import locale
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
EventSink = Callable[[str, object], None]


def _required_text(values: Mapping[str, object], key: str, label: str) -> str:
    value = str(values.get(key, "")).strip()
    if not value:
        raise ValueError(f"{label}을(를) 입력하세요.")
    return value


def _port(values: Mapping[str, object], key: str, label: str) -> int:
    try:
        value = int(values.get(key, ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}은 정수여야 합니다.") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{label}은 1~65535 범위여야 합니다.")
    return value


@dataclass(frozen=True, slots=True)
class TunnelConfig:
    backend_host: str
    backend_port: int
    ssh_user: str
    ssh_host: str
    chrome_debug_port: int
    remote_debug_port: int
    chrome_profile: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "TunnelConfig":
        return cls(
            backend_host=_required_text(values, "backend_host", "백엔드 호스트"),
            backend_port=_port(values, "backend_port", "백엔드 웹 포트"),
            ssh_user=_required_text(values, "ssh_user", "SSH 사용자"),
            ssh_host=str(values.get("ssh_host", "")).strip(),
            chrome_debug_port=_port(values, "chrome_debug_port", "이 PC Chrome 포트"),
            remote_debug_port=_port(values, "remote_debug_port", "원격 DevTools 포트"),
            chrome_profile=str(values.get("chrome_profile", "")).strip(),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "backend_host": self.backend_host,
            "backend_port": self.backend_port,
            "ssh_user": self.ssh_user,
            "ssh_host": self.ssh_host,
            "chrome_debug_port": self.chrome_debug_port,
            "remote_debug_port": self.remote_debug_port,
            "chrome_profile": self.chrome_profile,
        }

    @property
    def ssh_target(self) -> str:
        return self.ssh_host or f"{self.ssh_user}@{self.backend_host}"

    @property
    def demo_url(self) -> str:
        return f"http://{self.backend_host}:{self.backend_port}/"

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


def build_chrome_command(config: TunnelConfig, chrome: Path | str) -> list[str]:
    return [
        str(chrome),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={config.chrome_debug_port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={config.chrome_profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        config.demo_url,
    ]


def build_ssh_command(config: TunnelConfig, ssh: str = "ssh.exe") -> list[str]:
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


def get_devtools_version(port: int, timeout: float = 2.0) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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
        if not process_handle or not self._kernel32.AssignProcessToJobObject(
            self.handle, process_handle
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle is None:
            return
        handle = self.handle
        self.handle = None
        if os.name == "nt":
            self._kernel32.TerminateJobObject(handle, 1)
            self._kernel32.CloseHandle(handle)


class TunnelRunner:
    def __init__(self) -> None:
        self._ssh_process: subprocess.Popen[bytes] | None = None
        self._chrome_process: subprocess.Popen[bytes] | None = None
        self._chrome_job: _WindowsJob | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        with self._lock:
            process = self._ssh_process
            return process is not None and process.poll() is None

    def run(self, config: TunnelConfig, emit: EventSink) -> int:
        self._stop_event.clear()
        try:
            return self._run(config, emit)
        finally:
            self._close_chrome()

    def _run(self, config: TunnelConfig, emit: EventSink) -> int:
        devtools = get_devtools_version(config.chrome_debug_port)

        if not devtools:
            chrome = find_chrome()
            command = build_chrome_command(config, chrome)
            emit("log", f"[1/3] Chrome DevTools를 {config.chrome_debug_port} 포트로 실행합니다.")
            emit("log", f"      프로필: {config.chrome_profile_path}")
            self._launch_chrome(command)

            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not self._stop_event.is_set():
                devtools = get_devtools_version(config.chrome_debug_port)
                if devtools:
                    break
                time.sleep(0.5)

        if self._stop_event.is_set():
            return 0
        if not devtools:
            raise RuntimeError(
                f"Chrome DevTools가 127.0.0.1:{config.chrome_debug_port}에서 응답하지 않습니다."
            )

        emit("log", f"[2/3] Chrome DevTools 확인: {devtools.get('Browser', 'unknown')}")
        emit("log", f"      데모: {config.demo_url}")

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

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self._ssh_process = process
        emit("state", "실행 중")

        try:
            assert process.stdout is not None
            for raw_line in iter(process.stdout.readline, b""):
                line = decode_process_output(raw_line)
                if line:
                    emit("log", line)
            return process.wait()
        finally:
            with self._lock:
                if self._ssh_process is process:
                    self._ssh_process = None

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._ssh_process
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        self._close_chrome()

    def _launch_chrome(self, command: list[str]) -> None:
        job: _WindowsJob | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            job = _WindowsJob()
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NEW_PROCESS_GROUP,
            )
            try:
                job.assign(process)
            except OSError:
                # Job Object를 사용할 수 없는 환경에서는 주 프로세스만 정리한다.
                job.close()
                job = None
            with self._lock:
                self._chrome_process = process
                self._chrome_job = job
        except Exception:
            if job:
                job.close()
            if process and process.poll() is None:
                process.terminate()
            raise

    def _close_chrome(self) -> None:
        with self._lock:
            process = self._chrome_process
            job = self._chrome_job
            self._chrome_process = None
            self._chrome_job = None

        if job:
            job.close()
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
