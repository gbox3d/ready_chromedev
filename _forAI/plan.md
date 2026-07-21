# Plan

## 목차

- [Current goal](#current-goal)
- [Near-term work](#near-term-work)
- [미결 항목](#미결-항목)
- [Structure decisions](#structure-decisions)
- [Risks](#risks)

## Current goal

**`chrome-devtools-mcp` 등록·확인법과 원격 서버에서 이 PC의 Chrome DevTools로 연결하는
독립 Python SSH 역터널 GUI를 재현 가능하게 제공한다.**

강의안·방법론 비교는 범위가 아니다. 실행 코드는 `tunnel_gui/`의 Python·Tkinter 앱과 정적 데모로 제한한다.

## Near-term work

1. 실제 원격 서버에서 GUI 터널을 시작하고 `curl http://127.0.0.1:9222/json/version` 응답을 확인한다.
   공개키 SSH 인증 자체는 2026-07-20에 확인했지만, 실제 reverse forward 응답은 아직 미검증이다.
2. macOS·Ubuntu의 MCP 등록 문서는 환경이 준비되면 별도로 확인한다.

## 미결 항목

- **`/mcp reconnect all` 이 실패한 서버를 세션 재시작 없이 되살리는가.** 미검증.
  `/mcp` 출력이 그렇게 권하지만 실제로 확인하지 않았다. `readme.md` 는 이 방법을 싣지 않았다.
- **설정 파일을 세션 도중에 고쳤을 때 자동 반영되는가.** 미검증.
  2026-07-09 관측은 전부 "재시작 후 붙었다" 로 설명된다. 자동 감지의 증거는 없다.
  가르는 실험: `/mcp` 를 건드리지 않고 서버를 하나 더 등록한 뒤 도구가 저절로 나타나는지 본다.

## Structure decisions

- **Claude Code는 `.mcp.json` (project scope) 하나만 사용한다.** `-s user`와 `-s local` 등록은
  2026-07-09 제거했다. user scope는 모든 프로젝트를 오염시킨다.
- **Codex는 사용자 전역 MCP 등록을 사용한다.** VS Code에서 상위 폴더를 작업 루트로 열어도
  Chrome DevTools MCP를 쓰기 위한 2026-07-14 결정이다. 프로젝트 `.codex/config.toml`은
  저장소 루트 사용을 위한 예시로 유지한다.
- **`.claude/` 는 커밋하지 않는다.** 승인 기록이며, 커밋하면 클론한 사람의 승인 관문이 사라진다.
- `tunnel_gui/`는 독립 uv 프로젝트이며 PyYAML 6.0.3만 외부 Python 의존성으로 사용한다.
- SSH 연결·Chrome 실행·프로파일 저장·GUI는 모두 Python으로 처리한다. PowerShell 스크립트는 없다.
- 앱이 소유한 Chrome만 Windows Job Object로 종료하고, 기존 Chrome은 건드리지 않는다.

## Risks

- **`@latest` 는 조용히 올라간다.** `readme.md` 에 박은 "1.5.0 / 도구 29개" 는 언젠가 틀려진다.
- **로그인 세션 노출.** `--autoConnect` 로 내 창에 붙으면 열린 탭·쿠키·인증 헤더가 에이전트 컨텍스트로 들어간다.
  `--redactNetworkHeaders` 기본값은 `false` 다. 이 저장소는 autoConnect 를 다루지 않는다.
- **프롬프트 인젝션.** 에이전트가 읽는 페이지가 에이전트에게 명령할 수 있다.
- **DevTools 포트 노출.** 원격 `9222`는 반드시 `127.0.0.1`에만 바인딩한다.
- **GUI의 비대화.** SSH 비밀번호 저장, 서비스 설치, 자동 재연결은 현재 범위에 넣지 않는다.
- **실제 reverse forward 미검증.** SSH 공개키 인증과 명령 생성은 확인했지만, 원격 서버의
  `curl http://127.0.0.1:9222/json/version`은 실행 환경에서 아직 확인하지 않았다.
- **미검증 항목을 검증된 것처럼 쓰지 말 것.** 위 "미결 항목" 두 개는 전부 미검증이다.
