# Plan

## 목차

- [Current goal](#current-goal)
- [Near-term work](#near-term-work)
- [실험 목록](#실험-목록)
- [Structure decisions](#structure-decisions)
- [Risks](#risks)

## Current goal

**MCP 개념을 손으로 익히고, 브라우저에 AI를 붙이는 4가지 방법 중 무엇을 쓸지 직접 판단한다.**

특강 자료 제작은 부차적이다. 먼저 도구를 이해하고, 그 다음에 무엇을 가르칠지 정한다.
(순서를 거꾸로 해서 하루를 썼다 — `dev_log.md` 2026-07-09 참조)

## Near-term work

1. **실험 1 을 먼저 한다.** 이교수님이 원한 것("내 로그인 창을 같이 보기")의 답이 거기 있을 가능성이 가장 높다.
2. 실험 1~3 결과가 나오면 `memo.md` 의 "선택 기준" 표를 실측으로 갱신한다.
3. 그 다음에 강의 형식을 정한다. **20분판이 맞다** (현재 `docs/lecture-plan.md` 는 150분, 과잉).
4. 20분판을 쓸 때 철학 섹션·인문학 인용은 넣지 않는다. 주제는 **"소통의 대역폭"** 이지 감정이 아니다.

## 실험 목록

각 실험은 **하나의 질문에 답한다.** 순서대로 하면 다음 실험의 전제가 채워진다.

### 실험 1 — Claude Code `--chrome` 은 무엇을 노출하는가 (최우선)

> 질문: MCP 를 거치지 않는 1차 통합은 어떤 도구를 주는가? 내 로그인 세션을 보는가?

- 준비: Claude 확장(`fcoeoabgfenejglbffodgkkbkcdhcgfn`)이 **Profile 1** 에만 있다.
  Default 에 설치하거나, Profile 1 창을 쓴다.
- 실행: `claude --chrome --continue`
- 확인: 도구 목록에 무엇이 뜨는가. `/mcp` 에 뜨는가, 아니면 내장 도구인가.
- 판단 근거: 이 방법이 충분하면 A(CDP)와 B(Playwright)는 특강에서 뺄 수 있다.

### 실험 2 — Playwright MCP `--extension` 으로 실제 로그인 창에 붙기

> 질문: 확장 브리지 방식이 실제로 동작하는가? 진단 능력은 얼마나 부족한가?

- 준비: Chrome Web Store 에서 **Playwright Extension** (`mmlmfjhmonkocbjadbfplnigmagldckm`) 설치
- 등록: `claude mcp add playwright -s project -- npx @playwright/mcp@0.0.77 --extension`
- 확인: 노출 도구 목록. 성능 트레이스가 정말 없는지. a11y 스냅샷 형식이 `chrome-devtools-mcp` 와 어떻게 다른지.

### 실험 3 — `chrome-devtools-mcp --autoConnect` 가 기본 프로필에 붙는가

> 질문: CDP 방식으로도 내 로그인 창에 붙을 수 있는가? (알려진 이슈 #1830 이 Windows 에서도 재현되는가)

- 준비: Chrome 에서 `chrome://inspect/#remote-debugging` → 원격 디버깅 허용 토글
- 실행: `npx chrome-devtools-mcp@1.5.0 --autoConnect`
- 확인: 첫 연결 시 Chrome 이 허용 다이얼로그를 띄우는가. 붙으면 Default 프로필의 탭이 보이는가.
- 예상: 실패할 수 있다 (Chrome 136+ 하드닝). 실패해도 결과다.

### 실험 4 — MCP 서버를 직접 하나 짠다 (개념 체득용)

> 질문: 서버를 만드는 쪽에서 보면 MCP 는 무엇인가?

- stdio 로 JSON-RPC 2.0 을 읽고 쓰는 30~50줄짜리 Node 서버.
- `initialize` → `notifications/initialized` → `tools/list` → `tools/call` 만 구현.
- 도구는 하나면 된다 (예: `system_info` — 이 머신의 CPU/RAM 을 돌려준다).
- `claude mcp add my-server -s local -- node my-server.mjs` 로 등록해 실제로 부른다.
- **이 실험이 MCP 를 가장 빨리 이해시킨다.** `demo/tools/mcp-handshake.mjs` 가 클라이언트 쪽 예제이니,
  이건 서버 쪽 짝이다.

### 실험 5 — WebMCP (Chrome 150 에서 되는가)

> 질문: 페이지가 스스로 도구를 노출하는 미래는 지금 만져볼 수 있는가?

- Chrome 을 `--enable-features=WebMCP,DevToolsWebMCPSupport` 로 기동
- `npx chrome-devtools-mcp@1.5.0 --categoryExperimentalWebmcp`
- 데모 페이지에 WebMCP 도구를 하나 선언해보고, 에이전트가 그것을 보는지 확인.

### 실험 6 — `unreal-mcp` 를 살려서 비교한다

> 질문: 브라우저 쪽 구조를 언리얼 쪽 구조와 나란히 놓고 보면 무엇이 보이는가?

- 현재 `http://127.0.0.1:8000/mcp` 연결 실패 (서버 미기동).
- 언리얼 플러그인을 띄우고 `tools/list` 를 받아, 브라우저 MCP 의 도구 목록과 대조한다.
- HTTP transport vs stdio transport 의 실제 차이를 본다.

## Structure decisions

- **`ready_chromedev` 는 아직 git 저장소가 아니다.** 실험이 안정되면 `git init` 을 고려한다.
  (사용자 동의 없이 하지 않는다.)
- 검증 스크립트는 `demo/tools/` 에 둔다. 전부 "서버를 spawn 해서 JSON-RPC 로 대화"라는 같은 패턴이다.
- 슬라이드는 `index.html`(Artifact 소스) / `present.html`(생성물, git 제외) 로 분리한다.
- **강의안은 갈아엎지 말고 `docs/lecture-20min.md` 를 따로 만든다.**
  150분판의 측정값·데모·검증 스크립트는 그대로 재사용된다.

## Risks

- **로그인 세션 노출.** B/C 방식은 실제 로그인 브라우저를 본다. 붙는 순간 쿠키·인증 헤더·열린 탭 내용이
  에이전트 컨텍스트로 들어간다. `--redactNetworkHeaders` 기본값은 `false` 다.
  실험 전에 민감한 탭을 닫는다.
- **프롬프트 인젝션.** 에이전트가 읽는 페이지가 에이전트에게 명령할 수 있다. 실증 사례 다수(Brave/Comet 2025-08).
  OpenAI 는 *"unlikely to ever be fully solved"* 라고 했다. Anthropic 실측: 완화 전 23.6% → 후 11.2%.
- **확장 권한 고지 부재.** Playwright Extension 문서에 권한/보안 고지가 없다. Microsoft 저장소 기준.
- **`--remote-debugging-port` 를 열면** 로컬의 아무 프로세스나 브라우저를 조종할 수 있다 (README 명시).
- **실험 3 은 실패 가능성이 높다** (Chrome 136+ 하드닝). 실패를 결과로 기록할 것.
- **미검증 항목을 검증된 것처럼 쓰지 말 것.** `memo.md` 에서 B, C, D 는 전부 "미검증" 이다.
