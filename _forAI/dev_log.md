# Dev Log

## 목차

- [Entries](#entries)

## Entries

### 2026-07-21 (1) — forAI 문서 정합성 검증 및 Mermaid 문서 보강

**시간**: 2026-07-21 16:55:26 +09:00 (Korea Standard Time)

**검증 대상**: `_forAI/README.md` → `inventory.md` → `memo.md` → `dev_log.md` → `plan.md` 순서로
문서를 읽고, `tunnel_gui/`의 Python 구현·프로파일·실행 명령과 대조했다.

**문서 갱신**

- `_forAI/README.md`에 SSH 역터널 구조와 Tkinter GUI 생명주기 Mermaid 다이어그램을 유지하고,
  실제 확인된 Tk 8.6.14 버전으로 기준값을 맞췄다.
- `inventory.md`의 `.gitignore` 목록과 Python/Tk 검증 기준을 현재 파일 및 실행 환경에 맞췄다.
- `memo.md`의 `chrome-devtools-mcp` 버전에 확인 시점(2026-07-09)과 tunnel_gui 런타임 기준을 명시했다.
- `tunnel_gui/README.md`의 Mermaid 블록 뒤에 남아 있던 중복 Markdown 닫힘 표시를 제거했다.

**검증**

- `uv run python -m unittest discover -s tests -v`: 6개 테스트 통과.
- `uv run python -m compileall -q chrome_tunnel_gui chrome_devtools_tunnel_gui.py`: 통과.
- uv 실행 환경: Python 3.14.6, Tk 8.6.14, PyYAML 6.0.3.
- 문서의 SSH 포트 9222/9333, 기본 프로파일 `dgx-01`, SSH Host 별칭과 `-R` 명령이 구현과 일치함을 확인했다.
- `git diff --check`: 통과.

**미검증**: 실제 원격 서버에서 reverse forward 후 `curl http://127.0.0.1:9222/json/version` 응답을 받는 과정은
이번에도 실행 환경상 확인하지 않았다.

### 2026-07-20 (3) — tunnel_gui 독립 Python 앱과 문서 정리 완료

**시간**: 2026-07-20 22:24:54 +09:00

**결정**: 터널 관리 기능을 `tunnel_gui/` 독립 프로젝트로 분리하고 PowerShell 스크립트 의존성을
제거했다. Python·Tkinter·uv와 PyYAML 프로파일 저장소만 사용한다.

**구성**

- `tunnel_gui/chrome_tunnel_gui/tunnel.py`: Chrome 탐색·실행, DevTools 준비 확인, SSH `-R`,
  프로세스 상태와 종료.
- `tunnel_gui/chrome_tunnel_gui/profiles.py`: `profiles.yaml` 로드·저장·프로파일 선택·삭제.
- `tunnel_gui/chrome_tunnel_gui/app.py`: Tkinter GUI, AI 협업 문장, 로그와 프로파일 관리.
- `tunnel_gui/profiles.yaml`: `dgx-01` 기본 프로파일과 SSH Host 별칭 설정.
- `tunnel_gui/tests/`: 프로파일 round-trip, 포트 검증, SSH/Chrome 명령 테스트.

**Chrome 종료 정책**

앱이 직접 시작한 Chrome만 Windows Job Object에 연결한다. 터널 중지·SSH 종료·오류·GUI 종료
시 Job Object를 닫아 Chrome 자식 프로세스까지 종료한다. 시작 전부터 포트를 사용하던 Chrome은
앱 소유가 아니므로 종료하지 않는다.

**문서 정리**

- `readme.md`를 `tunnel_gui` 실행법과 프로파일 관리법에 맞게 수정했다.
- `_forAI/README.md`, `inventory.md`, `memo.md`, `plan.md`를 독립 Python 구조와 검증 결과에
  맞게 동기화했다.
- 루트의 이전 uv 설정과 이전 PS1 구현은 제거했으며, `tunnel_gui/uv.lock`을 기준으로 관리한다.

**검증**

- PyYAML 6.0.3 uv lock/sync 성공.
- 단위 테스트 6개 통과.
- Python compileall 통과.
- Tkinter GUI 초기화 성공.
- Windows Job Object 생성·종료 성공.
- Chrome 실행 파일 자동 탐색 성공.
- SSH Host 별칭 및 공개키 인증은 앞선 검증에서 exit code 0 확인.
- 실제 reverse forward 이후 원격 `/json/version` 응답은 아직 미검증.

---

### 2026-07-20 (2) — SSH Host 별칭을 통해 공개키 인증 확인

**배경**: 사용자 SSH 설정은 `Host gblab-dgx-01`에
`IdentityFile ~/.ssh/id_ed25519_myservers`를 지정했지만, 기존 스크립트는
`gblab-dgx-01@192.168.0.220`을 SSH 대상에 넣고 있었다. 이 형식은 `Host gblab-dgx-01`
블록을 적용하지 않는다.

**변경**

- PowerShell에 선택적 `-SshHost` 파라미터를 추가했다.
- GUI에 `SSH Host 별칭` 입력란을 추가하고 기본값을 `gblab-dgx-01`로 설정했다.
- 별칭이 있으면 별칭을 그대로 SSH 대상에 전달하고, 비어 있으면 기존 `사용자@IP` 방식으로
  동작한다.
- README와 `_forAI/README.md`에 Host 별칭 사용 규칙을 기록했다.

**검증**

- `ssh -G gblab-dgx-01`에서 `identityfile ~/.ssh/id_ed25519_myservers` 선택 확인.
- `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes gblab-dgx-01 exit` 성공,
  exit code 0.
- GUI 명령에 `-SshHost gblab-dgx-01`이 포함되는 것과 Python/PowerShell 구문을 확인했다.

---

### 2026-07-20 (1) — Chrome DevTools SSH 역터널 Tkinter 관리자 추가

**시간**: 2026-07-20 20:45:19 +09:00

**요청**: `start_chrome_devtools_tunnel.ps1`의 SSH 역터널 동작을 문서에 설명하고,
Python·uv·Tkinter 기반 GUI로 관리한다.

**변경**

- `pyproject.toml`, `uv.lock`을 추가해 외부 패키지 없는 uv 실행 환경을 정의했다.
- `scripts/chrome_devtools_tunnel_gui.py`를 추가했다.
  - 호스트·포트·SSH 사용자 입력 검증
  - 기존 PowerShell 터널 스크립트 실행과 실시간 로그 표시
  - 시작·중지 상태 관리와 자신이 시작한 프로세스 트리 종료
- `readme.md`와 `_forAI/README.md`에 SSH 역터널 방향 도표, GUI·CLI 실행법,
  원격 확인 명령과 보안 경계를 기록했다.
- `inventory.md`, `memo.md`, `plan.md`를 확장된 저장소 범위에 맞게 동기화했다.

**검증**

- `uv run python -m py_compile scripts\chrome_devtools_tunnel_gui.py` 통과.
- uv 관리 CPython 3.14.6에서 Tk 8.6 import 확인.
- 숨긴 Tk 루트에서 `TunnelManager` 객체와 위젯 초기화 확인.
- 명령 생성과 포트 파싱 스모크 테스트 통과.
- 실제 SSH 서버 연결과 원격 `/json/version` 응답은 아직 미검증.

---

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
