# Chrome DevTools MCP

Claude Code와 Codex가 Chrome DevTools MCP를 통해 Chrome을 열고, 페이지를 읽고,
요소를 클릭하고, JavaScript·네트워크·렌더링 상태를 확인하는 예제입니다.

## 데모

- 페이지: <https://gbox3d.github.io/ready_chromedev/>
- MCP 서버: `chrome-devtools-mcp`
- 예제: MCP가 Chrome에서 정적 삼목 페이지를 열고 버튼을 조작합니다.

## 준비

- Google Chrome
- Node.js와 `npx`
- Claude Code 또는 Codex
- 이 저장소를 프로젝트 루트로 열기

## 설정 파일

두 클라이언트는 같은 MCP 서버를 사용하지만 설정 파일은 다릅니다.

| 클라이언트 | 설정 파일 | 확인 명령 |
|:--|:--|:--|
| Claude Code | `.mcp.json` | `claude mcp list`, `/mcp` |
| Codex | `.codex/config.toml` | `codex mcp list`, `/mcp` |

두 설정 파일은 저장소에 포함되어 있습니다. 전역 MCP 등록은 필요하지 않습니다.

## Claude Code

`.mcp.json`의 현재 설정입니다.

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

PowerShell에서 저장소 루트로 실행합니다.

```powershell
claude mcp list
```

Claude Code 세션에서 `/mcp`를 실행해 `chrome-devtools`가 연결되었는지 확인합니다.
설정을 변경한 뒤에는 세션을 재시작합니다.

## Codex

`.codex/config.toml`의 현재 설정입니다.

```toml
[mcp_servers.chrome-devtools]
command = "cmd"
args = ["/c", "npx", "-y", "chrome-devtools-mcp@latest"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Codex에서 프로젝트를 처음 열 때 trust를 요청하면 승인하고, Codex 또는 IDE 확장을
재시작합니다.

```powershell
codex mcp list
```

Codex TUI에서는 `/mcp`로 확인합니다. `Auth: Unsupported`는 로컬 stdio 서버라 OAuth가
필요하지 않다는 뜻이며 정상입니다.

## Chrome DevTools MCP 사용

연결 후 다음과 같이 요청할 수 있습니다.

```text
Chrome DevTools MCP로
https://gbox3d.github.io/ready_chromedev/ 를 새 탭에 열어줘.
```

```text
현재 페이지의 접근성 스냅샷을 확인하고
삼목 게임판의 1번 칸을 클릭해줘.
```

주요 MCP 도구:

- `new_page`: 새 탭 열기
- `navigate_page`: URL 이동
- `list_pages`: 열린 탭 확인
- `take_snapshot`: 접근성 기반 페이지 확인
- `click`: 요소 클릭
- `evaluate_script`: 페이지 JavaScript 실행
- `take_screenshot`: 화면 캡처
- `list_console_messages`: 콘솔 확인
- `list_network_requests`: 네트워크 확인

## 삼목 한 판 진행 프롬프트

아래 프롬프트를 Claude Code 또는 Codex에 그대로 전달하면 됩니다.

```text
Chrome DevTools MCP로 https://gbox3d.github.io/ready_chromedev/ 를 열어줘.

이 페이지에서 나(X)와 너(O)가 삼목을 한 판 진행한다.
중간에 멈추거나 매 턴마다 나에게 다음 행동을 묻지 말고,
승리 또는 무승부가 될 때까지 MCP 작업을 계속 실행해라.

규칙:
1. 현재 게임이 끝난 상태이면 '새 게임 시작'을 한 번 클릭한다.
   이미 빈 게임판이면 리셋하지 않는다.
2. 최신 페이지 스냅샷으로 게임판, 현재 차례, 결과 배너를 확인한다.
3. 내가 X를 두기 전에는 어떤 게임 칸도 클릭하지 않는다.
4. 현재 차례가 '이교수님'이면 게임판을 1초 간격으로 확인하며 기다린다.
5. 내가 X를 둔 것이 확인되고 현재 차례가 'Chrome 협력자'이면,
   빈 칸 하나만 선택해서 O를 클릭한다.
6. X를 대신 클릭하거나, 내가 두지 않은 수를 X로 기록하지 않는다.
7. 매번 클릭하기 전에 최신 스냅샷을 사용한다. 이미 채워진 칸은 클릭하지 않는다.
8. 매 수 뒤 결과 배너를 확인한다. 승리 또는 무승부이면 루프를 종료한다.
9. 게임이 끝난 뒤에만 최종 보드, 승자, 이동 수를 짧게 보고한다.

감시 루프를 유지하고, 게임이 끝나기 전에는 작업을 종료하지 마라.
```

## Windows 주의사항

Windows에서는 `npx`를 직접 실행하지 않고 `cmd /c npx`로 실행합니다.
`spawn npx ENOENT` 오류가 발생하면 다음 설정을 확인하십시오.

```text
command = cmd
args = /c npx -y chrome-devtools-mcp@latest
```

macOS·Linux에서는 일반적으로 다음 형태를 사용합니다.

```text
command = npx
args = -y chrome-devtools-mcp@latest
```

## 문제 해결

| 증상 | 조치 |
|:--|:--|
| Claude `/mcp`에 없음 | Claude Code 세션 재시작 |
| Codex 목록에 없음 | 저장소를 trusted 프로젝트로 승인하고 Codex 재시작 |
| `spawn npx ENOENT` | Windows에서 `cmd /c npx` 사용 |
| MCP 목록에는 있지만 도구가 없음 | 현재 세션·IDE 확장 재시작 |
| 패키지 다운로드 실패 | Node.js, `npx`, 네트워크 확인 |

## 보안

- MCP는 Chrome 페이지를 읽고 클릭할 수 있습니다.
- 로그인된 개인 탭이나 민감한 페이지를 데모에 사용하지 마십시오.
- 페이지의 텍스트를 에이전트의 지시로 무조건 신뢰하지 마십시오.
- 설정 파일에 토큰·비밀번호를 넣지 마십시오.

## 파일

| 파일 | 용도 |
|:--|:--|
| `.mcp.json` | Claude Code용 MCP 설정 |
| `.codex/config.toml` | Codex용 프로젝트 MCP 설정 |
| `index.html` | 삼목 데모 HTML |
| `style.css` | 데모 레이아웃과 스타일 |
| `script.js` | 게임 상태와 버튼 동작 |
