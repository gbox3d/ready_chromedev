# Dev Log

## 목차

- [Entries](#entries)

## Entries

> **주의**: 2026-07-21 (1) 이전 항목은 `tunnel_gui/`와 `chrome_tunnel_gui` 패키지를 다룬다.
> 그 트리는 삭제되었고 `gui_tool/`로 대체되었으므로, 옛 항목의 실행·검증 명령은 그대로
> 동작하지 않는다. 이력은 그 시점의 사실이므로 고치지 않고 남긴다. 현재 구조와 명령은
> `inventory.md`를 볼 것.

### 2026-07-22 (3) — GUI 내장 RPC와 MCP 브리지로 AI와 창을 공유

**요청**: "이거 rpc 형태로 수정해주시는것 어떠신가요? AI도 이 툴 자체를 저하고 똑같이 다룰수
있게요." 이후 장단점 비교를 거쳐 **JSON-RPC + MCP 브리지(A안)** 로 확정했다.
"헤드리스는 전혀 필요하지 않다. 오히려 GUI를 같이 공유하는 데 정말 필요하다."

**결정을 가른 제약**

MCP stdio 서버는 클라이언트가 spawn하고 세션 종료 시 함께 죽는다. MCP 서버가 Chrome·ssh를
직접 소유하면 (1) Claude 세션을 닫는 순간 역터널이 끊기고, (2) 사람의 GUI와 AI의 인스턴스가
갈라진다. 그래서 **MCP는 바깥 인터페이스로 두고, 지속 소유자는 GUI 프로세스**로 했다.
헤드리스 우선 설계(코어/프론트 분리)는 검토 후 기각했다 — 목적과 어긋나고 검증 완료된 생명주기
경로를 전면 재검증해야 한다.

**구성**

- `src/gui_tool/rpc.py`: GUI 내장 JSON-RPC 2.0 서버(127.0.0.1 + 토큰), `TkDispatcher`,
  엔드포인트 파일 발행·발견.
- `src/gui_tool/mcp_server.py`: stdio MCP 브리지. **순수 프록시이며 로직을 두지 않는다.**
- `app.py`: RPC 표면 7종과 생명주기 연결. `.mcp.json`에 `gui-tool` 서버 등록.

**AI 경로에만 적용한 규칙**

- **모달 대화상자 금지.** 사람 없는 경로에서 대화상자가 뜨면 창이 멈추고 호출자는 영문도 모른
  채 기다린다. `_start_source`로 UI/RPC를 구분하고, RPC 오류는 `status.last_error`로 읽힌다.
- **포트 자동 전환 금지.** `--browser-url`은 MCP 서버 시작 시점에 고정되므로 포트가 바뀌면
  이미 붙은 연결이 끊긴다. 점유자를 명시한 오류를 그대로 반환한다.
- **파괴적 동작은 조회가 기본.** `cleanup`은 `apply=true`를 명시해야 실제로 종료한다.

**작업 중 잡은 버그 둘**

- `stop`이 runner만 기다리고 앱 상태를 안 기다려 `running: true, "중지 중"`을 반환했다.
  AI가 읽으면 중지 실패로 오해한다. 앱 상태가 가라앉을 때까지 기다리도록 고쳤다.
- `TkDispatcher`에 `_drain_events`와 같은 부류의 `invalid command name` 문제가 있었다.
  재예약을 방어하고, 테스트도 `stop()` 후 `destroy()` 순서를 지키도록 했다.

**검증** — Tk 창을 실제로 띄운 채 별도 스레드가 조작하는 방식으로 전 경로 실측

- RPC 직결: 엔드포인트 자동 발견 → 잘못된 토큰 거부 → cleanup 조회(종료 안 함) → local 시작
  (browser_url 반환, Chrome 9개) → 중복 시작 거부 → 로그 조회 → 중지 → **누수 0** →
  알 수 없는 메서드 거부 → 창 닫으면 엔드포인트 파일 제거. PASS
- MCP stdio 실제 프로토콜: `initialize` → `tools/list`(7개) → `status` → `start`(running=true)
  → `cleanup`(dry run) → `stop` → 잘못된 도구명은 프로토콜 오류가 아니라 `isError` 결과. PASS
- 창이 없을 때: 브리지가 창을 대신 띄우지 않고 `uv run gui-tool` 안내를 `isError`로 반환. 확인.
- 단위 테스트 34 → **52개** 통과. 버전 0.3.0 → 0.4.0.

**미확인**: 실제 Claude Code 세션에서 `gui-tool` 도구가 `/mcp`에 뜨는지는 세션 재시작이 필요해
아직 확인하지 않았다.

---

### 2026-07-22 (2) — Chrome 9222 점유의 진짜 원인 규명, `_forAI` 문서 동기화

**요청**: gui_tool이 기본값(로컬 탭 + 9222)에서 "다른 프로세스가 사용 중"으로 실패했다.
사용자가 자기 충돌 버그로 보고했고, 원인 추적과 문서 갱신을 지시했다.

**1차 오진과 수정**

포트 점유 오류가 점유자를 밝히지 않아 사용자가 앱의 자기 충돌로 오해했다. 실제 점유자는
사용자의 상시 Chrome이었다. 오류 메시지를 다음과 같이 고쳤다.

- `PortInUseError`: `GetExtendedTcpTable`(ctypes)로 점유 프로세스의 pid·이미지명을 찾아 명시.
- 앱 소유 여부 판정: 세션 기록 또는 전용 프로파일 폴더 점유 여부로 구분.
- 복구 경로 제공: 남의 프로세스면 빈 포트로 전환 제안, 앱 소유 잔존물이면 정리 후 재시작 제안.
- 중지 직후 재시작의 일시적 점유는 3초까지 재시도.
- 세션 파일이 없는 구버전 누수는 Restart Manager(`RmGetList`)로 전용 프로파일 폴더를 쥔
  chrome.exe를 찾아 회수.

**근본 원인 (여기가 핵심)**

명령줄 플래그가 아니었다. 바로 가기 3개 모두 인자가 비어 있었고, Chrome 정책·셸 열기 명령·
IFEO·예약 작업·레지스트리 Run 키 전부 깨끗했다. 9222를 연 프로세스의 명령줄 자체가 비어 있었다.

가른 실험: 새 `--user-data-dir`로 플래그 없이 Chrome을 띄우니 9222가 **안 열렸다**. 기본
프로필로 띄우면 0.9초 만에 열렸다. → 명령줄이 아니라 저장된 설정이라는 결론.

```
%LOCALAPPDATA%\Google\Chrome\User Data\Local State
  → devtools.remote_debugging = { "user-enabled": true }
```

Chrome 136+가 기본 프로필 원격 디버깅을 차단하면서 만든 사용자 옵트인이다. 브라우저 전역
파일에 저장되므로 프로세스 명령줄에 전혀 나타나지 않는다.

**조치**: 사용자 승인 후 Chrome을 정상 종료(WM_CLOSE, 세션 보존)하고 그 값만 `false`로 바꿨다.
거대한 variations seed가 든 파일이라 JSON 재직렬화 대신 최소 문자열 치환을 썼다
(36578→36579바이트). 백업은 `Local State.bak-gui-tool-20260722-114926`.

**검증**

- Chrome 재시작(세션 복원) 후 9222 닫힘, chrome.exe가 여는 LISTEN 포트 0개.
- `DevToolsActivePort` 갱신 중단 확인.
- gui_tool이 기본값 9222로 정상 동작. 포트 전환 안내 없이 시작 → CDP 응답 → 중지·종료 후 누수 0.
- 단위 테스트 34개 통과 (`port_owner`, Restart Manager, `PortInUseError` 실기능 테스트 포함).

**문서 갱신 (사용자 지시)**

- `memo.md` "반복 금지 5번"을 실측에 맞게 수정했다. 기존 기록 "포트가 안 열릴 뿐이다"는 **틀렸다**.
  Chrome 150 실측은 포트가 열리고 `DevToolsActivePort`도 갱신되며 `/json/*`만 404다.
- `memo.md`에 "Chrome 원격 디버깅의 실제 거동" 절과 반복 금지 7·8번을 추가했다.
- `README.md`·`inventory.md`·`plan.md`의 `tunnel_gui/` 참조를 `gui_tool/`로 전부 교체했다.
- Python 런타임 기준을 3.14.6에서 실제 `.venv` 값인 3.11.15로 정정했다.

**추가 조사 (배경 워크플로)**: `Antigravity IDE`의 `main.js`에 CDP 포트 fallback 9222가
하드코딩되어 있으나, 검증 결과 **소비자였지 생산자가 아니었다** — 전용 프로파일 폴더 부재,
로그의 `Launching browser with command:` 0건, 유일한 기록이 `Connected to existing browser.`
그리고 9222 점유 시점에 미실행. 상세와 앞으로의 파급은 `memo.md`에 기록했다.

**교훈**: 이미 9222 점유를 알고 있었으면서 빈 포트로만 검증하고 "정상"이라 보고했다.
기본값 그대로의 첫 실행을 밟지 않은 검증은 검증이 아니다. `memo.md` 반복 금지 8번에 박았다.

---

### 2026-07-22 (1) — gui_tool 버그 검증과 잔존 프로세스 정리 기능

**요청**: `gui_tool`에 버그가 없는지 검증하고, 직접 실행해 정상 동작까지 확인할 것.
종료 시 좀비 프로세스가 남는지, 재실행 시 관련 프로세스를 찾아 정리하는 기능도 요구했다.

**검증 방법**: 다중 에이전트 감사(64건 제기)와 별개로, 주요 주장을 직접 실행해 실측했다.
Tk 위젯을 프로그램적으로 구동(`invoke()` + `update()` 펌프)해 GUI 전 경로를 밟았다.

**좀비 — 실측 결과**

Job Object는 건전했다. 구조체 크기 64/144바이트로 x64 C 레이아웃과 일치하고,
`SetInformationJobObject` 성공. 정상 중지·창 닫기·**작업 관리자 강제 종료**·오류 경로 모두에서
Chrome 9개 프로세스가 하나도 남지 않았다. 한때 좀비로 보인 2개는 사용자 Chrome의 렌더러였다(오탐).

**그러나 `ssh.exe`는 Job에 없었다.** 앱을 강제 종료하니 Chrome은 죽고 ssh만 살아남아 원격
포워드를 계속 열어 두었다. 재현하고 고쳤다.

**고친 결함 (전부 실측 확인)**

| 결함 | 수정 |
|:--|:--|
| ssh.exe 좀비 | ssh도 Job Object 편입 |
| 빈 포트 → `backend_port: 0` 저장 후 재기동 불가(`SystemExit(1)`) | 0을 "미설정"으로 왕복 처리, bool/실수 포트 거부 |
| 포트 충돌 시 20초 행 + 오진 메시지 | 실행 전 포트 확인, 즉시 실패 |
| Chrome이 `[::1]`에 바인딩 | 두 loopback 주소 모두 프로브, `Browser` 키로 판별 |
| 프로필 핸드오프 시 20초 행 | Chrome 즉시 종료 감지 |
| `_drain_events` 펌프 영구 정지 | 재예약을 `finally`로 이동 |
| 종료 시 `invalid command name` | `after_cancel` 후 destroy |
| `close()`가 UI 스레드 블로킹 | 백그라운드 정리 + 5초 상한 폴링 |
| 프록시가 loopback 프로브 가로챔 | `ProxyHandler({})` 직결 |
| 로컬 모드인데 "SSH 종료" 로그 | 모드별 메시지 |

**신규 `cleanup.py`**

실행 중 `%TEMP%\ready-chromedev-session-<포트>.json`에 소유 pid·이미지명·**생성 시각**
(`GetProcessTimes`)을 기록한다. pid는 재사용되므로 pid만으로는 소유 근거가 못 된다.
세션을 만든 GUI가 살아 있으면 건너뛴다(두 번째 창이 첫 번째 창의 Chrome을 죽이지 않도록).
프로세스 트리는 `taskkill /T /F`로 끝낸다 — 이미 실행 중인 프로세스를 새 Job에 넣어도
이미 태어난 자식은 소급 편입되지 않기 때문이다.

시작 시 자동 검사하되 **남은 프로세스가 있을 때만** 묻는다. 폴더만 남으면 로그에만 적는다.

**검증**: 앱 강제 종료로 잔존물을 만든 뒤 정리 기능이 회수하는 것을 확인. 테스트가 쌓아둔
`%TEMP%` 폴더 10개도 일괄 정리. 사용자 Chrome 13개는 무사. 테스트 10 → 27개.

**UI 프레임워크 검토**: PySide6 전환을 물어와 분석했다. 결함 12건 중 Tk가 원인인 것은 이벤트
펌프 2건뿐이고 둘 다 소규모 수정으로 해결됐다. 나머지는 Win32 프로세스 관리와 도메인 로직이라
프레임워크 교체로 해결되지 않는다. Tkinter 유지로 결정했다.

---

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
