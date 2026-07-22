"""GUI 프로세스에 내장하는 JSON-RPC 2.0 서버.

사람이 보고 있는 그 창을 AI가 함께 조작하게 하는 것이 목적이다. 그래서 서버를 별도
프로세스로 빼지 않는다. Chrome과 ssh를 붙잡은 Job Object는 그것을 만든 프로세스와 수명을
같이하므로, 서버가 GUI 밖으로 나가는 순간 "같은 인스턴스"라는 전제가 깨진다.

전송은 127.0.0.1에 바인딩한 TCP 위의 JSON Lines(요청 한 줄, 응답 한 줄)다. 인증은 토큰이며,
접속 정보는 `%TEMP%`의 엔드포인트 파일로 알린다.
"""
from __future__ import annotations

import hmac
import json
import os
import queue
import secrets
import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import cleanup


ENDPOINT_PREFIX = "ready-chromedev-rpc-"
MAX_REQUEST_BYTES = 1 << 20
PROTOCOL_VERSION = 1

# JSON-RPC 2.0 표준 오류 코드
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# 이 서버 고유 코드
UNAUTHORIZED = -32001
SHUTTING_DOWN = -32002


def endpoint_path(pid: int) -> Path:
    return cleanup.temp_root() / f"{ENDPOINT_PREFIX}{pid}.json"


def read_endpoints() -> list[dict[str, object]]:
    """살아 있는 GUI 인스턴스의 접속 정보를 최신 순으로 돌려준다.

    죽은 인스턴스가 남긴 파일은 그 자리에서 지운다. 소유자 pid가 살아 있는지 확인하지 않으면
    브리지가 이미 없는 창에 붙으려다 실패한다.
    """
    found = []
    try:
        candidates = sorted(cleanup.temp_root().glob(f"{ENDPOINT_PREFIX}*.json"))
    except OSError:
        return found
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        pid = payload.get("pid")
        if not isinstance(pid, int) or not cleanup.is_alive(pid):
            path.unlink(missing_ok=True)
            continue
        found.append(payload)
    found.sort(key=lambda item: item.get("started_at", 0), reverse=True)
    return found


class RpcError(Exception):
    """메서드가 호출자에게 그대로 보여 주고 싶은 오류."""

    def __init__(self, message: str, code: int = INTERNAL_ERROR, data: object = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class TkDispatcher:
    """다른 스레드의 호출을 Tk 메인 스레드에서 실행하고 결과를 돌려준다.

    Tkinter는 스레드 안전하지 않다. 소켓 스레드가 위젯을 직접 만지면 안 되므로 큐에 넣고
    Tk의 ``after`` 루프가 꺼내 실행한다.
    """

    def __init__(self, root: object, interval: int = 50) -> None:
        self._root = root
        self._interval = interval
        self._queue: queue.Queue[tuple[Callable[[], object], dict, threading.Event]] = queue.Queue()
        self._stopped = False
        self._job = root.after(interval, self._pump)

    def call(self, func: Callable[[], object], timeout: float = 30.0) -> object:
        if self._stopped:
            raise RpcError("앱이 종료 중입니다.", SHUTTING_DOWN)
        done = threading.Event()
        box: dict[str, object] = {}
        self._queue.put((func, box, done))
        if not done.wait(timeout):
            raise RpcError("UI 스레드가 시간 안에 응답하지 않았습니다.", INTERNAL_ERROR)
        if "error" in box:
            raise box["error"]  # type: ignore[misc]
        return box.get("value")

    def _pump(self) -> None:
        # 재예약은 finally에 둔다. 밖에 두면 예외 한 번에 펌프가 영구히 멈춘다.
        self._job = None
        try:
            while True:
                func, box, done = self._queue.get_nowait()
                try:
                    box["value"] = func()
                except Exception as exc:  # noqa: BLE001 - 호출자에게 그대로 전달한다.
                    box["error"] = exc
                finally:
                    done.set()
        except queue.Empty:
            pass
        finally:
            if not self._stopped:
                try:
                    self._job = self._root.after(self._interval, self._pump)
                except Exception:  # noqa: BLE001 - 창이 이미 파괴되었다는 뜻이다.
                    # stop() 없이 destroy()된 경우다. 여기서 예외를 올리면 Tk가
                    # "invalid command name"을 stderr에 뱉는다.
                    self._stopped = True

    def stop(self) -> None:
        self._stopped = True
        if self._job is not None:
            try:
                self._root.after_cancel(self._job)
            except Exception:  # noqa: BLE001 - 이미 파괴된 창이면 취소할 것도 없다.
                pass
            self._job = None
        # 대기 중인 호출자를 풀어 준다. 그러지 않으면 소켓 스레드가 타임아웃까지 매달린다.
        while True:
            try:
                _, box, done = self._queue.get_nowait()
            except queue.Empty:
                break
            box["error"] = RpcError("앱이 종료 중입니다.", SHUTTING_DOWN)
            done.set()


@dataclass(frozen=True, slots=True)
class Endpoint:
    host: str
    port: int
    token: str


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: "_Server" = self.server  # type: ignore[assignment]
        while not server.closing:
            try:
                line = self.rfile.readline(MAX_REQUEST_BYTES)
            except OSError:
                return
            if not line:
                return
            response = server.owner.handle_line(line)
            if response is None:
                continue
            try:
                self.wfile.write(response + b"\n")
                self.wfile.flush()
            except OSError:
                return


class _Server(socketserver.ThreadingTCPServer):
    # Windows에서 SO_REUSEADDR은 남의 소켓을 가로챌 수 있게 한다. 절대 켜지 않는다.
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, address: tuple[str, int], owner: "RpcServer") -> None:
        self.owner = owner
        self.closing = False
        super().__init__(address, _Handler)


class RpcServer:
    """GUI가 소유하는 JSON-RPC 서버."""

    def __init__(
        self,
        methods: dict[str, Callable[[dict], object]],
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        # 메서드가 Tk 스레드로 넘어가야 한다면 그 책임은 메서드 쪽에 있다(app.py의 _dispatch).
        # 서버는 전송과 인증만 맡는다.
        self._methods = methods
        self._token = secrets.token_hex(32)
        self._server = _Server((host, port), self)
        self.endpoint = Endpoint(host, self._server.server_address[1], self._token)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._endpoint_path = endpoint_path(os.getpid())

    def start(self) -> Endpoint:
        self._thread.start()
        self._write_endpoint_file()
        return self.endpoint

    def _write_endpoint_file(self) -> None:
        payload = {
            "version": PROTOCOL_VERSION,
            "pid": os.getpid(),
            "host": self.endpoint.host,
            "port": self.endpoint.port,
            "token": self.endpoint.token,
            # 창을 여러 개 띄웠을 때 브리지가 가장 최근 것을 고르는 기준.
            "started_at": time.time(),
        }
        temporary = self._endpoint_path.with_name(self._endpoint_path.name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self._endpoint_path)

    def close(self) -> None:
        self._server.closing = True
        self._endpoint_path.unlink(missing_ok=True)
        try:
            self._server.shutdown()
        except Exception:  # noqa: BLE001 - 종료 경로에서 예외로 창을 막지 않는다.
            pass
        self._server.server_close()

    def handle_line(self, line: bytes) -> bytes | None:
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._error(None, PARSE_ERROR, "JSON을 해석할 수 없습니다.")
        if not isinstance(request, dict):
            return self._error(None, INVALID_REQUEST, "요청은 JSON 객체여야 합니다.")

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(method, str):
            return self._error(request_id, INVALID_REQUEST, "method가 없습니다.")
        if not isinstance(params, dict):
            return self._error(request_id, INVALID_PARAMS, "params는 객체여야 합니다.")

        token = request.get("token")
        # 타이밍 공격을 막기 위해 상수 시간 비교를 쓴다.
        if not isinstance(token, str) or not hmac.compare_digest(token, self._token):
            return self._error(request_id, UNAUTHORIZED, "토큰이 올바르지 않습니다.")

        handler = self._methods.get(method)
        if handler is None:
            return self._error(request_id, METHOD_NOT_FOUND, f"알 수 없는 메서드: {method}")

        try:
            result = handler(params)
        except RpcError as exc:
            return self._error(request_id, exc.code, str(exc), exc.data)
        except Exception as exc:  # noqa: BLE001 - 서버를 죽이지 않고 오류로 돌려준다.
            return self._error(request_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

        if request_id is None:
            return None
        return self._encode({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id: object, code: int, message: str, data: object = None) -> bytes:
        error: dict[str, object] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return self._encode({"jsonrpc": "2.0", "id": request_id, "error": error})

    @staticmethod
    def _encode(payload: dict[str, object]) -> bytes:
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def call_endpoint(
    endpoint: dict[str, object], method: str, params: dict | None = None, timeout: float = 120.0
) -> object:
    """엔드포인트 정보로 서버에 한 번 호출한다. 브리지와 테스트가 함께 쓴다."""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
        "token": endpoint["token"],
    }
    with socket.create_connection(
        (str(endpoint["host"]), int(endpoint["port"])), timeout=timeout
    ) as sock:
        sock.settimeout(timeout)
        sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
        chunks = bytearray()
        while b"\n" not in chunks:
            data = sock.recv(65536)
            if not data:
                raise RpcError("서버가 응답 없이 연결을 닫았습니다.")
            chunks.extend(data)
            if len(chunks) > MAX_REQUEST_BYTES:
                raise RpcError("응답이 너무 큽니다.")
    response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if "error" in response:
        error = response["error"]
        raise RpcError(str(error.get("message")), int(error.get("code", INTERNAL_ERROR)))
    return response.get("result")
