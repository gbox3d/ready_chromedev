# Dev Log

## 목차

- [Entries](#entries)

## Entries

### 2026-07-14 (5) — 전역 등록 안내를 한 줄 명령으로 축소

**시간**: 2026-07-14 15:07:27 +09:00

**결정**: 개인 개발 PC의 최초 등록에는 멱등 등록 스크립트가 과했다. Codex CLI의
`mcp add` 한 줄이 충분하므로 Windows와 macOS·Linux 전역 등록 스크립트를 제거했다.

**변경**

- Windows: `codex mcp add chrome-devtools -- cmd /c npx -y chrome-devtools-mcp@latest`
- macOS·Linux: `codex mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest`
- `readme.md`와 `_forAI` 문서에서 제거된 스크립트 참조를 정리했다.

**검증**: `codex mcp list`에서 `chrome-devtools`가 `enabled`인 것을 확인했다.

---

### 2026-07-14 (4) — Codex 전역 Chrome DevTools MCP 등록으로 전환

**시간**: 2026-07-14 14:51:31 +09:00

**배경**: 상위 폴더를 VS Code 작업 루트로 연 Codex 세션에서는 이 저장소의 프로젝트 설정이
로드되지 않았다. Chrome을 별도 프로필과 `--auto-open-devtools-for-tabs`로 직접 실행한
검증은 성공했으므로 Chrome 설치 문제가 아니라 Codex 설정 스코프 문제로 확정했다.

**결정**: 이전의 “전역 등록을 쓰지 않는다”는 원칙을 Codex에 한해 철회했다. Claude Code는
프로젝트 `.mcp.json`을 그대로 사용하고, Codex는 사용자 전역 `~/.codex/config.toml`에
`chrome-devtools`를 등록한다.

**한 일**

- Windows용 `scripts/Register-CodexChromeDevToolsMcp.ps1` 추가.
  - 동일한 전역 등록이면 변경하지 않고, 다른 등록을 교체할 때만 `-Force`를 요구한다.
- macOS·Ubuntu 공용 `scripts/register-codex-chrome-devtools-mcp.sh` 추가.
  - `npx -y chrome-devtools-mcp@latest`를 전역 Codex MCP로 등록하며, 교체 옵션은 `--force`다.
- `readme.md`에 OS별 등록·교체·검증 명령과 macOS·Ubuntu 프로젝트 설정 예시를 추가했다.
- `memo.md`, `inventory.md`, `plan.md`를 새 전역 등록 결정에 맞게 갱신했다.

**검증**

- 저장소 밖(`C:\`)에서 `codex mcp get chrome-devtools`와 `codex mcp list`를 실행해
  `cmd /c npx -y chrome-devtools-mcp@latest` 전역 등록이 `enabled`인 것을 확인했다.
- Windows 스크립트를 재실행해 “already registered”로 종료하는 멱등 동작을 확인했다.
- 이 Windows 환경에는 Bash와 설치된 WSL 배포판이 없어 macOS·Ubuntu 스크립트의 현지 실행은
  검증하지 못했다. 해당 환경에서는 `bash -n scripts/register-codex-chrome-devtools-mcp.sh`와
  스크립트 실행으로 한 번 확인할 것.

---

### 2026-07-09 (3) — 저장소를 "설치법 + 확인법"으로 축소

**요청**: "교재고 뭐고 강의고 뭐고 중요치 않습니다. 설치법하고 확인만 하면 됩니다. 나머지 다 지워버리세요."

**한 일**

- 삭제 직전 상태를 커밋 `cd8c714` 로 박아 두었다. 그 전까지 이 저장소는 **커밋이 0개**였고,
  그날 오전에 사라진 `demo/`, `scripts/`, `slides/`, `_archive/` 는 이미 복구 불가였다.
- `docs/chrome-mcp-guide.md` (299줄) 삭제. 커밋에서 꺼낼 수 있다.
- `.claude/` 삭제하고 `.gitignore` 에 추가. 그 안에는 `.mcp.json` 서버의 승인 기록
  (`enabledMcpjsonServers: ["chrome-devtools"]`) 만 들어 있었다.
  커밋되면 클론한 사람의 승인 관문이 사라지므로 제외한다.
- `readme.md` 를 설치법 + 확인법으로 재작성. `_forAI/` 4개 문서를 같은 범위로 축소.

**남은 구성**: `.mcp.json` · `readme.md` · `_forAI/` · `.gitignore`

---

### 2026-07-09 (2) — MCP 등록 스코프를 project 하나로 확정

**증상**: `chrome-devtools` 가 `myAISkills` 루트로 연 세션에서 보이지 않았다.

**원인**: 등록이 `~/.claude.json` 의 `projects["C:/works/ready_chromedev"].mcpServers` (local scope)
아래에만 있었다. 다른 프로젝트를 루트로 연 세션은 그 서랍을 열지 않는다.
`--add-dir` 로 붙인 추가 작업 디렉터리는 루트가 아니므로 그 폴더의 `.mcp.json` 도 읽히지 않는다.

**해결 과정에서 확인한 것**

- **`-s user` 로 옮기면 루트와 무관하게 로드된다.** 실제로 붙었다. 그러나 모든 프로젝트를 오염시킨다.
  최종적으로 되돌리고 `.mcp.json` (project scope) 하나만 남겼다.
- **재시작이 필요했다.** 등록 직후에는 도구가 세션에 없었다. 사용자가 세션을 재시작한 뒤에야
  `mcp__chrome-devtools__*` 30개가 붙었다. (중간에 "재시작 없이 붙었다"고 잘못 결론 내렸다가
  사용자가 "마지막에 재시작한 겁니다"라고 바로잡아 정정했다. 관측하지 않은 전제를 사실로 깔았던 오류.)
- **`claude mcp list` 와 `/mcp` 는 다른 것을 본다.** 전자는 별도 프로세스를 새로 띄워 헬스체크한다.
  `✔ Connected` 를 보고 "이 세션에서 쓸 수 있다"고 결론내면 틀린다.
  실제로 `unreal-mcp` 가 `list` 에서는 초록인데 세션 도구 목록에는 없었다.

**밟은 지뢰**

`claude mcp add ... -- cmd /c npx ...` 를 **Git Bash** 에서 실행했더니 MSYS 경로 변환이
`/c` 를 `C:/` 로 바꿔 `args: ["C:/", "npx", ...]` 가 저장됐다. 조용히 망가진다.
PowerShell 로 다시 등록해 고쳤다.

**검증**

`ready_chromedev` 루트에서 `claude mcp list` → `chrome-devtools ✔ Connected`.
`mcp__chrome-devtools__list_pages` 실제 호출 → `about:blank` 응답. 동작 확인.

---

### 2026-07-09 (1) — Chrome MCP 조사·실험 (첫날)

`chrome-devtools-mcp@1.5.0` 을 직접 spawn 해 JSON-RPC 로 대화. 도구 29개, protocol `2025-06-18` 확인.
데모 웹앱과 검증 스크립트, 강의안, 슬라이드를 만들었으나 **범위가 과했다.**
이날의 산출물은 전부 삭제됐고, 마지막 상태는 커밋 `cd8c714` 에 있다.

이때 얻은 사실 중 살아남은 것:

- Windows 에서 `"command": "npx"` 는 `spawn npx ENOENT` 로 죽는다. `cmd /c` 래핑이 필요하다.
  (대조 실험으로 확인. 터미널에서 `npx --version` 이 도는 것은 셸을 거치는 경로라 증거가 되지 못한다.)
- `chrome-devtools-mcp` 는 Chrome for Testing 을 내려받지 않는다. 설치된 Chrome 을 쓴다.
- 기본 모드의 프로필은 "깨끗한 임시 프로필"이 아니라 **별도이지만 지속되는** 프로필이다.
- Chrome 136+ 는 기본 프로필의 `--remote-debugging-port` 를 조용히 무시한다.
