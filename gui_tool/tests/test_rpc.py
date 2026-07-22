from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from gui_tool import cleanup, mcp_server, rpc


def _send_raw(endpoint: rpc.Endpoint, payload: str) -> dict:
    """JSON-RPC 봉투를 직접 보낸다. 잘못된 요청도 시험해야 하므로 헬퍼를 쓰지 않는다."""
    with socket.create_connection((endpoint.host, endpoint.port), timeout=5) as sock:
        sock.sendall(payload.encode("utf-8") + b"\n")
        chunks = bytearray()
        while b"\n" not in chunks:
            data = sock.recv(65536)
            if not data:
                break
            chunks.extend(data)
    return json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))


class RpcServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[dict] = []

        def echo(params: dict) -> dict:
            self.calls.append(params)
            return {"got": params}

        def boom(params: dict) -> None:
            raise rpc.RpcError("의도된 실패", rpc.INVALID_PARAMS)

        def crash(params: dict) -> None:
            raise ZeroDivisionError("bang")

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        patcher = patch.object(cleanup, "temp_root", lambda: root)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.server = rpc.RpcServer({"echo": echo, "boom": boom, "crash": crash})
        self.endpoint = self.server.start()
        self.addCleanup(self.server.close)

    def test_binds_loopback_only(self) -> None:
        self.assertEqual(self.endpoint.host, "127.0.0.1")
        self.assertGreater(self.endpoint.port, 0)
        self.assertEqual(len(self.endpoint.token), 64)

    def test_round_trips_a_call(self) -> None:
        result = rpc.call_endpoint(
            {"host": self.endpoint.host, "port": self.endpoint.port, "token": self.endpoint.token},
            "echo",
            {"a": 1},
        )

        self.assertEqual(result, {"got": {"a": 1}})
        self.assertEqual(self.calls, [{"a": 1}])

    def test_rejects_a_wrong_token(self) -> None:
        response = _send_raw(
            self.endpoint,
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "echo", "token": "nope"}),
        )

        self.assertEqual(response["error"]["code"], rpc.UNAUTHORIZED)
        self.assertEqual(self.calls, [])

    def test_rejects_a_missing_token(self) -> None:
        response = _send_raw(
            self.endpoint, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "echo"})
        )

        self.assertEqual(response["error"]["code"], rpc.UNAUTHORIZED)
        self.assertEqual(self.calls, [])

    def test_reports_unknown_method(self) -> None:
        response = _send_raw(
            self.endpoint,
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "nope", "token": self.endpoint.token}),
        )

        self.assertEqual(response["error"]["code"], rpc.METHOD_NOT_FOUND)

    def test_reports_bad_json(self) -> None:
        response = _send_raw(self.endpoint, "{ not json")

        self.assertEqual(response["error"]["code"], rpc.PARSE_ERROR)

    def test_surfaces_rpc_error_code(self) -> None:
        response = _send_raw(
            self.endpoint,
            json.dumps({"jsonrpc": "2.0", "id": 7, "method": "boom", "token": self.endpoint.token}),
        )

        self.assertEqual(response["id"], 7)
        self.assertEqual(response["error"]["code"], rpc.INVALID_PARAMS)
        self.assertIn("의도된 실패", response["error"]["message"])

    def test_an_unexpected_exception_does_not_kill_the_server(self) -> None:
        response = _send_raw(
            self.endpoint,
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "crash", "token": self.endpoint.token}),
        )
        self.assertEqual(response["error"]["code"], rpc.INTERNAL_ERROR)

        # 서버는 계속 살아 있어야 한다.
        still = rpc.call_endpoint(
            {"host": self.endpoint.host, "port": self.endpoint.port, "token": self.endpoint.token},
            "echo",
            {"b": 2},
        )
        self.assertEqual(still, {"got": {"b": 2}})

    def test_publishes_and_removes_its_endpoint_file(self) -> None:
        found = rpc.read_endpoints()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["port"], self.endpoint.port)
        self.assertEqual(found[0]["pid"], os.getpid())

        self.server.close()
        self.assertEqual(rpc.read_endpoints(), [])

    def test_discards_endpoint_file_of_a_dead_owner(self) -> None:
        stale = rpc.endpoint_path(999999)
        stale.write_text(
            json.dumps({"version": 1, "pid": 999999, "host": "127.0.0.1", "port": 1, "token": "x"}),
            encoding="utf-8",
        )

        found = rpc.read_endpoints()

        self.assertTrue(all(item["pid"] != 999999 for item in found))
        self.assertFalse(stale.exists())


class TkDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import tkinter as tk
        except ImportError:  # pragma: no cover
            self.skipTest("Tk를 사용할 수 없습니다.")
        self.tk = tk
        try:
            self.root = tk.Tk()
        except tk.TclError:  # pragma: no cover - 헤드리스 환경
            self.skipTest("Tk 디스플레이가 없습니다.")
        self.root.withdraw()
        self.addCleanup(self._destroy)
        self.dispatcher = rpc.TkDispatcher(self.root, interval=10)

    def _destroy(self) -> None:
        # 창을 부수기 전에 펌프를 멈춘다. 순서를 지키지 않으면 예약된 after 콜백이
        # 깨어나 "invalid command name"을 남긴다 — 앱의 close()도 같은 순서를 지킨다.
        self.dispatcher.stop()
        try:
            self.root.destroy()
        except self.tk.TclError:
            pass

    def _pump_until(self, done: threading.Event, seconds: float = 5.0) -> None:
        import time

        end = time.monotonic() + seconds
        while time.monotonic() < end and not done.is_set():
            self.root.update()
            time.sleep(0.01)

    def test_runs_the_callable_on_the_tk_thread(self) -> None:
        tk_thread = threading.get_ident()
        box: dict[str, object] = {}
        done = threading.Event()

        def caller() -> None:
            try:
                box["value"] = self.dispatcher.call(lambda: threading.get_ident())
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=caller, daemon=True).start()
        self._pump_until(done)

        self.assertNotIn("error", box)
        self.assertEqual(box["value"], tk_thread)

    def test_propagates_the_exception_to_the_caller(self) -> None:
        box: dict[str, object] = {}
        done = threading.Event()

        def caller() -> None:
            try:
                self.dispatcher.call(lambda: (_ for _ in ()).throw(ValueError("nope")))
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=caller, daemon=True).start()
        self._pump_until(done)

        self.assertIsInstance(box.get("error"), ValueError)

    def test_stop_releases_a_waiting_caller(self) -> None:
        # 종료 중에 들어온 호출이 타임아웃까지 매달리면 창이 닫히지 않는다.
        self.dispatcher.stop()

        with self.assertRaises(rpc.RpcError) as caught:
            self.dispatcher.call(lambda: 1, timeout=1)
        self.assertEqual(caught.exception.code, rpc.SHUTTING_DOWN)


class McpBridgeTests(unittest.TestCase):
    def test_initialize_reports_tool_capability(self) -> None:
        response = mcp_server._handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )

        self.assertEqual(response["result"]["protocolVersion"], mcp_server.PROTOCOL_VERSION)
        self.assertIn("tools", response["result"]["capabilities"])

    def test_initialized_notification_gets_no_response(self) -> None:
        self.assertIsNone(
            mcp_server._handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_every_tool_maps_to_an_rpc_method(self) -> None:
        response = mcp_server._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertEqual(names, set(mcp_server._METHOD_BY_TOOL))
        for tool in response["result"]["tools"]:
            self.assertIn("description", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_missing_window_is_a_tool_error_not_a_protocol_error(self) -> None:
        with patch.object(rpc, "read_endpoints", return_value=[]):
            response = mcp_server._handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "gui_tool_status", "arguments": {}},
                }
            )

        # 프로토콜 오류로 만들면 모델이 스스로 고칠 수 없다. isError 결과여야 한다.
        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("uv run gui-tool", response["result"]["content"][0]["text"])

    def test_cleanup_tool_defaults_to_dry_run(self) -> None:
        tool = next(t for t in mcp_server.TOOLS if t["name"] == "gui_tool_cleanup")

        self.assertNotIn("required", tool)
        self.assertIn("기본 false", tool["inputSchema"]["properties"]["apply"]["description"])


if __name__ == "__main__":
    unittest.main()
