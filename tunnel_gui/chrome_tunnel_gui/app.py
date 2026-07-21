from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .profiles import ProfileStore, validate_profile_name
from .tunnel import TunnelConfig, TunnelRunner


APP_DIR = Path(__file__).resolve().parents[1]
PROFILE_PATH = APP_DIR / "profiles.yaml"


class TunnelApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.runner = TunnelRunner()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.stop_requested = False

        self.store = ProfileStore(PROFILE_PATH)
        try:
            self.store.load()
        except (OSError, ValueError) as exc:
            messagebox.showerror("프로파일 오류", str(exc))
            raise SystemExit(1) from exc

        self.profile_name = tk.StringVar(value=self.store.active_profile)
        self.status = tk.StringVar(value="중지됨")
        self.values = {
            "backend_host": tk.StringVar(),
            "backend_port": tk.StringVar(),
            "ssh_user": tk.StringVar(),
            "ssh_host": tk.StringVar(),
            "chrome_debug_port": tk.StringVar(),
            "remote_debug_port": tk.StringVar(),
            "chrome_profile": tk.StringVar(),
        }
        self.field_widgets: list[ttk.Entry] = []

        self._build_ui()
        self._refresh_profile_names()
        self._load_profile(self.store.active_profile)
        for variable in (*self.values.values(), self.profile_name, self.status):
            variable.trace_add("write", lambda *_: self._refresh_ai_context())
        self._refresh_ai_context()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        self.root.title("Chrome DevTools SSH 역터널 관리자")
        self.root.minsize(780, 760)

        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(11, weight=1)

        profile_frame = ttk.LabelFrame(outer, text="프로파일", padding=8)
        profile_frame.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")
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

        fields = (
            ("백엔드 호스트", "backend_host"),
            ("백엔드 웹 포트", "backend_port"),
            ("SSH 사용자 (별칭 없을 때)", "ssh_user"),
            ("SSH Host 별칭 (선택)", "ssh_host"),
            ("이 PC Chrome 포트", "chrome_debug_port"),
            ("원격 DevTools 포트", "remote_debug_port"),
            ("Chrome 프로필 경로 (선택)", "chrome_profile"),
        )
        for row, (label, key) in enumerate(fields, start=1):
            ttk.Label(outer, text=label).grid(
                row=row, column=0, padx=(0, 12), pady=4, sticky="w"
            )
            entry = ttk.Entry(outer, textvariable=self.values[key])
            entry.grid(row=row, column=1, pady=4, sticky="ew")
            self.field_widgets.append(entry)

        info = (
            "원격 서버 127.0.0.1:9222 → SSH -R → 이 PC 127.0.0.1:9333\n"
            "SSH Host 별칭을 사용하면 ~/.ssh/config의 IdentityFile 설정이 적용됩니다."
        )
        ttk.Label(outer, text=info, foreground="#444444").grid(
            row=8, column=0, columnspan=2, pady=(10, 6), sticky="w"
        )

        context_frame = ttk.LabelFrame(outer, text="AI 협업용 현재 상태 설명", padding=6)
        context_frame.grid(row=9, column=0, columnspan=2, pady=(4, 10), sticky="ew")
        context_frame.columnconfigure(0, weight=1)
        self.ai_context = tk.Text(context_frame, height=5, wrap="word")
        self.ai_context.grid(row=0, column=0, sticky="ew")
        self.ai_context.configure(state="disabled")
        ttk.Button(context_frame, text="AI 설명 복사", command=self.copy_ai_context).grid(
            row=1, column=0, pady=(6, 0), sticky="e"
        )

        buttons = ttk.Frame(outer)
        buttons.grid(row=10, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        self.start_button = ttk.Button(buttons, text="터널 시작", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="터널 중지", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Label(buttons, text="상태:").pack(side="left", padx=(16, 4))
        ttk.Label(buttons, textvariable=self.status).pack(side="left")

        log_frame = ttk.LabelFrame(outer, text="실행 로그", padding=6)
        log_frame.grid(row=11, column=0, columnspan=2, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _refresh_profile_names(self) -> None:
        self.profile_combo.configure(values=list(self.store.profiles))

    def _load_profile(self, name: str) -> None:
        config = self.store.profiles[name]
        for key, value in config.to_mapping().items():
            self.values[key].set(str(value))
        self.profile_name.set(name)

    def _on_profile_selected(self, _event: object = None) -> None:
        name = self.profile_name.get()
        self.store.set_active(name)
        self._load_profile(name)
        self._append_log(f"프로파일을 불러왔습니다: {name}")

    def _config_from_ui(self) -> TunnelConfig:
        return TunnelConfig.from_mapping(
            {key: variable.get().strip() for key, variable in self.values.items()}
        )

    def save_profile(self, *, silent: bool = False) -> TunnelConfig | None:
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

    def start(self) -> None:
        if self.running:
            return
        config = self.save_profile(silent=True)
        if config is None:
            return

        self.running = True
        self.stop_requested = False
        self.status.set("시작 중")
        self._set_running_controls(True)
        profile = self.profile_name.get()
        self._append_log(f"프로파일 '{profile}'로 터널을 시작합니다.")

        def worker() -> None:
            try:
                code = self.runner.run(config, self._emit)
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
        self._append_log("SSH 역터널을 종료합니다.")
        threading.Thread(target=self.runner.stop, daemon=True).start()

    def _emit(self, event: str, payload: object) -> None:
        self.events.put((event, payload))

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self._append_log(str(payload))
                elif event == "state":
                    self.status.set(str(payload))
                elif event == "finished":
                    code = int(payload)
                    self.running = False
                    if self.stop_requested:
                        self.status.set("중지됨")
                    elif code == 0:
                        self.status.set("종료됨")
                    else:
                        self.status.set(f"종료됨 ({code})")
                        self._append_log(f"SSH 프로세스가 종료되었습니다. exit code={code}")
                    self._set_running_controls(False)
                elif event == "error":
                    self.running = False
                    self.status.set("오류")
                    self._set_running_controls(False)
                    self._append_log(f"오류: {payload}")
                    messagebox.showerror("터널 오류", str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _set_running_controls(self, running: bool) -> None:
        normal = "disabled" if running else "normal"
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.profile_combo.configure(state="disabled" if running else "readonly")
        self.new_button.configure(state=normal)
        self.save_button.configure(state=normal)
        self.delete_button.configure(state=normal)
        for entry in self.field_widgets:
            entry.configure(state=normal)

    def _refresh_ai_context(self) -> None:
        if not hasattr(self, "ai_context"):
            return
        values = {key: value.get().strip() for key, value in self.values.items()}
        host = values["backend_host"] or "<백엔드 호스트>"
        ssh_user = values["ssh_user"] or "<SSH 사용자>"
        ssh_target = values["ssh_host"] or f"{ssh_user}@{host}"
        local_port = values["chrome_debug_port"] or "<로컬 포트>"
        remote_port = values["remote_debug_port"] or "<원격 포트>"
        profile_path = values["chrome_profile"] or "TEMP 아래의 전용 자동 프로필"
        description = (
            f"현재 프로파일 '{self.profile_name.get()}'의 Chrome DevTools SSH 역터널 상태입니다. "
            f"이 PC의 Chrome DevTools는 127.0.0.1:{local_port}에서 실행되고, "
            f"SSH 대상 '{ssh_target}'의 127.0.0.1:{remote_port}에서 역터널로 접근합니다. "
            f"현재 상태는 '{self.status.get()}'이며 Chrome 프로필은 '{profile_path}'입니다. "
            f"원격 서버에서 http://127.0.0.1:{remote_port}/json/version을 조회하면 연결을 확인할 수 "
            "있습니다. 터널이 유지되는 동안 AI 에이전트는 원격 DevTools 주소를 통해 이 PC의 "
            "전용 Chrome을 조회하고 조작할 수 있습니다."
        )
        self.ai_context.configure(state="normal")
        self.ai_context.delete("1.0", "end")
        self.ai_context.insert("1.0", description)
        self.ai_context.configure(state="disabled")

    def copy_ai_context(self) -> None:
        context = self.ai_context.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(context)
        self._append_log("AI 협업용 상태 설명을 클립보드에 복사했습니다.")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def close(self) -> None:
        if self.running:
            if not messagebox.askyesno("종료 확인", "실행 중인 SSH 터널도 함께 종료하시겠습니까?"):
                return
            self.runner.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TunnelApp(root)
    root.mainloop()
