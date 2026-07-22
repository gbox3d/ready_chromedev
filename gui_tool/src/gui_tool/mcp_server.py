"""실행 중인 gui-tool 창을 AI에게 MCP 도구로 노출하는 stdio 브리지.

**순수 프록시다.** 여기에는 로직을 두지 않는다. 모든 판단은 GUI 프로세스가 하고, 이 파일은
MCP `tools/call`을 GUI의 JSON-RPC 호출로 옮겨 담기만 한다. 로직이 두 군데로 갈라지면 사람이
보는 창과 AI가 보는 상태가 어긋나기 시작한다.

등록 예 (`.mcp.json`):

```json
{
  "mcpServers": {
    "gui-tool": {
      "command": "cmd",
      "args": ["/c", "uv", "--directory", "C:\\\\works\\\\ready_chromedev\\\\gui_tool",
               "run", "python", "-m", "gui_tool.mcp_server"]
    }
  }
}
```
"""
from __future__ import annotations

import json
import sys
from typing import Any

from . import rpc


PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "gui-tool", "version": "0.4.0"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "gui_tool_status",
        "description": (
            "실행 중인 gui-tool 창의 현재 상태를 읽는다. MCP가 연결해야 할 browser_url, "
            "현재 탭(local/tunnel), 실행 여부, 마지막 오류를 돌려준다. 다른 도구를 쓰기 전에 "
            "먼저 호출해 상태를 확인하라."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gui_tool_start",
        "description": (
            "Chrome CDP 엔드포인트를 시작한다. mode='local'이면 이 PC에 전용 Chrome을 띄우고, "
            "mode='tunnel'이면 Chrome에 더해 SSH 역터널까지 연다. 기본적으로 실행 상태가 될 "
            "때까지 기다린 뒤 최종 상태를 돌려준다. 포트가 다른 프로세스에 점유되어 있으면 "
            "포트를 임의로 바꾸지 않고 점유자를 명시한 오류를 낸다 — chrome-devtools-mcp의 "
            "--browser-url은 서버 시작 시점에 고정되므로 포트가 바뀌면 연결이 깨지기 때문이다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["local", "tunnel"],
                    "description": "생략하면 창에서 현재 선택된 탭을 쓴다.",
                },
                "chrome_debug_port": {
                    "type": "integer",
                    "description": "이 PC의 Chrome CDP 포트. 생략하면 창의 현재 값을 쓴다.",
                },
                "profile": {
                    "type": "string",
                    "description": "역터널 모드에서 쓸 프로파일 이름.",
                },
                "wait": {
                    "type": "boolean",
                    "description": "실행 상태가 될 때까지 대기할지. 기본 true.",
                },
                "timeout": {"type": "number", "description": "대기 상한(초). 기본 45."},
            },
        },
    },
    {
        "name": "gui_tool_stop",
        "description": "실행 중인 Chrome과 SSH 역터널을 중지한다. 앱이 시작한 것만 종료하며, 빌려 쓰던 기존 Chrome은 닫지 않는다.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gui_tool_cleanup",
        "description": (
            "이전 실행이 남긴 프로세스와 전용 프로파일 폴더를 조회하거나 정리한다. "
            "기본은 조회만 한다(apply=false). 실제로 종료하려면 apply=true를 명시하라. "
            "소유권이 확인된 것만 정리하며 사용자의 평소 Chrome은 절대 건드리지 않는다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "apply": {
                    "type": "boolean",
                    "description": "true면 실제로 종료·삭제한다. 기본 false(조회만).",
                }
            },
        },
    },
    {
        "name": "gui_tool_log",
        "description": "창의 실행 로그 끝부분을 읽는다. 시작 실패 원인을 볼 때 쓴다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tail": {"type": "integer", "description": "가져올 줄 수. 기본 50."}
            },
        },
    },
    {
        "name": "gui_tool_profiles",
        "description": "SSH 역터널 프로파일 목록과 현재 선택을 읽는다.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "gui_tool_select_profile",
        "description": "역터널 프로파일을 선택한다. 실행 중에는 바꿀 수 없다.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]

_METHOD_BY_TOOL = {
    "gui_tool_status": "status",
    "gui_tool_start": "start",
    "gui_tool_stop": "stop",
    "gui_tool_cleanup": "cleanup",
    "gui_tool_log": "log",
    "gui_tool_profiles": "profiles",
    "gui_tool_select_profile": "select_profile",
}

NO_WINDOW_HINT = (
    "실행 중인 gui-tool 창을 찾지 못했습니다. 이 브리지는 창을 대신 띄우지 않습니다 — "
    "사람이 보고 있는 인스턴스를 함께 조작하는 것이 목적이기 때문입니다. "
    "먼저 다음을 실행하세요:\n"
    "    cd C:\\works\\ready_chromedev\\gui_tool\n"
    "    uv run gui-tool"
)


def _live_endpoint() -> dict[str, object]:
    endpoints = rpc.read_endpoints()
    if not endpoints:
        raise rpc.RpcError(NO_WINDOW_HINT)
    return endpoints[0]


def _call_tool(name: str, arguments: dict[str, Any]) -> object:
    method = _METHOD_BY_TOOL.get(name)
    if method is None:
        raise rpc.RpcError(f"알 수 없는 도구: {name}")
    return rpc.call_endpoint(_live_endpoint(), method, arguments)


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = _call_tool(str(name), dict(arguments))
        except rpc.RpcError as exc:
            # MCP는 도구 실패를 프로토콜 오류가 아니라 isError 결과로 돌려준다.
            # 그래야 모델이 메시지를 읽고 스스로 고칠 수 있다.
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            }
        except OSError as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"{NO_WINDOW_HINT}\n\n({exc})"}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                ]
            },
        }

    if request_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"지원하지 않는 메서드: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            _write({"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "JSON을 해석할 수 없습니다."}})
            continue
        if not isinstance(request, dict):
            continue
        response = _handle(request)
        if response is not None:
            _write(response)


if __name__ == "__main__":
    main()
