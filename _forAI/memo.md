# Memo

## 목차

- [제품 기준선](#제품-기준선)
- [등록 스코프](#등록-스코프)
- [로드 시점](#로드-시점)
- [MCP 최소 개념](#mcp-최소-개념)
- [기본 설정값](#기본-설정값)
- [반복 금지](#반복-금지)

## 제품 기준선

| 항목 | 값 | 확인 방법 |
|:--|:--|:--|
| OS | Windows 11 Home 26200 | — |
| Node.js | v24.18.0 (nvm-windows, `C:\nvm4w\nodejs`) | `node -v` |
| Chrome | 150.0.7871.115 | `(Get-Item chrome.exe).VersionInfo` |
| Claude Code | 2.1.193 | `claude --version` |
| chrome-devtools-mcp | `@latest` → 1.5.0, 도구 29개 | `npx -y chrome-devtools-mcp@latest --version` |
| MCP protocol | `2025-06-18` (서버 최신 지원 `2025-11-25`) | `initialize` 응답 |

---

## 등록 스코프

MCP 서버는 세 군데서 읽힌다. **어디에 등록했느냐가 어느 세션에서 보이느냐를 결정한다.**

| 스코프 | 저장 위치 | 어느 세션에서 보이나 |
|:--|:--|:--|
| project | 프로젝트 루트의 `.mcp.json` | 그 폴더를 **루트로 연** 세션 |
| local | `~/.claude.json` 의 `projects["<루트경로>"].mcpServers` | 그 폴더를 루트로 연 세션, 나만 |
| user | `~/.claude.json` 최상위 `mcpServers` | **모든** 세션 |

```powershell
claude mcp add <name> -s project -- cmd /c npx -y <pkg>
claude mcp add <name> -s local   -- ...
claude mcp add <name> -s user    -- ...
```

우선순위: local → project → user → plugin.

**`--add-dir` 로 붙인 추가 작업 디렉터리는 루트가 아니다.** 그 폴더의 `.mcp.json` 은 읽히지 않는다.
세션 중에 루트를 바꾸는 방법은 없다 (`claude --help` 확인). 대신 두 길이 있다 —
`--mcp-config <파일>` 로 설정만 끌어오거나, `-s user` 로 전역 등록한다.

이 저장소는 **project scope 하나만** 쓴다 (2026-07-09 확정).
`-s user` 등록은 모든 프로젝트를 오염시키므로 쓰지 않는다.

---

## 로드 시점

**MCP 서버 목록과 연결은 세션이 시작될 때 확정된다.**

- 등록만으로는 부족하다. 세션 시작 **시점에** 설정에 있어야 한다.
- HTTP transport 서버는 그 시점에 살아 있어야 한다. 나중에 서버를 띄워도 이미 늦다.
- 그래서 설정을 고쳤으면 **세션을 재시작**한다. (`/mcp reconnect all` 도 있으나 미검증.)

`claude mcp list` 는 이 규칙 바깥에 있다. **별도 프로세스를 새로 띄워** 헬스체크하므로,
현재 세션이 그 도구를 쓸 수 있는지 아무것도 말해 주지 않는다.
`✔ Connected` 를 보고 "이 세션에서 쓸 수 있다"고 결론내지 말 것. 세션 상태는 `/mcp` 로 본다.

---

## MCP 최소 개념

- **Host** (Claude Code) 안에 **Client** 가 있고, 각 Client 가 하나의 **Server** 에 붙는다.
- 전송: **stdio** (자식 프로세스, 줄 단위 JSON) 또는 **Streamable HTTP**
- 메시지: **JSON-RPC 2.0** — `id` 있으면 요청, 없으면 알림(notification)
- 핸드셰이크: `initialize` → `notifications/initialized` → `tools/list` → `tools/call`
- `chrome-devtools-mcp` 는 **stdio** 다. Claude Code 가 자식 프로세스로 직접 띄운다.
  그래서 미리 켜 둘 서버가 없다.

---

## 기본 설정값

`chrome-devtools-mcp` 에서 **기본값이 위험한 것들** (`--help` 실측):

| 플래그 | 기본값 | 의미 |
|:--|:--|:--|
| `--redactNetworkHeaders` | `false` | 쿠키·인증 헤더가 그대로 클라이언트로 간다 |
| `--usageStatistics` | `true` | 사용 통계가 Google 로 전송 |
| `--performanceCrux` | `true` | 성능 트레이스의 **URL** 이 Google CrUX API 로 전송 |
| `--isolated` | `false` | 임시 프로필을 쓰지 않는다 |

기본 모드는 설치된 Chrome 을 **별도이지만 지속되는 프로필**로 새 창에 띄운다.
"깨끗한 임시 프로필"이 아니다. 매번 새것을 원하면 `--isolated`.

---

## 반복 금지

**1. `claude mcp add` 를 Git Bash 에서 돌리지 말 것.**
MSYS 경로 변환이 `-- cmd /c npx ...` 의 `/c` 를 `C:/` 로 바꾼다.
설정에 `args: ["C:/", "npx", ...]` 가 저장되고 **조용히 망가진다.**
PowerShell 에서 등록할 것. (2026-07-09 실측)

**2. "MCP 서버가 뜬다" ≠ "이 세션이 도구로 쓸 수 있다".**
`claude mcp list` 의 `✔ Connected` 는 별도 프로세스의 헬스체크 결과다.
세션에 실제로 붙었는지는 `/mcp` 로만 확인된다.

**3. `-s user` 스코프는 모든 프로젝트에 상속된다.**
"MCP 없는 상태"를 재현해야 하는 실험에서 조용히 오염된다.

**4. Windows 에서 `"command": "npx"` 는 동작하지 않는다.**
Claude Code 는 셸 없이 `spawn()` 한다. 터미널에서 `npx ... --version` 이 도는 것은
**셸을 거치는 경로**이므로 아무것도 증명하지 못한다.

**5. Chrome 136+ 는 기본 프로필의 원격 디버깅을 조용히 무시한다.**
에러도 안 낸다. 포트가 안 열릴 뿐이다. 반드시 비기본 `--user-data-dir` 를 줄 것.

**6. `@latest` 는 조용히 올라간다.** 문서에 도구 개수를 박아 두었으면 데모 전 `/mcp` 로 재확인할 것.
