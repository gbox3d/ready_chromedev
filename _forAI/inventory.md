# Inventory

## 목차

- [Repository](#repository)
- [Top-level structure](#top-level-structure)
- [Entrypoints and key modules](#entrypoints-and-key-modules)
- [Build and validation commands](#build-and-validation-commands)
- [Tests](#tests)
- [Notes](#notes)

## Repository

- Name: `ready_chromedev`
- Path: `c:\works\ready_chromedev`
- git: **초기화됨** (브랜치 `master`, **커밋 0개**). 아직 아무것도 커밋되지 않았다.
- Summary: `chrome-devtools-mcp` 를 순정 Chrome 에 붙여 쓰는 법을 다룬 **문서 저장소**.
  코드는 없다. 산출물은 `docs/chrome-mcp-guide.md` 하나다.

## Top-level structure

```
.mcp.json               chrome-devtools MCP 서버 등록 (project scope). 이 저장소의 핵심 설정.
readme.md               한 줄짜리 제목만 있다.
docs/
  chrome-mcp-guide.md   299줄. 본 저장소의 산출물. 설치 → 실습 → autoConnect → 안전수칙 → 근거표.
_forAI/                 이 문서 세트
.gitignore              node_modules/, _archive/, .claude/
```

**2026-07-09 대규모 정리.** 이전에 있던 `demo/`, `scripts/`, `slides/`, `_archive/` 를
사용자가 직접 삭제했다. 커밋이 없었으므로 git 으로는 복구되지 않는다.
이전 구조를 전제로 한 서술은 이 문서에서 모두 걷어냈다.

## Entrypoints and key modules

| 파일 | 역할 |
|:--|:--|
| `.mcp.json` | `cmd /c npx -y chrome-devtools-mcp@latest`. Windows 에서 `cmd /c` 래핑이 **필수**다 (아래 Notes). |
| `docs/chrome-mcp-guide.md` | 강의·배포용 본문. 사실마다 근거를 붙였고, 미확인 항목은 미확인이라 표기했다. |

## Build and validation commands

빌드가 없다. 검증은 두 층위다.

```powershell
# 1) npx 캐시 예열 + 실제로 받아오는 버전 확인 (셸을 거치는 경로)
npx -y chrome-devtools-mcp@latest --version     # 2026-07-09 기준 1.5.0

# 2) 등록/연결 상태 확인 (반드시 저장소 루트에서)
claude mcp list                                 # chrome-devtools: ✔ Connected
```

`claude mcp list` 는 **별도 프로세스를 새로 띄워** 헬스체크한다.
현재 대화 세션이 그 도구를 실제로 쓸 수 있는지와는 **별개**다.
세션에서 확인하려면 `/mcp` 를 쓴다.

> **`--version` 통과 ≠ Claude Code 에서 붙음.** 터미널은 셸이라 `npx` → `npx.cmd` 확장자를
> 대신 풀어 준다. Claude Code 는 셸 없이 `spawn()` 한다. 둘은 다른 경로다.
> 셸 없는 `spawn` 을 검사하던 `scripts/verify-mcp.mjs` 는 현재 **삭제된 상태**이며,
> `docs/chrome-mcp-guide.md` 는 아직 그 파일을 3곳에서 참조한다 (`plan.md` 미결 항목 참조).

## Tests

자동화된 테스트는 **없다.** 코드가 없으므로 테스트할 대상도 없다.
검증 대상은 문서의 사실 주장이며, 근거는 `docs/chrome-mcp-guide.md` 부록 표에 있다.

## Notes

- **의존성 0.** `package.json` 이 없다. `npx chrome-devtools-mcp@latest` 만 네트워크를 쓴다.
- **`.mcp.json` 은 project scope** 다. 이 저장소를 루트로 연 세션에서만 읽힌다.
  첫 사용 전 승인이 필요하고, 승인 기록은 `.claude/settings.local.json` 에 남는다.
  그 파일은 `.gitignore` 에 있다 — 커밋하면 클론한 사람의 승인 관문이 사라지기 때문이다.
- **`@latest` 를 쓰고 있다.** 오늘은 1.5.0 으로 해석되지만 언제든 올라간다.
  가이드 본문의 "도구 29개" 같은 수치는 1.5.0 실측이므로, 데모 전 `/mcp` 로 재확인할 것.
- Artifact 로 배포된 슬라이드: `https://claude.ai/code/artifact/7449c14c-556a-406a-9316-cf89f626d525`
  (소스였던 `slides/` 는 삭제됐다. Artifact 는 살아 있다.)
