from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from . import cleanup, rpc
from .profiles import ProfileStore, validate_profile_name
from .devtools import DevToolsConfig, DevToolsRunner, PortInUseError


# 로그가 무한히 자라면 Tk Text 위젯이 느려진다.
MAX_LOG_LINES = 2000


# In the editable uv workflow this resolves from ``src/gui_tool/app.py`` to
# the project directory, keeping the user-editable profile beside pyproject.toml.
APP_DIR = Path(__file__).resolve().parents[2]
PROFILE_PATH = APP_DIR / "profiles.yaml"


class DevToolsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.runner = DevToolsRunner()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.stop_requested = False
        self._closing = False
        self._drain_job: str | None = None
        # AI가 RPC로 시작한 실행에서는 모달 대화상자를 띄우지 않는다. 사람이 없는 경로에서
        # 대화상자가 뜨면 UI가 멈추고 호출자는 영문도 모른 채 기다린다.
        self._start_source = "ui"
        self._last_error: str | None = None
        self._dispatcher: rpc.TkDispatcher | None = None
        self._rpc: rpc.RpcServer | None = None

        self.store = ProfileStore(PROFILE_PATH)
        try:
            self.store.load()
        except (OSError, ValueError) as exc:
            messagebox.showerror("프로파일 오류", str(exc))
            raise SystemExit(1) from exc

        self.profile_name = tk.StringVar(value=self.store.active_profile)
        self.status = tk.StringVar(value="중지됨")
        self.mode = tk.StringVar(value="local")
        self.local_mcp_info = tk.StringVar()
        self.tunnel_mcp_info = tk.StringVar()
        self.local_values = {
            "backend_host": tk.StringVar(value="localhost"),
            "backend_port": tk.StringVar(value="8000"),
            "chrome_debug_port": tk.StringVar(value="9222"),
        }
        self.values = {
            "backend_host": tk.StringVar(),
            "backend_port": tk.StringVar(),
            "ssh_target": tk.StringVar(),
            "chrome_debug_port": tk.StringVar(),
            "remote_debug_port": tk.StringVar(),
            "chrome_profile": tk.StringVar(),
        }
        self.field_widgets: list[ttk.Entry] = []

        self._build_ui()
        self._refresh_profile_names()
        self._load_profile(self.store.active_profile)
        for variable in (
            *self.local_values.values(),
            *self.values.values(),
            self.status,
            self.mode,
        ):
            variable.trace_add("write", lambda *_: self._refresh_ai_context())
        self._on_tab_changed()
        self._refresh_ai_context()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._drain_job = self.root.after(100, self._drain_events)
        self.root.after(300, self.scan_leftovers)

    def _build_ui(self) -> None:
        self.root.title("DevTools MCP 연결 GUI")
        self.root.minsize(860, 900)

        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        self.mode_notebook = ttk.Notebook(outer)
        self.mode_notebook.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        self.local_tab = ttk.Frame(self.mode_notebook, padding=12)
        self.tunnel_tab = ttk.Frame(self.mode_notebook, padding=12)
        self.mode_notebook.add(self.local_tab, text="로컬 DevTools MCP")
        self.mode_notebook.add(self.tunnel_tab, text="SSH 역터널 MCP")

        ttk.Label(
            self.local_tab,
            text=(
                "프로파일 없이 localhost의 개발 서버와 Chrome 기본 CDP 포트를 사용하는 "
                "단순한 로컬 구성입니다. SSH 인자는 사용하지 않습니다."
            ),
            wraplength=790,
        ).grid(row=0, column=0, pady=(0, 8), sticky="w")
        local_fields = ttk.LabelFrame(self.local_tab, text="로컬 Chrome / CDP 인자", padding=8)
        local_fields.grid(row=1, column=0, sticky="ew")
        self._add_fields(
            local_fields,
            (
                ("로컬 웹 호스트", "backend_host"),
                ("로컬 웹 포트", "backend_port"),
                ("Chrome CDP 포트", "chrome_debug_port"),
            ),
            self.local_values,
        )
        local_mcp_frame = ttk.LabelFrame(self.local_tab, text="MCP 연결 인자", padding=8)
        local_mcp_frame.grid(row=2, column=0, pady=(8, 0), sticky="ew")
        ttk.Label(local_mcp_frame, textvariable=self.local_mcp_info, wraplength=760).grid(
            row=0, column=0, sticky="w"
        )
        self.local_tab.columnconfigure(0, weight=1)

        ttk.Label(
            self.tunnel_tab,
            text=(
                "이 PC의 Chrome CDP를 SSH -R로 원격 서버의 loopback 포트에 전달하고, "
                "원격 서버의 chrome-devtools-mcp가 그 포트에 연결하는 구성입니다."
            ),
            wraplength=790,
        ).grid(row=0, column=0, pady=(0, 8), sticky="w")

        profile_frame = ttk.LabelFrame(self.tunnel_tab, text="역터널 프로파일", padding=8)
        profile_frame.grid(row=1, column=0, pady=(0, 8), sticky="ew")
        profile_frame.columnconfigure(0, weight=1)
        self.profile_combo = ttk.Combobox(
            profile_frame, textvariable=self.profile_name, state="readonly"
        )
        self.profile_combo.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self.new_button = ttk.Button(profile_frame, text="새 프로파일", command=self.new_profile)
        self.new_button.grid(row=0, column=1, padx=3)
        self.save_button = ttk.Button(profile_frame, text="설정 저장", command=self.save_profile)
        self.save_button.grid(row=0, column=2, padx=3)
        self.delete_button = ttk.Button(profile_frame, text="삭제", command=self.delete_profile)
        self.delete_button.grid(row=0, column=3, padx=(3, 0))

        tunnel_chrome_fields = ttk.LabelFrame(
            self.tunnel_tab, text="이 PC Chrome / CDP 인자", padding=8
        )
        tunnel_chrome_fields.grid(row=2, column=0, sticky="ew")
        self._add_fields(
            tunnel_chrome_fields,
            (
                ("기본 시작 URL 호스트", "backend_host"),
                ("기본 시작 URL 포트", "backend_port"),
                ("이 PC Chrome CDP 포트", "chrome_debug_port"),
                ("Chrome 프로필 경로 (선택)", "chrome_profile"),
            ),
            self.values,
        )
        tunnel_ssh_fields = ttk.LabelFrame(
            self.tunnel_tab, text="SSH 역터널 인자", padding=8
        )
        tunnel_ssh_fields.grid(row=3, column=0, pady=(8, 0), sticky="ew")
        self._add_fields(
            tunnel_ssh_fields,
            (
                ("SSH 대상 (별칭 또는 user@host)", "ssh_target"),
                ("원격 MCP용 CDP 포트", "remote_debug_port"),
            ),
            self.values,
        )
        tunnel_mcp_frame = ttk.LabelFrame(self.tunnel_tab, text="원격 MCP 연결 인자", padding=8)
        tunnel_mcp_frame.grid(row=4, column=0, pady=(8, 0), sticky="ew")
        ttk.Label(tunnel_mcp_frame, textvariable=self.tunnel_mcp_info, wraplength=760).grid(
            row=0, column=0, sticky="w"
        )
        self.tunnel_tab.columnconfigure(0, weight=1)

        context_frame = ttk.LabelFrame(outer, text="AI 전달용 MCP 연결 정보", padding=6)
        context_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        context_frame.columnconfigure(0, weight=1)
        self.ai_context = tk.Text(context_frame, height=5, wrap="word")
        self.ai_context.grid(row=0, column=0, sticky="ew")
        self.ai_context.configure(state="disabled")
        ttk.Button(context_frame, text="연결 정보 복사", command=self.copy_ai_context).grid(
            row=1, column=0, pady=(6, 0), sticky="e"
        )

        buttons = ttk.Frame(outer)
        buttons.grid(row=2, column=0, pady=(0, 10), sticky="ew")
        self.start_button = ttk.Button(buttons, command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.cleanup_button = ttk.Button(
            buttons, text="남은 프로세스 정리", command=self.clean_leftovers
        )
        self.cleanup_button.pack(side="left")
        ttk.Label(buttons, text="상태:").pack(side="left", padx=(16, 4))
        ttk.Label(buttons, textvariable=self.status).pack(side="left")

        log_frame = ttk.LabelFrame(outer, text="실행 로그", padding=6)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        self.mode_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _add_fields(
        self,
        parent: ttk.LabelFrame,
        fields: tuple[tuple[str, str], ...],
        values: dict[str, tk.StringVar],
    ) -> None:
        parent.columnconfigure(1, weight=1)
        for row, (label, key) in enumerate(fields):
            ttk.Label(parent, text=label).grid(
                row=row, column=0, padx=(0, 12), pady=3, sticky="w"
            )
            entry = ttk.Entry(parent, textvariable=values[key])
            entry.grid(row=row, column=1, pady=3, sticky="ew")
            self.field_widgets.append(entry)

    def _refresh_profile_names(self) -> None:
        self.profile_combo.configure(values=list(self.store.profiles))

    def _load_profile(self, name: str) -> None:
        config = self.store.profiles[name]
        for key, value in config.to_mapping().items():
            self.values[key].set(str(value))
        self.profile_name.set(name)

    def _on_profile_selected(self, _event: object = None) -> None:
        name = self.profile_name.get()
        try:
            self.store.set_active(name)
        except (OSError, KeyError) as exc:
            # 여기서 빠져나가면 콤보박스는 B를, 입력란은 A를 보여주게 된다.
            messagebox.showerror("프로파일 오류", str(exc))
        self._load_profile(name)
        self._append_log(f"프로파일을 불러왔습니다: {name}")

    def _config_from_ui(self) -> DevToolsConfig:
        return DevToolsConfig.from_mapping(
            {key: variable.get().strip() for key, variable in self.values.items()}
        )

    def _local_config_from_ui(self) -> DevToolsConfig:
        values = {key: variable.get().strip() for key, variable in self.local_values.items()}
        return DevToolsConfig.from_mapping(
            {
                **values,
                "ssh_target": "",
                "remote_debug_port": "",
                "chrome_profile": "",
            }
        )

    def save_profile(self, *, silent: bool = False) -> DevToolsConfig | None:
        try:
            name = validate_profile_name(self.profile_name.get())
            config = self._config_from_ui()
            self.store.save_profile(name, config)
        except (OSError, ValueError) as exc:
            messagebox.showerror("저장 오류", str(exc))
            return None
        self._refresh_profile_names()
        if not silent:
            self._append_log(f"프로파일을 저장했습니다: {name}")
        return config

    def new_profile(self) -> None:
        name = simpledialog.askstring("새 프로파일", "새 프로파일 이름을 입력하세요:", parent=self.root)
        if name is None:
            return
        try:
            name = validate_profile_name(name)
            if name in self.store.profiles:
                raise ValueError(f"이미 존재하는 프로파일입니다: {name}")
            config = self._config_from_ui()
            self.store.save_profile(name, config)
        except (OSError, ValueError) as exc:
            messagebox.showerror("프로파일 오류", str(exc))
            return
        self._refresh_profile_names()
        self._load_profile(name)
        self._append_log(f"새 프로파일을 만들었습니다: {name}")

    def delete_profile(self) -> None:
        name = self.profile_name.get()
        if not messagebox.askyesno("삭제 확인", f"프로파일 '{name}'을 삭제하시겠습니까?"):
            return
        try:
            active = self.store.delete_profile(name)
        except (OSError, KeyError, ValueError) as exc:
            messagebox.showerror("삭제 오류", str(exc))
            return
        self._refresh_profile_names()
        self._load_profile(active)
        self._append_log(f"프로파일을 삭제했습니다: {name}")

    def start(self, *, source: str = "ui") -> None:
        if self.running:
            return
        self._start_source = source
        self._last_error = None
        mode = self.mode.get()
        if mode == "local":
            try:
                config = self._local_config_from_ui()
            except ValueError as exc:
                self._report_error("로컬 설정 오류", str(exc))
                return
        else:
            config = self.save_profile(silent=True)
            if config is None:
                return

        self.running = True
        self.stop_requested = False
        self.status.set("시작 중")
        self._set_running_controls(True)
        if mode == "local":
            self._append_log("로컬 기본 설정으로 DevTools MCP용 Chrome을 시작합니다.")
        else:
            profile = self.profile_name.get()
            self._append_log(f"프로파일 '{profile}'로 SSH 역터널 MCP를 시작합니다.")

        def worker() -> None:
            try:
                if mode == "local":
                    code = self.runner.run_local(config, self._emit)
                else:
                    code = self.runner.run_tunnel(config, self._emit)
            except Exception as exc:  # UI 경계에서 예외를 사용자에게 전달한다.
                self.events.put(("error", exc))
            else:
                self.events.put(("finished", code))

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        if not self.running:
            return
        self.stop_requested = True
        self.status.set("중지 중")
        self.stop_button.configure(state="disabled")
        self._append_log("실행 중인 DevTools를 종료합니다.")
        threading.Thread(target=self.runner.stop, daemon=True).start()

    def _emit(self, event: str, payload: object) -> None:
        self.events.put((event, payload))

    def _drain_events(self) -> None:
        # 재예약은 반드시 finally에 둔다. try 밖에 두면 이벤트 처리 중 예외가 한 번만
        # 나도 펌프가 영구히 멈추고, 창은 멀쩡해 보이는데 로그만 죽는다.
        self._drain_job = None
        try:
            while True:
                event, payload = self.events.get_nowait()
                self._handle_event(event, payload)
        except queue.Empty:
            pass
        finally:
            if not self._closing:
                self._drain_job = self.root.after(100, self._drain_events)

    def _handle_event(self, event: str, payload: object) -> None:
        if event == "log":
            self._append_log(str(payload))
        elif event == "state":
            self.status.set(str(payload))
        elif event == "finished":
            code = payload if isinstance(payload, int) else 0
            self.running = False
            if self.stop_requested:
                self.status.set("중지됨")
            elif code == 0:
                self.status.set("종료됨")
            else:
                self.status.set(f"종료됨 ({code})")
                subject = "SSH" if self.mode.get() == "tunnel" else "Chrome"
                self._append_log(f"{subject} 프로세스가 종료되었습니다. exit code={code}")
            self._set_running_controls(False)
        elif event == "error":
            self.running = False
            self.status.set("오류")
            self._set_running_controls(False)
            self._append_log(f"오류: {payload}")
            self._last_error = str(payload)
            if self._start_source == "rpc":
                # RPC 호출자는 status로 오류를 읽어 간다. 대화상자를 띄우면 사람이 없는
                # 창이 응답을 기다리며 멈춰 버린다.
                return
            if isinstance(payload, PortInUseError) and not self._closing:
                self._offer_port_recovery(payload)
            else:
                messagebox.showerror("DevTools 오류", str(payload))

    def _report_error(self, title: str, message: str) -> None:
        self._last_error = message
        self._append_log(f"오류: {message}")
        if self._start_source != "rpc":
            messagebox.showerror(title, message)

    def _offer_port_recovery(self, error: PortInUseError) -> None:
        """포트 점유 오류를 막다른 골목으로 두지 않는다.

        앱 소유 잔존물이면 정리 후 같은 포트로 재시작을, 남의 프로세스면 빈
        포트로 바꿔 재시작을 제안한다. 어느 쪽도 묻지 않고는 실행하지 않는다.
        """
        if error.owned_by_app:
            if messagebox.askyesno(
                "이전 실행 정리",
                f"{error}\n\n이전 실행이 남긴 Chrome을 정리하고 "
                f"포트 {error.port}(으)로 다시 시작할까요?",
            ):
                try:
                    leftovers = [
                        item for item in cleanup.find_leftovers() if item.port == error.port
                    ]
                except OSError as exc:
                    messagebox.showerror("정리 오류", str(exc))
                    return
                self._clean(leftovers)
                self.start()
            return
        if error.suggested_port is not None:
            if messagebox.askyesno(
                "포트 사용 중",
                f"{error}\n\n포트 {error.suggested_port}(으)로 바꿔서 다시 시작할까요?",
            ):
                port_var = (
                    self.values["chrome_debug_port"]
                    if self.mode.get() == "tunnel"
                    else self.local_values["chrome_debug_port"]
                )
                port_var.set(str(error.suggested_port))
                self._append_log(
                    f"CDP 포트를 {error.port} → {error.suggested_port}(으)로 바꿔 다시 시작합니다."
                )
                self.start()
            return
        messagebox.showerror("DevTools 오류", str(error))

    def _set_running_controls(self, running: bool) -> None:
        normal = "disabled" if running else "normal"
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.profile_combo.configure(state="disabled" if running else "readonly")
        self.new_button.configure(state=normal)
        self.save_button.configure(state=normal)
        self.delete_button.configure(state=normal)
        self.cleanup_button.configure(state=normal)
        for entry in self.field_widgets:
            entry.configure(state=normal)
        if not running:
            self._apply_mode_ui()

    def _on_tab_changed(self, _event: object = None) -> None:
        if not hasattr(self, "mode_notebook"):
            return
        selected = self.mode_notebook.select()
        current = self.tunnel_tab if self.mode.get() == "tunnel" else self.local_tab
        if self.running and selected != str(current):
            self.root.after_idle(lambda: self.mode_notebook.select(current))
            return
        self.mode.set("tunnel" if selected == str(self.tunnel_tab) else "local")
        self._apply_mode_ui()

    def _apply_mode_ui(self) -> None:
        if self.mode.get() == "tunnel":
            self.start_button.configure(text="Chrome + 역터널 시작")
            self.stop_button.configure(text="역터널 중지")
        else:
            self.start_button.configure(text="로컬 Chrome 시작")
            self.stop_button.configure(text="로컬 Chrome 중지")

    def _refresh_ai_context(self) -> None:
        if not hasattr(self, "ai_context"):
            return
        tunnel_values = {key: value.get().strip() for key, value in self.values.items()}
        local_cdp_port = self.local_values["chrome_debug_port"].get().strip() or "9222"
        local_browser_url = f"http://127.0.0.1:{local_cdp_port}"
        tunnel_local_port = tunnel_values["chrome_debug_port"] or "<이 PC 포트>"
        remote_port = tunnel_values["remote_debug_port"] or "<원격 포트>"
        tunnel_browser_url = f"http://127.0.0.1:{tunnel_local_port}"
        remote_browser_url = f"http://127.0.0.1:{remote_port}"
        self.local_mcp_info.set(f"chrome-devtools-mcp --browser-url={local_browser_url}")
        self.tunnel_mcp_info.set(
            f"원격 서버: chrome-devtools-mcp --browser-url={remote_browser_url}"
        )
        if self.mode.get() == "local":
            description = (
                f"상태: {self.status.get()}\n"
                f"로컬 Chrome DevTools: {local_browser_url}\n"
                f"MCP에서 '--browser-url={local_browser_url}'로 연결해 사용하세요."
            )
        else:
            description = (
                f"상태: {self.status.get()}\n"
                f"SSH 역터널: 원격 {remote_browser_url} → 이 PC {tunnel_browser_url}\n"
                f"원격 MCP에서 '--browser-url={remote_browser_url}'로 연결해 사용하세요."
            )
        self.ai_context.configure(state="normal")
        self.ai_context.delete("1.0", "end")
        self.ai_context.insert("1.0", description)
        self.ai_context.configure(state="disabled")

    def copy_ai_context(self) -> None:
        context = self.ai_context.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(context)
        self._append_log("MCP 연결 정보를 클립보드에 복사했습니다.")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        excess = int(self.log.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if excess > 0:
            self.log.delete("1.0", f"{excess + 1}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def scan_leftovers(self) -> list[cleanup.Leftover]:
        """이전 실행이 남긴 것을 찾아 로그에 적고, 정리할지 물어본다.

        묻지 않고 바로 죽이지 않는다. 소유권 판정이 틀렸을 때 사용자의 평소 Chrome을
        날리는 사고가 바로 이 지점에서 난다.
        """
        try:
            leftovers = cleanup.find_leftovers()
        except OSError as exc:
            self._append_log(f"남은 프로세스 확인 실패: {exc}")
            return []
        if not leftovers:
            return []

        self._append_log("이전 실행이 남긴 항목을 찾았습니다:")
        for leftover in leftovers:
            self._append_log(f"  - {leftover.describe()}")

        stranded = [item for item in leftovers if item.processes]
        if not stranded:
            # 폴더만 남았다면 알리기만 한다. 매 실행마다 묻는 것은 성가시고, 전용
            # 프로파일에는 로그인 상태가 들어 있을 수 있어 함부로 지울 것이 아니다.
            self._append_log("남은 프로세스는 없습니다. 폴더는 '남은 프로세스 정리'로 지울 수 있습니다.")
            return leftovers

        if messagebox.askyesno(
            "남은 프로세스 정리",
            "이전 실행이 남긴 프로세스가 있습니다. 지금 정리할까요?\n\n"
            + "\n".join(f"- {item.describe()}" for item in stranded),
        ):
            self._clean(stranded)
        else:
            self._append_log("정리를 건너뛰었습니다. '남은 프로세스 정리'로 언제든 실행할 수 있습니다.")
        return leftovers

    def clean_leftovers(self) -> None:
        try:
            leftovers = cleanup.find_leftovers()
        except OSError as exc:
            messagebox.showerror("정리 오류", str(exc))
            return
        if not leftovers:
            self._append_log("정리할 남은 프로세스가 없습니다.")
            return
        if not messagebox.askyesno(
            "정리 확인",
            "다음 항목을 종료하고 삭제합니다.\n\n"
            + "\n".join(f"- {item.describe()}" for item in leftovers),
        ):
            return
        self._clean(leftovers)

    def _clean(self, leftovers: list[cleanup.Leftover]) -> None:
        killed, removed = cleanup.clean_leftovers(leftovers, self._append_log)
        self._append_log(f"정리 완료: 프로세스 {killed}개 종료, 폴더 {removed}개 삭제.")

    # ------------------------------------------------------------------
    # RPC 표면. 모든 메서드는 Tk 메인 스레드에서 실행된다(TkDispatcher 경유).
    # 여기서는 절대 블로킹하지 않는다 — 대기는 호출자 스레드가 rpc_status를 폴링해서 한다.
    # ------------------------------------------------------------------

    def start_rpc_server(self) -> rpc.Endpoint | None:
        methods = {
            "status": lambda p: self.rpc_status(),
            "start": self.rpc_start,
            "stop": lambda p: self.rpc_stop(),
            "cleanup": self.rpc_cleanup,
            "log": self.rpc_log,
            "profiles": lambda p: self.rpc_profiles(),
            "select_profile": self.rpc_select_profile,
        }
        try:
            self._dispatcher = rpc.TkDispatcher(self.root)
            server = rpc.RpcServer(methods)
            endpoint = server.start()
        except OSError as exc:
            self._append_log(f"RPC 서버를 열지 못했습니다: {exc}")
            self._dispatcher = None
            return None
        self._rpc = server
        self._append_log(
            f"RPC 서버 준비됨: {endpoint.host}:{endpoint.port} "
            f"(접속 정보: {rpc.endpoint_path(os.getpid()).name})"
        )
        return endpoint

    def _dispatch(self, func: Callable[[], object]) -> object:
        """소켓 스레드에서 온 호출을 Tk 스레드로 넘긴다."""
        if self._dispatcher is None:
            raise rpc.RpcError("RPC 서버가 준비되지 않았습니다.")
        return self._dispatcher.call(func)

    def rpc_status(self) -> dict[str, object]:
        def read() -> dict[str, object]:
            mode = self.mode.get()
            if mode == "local":
                port = self.local_values["chrome_debug_port"].get().strip()
                remote = ""
            else:
                port = self.values["chrome_debug_port"].get().strip()
                remote = self.values["remote_debug_port"].get().strip()
            # MCP가 실제로 연결해야 할 주소. 역터널이면 원격 loopback 포트다.
            mcp_port = remote if mode == "tunnel" else port
            return {
                "mode": mode,
                "running": self.running,
                "status": self.status.get(),
                "chrome_debug_port": port,
                "remote_debug_port": remote,
                "browser_url": f"http://127.0.0.1:{mcp_port}" if mcp_port else None,
                "devtools_host": self.runner.devtools_host,
                "owns_chrome": self.runner.owns_chrome,
                "profile": self.profile_name.get() if mode == "tunnel" else None,
                "last_error": self._last_error,
            }

        return self._dispatch(read)  # type: ignore[return-value]

    def rpc_start(self, params: dict) -> dict[str, object]:
        mode = params.get("mode")
        if mode is not None and mode not in ("local", "tunnel"):
            raise rpc.RpcError("mode는 'local' 또는 'tunnel'이어야 합니다.", rpc.INVALID_PARAMS)
        port = params.get("chrome_debug_port")
        profile = params.get("profile")

        def begin() -> None:
            if self.running:
                raise rpc.RpcError("이미 실행 중입니다. 먼저 stop을 호출하세요.")
            if mode is not None:
                self.mode_notebook.select(self.tunnel_tab if mode == "tunnel" else self.local_tab)
                self._on_tab_changed()
            if profile is not None:
                if profile not in self.store.profiles:
                    raise rpc.RpcError(f"없는 프로파일입니다: {profile}", rpc.INVALID_PARAMS)
                self.profile_name.set(profile)
                self._on_profile_selected()
            if port is not None:
                target = (
                    self.values if self.mode.get() == "tunnel" else self.local_values
                )["chrome_debug_port"]
                target.set(str(port))
            self.start(source="rpc")

        self._dispatch(begin)

        if not params.get("wait", True):
            return self.rpc_status()
        timeout = float(params.get("timeout", 45))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.rpc_status()
            if not state["running"]:
                # 워커가 끝났다. 오류면 그대로 올려 준다.
                if state["last_error"]:
                    raise rpc.RpcError(str(state["last_error"]))
                return state
            if str(state["status"]) not in ("시작 중",):
                return state
            time.sleep(0.3)
        raise rpc.RpcError(f"{timeout:.0f}초 안에 시작되지 않았습니다.")

    def rpc_stop(self) -> dict[str, object]:
        self._dispatch(lambda: self.stop() if self.running else None)
        # runner가 아니라 앱 상태가 가라앉을 때까지 기다린다. runner만 보면 "중지 중"인 채로
        # running=true를 돌려주게 되고, 호출자는 중지가 실패했다고 읽는다.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.rpc_status()
            if not state["running"]:
                return state
            time.sleep(0.2)
        raise rpc.RpcError("중지가 시간 안에 끝나지 않았습니다.")

    def rpc_cleanup(self, params: dict) -> dict[str, object]:
        # 기본은 조회다. 프로세스를 죽이는 쪽이 기본 경로가 되면 안 된다.
        apply = bool(params.get("apply", False))
        leftovers = cleanup.find_leftovers()
        found = [
            {
                "port": item.port,
                "description": item.describe(),
                "processes": [
                    {"kind": p.kind, "pid": p.pid, "image": p.image} for p in item.processes
                ],
                "profile_dir": str(item.profile_dir) if item.profile_dir else None,
            }
            for item in leftovers
        ]
        if not apply:
            return {"applied": False, "leftovers": found}
        lines: list[str] = []
        killed, removed = cleanup.clean_leftovers(leftovers, lines.append)

        def echo() -> None:
            for line in lines:
                self._append_log(line)

        self._dispatch(echo)
        return {"applied": True, "leftovers": found, "killed": killed, "removed": removed}

    def rpc_log(self, params: dict) -> dict[str, object]:
        tail = max(1, min(int(params.get("tail", 50)), MAX_LOG_LINES))

        def read() -> list[str]:
            text = self.log.get("1.0", "end-1c")
            return text.splitlines()[-tail:] if text else []

        return {"lines": self._dispatch(read)}

    def rpc_profiles(self) -> dict[str, object]:
        def read() -> dict[str, object]:
            return {
                "active": self.store.active_profile,
                "selected": self.profile_name.get(),
                "profiles": {
                    name: config.to_mapping() for name, config in self.store.profiles.items()
                },
            }

        return self._dispatch(read)  # type: ignore[return-value]

    def rpc_select_profile(self, params: dict) -> dict[str, object]:
        name = params.get("name")
        if not isinstance(name, str):
            raise rpc.RpcError("name이 필요합니다.", rpc.INVALID_PARAMS)

        def select() -> None:
            if self.running:
                raise rpc.RpcError("실행 중에는 프로파일을 바꿀 수 없습니다.")
            if name not in self.store.profiles:
                raise rpc.RpcError(f"없는 프로파일입니다: {name}", rpc.INVALID_PARAMS)
            self.profile_name.set(name)
            self._on_profile_selected()

        self._dispatch(select)
        return self.rpc_profiles()

    def close(self) -> None:
        if self._closing:
            return
        if self.running and not messagebox.askyesno(
            "종료 확인",
            "실행 중인 Chrome과 터널도 함께 종료됩니다. 창을 닫을까요?",
        ):
            return

        self._closing = True
        # RPC를 먼저 닫는다. 그래야 종료 도중에 들어온 호출이 반쯤 정리된 상태를 만지지 않는다.
        if self._rpc is not None:
            self._rpc.close()
            self._rpc = None
        if self._dispatcher is not None:
            self._dispatcher.stop()
            self._dispatcher = None
        if self._drain_job is not None:
            # 취소하지 않으면 destroy() 뒤에 예약된 콜백이 깨어나
            # invalid command name 오류를 남긴다.
            self.root.after_cancel(self._drain_job)
            self._drain_job = None
        self.status.set("종료 중")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.cleanup_button.configure(state="disabled")
        # 정리는 몇 초가 걸릴 수 있다. UI 스레드에서 직접 기다리면 창이 '응답 없음'이 된다.
        threading.Thread(target=self.runner.stop, daemon=True).start()
        self._finish_close(time.monotonic() + 5)

    def _finish_close(self, deadline: float) -> None:
        if self.runner.is_running and time.monotonic() < deadline:
            self.root.after(100, lambda: self._finish_close(deadline))
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        app = DevToolsApp(root)
    except SystemExit:
        # 프로파일을 읽지 못하면 빈 창만 남는다. 창까지 정리하고 나간다.
        root.destroy()
        raise
    app.start_rpc_server()
    root.mainloop()
