# Inventory

## 목차

- [Repository](#repository)
- [Top-level structure](#top-level-structure)
- [설정 파일](#설정-파일)
- [확인 명령](#확인-명령)
- [Tests](#tests)
- [Notes](#notes)

## Repository

- Name: `ready_chromedev`
- Path: `c:\works\ready_chromedev`
- git: 브랜치 `master`. 커밋 1개 — `cd8c714` "정리 전 스냅샷".
- Summary: **`chrome-devtools-mcp` 설치법과 확인법만 담는 저장소.** 코드는 없다.

## Top-level structure

```
.mcp.json     chrome-devtools MCP 서버 등록 (project scope). 이 저장소의 전부다.
readme.md     설치법 + 확인법.
_forAI/       이 문서 세트.
.gitignore    node_modules/, _archive/, .claude/
```

## 설정 파일

`.mcp.json`:

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

- **project scope.** 이 폴더를 루트로 연 세션에서만 읽힌다.
- 첫 사용 전 **승인**이 필요하다. 승인 기록은 `.claude/settings.local.json` 에 남고,
  그 디렉터리는 `.gitignore` 에 있다.
- Windows 에서 `cmd /c` 래핑은 **필수**다. Claude Code 는 셸 없이 `spawn()` 하므로
  `"command": "npx"` 는 `spawn npx ENOENT` 로 죽는다.

## 확인 명령

```powershell
# 1) npx 캐시 예열 + 실제로 받아오는 버전 (셸을 거치는 경로)
npx -y chrome-devtools-mcp@latest --version     # 2026-07-09 기준 1.5.0

# 2) 등록/연결 헬스체크 — 반드시 이 저장소를 루트로
claude mcp list                                 # chrome-devtools: ✔ Connected
```

세션 안에서는 `/mcp` 로 본다. **`claude mcp list` 와 `/mcp` 는 다른 것을 본다.**
전자는 별도 프로세스를 새로 띄워 헬스체크하고, 후자는 현재 세션의 실제 상태를 보여준다.
`claude mcp list` 가 초록이어도 현재 세션에 도구가 없을 수 있다 (2026-07-09 실측).

## Tests

없다. 코드가 없다.

## Notes

- 의존성 0. `package.json` 이 없다. `npx` 만 네트워크를 쓴다.
- `@latest` 를 쓰므로 버전이 조용히 올라간다. 도구 개수·이름은 `/mcp` 로 확인할 것.
- 2026-07-09 저장소를 대폭 축소했다. `demo/`, `scripts/`, `slides/`, `docs/` 삭제.
  삭제 직전 상태는 커밋 `cd8c714` 에 전부 들어 있다. 필요하면 거기서 꺼낸다.
