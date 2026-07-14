# Chrome DevTools MCP 서버 사용법

## 목차

- [소개](#소개)
- [설치](#설치)
- [확인](#확인)
- [막히는 지점](#막히는-지점)
- [등록 스코프](#등록-스코프)
- [참고](#참고)

## 소개

Chrome DevTools MCP 서버는 Chrome DevTools Protocol을 사용하여 브라우저를 조작하고 진단할 수 있는 기능을 제공합니다.

vscode claude plugin은 MCP 서버를 통해 브라우저에 연결하여 다양한 작업을 수행할 수 있습니다. 이 저장소에서는  Chrome DevTools MCP 서버를 설정하고 사용하는 방법을 안내합니다.

## 설치

프로젝트 루트에 `.mcp.json` 파일 하나를 두면 등록이 끝납니다. 별도로 설치할 것은 없습니다. `npx`가 필요할 때 받아서 실행합니다.

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

### Windows에서 `cmd /c`는 필수입니다

Claude Code는 MCP stdio 서버를 **셸 없이** `spawn()` 합니다. Windows의 `CreateProcess`는 `PATHEXT`를 대신 붙여 주지 않으므로, PATH에 `npx.cmd`가 멀쩡히 있어도 `spawn("npx")`는 실행 대상을 찾지 못하고 `spawn npx ENOENT`로 죽습니다.

터미널에서 `npx chrome-devtools-mcp@latest --version`이 잘 돈다고 안심하면 안 됩니다. 터미널은 셸이라 확장자를 대신 풀어 줍니다. Claude Code의 실행 경로와 다릅니다.

macOS · Linux라면 `"command": "npx"`로 충분합니다.

## 확인

`.mcp.json`을 만든 뒤 **세션을 새로 시작**합니다. 채팅창에 `/mcp`를 치면 `chrome-devtools`가 목록에 뜨고, `✔ Connected`이면 끝입니다. 처음 한 번은 승인을 묻습니다.

터미널에서 확인하려면 **이 저장소를 루트로** 실행합니다.

```powershell
claude mcp list
# chrome-devtools: cmd /c npx -y chrome-devtools-mcp@latest - ✔ Connected
```

다만 `claude mcp list`는 **별도 프로세스를 새로 띄워** 헬스체크한 결과입니다. 지금 대화 세션이 그 도구를 쓸 수 있는지와는 별개입니다. 세션의 실제 상태는 `/mcp`로 확인합니다.

## 막히는 지점

| 증상 | 원인 | 해결 |
|:--|:--|:--|
| `/mcp`에 안 보임 | MCP 서버는 세션 시작 시점에 로드됩니다 | 세션 재시작 |
| `Pending approval` | `.mcp.json`은 project scope라 첫 사용 전 승인이 필요합니다 | 승인하면 `.claude/settings.local.json`에 기록됩니다 |
| `spawn npx ENOENT` | `"command": "npx"`로 적었습니다 | `cmd /c`로 감쌉니다 |
| 다른 폴더에서 안 잡힘 | project scope는 **그 폴더를 루트로 연 세션**에서만 읽힙니다 | 이 폴더를 열거나, `-s user`로 전역 등록합니다 |

### `claude mcp add`는 Git Bash에서 실행하지 마십시오

```bash
# Git Bash — 망가집니다
claude mcp add chrome-devtools -- cmd /c npx -y chrome-devtools-mcp@latest
#   → args가 ["C:/", "npx", ...] 로 저장됩니다.
#      MSYS가 /c 를 경로로 착각해 C:/ 로 변환하기 때문입니다.
```

PowerShell에서 실행하면 `["/c", "npx", ...]`로 제대로 들어갑니다. 조용히 망가지고, 헬스체크를 돌리기 전까지는 그럴듯해 보입니다. (2026-07-09 실측)

## 등록 스코프

```powershell
claude mcp add <name> -s project -- cmd /c npx -y <pkg>   # .mcp.json, 팀 공유
claude mcp add <name> -s local   -- ...                   # 이 프로젝트, 나만
claude mcp add <name> -s user    -- ...                   # 모든 프로젝트
```

`-s user`는 루트와 무관하게 어디서든 로드됩니다. 편리하지만 모든 프로젝트가 그 서버를 보게 됩니다. 이 저장소는 `.mcp.json`(project scope) 하나만 씁니다.

VS Code에는 `.vscode/mcp.json`이라는 별도 파일도 있지만, 그것은 **VS Code 내장 Copilot용**입니다. Claude 확장은 그 파일을 읽지 않습니다. 반드시 프로젝트 루트의 `.mcp.json`에 넣어야 합니다.

## 참고

- `@latest`는 2026-07-09 기준 **1.5.0**으로 해석되며 도구는 29개입니다. 버전이 올라가면 도구 이름과 개수가 달라질 수 있으니 데모 전 `/mcp`로 확인합니다.
- 기본 모드는 설치된 Chrome을 **별도 프로필의 새 창**으로 띄웁니다. 내가 로그인해 쓰는 창이 아닙니다. 그 프로필은 지워지지 않고 남으므로, 매번 깨끗한 임시 프로필을 원하면 `--isolated`를 붙입니다.
- `.claude/`는 승인 기록이라 `.gitignore`에 넣었습니다. 커밋하면 저장소를 클론한 사람의 승인 관문이 사라집니다.
