# Inventory

## 목차

- [Repository](#repository)
- [Top-level structure](#top-level-structure)
- [설정 파일](#설정-파일)
- [SSH 역터널](#ssh-역터널)
- [확인 명령](#확인-명령)
- [Tests](#tests)
- [Notes](#notes)

## Repository

- Name: `ready_chromedev`
- Path: `c:\works\ready_chromedev`
- git: 브랜치 `main`.
- Summary: **`chrome-devtools-mcp` 등록·확인과 Chrome DevTools SSH 역터널 관리 저장소.**

## Top-level structure

```
.mcp.json     Claude Code용 chrome-devtools MCP 서버 등록 (project scope).
.codex/       Codex 프로젝트 설정 예시.
readme.md     MCP 설치·확인법과 SSH 역터널 사용법.
index.html    삼목 데모 진입점.
style.css     데모 스타일.
script.js     데모 동작.
tunnel_gui/   독립 Python·uv·Tkinter SSH 역터널 관리자.
_forAI/       이 문서 세트.
.gitignore    node_modules/, _archive/, .venv/, .claude/, Python 캐시
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

Codex 전역 등록:

- Windows: `codex mcp add chrome-devtools -- cmd /c npx -y chrome-devtools-mcp@latest`
- macOS·Ubuntu: `codex mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest`
- 저장 위치: `~/.codex/config.toml` (`CODEX_HOME`을 설정했으면 그 경로)
- Codex 전역 등록은 상위 폴더를 VS Code 작업 루트로 열어도 MCP를 쓰기 위한 의도적인 결정이다.

## SSH 역터널

- `tunnel_gui/chrome_tunnel_gui/tunnel.py`: 로컬 Chrome을 `127.0.0.1:9333`에 열고
  `ssh -NT -R 127.0.0.1:9222:127.0.0.1:9333`을 유지한다.
- `tunnel_gui/chrome_tunnel_gui/app.py`: Tkinter GUI와 프로파일 UI를 제공한다.
- `tunnel_gui/chrome_tunnel_gui/profiles.py`: YAML 프로파일 저장소를 제공한다.
- 기본 원격 대상: 백엔드 `192.168.0.220:8000`, SSH Host 별칭 `gblab-dgx-01`.
  별칭을 사용해야 `~/.ssh/config`의 `id_ed25519_myservers`가 적용된다.
- Python 외부 의존성은 PyYAML 6.0.3 하나다. uv 관리 Python 3.14.6의 Tk 8.6.14 import를 확인했다.
- SSH 인증은 키 또는 비대화형 `ssh-agent` 인증이 필요하다. GUI stdin은 닫혀 있어 암호 프롬프트를 지원하지 않는다.
- 앱이 시작한 전용 Chrome은 Windows Job Object로 추적하며 터널 중지·종료 시 자식 프로세스까지 닫는다.

## 확인 명령

```powershell
# 1) npx 캐시 예열 + 실제로 받아오는 버전 (셸을 거치는 경로)
npx -y chrome-devtools-mcp@latest --version     # 2026-07-09 기준 1.5.0

# 2) 등록/연결 헬스체크 — 반드시 이 저장소를 루트로
claude mcp list                                 # chrome-devtools: ✔ Connected

# 3) Codex 전역 등록 확인 — 어느 폴더에서나
codex mcp list                                  # chrome-devtools ... enabled

# 4) 독립 tunnel_gui 테스트
Set-Location .\tunnel_gui
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q chrome_tunnel_gui chrome_devtools_tunnel_gui.py

# 5) GUI 실행
uv run python -m chrome_tunnel_gui
```

세션 안에서는 `/mcp` 로 본다. **`claude mcp list` 와 `/mcp` 는 다른 것을 본다.**
전자는 별도 프로세스를 새로 띄워 헬스체크하고, 후자는 현재 세션의 실제 상태를 보여준다.
`claude mcp list` 가 초록이어도 현재 세션에 도구가 없을 수 있다 (2026-07-09 실측).

## Tests

- `codex mcp list`에서 `chrome-devtools`가 `enabled`인지 확인한다.
- `tunnel_gui`에서 `uv run python -m unittest discover -s tests -v`를 실행한다.
- `tunnel_gui`에서 `uv run python -m compileall -q chrome_tunnel_gui chrome_devtools_tunnel_gui.py`를 실행한다.

## Notes

- `package.json`은 없다. `npx`는 Chrome DevTools MCP가 필요할 때만 네트워크를 쓴다.
- `tunnel_gui` Python 의존성은 PyYAML 하나이며, `uv.lock`으로 고정한다.
- `@latest` 를 쓰므로 버전이 조용히 올라간다. 도구 개수·이름은 `/mcp` 로 확인할 것.
- 2026-07-09 저장소를 대폭 축소했다. `demo/`, `scripts/`, `slides/`, `docs/` 삭제.
  삭제 직전 상태는 커밋 `cd8c714` 에 전부 들어 있다. 필요하면 거기서 꺼낸다.
- 2026-07-14 Codex 전역 등록은 스크립트 대신 `codex mcp add` 한 줄 명령으로 문서화했다.
