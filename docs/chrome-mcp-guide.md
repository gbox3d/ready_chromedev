# Chrome + AI 협업 입문 — Playwright 없이, 순정 크롬으로

> **대상**: 웹 기초가 있는 개발자 · 학생
> **환경**: Windows 11 · VS Code + Claude Code 확장 · Chrome
> **한 줄로**: 코딩 에이전트는 지금까지 *눈을 가린 채* 웹 코드를 짜 왔다. 이 문서는 에이전트에게 눈을 달아주는 가장 순정에 가까운 방법을 다룬다. 그 다음부터는 전부 측정이다.

---

## 목차

- [0. 이 문서가 답하는 질문](#0-이-문서가-답하는-질문)
- [1. 큰 그림 — MCP, CDP, 그리고 그 토글](#1-큰-그림--mcp-cdp-그리고-그-토글)
- [2. "순정의 느낌"은 두 단계다](#2-순정의-느낌은-두-단계다)
- [3. VS Code 셋업 — 단계별](#3-vs-code-셋업--단계별)
- [4. 첫 실습 — 도구 여섯 개를 손에 익힌다](#4-첫-실습--도구-여섯-개를-손에-익힌다)
- [5. 내 크롬에 붙기 — 정문으로 (autoConnect)](#5-내-크롬에-붙기--정문으로-autoconnect)
- [6. 안전 수칙과 데모 전 체크리스트](#6-안전-수칙과-데모-전-체크리스트)
- [부록. 이 문서의 사실은 어디서 왔는가](#부록-이-문서의-사실은-어디서-왔는가)

---

## 0. 이 문서가 답하는 질문

이 문서는 세 가지 질문에 답한다.

1. **Playwright 말고, 순정 크롬으로 AI와 협업이 되는가?** → 된다.
2. **"순정의 느낌"이 어디까지 가능한가?** → 설치된 진짜 Chrome을 그대로 쓴다. 내가 로그인해 쓰는 창까지 붙일 수 있다.
3. **보안은 어떻게 되는가?** → 민감한 판단은 사람이 승인하고, 편의 기능만 AI에게 맡기는 구조가 프로토콜에 이미 박혀 있다.

핵심 도구는 **`chrome-devtools-mcp`** 다. Google의 Chrome DevTools 팀이 만든 공식 MCP 서버이며, **번들 브라우저를 내려받지 않고 PC에 설치된 진짜 Google Chrome을 사용한다.** 이것이 Playwright와의 가장 큰 차이다 — Playwright는 기본적으로 별도의 오픈소스 Chromium 빌드를 쓴다.

---

## 1. 큰 그림 — MCP, CDP, 그리고 그 토글

셋업에 앞서, 등장인물 셋을 구분한다. 이 셋을 섞으면 반드시 헤맨다.

```
   VS Code (Claude Code)
        │
        │   ← MCP: AI가 "도구"와 대화하는 공통 언어 (JSON-RPC 2.0)
        │
   chrome-devtools-mcp  (도구. npx로 뜨는 작은 서버 프로세스)
        │
        │   ← CDP: 그 도구가 크롬을 들여다보는 배선 (Chrome DevTools Protocol)
        │
     Chrome
```

- **MCP (Model Context Protocol)** 는 *AI와 도구 사이의 언어*다. 크롬과는 직접 관계가 없다. AI가 어떤 도구든 같은 문법으로 부를 수 있게 하는 공통 규약이다.
- **CDP (Chrome DevTools Protocol)** 는 *그 도구가 크롬을 조종·관찰하는 배선*이다. 크롬 개발자 도구(F12)가 내부적으로 쓰는 바로 그 프로토콜이다.
- 즉 `chrome-devtools-mcp`는 **위로는 MCP로 AI와 말하고, 아래로는 CDP로 크롬과 말하는 번역기**다.

### 그렇다면 `chrome://inspect`의 "리모트 디버깅" 토글은 왜 켜는가

이 토글은 MCP와 **직접** 상관이 없다. 이 토글이 결정하는 것은 딱 하나다:

> **"그 CDP 배선을, *내가 매일 쓰는* 크롬에 꽂아도 되는가?"**

- 토글을 켜지 **않아도** MCP는 잘 동작한다. 대신 도구가 **자기용 크롬 창을 새로 띄운다** (설치된 진짜 크롬이지만, 내 로그인이 없는 별도 창 — [2장](#2-순정의-느낌은-두-단계다) 참조).
- 토글을 **켜면**, "내가 지금 로그인해 쓰고 있는 그 창"에도 붙을 수 있게 된다. 단, 켜 두었다고 아무 일도 일어나지 않는다. 어떤 도구가 연결을 **시도하는 순간마다** 크롬이 허용/거부 다이얼로그를 띄우고, **사람이 허용해야만** 붙는다.

즉 토글은 "나중에 쓸 문을 열어 두는 것"이고, 그 문은 지날 때마다 사람이 승인해야 한다. 이 구조가 이 문서 전체의 보안 철학이다 — **민감한 결정은 사람, 편의는 AI.**

---

## 2. "순정의 느낌"은 두 단계다

`chrome-devtools-mcp`는 두 가지 모드로 동작한다. "얼마나 내 것인가"가 다르다.

| 모드 | 무엇을 하나 | 순정도 | 언제 |
|:--|:--|:--|:--|
| **기본** (플래그 없음) | 설치된 크롬을 **새 창**으로 띄운다 | 진짜 Chrome, 하지만 내 세션은 아님 | 처음 배울 때, 안전한 실험 |
| **`--autoConnect`** | **지금 쓰는 그 창**에 붙는다 (로그인·확장 그대로) | 완전한 내 크롬 | 내 로그인 상태로 작업할 때 ([5장](#5-내-크롬에-붙기--정문으로-autoconnect)) |

### 기본 모드의 프로필을 정확히 이해하기

기본 모드가 띄우는 창은 "깨끗한 임시 창"이 **아니다.** 정확히는 **"별도이지만 지속되는(persistent) 프로필"** 이다.

- **별도**: 내 평소 크롬 프로필이 아니라 전용 폴더에 만들어진다.
  경로 — `%HOMEPATH%\.cache\chrome-devtools-mcp\chrome-profile` (Windows, stable 채널).
- **지속**: 이 프로필은 **실행이 끝나도 지워지지 않고**, `chrome-devtools-mcp`의 **모든 인스턴스가 공유**한다. 한번 어떤 사이트에 로그인하면 다음 실행에도 그 로그인이 남는다.
- **매번 깨끗한 임시 프로필**을 원하면 `--isolated` 플래그를 켜야 한다. 이때만 브라우저 종료 시 프로필이 자동 삭제된다.

> 강의에서 "깨끗한 프로필"이라고 말하지 말 것. 학생이 "매번 초기화된다"고 오해한다. "별도지만 남아 있다, 정말 매번 새것을 원하면 `--isolated`"가 정확하다.

### 순정임을 눈으로 확인하는 신호

기본 모드로 크롬이 뜨면 상단에 이런 배너가 보인다:

> **"자동화된 테스트 소프트웨어에 의해 Chrome이 제어되고 있습니다."**
> (영문: *"Chrome is being controlled by automated test software"*)

이 배너는 **화면에 보이는 창(headful)일 때만** 뜬다. 이것은 두 가지를 동시에 말해준다 — (1) 진짜 크롬이 맞다, (2) 지금 자동화가 제어 중이다. 숨기려 하지 말 것. 이 배너가 곧 정직함이다.

---

## 3. VS Code 셋업 — 단계별

> 아래는 **CLI가 아니라 VS Code의 Claude Code 확장**을 기준으로 한다.

### 0단계 — 준비물 (설치할 것 없음)

이미 갖춰져 있다: Node.js, Chrome, VS Code의 Claude Code 확장. `chrome-devtools-mcp`는 별도 설치가 필요 없다 — `npx`가 필요할 때 자동으로 받아 실행한다.

### 1단계 — 프로젝트에 설정 파일 하나

프로젝트 루트에 **`.mcp.json`** 파일을 만든다. MCP 서버 등록은 이 파일 하나가 전부다.

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

읽는 법: *"chrome-devtools라는 이름의 서버를, `cmd /c npx -y chrome-devtools-mcp@latest` 명령으로 띄워라."* 그게 등록의 전부다.

세 가지 참고:
- **`.mcp.json`은 "project scope"** 다. 프로젝트 루트에 두며, 버전 관리에 커밋해 팀과 공유하도록 설계된 파일이다.
- **Windows에서는 `npx`를 `cmd /c`로 감싸야 한다.** Claude Code는 MCP stdio 서버를 **셸 없이** `spawn()` 한다. 그런데 Windows의 `CreateProcess`는 `PATHEXT`를 대신 붙여 주지 않으므로, PATH에 `npx.cmd`가 멀쩡히 있어도 `spawn("npx")`는 실행 대상을 찾지 못하고 `spawn npx ENOENT`로 죽는다. macOS·Linux라면 `"command": "npx"`로 충분하다. → [부록](#부록-이-문서의-사실은-어디서-왔는가)에 대조 실험 결과.

  > **여기서 거의 모두가 한 번은 속는다.** 터미널에서 `npx chrome-devtools-mcp@latest --version`이 잘 돈다고 안심하지 말 것. 터미널은 **셸**이라 확장자를 대신 풀어 준다. Claude Code의 실행 경로(셸 없는 `spawn`)와 다르다. 셸을 거친 테스트는 셸 없는 실행에 대해 아무것도 증명하지 못한다. 확인하려면 `node scripts/verify-mcp.mjs`처럼 **같은 방식으로 spawn하는** 검사를 써야 한다.
- **`@latest`로 항상 최신을 쓴다.** 새 버전이 나오면 자동으로 따라간다. 대신 재현성이 약해지므로, **데모 전 반드시 `/mcp`에서 도구 목록을 확인**한다 — 아래 [4장](#4-첫-실습--도구-여섯-개를-손에-익힌다)의 도구 이름·개수, 스냅샷 형식은 이 문서 작성 시점의 최신인 **1.5.0에서 실측**한 것이라, 이후 버전에서 세부가 달라질 수 있다. 특정 버전에 고정하고 싶다면 `@latest` 자리에 `@1.5.0`처럼 버전을 박는다.

> ⚠️ **VS Code의 함정**: VS Code에는 `.vscode/mcp.json`이라는 별도 파일도 있는데, 그건 **VS Code 내장 Copilot용**이다. **Claude Code 확장은 그 파일을 읽지 않는다.** 반드시 프로젝트 루트의 `.mcp.json`에 넣어야 한다.

### 2단계 — 승인 (project scope의 보안 관문)

`.mcp.json`으로 등록한 서버는 **첫 사용 전에 승인**을 받아야 한다. 이것은 보안 기능이다 — 아무 프로젝트나 열었다고 그 안의 MCP 서버가 말없이 실행되면 안 되기 때문이다.

승인 전에는 서버가 `⏸ Pending approval` 상태로 표시된다. VS Code에서 폴더를 열고 Claude Code를 시작하면 승인을 묻는다. 승인하면 다음 단계로 넘어간다.

### 3단계 — 세션 재시작 후 확인

여기가 첫 번째 개념 포인트다: **MCP 서버는 세션이 시작될 때 연결된다.** 설정을 고쳤는데 반영이 안 된다면 답은 거의 항상 이것이다 — **`.mcp.json`을 편집한 뒤에는 `/mcp`에서 재연결하거나 세션을 재시작**해야 한다.

새 세션의 채팅 입력창에 **`/mcp`** 를 치면 `chrome-devtools`가 목록에 뜨고, 선택하면 도구 약 26~29개가 보인다. 이 목록이 곧 "AI가 크롬에 대해 할 수 있는 일의 전부"다.

### 4단계 — 첫 실행

채팅에 이렇게 쳐 본다:

> example.com 을 열고 스냅샷을 찍어줘

이때 **크롬 창이 하나 새로 뜬다.** 내 크롬과 같은 바이너리지만 프로필이 다른 창이며([2장](#2-순정의-느낌은-두-단계다)), 상단에 자동화 배너가 보인다.

> `@latest`로 등록했으므로, 첫 실행 전에 `/mcp`에서 `chrome-devtools`를 열어 **실제로 뜬 도구 목록**을 한 번 훑어 둔다. 아래 도구 표는 1.5.0 기준이며, 받은 버전이 다르면 이름이나 개수가 조금 다를 수 있다.

### 흔한 실패 세 가지

| 증상 | 원인 | 해결 |
|:--|:--|:--|
| `/mcp`에 서버가 안 보임 | 설정 후 세션을 재시작 안 함 | 세션 재시작 또는 `/mcp reconnect all` |
| 서버가 `Pending approval` | project scope 승인 안 함 | 2단계 승인 |
| 서버가 `not connected` / `spawn npx ENOENT` | **Windows의 기본 증상.** `command: "npx"`는 셸 없이 실행되지 않는다 | `.mcp.json`을 `cmd /c`로 감싼다 (1단계 참고). `node scripts/verify-mcp.mjs`로 확인 |

---

## 4. 첫 실습 — 도구 여섯 개를 손에 익힌다

`chrome-devtools-mcp` 1.5.0에는 도구가 많지만, 처음에는 여섯 개면 충분하다.

| # | 도구 | 하는 일 | 필수 인자 |
|:--|:--|:--|:--|
| 1 | `navigate_page` | URL로 이동 (뒤로/앞으로/새로고침도) | 없음 |
| 2 | `take_snapshot` | 페이지를 **텍스트**로 떠서 각 요소에 `uid` 부여 | 없음 |
| 3 | `click` | `uid`로 지목한 요소를 클릭 | **`uid`** |
| 4 | `list_console_messages` | 콘솔 메시지 목록 | 없음 |
| 5 | `list_network_requests` | 네트워크 요청 목록 | 없음 |
| 6 | `evaluate_script` | 페이지 안에서 JS 함수 실행 (반환값은 JSON) | **`function`** |

> 참고: 위 여섯 중 **필수 인자가 있는 것은 `click`(uid)과 `evaluate_script`(function) 둘뿐**이다. `navigate_page`의 url조차 선택 인자다. "url이 필수 아니냐"는 흔한 오해다.

### 핵심 도구 `take_snapshot` — AI는 픽셀이 아니라 구조를 본다

`take_snapshot`은 스크린샷이 아니라 **접근성 트리(a11y tree)를 텍스트로** 뜬다. `example.com`에서 실제로 돌린 출력이다:

```
## Latest page snapshot
uid=1_0 RootWebArea "Example Domain" url="https://example.com/"
  uid=1_1 heading "Example Domain" level="1"
  uid=1_2 StaticText "This domain is for use in documentation examples..."
  uid=1_3 link "Learn more" url="https://iana.org/domains/example"
    uid=1_4 StaticText "Learn more"
```

읽는 법:
- 각 줄은 `uid=<id> <역할> "<이름>" <속성...>` 형식이다.
- **`uid`는 정수가 아니라 `스냅샷번호_일련번호` 문자열**이다 (`1_0`, `1_3` …). 스냅샷을 다시 찍으면 앞 번호가 올라가(`2_0` …) **모든 uid가 새로 매겨진다.** 그래서 **항상 방금 찍은 최신 스냅샷의 uid만 써야 한다.**
- 들여쓰기는 DOM 계층이다.

도구 설명 원문이 직접 권한다: *"Prefer taking a snapshot over taking a screenshot."* 이유는 도덕이 아니라 공학이다 — 텍스트라서 (1) 토큰이 훨씬 적게 들고, (2) 각 요소에 `uid`라는 **클릭 가능한 손잡이**가 붙는다. 스크린샷은 이미지라 좌표를 추측해야 하지만, 스냅샷은 "`uid=1_3`을 클릭"이라고 정확히 지목할 수 있다.

### `uid` → `click` 흐름

```
1) take_snapshot 호출
   → 응답에서 대상 줄을 찾는다:  uid=1_3 link "Learn more"
2) click 호출  { "uid": "1_3" }
   → "Successfully clicked on the element"
3) 클릭 후 상태를 보려면 take_snapshot을 다시 찍는다 (uid는 새로 갱신됨)
```

이것이 에이전트가 "픽셀을 보고 추측"하는 게 아니라 **구조 위에서 정확히 행동(grounding)** 하는 방식이다.

### 따라 칠 프롬프트 여섯 개

1. `example.com 으로 이동해줘.` → `navigate_page`
2. `지금 페이지의 스냅샷을 찍어줘.` → `take_snapshot` (출력에서 uid 관찰)
3. `방금 스냅샷에서 "Learn more" 링크를 클릭해줘.` → `click`
4. `이 페이지의 콘솔 메시지를 전부 보여줘.` → `list_console_messages`
5. `이 페이지가 보낸 네트워크 요청 목록을 보여줘.` → `list_network_requests`
6. `() => document.title 을 실행해서 페이지 제목을 반환해줘.` → `evaluate_script`

---

## 5. 내 크롬에 붙기 — 정문으로 (autoConnect)

여기서 [1장](#1-큰-그림--mcp-cdp-그리고-그-토글)에서 켠 리모트 디버깅 토글이 쓰인다. 새 창을 띄우는 대신, **지금 로그인해 쓰는 실제 크롬에 붙는다.**

이것은 "보안을 뚫는 것"이 아니다. **Google이 만든 정문(正門)** 이며, 문을 지날 때마다 사람이 승인한다.

### 요구 조건

- **Chrome 144 이상.** (`chrome://version`으로 확인. 144 미만이면 이 방식이 안 된다.)
- **`chrome-devtools-mcp` 0.12.0 이상** (이 문서는 1.5.0 기준이라 충족).

### 단계

1. 실행 중인 크롬에서 `chrome://inspect/#remote-debugging`으로 이동해 **원격 디버깅을 켠다.**
2. `.mcp.json`의 args 맨 뒤에 **`"--autoConnect"`** 를 추가하고 세션을 재시작한다.
   ```json
   "args": ["/c", "npx", "-y", "chrome-devtools-mcp@latest", "--autoConnect"]
   ```
3. 에이전트가 연결을 시도하면, **크롬이 권한 다이얼로그를 띄운다** (제목: *"Allow remote debugging?"*). **`Allow`를 눌러야** 연결된다.
4. 연결되면 크롬 상단에 자동화 배너가 계속 표시된다.

> **다이얼로그는 매 연결 요청마다 뜬다.** (공식 블로그 명시.) 세션당 1회로 줄여 달라는 요청이 있으나 현재는 매번이다. 번거로움이 아니라 설계다 — 사람의 승인이 매번 개입한다는 뜻이다.

### 무엇이 AI에게 노출되는가 (반드시 이해하고 켤 것)

공식 문서의 보안 경고 원문:

> *"auto-connect가 활성인 동안, 에이전트는 당신의 브라우저 프로필의 모든 데이터 — 열린 탭, 세션 스토리지, 로컬 스토리지, 쿠키, 그리고 JavaScript API로 드러나는 기타 데이터 — 에 접근한다."*
> *"신뢰하는 에이전트에만 이 모드를 사용하라."*

그래서 순서가 중요하다: **민감한 탭을 먼저 닫고**, 그 다음에 원격 디버깅을 켠다. 붙는 순간 열린 탭의 내용이 AI의 컨텍스트로 들어간다.

---

## 6. 안전 수칙과 데모 전 체크리스트

### 안전 수칙 (이 순서가 곧 보안 모델이다)

1. **처음엔 기본 모드**(새 창)로 배운다. `--autoConnect`는 필요할 때만.
2. **`--autoConnect` 전에 민감한 탭을 닫는다.** 붙는 순간 열린 탭이 노출된다.
3. **다이얼로그가 뜨면 = "내 세션을 보겠다"는 뜻**이다. 무심코 Allow 하지 않는다.
4. **매번 깨끗한 환경**이 필요하면 `--isolated`.
5. **민감한 판단은 사람이, 편의는 AI가.** 로그인·결제·전송은 사람이 직접.

> 이 문서는 보안을 **우회하는** 방법(하드닝 우회, 배너 끄기, 프로필 복사 등)을 의도적으로 다루지 않는다. 그런 기법은 교육적이지 않다. 우리가 쓰는 것은 전부 크롬이 열어 둔 정문뿐이다.

### 라이브 데모 전 체크리스트

- [ ] `chrome://version`으로 Chrome이 **144 이상**인지 (autoConnect를 시연할 경우).
- [ ] `.mcp.json`이 프로젝트 루트에 있고, 서버가 승인되어 `/mcp`에 보이는지.
- [ ] 발표 전 `npx -y chrome-devtools-mcp@latest --version`을 한 번 돌려 **npx 캐시를 예열하고 실제로 받은 버전 번호를 확인**. (강의실 와이파이를 믿지 말 것 — `@latest`는 새 버전이 나와 있으면 그 자리에서 새로 받는다.)
- [ ] **`node scripts/verify-mcp.mjs`** 로 핸드셰이크까지 통과하는지 확인. 위의 `--version`은 셸을 거치므로 통과해도 Claude Code에서 붙는다는 보장이 없다. 이 스크립트만이 같은 방식(셸 없는 `spawn`)으로 검사한다.
- [ ] `@latest`라 **버전이 이 문서(1.5.0 실측)와 다를 수 있음**. `/mcp`로 도구 목록·이름을 데모 전 확인.
- [ ] 스냅샷 예제의 `uid`(예: `1_3`)는 **데모마다 값이 달라질 수 있음**. 하드코딩하지 말고 "방금 찍은 스냅샷의 uid"로 지목.
- [ ] autoConnect 다이얼로그·배너의 실제 화면을 미리 캡처. (한국어 문구는 강의 크롬에서 직접 확인.)

---

## 부록. 이 문서의 사실은 어디서 왔는가

이 문서의 사실은 웹 검색 요약이 아니라 **실측 또는 1차 출처**에서 왔다. 미확인 항목은 그렇게 표시했다.

| 사실 | 근거 |
|:--|:--|
| Windows에서 `command: "npx"`는 `spawn npx ENOENT`로 실패하고, `cmd /c` 래핑이 필요하다 | **이 PC 대조 실험** — `scripts/verify-mcp.mjs`. 대조군 `spawn("npx", …)` → `ENOENT`. 처치군 `spawn("cmd", ["/c","npx",…])` → `initialize` 성공, `tools/list` 29개. (초판은 `npx` 직접 연결이 된다고 적었으나, 그 근거였던 터미널 실행은 **셸을 거치는 경로**였다. 셸 없는 `spawn`에 대한 증거가 아니었으므로 정정한다.) |
| `chrome-devtools-mcp` 1.5.0의 도구 개수 = 29 | **이 PC 실측** (`tools/list` 응답) |
| `take_snapshot` 실제 출력 형식 (`uid=1_0 …`) | **이 PC 실측** (example.com 캡처) |
| 기본 프로필은 별도+지속, 공유. `--isolated`가 임시 | [chrome-devtools-mcp README](https://github.com/ChromeDevTools/chrome-devtools-mcp) |
| `.mcp.json` = project scope, 첫 사용 시 승인 필요 | [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp) |
| VS Code 확장은 `.vscode/mcp.json`을 안 읽음 | [code.claude.com/docs/en/vs-code](https://code.claude.com/docs/en/vs-code), [issue #47344](https://github.com/anthropics/claude-code/issues/47344) |
| 자동화 배너 문구·조건 (headful일 때) | [Chrome for Developers 블로그](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session), puppeteer `ChromeLauncher` 소스 |
| autoConnect: Chrome 144+, 다이얼로그 "Allow remote debugging?", 매 요청마다 | [config 문서](https://developer.chrome.com/docs/devtools/agents/get-started/configuration), [auto-connect 유스케이스](https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect) |
| `take_snapshot` 권장 이유, uid→click 흐름 | [tool-reference.md @v1.5.0](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/chrome-devtools-mcp-v1.5.0/docs/tool-reference.md) |

**아직 1차 출처로 확정하지 못한 것 (데모 전 실제 화면으로 확인 권장):**
- `chrome://inspect/#remote-debugging`에서 켜는 토글의 정확한 UI 라벨 문자열.
- autoConnect 권한 다이얼로그의 **본문 전체** 문장 (제목 "Allow remote debugging?"·버튼 "Allow"까지만 확정).
- 자동화 배너의 한국어 정확한 문구.
