# Memo

## 목차

- [제품 기준선](#제품-기준선)
- [핵심: AI를 브라우저에 붙이는 4가지 방법](#핵심-ai를-브라우저에-붙이는-4가지-방법)
- [이 머신의 실제 상태](#이-머신의-실제-상태)
- [chrome-devtools 설치·등록](#chrome-devtools-설치등록)
- [MCP 개념 정리](#mcp-개념-정리)
- [기본 설정값](#기본-설정값)
- [실측으로 확인한 사실](#실측으로-확인한-사실)
- [반복 금지](#반복-금지)

## 제품 기준선

| 항목 | 값 | 확인 방법 |
|:--|:--|:--|
| OS | Windows 11 Home 26200 | — |
| Node.js | v24.18.0 (nvm-windows, `C:\nvm4w\nodejs`) | `node -v` |
| Chrome | 150.0.7871.115 | `(Get-Item chrome.exe).VersionInfo` |
| Claude Code | 2.1.193 | `claude --version` |
| chrome-devtools-mcp | 1.5.0, 도구 29개 | `tools/list` 직접 호출 |
| MCP protocol | `2025-06-18` (서버 최신 지원 `2025-11-25`) | `initialize` 응답 |
| Python | **미설치** | 데모 서버를 node 로 짠 이유 |

---

## 핵심: AI를 브라우저에 붙이는 4가지 방법

**이것이 이 저장소의 가장 중요한 내용이다.** 방법마다 "누구의 브라우저를 보느냐"가 다르다.
목적을 정하지 않고 도구부터 고르면 반드시 헤맨다. (실제로 헤맸다 — `dev_log.md` 참조)

### A. CDP 외부 프로세스 — `chrome-devtools-mcp` (Google)

외부 프로세스가 Chrome DevTools Protocol 로 브라우저를 **바깥에서 조종**한다.

- **기본 동작**: 설치된 Chrome 을 **별도 프로필**로 새로 띄운다. 내 로그인 세션이 아니다.
- **내 창에 붙기**: `--browserUrl http://127.0.0.1:9222` — 단, Chrome 을 `--remote-debugging-port` +
  **비기본 `--user-data-dir`** 로 미리 띄워야 한다.
- **Chrome 136+ 제약**: 기본 프로필에서는 `--remote-debugging-port` 가 **조용히 무시된다.**
  그래서 "내가 매일 쓰는 그 창"은 이 방법으로 절대 못 붙는다.
- **강점**: 성능 트레이스, Core Web Vitals(LCP/CLS/INP), Lighthouse, 소스맵 붙은 스택,
  네트워크 요청/응답 본문, 힙 스냅샷, CPU/네트워크 스로틀링. **진단이 압도적.**
- **약점**: Chrome 전용. 내 세션이 아님. 포트를 열면 로컬 아무 프로세스나 붙을 수 있음.
- 실측: 이 저장소의 `demo/tools/*.mjs` 전부 이 방식.

### B. 확장 브리지 (MCP) — Playwright MCP `--extension`, mcp-chrome

브라우저 **안에 확장**이 앉아 통로가 되고, MCP 서버(외부 프로세스)가 그 확장을 통해 붙는다.
**디버깅 포트를 열지 않는다. 내 로그인 세션 그대로.**

| 도구 | 버전 (2026-07-09) | 상태 |
|:--|:--|:--|
| `@playwright/mcp` (Microsoft) | 0.0.77 (2026-07-08 갱신) | 활발 |
| `mcp-chrome-bridge` (hangwin) | 1.0.31 (2025-12-30) | 정체 |
| `@browsermcp/mcp` | 0.1.3 (2025-12-18) | 사실상 대체됨 |

- Playwright 확장: **Playwright Extension**, ID `mmlmfjhmonkocbjadbfplnigmagldckm`
  (Microsoft 저장소 `packages/extension` 이 직접 링크. Chrome Web Store.)
- 플래그 실측: `--extension  Connect to a running browser instance ... requires "Playwright Extension" to be installed.` (Edge/Chrome only)
- **강점**: 진짜 로그인 브라우저. 조작(클릭·입력·흐름)이 안정적. a11y 스냅샷 기반.
- **약점**: 성능 트레이스/Lighthouse/CDP 심층 진단 **없음.**
- 업계 요약: **Playwright 는 브라우저를 몰고, DevTools 는 브라우저를 진단한다.**
- **미검증**: 실제로 붙여보지 않았다. 확장 설치가 필요하고 사용자 동의가 있어야 한다.

### C. 1차 통합 (MCP 아님) — Claude Code `--chrome`

**MCP 서버가 아니다.** Anthropic 이 만든 Claude Code 전용 Chrome 확장 + 네이티브 메시징 브리지.
구조상 언리얼 플러그인과 가장 가깝다 — 브라우저 안에 앉아 있고, 확장이 `claude.exe` 를 직접 띄운다.

```
확장 (fcoeoabgfenejglbffodgkkbkcdhcgfn, 이름 "Claude")
   ↓ Chrome 네이티브 메시징
C:\Users\gbox3\.claude\chrome\chrome-native-host.bat
   ↓
"C:\Users\gbox3\.local\bin\claude.exe" --chrome-native-host
```

- 레지스트리: `HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.anthropic.claude_code_browser_extension`
- CLI 플래그: `claude --chrome` / `--no-chrome` ("Enable Claude in Chrome integration")
- **미검증**: 어떤 도구를 노출하는지 아직 못 봤다. `--chrome` 없이 뜬 세션에서는 확인 불가.

### D. WebMCP — 페이지가 스스로 도구를 노출 (미래)

에이전트가 "어디를 클릭할지 추측"하는 대신, **웹페이지가 자기 기능을 타입 있는 도구로 선언**한다.

- Chrome 146 Canary 에서 최초 프리뷰 (2026-02-10, "WebMCP for testing" 플래그)
- Chrome 149 에서 origin trial (2026년 5월 I/O 에서 발표)
- `chrome-devtools-mcp` 에 이미 훅이 있다: `--categoryExperimentalWebmcp`
  (Chrome 149+ 필요, `--enable-features=WebMCP,DevToolsWebMCPSupport`)
- 우리 Chrome 은 150 → **실험 가능.** 아직 안 해봤다.

### 선택 기준

| 원하는 것 | 답 |
|:--|:--|
| 내가 로그인한 그 창을 같이 보기 | **C** (Claude Code `--chrome`) 또는 **B** (Playwright `--extension`) |
| 성능 저하 원인 진단, LCP/CLS, 트레이스 | **A** (`chrome-devtools-mcp`) |
| 스크립트로 자동화, CI, 재현 가능한 환경 | **A** (`--isolated --headless`) |
| 웹사이트를 에이전트 친화적으로 만들기 | **D** (WebMCP) |

**A 와 B 는 배타적이지 않다.** 둘 다 등록해두고 목적에 따라 고르는 것이 일반적이다.

---

## 이 머신의 실제 상태

2026-07-09 확인.

- Claude 확장 `fcoeoabgfenejglbffodgkkbkcdhcgfn` → **Profile 1 에만 설치됨.** Default 에는 없음.
- 현재 실행 중인 Chrome → **Default 프로필**, `--remote-debugging-port` 없음.
- 현재 Claude Code 세션 → **`--chrome` 없이 시작됨.**
- 등록된 MCP 서버: HuggingFace / Gmail / Google Drive (연결됨), `unreal-mcp` (연결 실패, 127.0.0.1:8000 미기동)
- `chrome-devtools` 는 **등록되어 있지 않다.** 오늘 작업은 전부 서버를 직접 spawn 해서 했다.

> 참고: `unreal-mcp` 가 `http://127.0.0.1:8000/mcp` (HTTP transport) 로 등록된 것이,
> "플러그인이 엔진 안에서 서버를 연다"는 구조의 실례다. 브라우저 쪽 등가물이 B/C 다.

---

## MCP 개념 정리

### 무엇인가

M개의 모델 × N개의 도구를 잇는 데 M×N개의 어댑터가 필요하던 것을, 공통 문법 하나로 **M+N** 으로 만든다.

- 2024-11-25 Anthropic 이 오픈소스로 공개
- **2025-12-09 Linux Foundation 산하 Agentic AI Foundation 에 기증.**
  창립 Platinum: AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft, OpenAI
- 즉 지금 MCP 는 Anthropic 소유가 아니다.

### 구조

- **Host** (Claude Code) 안에 **Client** 가 있고, 각 Client 가 하나의 **Server** 에 붙는다.
- 전송: **stdio** (자식 프로세스, 줄 단위 JSON) 또는 **Streamable HTTP**
- 메시지: **JSON-RPC 2.0** — `id` 있으면 요청, 없으면 알림(notification)
- 서버가 제공: `tools` / `resources` / `prompts`
- 클라이언트가 제공: `sampling` / `roots` / `elicitation`

### 핸드셰이크 (직접 쳐볼 것: `demo/tools/mcp-handshake.mjs`)

```
1) → initialize            {protocolVersion, capabilities, clientInfo}
   ← {protocolVersion, capabilities, serverInfo}
2) → notifications/initialized     (id 없음, 응답 없음)
3) → tools/list
   ← {tools: [...29개...]}
4) → tools/call {name, arguments}
```

### 버전 협상 — 실측 (`demo/tools/probe-protocol.mjs`)

| 클라이언트가 말한 버전 | 서버 응답 |
|:--|:--|
| `2025-06-18` | `2025-06-18` 그대로 수용 |
| `2024-11-05` | **`2024-11-05`** — 구버전으로 내려와서 답함 |
| `2099-01-01` | `2025-11-25` — 자기가 아는 버전 제시 |
| `banana` | `2025-11-25` — **에러조차 없음** |

에러는 한 번도 없었다. **단, 명세상 서버 버전을 못 받아들이면 연결을 끊는 쪽은 클라이언트다.**
맞춰주는 쪽(서버)과 떠나는 쪽(클라이언트)의 비대칭이 있다.

### 등록 스코프

```powershell
claude mcp add <name> -s project -- npx <pkg> <args>   # .mcp.json (프로젝트 공유)
claude mcp add <name> -s local   -- ...                # 이 프로젝트, 나만
claude mcp add <name> -s user    -- ...                # 모든 프로젝트 (주의)
```

우선순위: local → project → user → plugin.
**MCP 서버는 세션 시작 시점에 로드된다.** 등록해도 실행 중인 세션에는 반영되지 않는다.

---

## 기본 설정값

`chrome-devtools-mcp` 에서 **기본값이 위험한 것들** (`--help` 실측):

| 플래그 | 기본값 | 의미 |
|:--|:--|:--|
| `--redactNetworkHeaders` | `false` | 쿠키·인증 헤더가 그대로 클라이언트로 간다 |
| `--usageStatistics` | `true` | 사용 통계가 Google 로 전송 |
| `--performanceCrux` | `true` | 성능 트레이스의 **URL** 이 Google CrUX API 로 전송 |
| `--isolated` | `false` | 임시 프로필을 쓰지 않는다 |

유용한 것:

- `--slim` : 도구 3개만 (navigate / evaluate / screenshot). 컨텍스트 절약.
- `--allowedUrlPattern` : 허용 목록. Chrome 149+ 필요. 차단 목록보다 강하다.
- `--screenshotFormat jpeg|webp` : PNG 대비 3~5배 작음.
- `--executablePath` : 설치된 Chrome 지정. 엉터리 경로를 주면 즉시 실패한다(= 플래그가 실제로 존중됨).

---

## 실측으로 확인한 사실

모두 `demo/tools/` 로 재현 가능. 서버(`node demo/server.mjs`)를 먼저 띄울 것.

| 사실 | 스크립트 |
|:--|:--|
| 도구 29개, protocol `2025-06-18` | `mcp-handshake.mjs` |
| 버전 협상은 에러 없이 맞춰준다 | `probe-protocol.mjs` |
| 투명 오버레이가 6개 뷰포트에서 버튼을 덮음 (여유 31px) | `verify-overlay.mjs` |
| Tab 키로 결제 버튼 도달 불가 (card→owner→BODY) | `verify-a11y.mjs` |
| 스택 `app.js:20:57` + 응답 본문 `receiptId` | `verify-stack.mjs` |
| LCP 946ms → 43,354ms (Slow 3G + CPU 4x) = **46배** | `verify-perf.mjs` |
| `--browserUrl` 로 붙으면 UA 에 `HeadlessChrome` 없음 = 실제 창 | `probe-attach.mjs` |

추가:

- `chrome-devtools-mcp` 는 **Chrome for Testing 을 내려받지 않는다.** 설치된 Chrome 사용.
  npx 캐시 총 36MB, `chrome.exe` 없음, `~/.cache/puppeteer` 생성 안 됨.
- `take_snapshot` 설명 원문: *"based on the a11y tree ... Prefer taking a snapshot over taking a screenshot."*
  이유는 도덕이 아니라 공학이다 — 의미론적이고, 안정적이고, 토큰이 적게 든다.
  Playwright MCP 도 같은 이유로 a11y 스냅샷을 쓴다.

---

## 반복 금지

**1. 목적을 확정하기 전에 아키텍처를 고르지 말 것.**
"내 로그인 브라우저를 같이 보고 싶다"와 "AI가 자기 브라우저를 띄워 진단하게 하고 싶다"는
완전히 다른 요구다. 이걸 안 묻고 A(CDP)를 밀어붙여서 하루를 썼다.

**2. "MCP 서버가 뜬다" ≠ "AI가 도구로 쓸 수 있다".**
서버는 `npx` 로 언제든 뜬다. 하지만 등록 + 세션 재시작이 없으면 도구 목록에 없다.
오늘 작업은 전부 서버를 직접 spawn 해서 JSON-RPC 를 손으로 주고받은 것이다.

**3. `-s user` 스코프는 모든 프로젝트에 상속된다.**
"MCP 없는 상태"를 재현해야 하는 실험에서, user scope 등록이 있으면 조용히 오염된다.

**4. Chrome 136+ 는 기본 프로필의 원격 디버깅을 조용히 무시한다.**
에러도 안 낸다. 포트가 안 열릴 뿐이다. 반드시 비기본 `--user-data-dir` 를 줄 것.

**5. `.ps1` 은 UTF-8 **with BOM** 으로 저장할 것.**
BOM 이 없으면 Windows PowerShell 5.1 이 한글을 코드페이지로 읽어 파서가 죽는다.
더 나쁜 것: 검사 항목이 실패했는데도 스크립트가 **"모두 통과"** 를 찍었다. 거짓 통과.

**6. 비치환 인라인 요소에는 `width`/`height` 가 적용되지 않는다.**
`<span class="bar-fill">` 에 `display:block` 이 없어 막대그래프가 통째로 렌더링되지 않았다.
CSS 도 HTML 도 문법적으로 완벽했다. **렌더링해야만 보인다.**

**7. "눈먼 AI 는 버그를 못 고친다"는 거짓이다.**
파일 읽기 + Bash 만 가진 에이전트에게 시켰더니, 헤드리스 Chrome 을 띄우고 CDP 드라이버를
직접 작성해 히트 테스트를 하고 고쳤다 (도구 호출 16회, 자체 확신도 99%).
참인 명제는 **"지각 없이는 확신할 수 없고, 없으면 스스로 만들어낸다"** 이다.

**8. `reqid` / `msgid` 는 실행마다 달라진다.** 문서나 슬라이드에 숫자를 박지 말 것.

**9. 이 머신에 Python 이 없다.** `python -m http.server` 금지. node 로 서빙한다.

**10. 렌더링 결과를 보지 않고 프런트엔드 작업을 끝내지 말 것.**
이 저장소에서 실제로 세 번 물렸다 (거짓 통과, 빈 막대, 어긋난 트랙 기준선).
