# Dev Log

## 목차

- [Entries](#entries)

## Entries

### 2026-07-09 — `_forAI` 문서 세트 생성

`README.md`, `inventory.md`, `memo.md`, `plan.md`, `dev_log.md` 신규 생성.
사용자 요청: "지금까지 알아본 방법론들을 정리하고, MCP 개념을 익히며 실험해보고 싶다."

### 2026-07-09 — Chrome MCP 조사·실험 (첫날)

**요청**: Chrome MCP 특강 준비 (Windows 11, 설치 → 개발 응용). 주제는 "AI와 인간의 소통·공감".

**실제로 한 일과 결과**

- `chrome-devtools-mcp@1.5.0` 을 직접 spawn 해 JSON-RPC 로 대화. 도구 29개, protocol `2025-06-18` 확인.
- 버전 협상 실측: 서버가 구버전으로 내려와서 답하고, 엉터리 버전에도 에러를 내지 않는다.
- 데모 웹앱 제작: **렌더링해야만 존재하는 버그** (투명 `.ribbon` 오버레이가 클릭을 삼킴).
  6개 뷰포트에서 31px 여유로 결정적 재현.
- `emulate` 실측: LCP 946ms → 43,354ms (Slow 3G + CPU 4x). 46배.
- `--browserUrl` attach 실측: UA 에 `HeadlessChrome` 없음 = 사람이 보는 실제 창.
- Chrome for Testing 다운로드 없음 확인 (npx 캐시 36MB).

**되돌아본 실패**

1. **아키텍처를 잘못 골랐다.** 사용자는 "내 로그인 브라우저를 같이 보는" 구조(언리얼 플러그인처럼)를
   원했는데, 나는 "AI가 자기 브라우저를 띄워 진단하는" CDP 방식만 밀었다.
   **"누구의 브라우저를 보느냐"를 처음에 묻지 않았다.**
   나중에 이 머신에 이미 Claude Code Chrome 확장(`--chrome`)이 깔려 있다는 것을 발견했다.

2. **주제를 과잉 해석했다.** 사용자가 말한 "공감"은 *소통의 대역폭을 극한까지 끌어올린다* 는
   공학적 개념이었는데, 접근성/장애인 서사와 인문학 인용(Stein, Turkle, Bender, Dennett)으로 끌고 가
   "심파조"가 되었다. 사용자 지적: *"공학의 탈을 쓴 정치쇼"*.
   → `take_snapshot` 이 a11y 트리를 쓰는 이유는 도덕이 아니라 공학이다 (의미론적·안정적·저토큰).
   Playwright MCP 도 같은 이유로 같은 것을 쓴다.

3. **분량을 잘못 잡았다.** 150분 워크숍으로 만들었으나 실제로는 **20분** 강의가 맞았다.

4. **눈먼 AI 실험이 전제를 반증했다.** 파일 읽기 + Bash 만 가진 에이전트가 헤드리스 Chrome 을 띄우고
   CDP 드라이버를 직접 작성해 버그를 찾아 고쳤다 (도구 호출 16회, 확신도 99%).
   → "눈먼 AI 는 못 고친다"는 거짓. 참인 명제는 "지각 없이는 확신할 수 없고, 없으면 스스로 만들어낸다".

**만들면서 잡은 실제 버그 3개** (전부 렌더링/실행해야만 보이는 것들)

- `preflight.ps1` 이 BOM 없이 저장되어 PowerShell 5.1 에서 한글이 깨지고 파서가 죽었는데도
  **"모두 통과"** 를 출력했다. 거짓 통과. → BOM 추가 + 종료코드 수정.
- 슬라이드의 46배 막대그래프가 통째로 렌더링되지 않았다.
  `<span class="bar-fill">` 에 `display:block` 이 없어서 (비치환 인라인 요소는 width 무시).
- 같은 슬라이드에서 두 막대의 트랙 길이가 서로 달랐다. 길이 비교 그래프의 기준선 어긋남.

**산출물**

- `demo/` (데모 웹앱 + 검증 스크립트 7종)
- `scripts/preflight.ps1`, `scripts/check-browser.mjs`
- `docs/lecture-plan.md` (150분판 — 과잉, 20분판으로 재작성 필요)
- `slides/` (19장, Artifact 배포: `https://claude.ai/code/artifact/7449c14c-556a-406a-9316-cf89f626d525`)

**미검증으로 남긴 것**

- Claude Code `--chrome` 통합이 노출하는 도구 (실험 1)
- Playwright MCP `--extension` 실제 동작 (실험 2)
- `--autoConnect` 로 기본 프로필 접속 가능 여부 (실험 3)
- WebMCP (실험 5)
- `unreal-mcp` 는 `127.0.0.1:8000` 미기동으로 연결 실패 상태
