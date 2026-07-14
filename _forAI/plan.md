# Plan

## 목차

- [Current goal](#current-goal)
- [Near-term work](#near-term-work)
- [미결 항목](#미결-항목)
- [Structure decisions](#structure-decisions)
- [Risks](#risks)

## Current goal

**`chrome-devtools-mcp`를 프로젝트와 Codex 전역에서 등록하고, 붙었는지 확인하는 법을 정확히 문서화한다.**

그 이상은 이 저장소의 범위가 아니다. 강의안·방법론 비교·데모 코드는 2026-07-09 에 걷어냈다.

## Near-term work

1. macOS 또는 Ubuntu의 깨끗한 환경에서 Bash 전역 등록 스크립트를 한 번 처음부터 따라해 본다.
2. 새 세션에서 `.mcp.json` 승인 프롬프트가 실제로 뜨는지 확인한다
   (`.claude/` 를 지웠으므로 다음 세션에 한 번 떠야 한다).

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
- 코드를 다시 들이지 않는다. 검증이 필요하면 명령 한 줄로 끝나야 한다.

## Risks

- **`@latest` 는 조용히 올라간다.** `readme.md` 에 박은 "1.5.0 / 도구 29개" 는 언젠가 틀려진다.
- **로그인 세션 노출.** `--autoConnect` 로 내 창에 붙으면 열린 탭·쿠키·인증 헤더가 에이전트 컨텍스트로 들어간다.
  `--redactNetworkHeaders` 기본값은 `false` 다. 이 저장소는 autoConnect 를 다루지 않는다.
- **프롬프트 인젝션.** 에이전트가 읽는 페이지가 에이전트에게 명령할 수 있다.
- **미검증 항목을 검증된 것처럼 쓰지 말 것.** 위 "미결 항목" 두 개는 전부 미검증이다.
