# Memo

## 목차

- [제품 기준선](#제품-기준선)
- [등록 스코프](#등록-스코프)
- [로드 시점](#로드-시점)
- [MCP 최소 개념](#mcp-최소-개념)
- [SSH 역터널](#ssh-역터널)
- [기본 설정값](#기본-설정값)
- [반복 금지](#반복-금지)

## 제품 기준선

| 항목 | 값 | 확인 방법 |
|:--|:--|:--|
| OS | Windows 11 Home 26200 | — |
| Node.js | v24.18.0 (nvm-windows, `C:\nvm4w\nodejs`) | `node -v` |
| Chrome | 150.0.7871.115 | `(Get-Item chrome.exe).VersionInfo` |
| Claude Code | 2.1.193 | `claude --version` |
| chrome-devtools-mcp | `@latest` → 1.5.0, 도구 29개 (2026-07-09 확인) | `npx -y chrome-devtools-mcp@latest --version` |
| MCP protocol | `2025-06-18` (서버 최신 지원 `2025-11-25`) | `initialize` 응답 |
| tunnel_gui 런타임 | Python 3.14.6 / Tk 8.6.14 / PyYAML 6.0.3 (2026-07-21 확인) | `uv run python` 및 import 확인 |

---

## 등록 스코프

Claude Code의 MCP 서버는 세 군데서 읽힌다. **어디에 등록했느냐가 어느 세션에서 보이느냐를 결정한다.**

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

Claude Code는 **project scope 하나만** 쓴다. `-s user` 등록은 모든 프로젝트를 오염시키므로
이 저장소에서는 쓰지 않는다.

Codex는 별도 설정 체계를 쓴다. `~/.codex/config.toml`의 사용자 전역 설정이 모든 프로젝트에
기본으로 적용되고, trusted 프로젝트의 `.codex/config.toml`이 그 위를 덮어쓴다. Codex VS Code
세션에서 상위 폴더를 작업 루트로 열어도 Chrome DevTools MCP를 써야 하므로, 2026-07-14부터
Codex에는 전역 `chrome-devtools` 등록을 사용한다. Windows 등록 명령은
`codex mcp add chrome-devtools -- cmd /c npx -y chrome-devtools-mcp@latest`다.

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

## SSH 역터널

`ssh -R 127.0.0.1:9222:127.0.0.1:9333`의 주소는 SSH를 실행하는 Windows PC 기준과
원격 서버 기준이 섞여 있다.

- 첫 `127.0.0.1:9222`: 원격 서버에서 열리는 수신 주소와 포트.
- 둘째 `127.0.0.1:9333`: Windows PC에서 SSH 클라이언트가 연결할 Chrome DevTools 주소와 포트.
- 연결 방향: Windows PC → 원격 서버로 SSH 세션을 만들지만, DevTools 요청은 원격 서버 →
  Windows PC로 전달되므로 reverse tunnel이다.
- `ExitOnForwardFailure=yes`: 원격 포트를 열지 못하면 즉시 실패한다.
- `ServerAliveInterval=30`, `ServerAliveCountMax=3`: 끊어진 세션을 무한히 살아 있는 것처럼
  두지 않는다.

원격 바인딩을 `127.0.0.1`로 제한한 것은 보안 경계다. Chrome DevTools는 브라우저 전체 제어에
가까운 권한을 주므로 `0.0.0.0:9222`로 바꾸지 않는다. GUI는 SSH 키/agent 인증만 전제로 하며,
최초 호스트 키 등록은 `ssh 사용자@서버`로 미리 수행한다.

현재 Windows SSH 설정은 `Host gblab-dgx-01`에
`IdentityFile ~/.ssh/id_ed25519_myservers`, `IdentitiesOnly yes`,
`PreferredAuthentications publickey`를 둔다. `ssh gblab-dgx-01@192.168.0.220`처럼
별칭과 IP를 한 명령에 섞으면 `Host gblab-dgx-01` 블록이 적용되지 않는다. Python GUI는
별칭을 `ssh` 대상 그대로 전달한다.

2026-07-20에 `ssh -G gblab-dgx-01`에서 해당 IdentityFile 선택을 확인했고,
`ssh -o BatchMode=yes ... gblab-dgx-01 exit`가 exit code 0으로 완료되어 공개키 인증을 검증했다.

`tunnel_gui/chrome_tunnel_gui/tunnel.py`는 PowerShell 없이 Chrome과 OpenSSH를 직접 실행한다.
터널 프로세스가 종료되거나 GUI에서 중지하면 앱이 시작한 Chrome만 정리한다. 시작 전에 이미
`127.0.0.1:9333`을 점유한 Chrome은 앱 소유가 아니므로 닫지 않는다.

Windows에서는 Chrome 프로세스와 자식 프로세스를 Job Object에 연결하고
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`를 사용한다. 따라서 탭 하나가 아니라 전용 Chrome
프로세스 트리 전체가 종료된다. Chrome 실행에 실패하거나 SSH 연결이 실패해도 정리 경로가
실행된다.

프로파일은 `tunnel_gui/profiles.yaml`에 저장한다. 기본 프로파일은 `dgx-01`이며, GUI의
프로파일 선택·새 프로파일·저장·삭제 작업은 이 파일을 원자적으로 갱신한다. `chrome_profile`
빈 값은 `%TEMP%\ready-chromedev-chrome-9333` 전용 프로파일을 뜻한다.

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

**3. Claude의 `-s user` 스코프는 모든 프로젝트에 상속된다.**
"MCP 없는 상태"를 재현해야 하는 실험에서 조용히 오염된다. 이 주의사항은 Codex의
전역 등록 결정과 별개다.

**4. Windows 에서 `"command": "npx"` 는 동작하지 않는다.**
Claude Code 는 셸 없이 `spawn()` 한다. 터미널에서 `npx ... --version` 이 도는 것은
**셸을 거치는 경로**이므로 아무것도 증명하지 못한다.

**5. Chrome 136+ 는 기본 프로필의 원격 디버깅을 조용히 무시한다.**
에러도 안 낸다. 포트가 안 열릴 뿐이다. 반드시 비기본 `--user-data-dir` 를 줄 것.

**6. `@latest` 는 조용히 올라간다.** 문서에 도구 개수를 박아 두었으면 데모 전 `/mcp` 로 재확인할 것.
