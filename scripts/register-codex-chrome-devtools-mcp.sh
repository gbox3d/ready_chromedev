#!/usr/bin/env bash
# Registers chrome-devtools-mcp in the current user's global Codex configuration.
# Supported on macOS and Ubuntu (and other Linux distributions with Bash).

set -euo pipefail

server_name='chrome-devtools'
expected_command='npx'
expected_args=(-y chrome-devtools-mcp@latest)
force=false
codex_home="${CODEX_HOME:-$HOME/.codex}"
config_path="$codex_home/config.toml"

usage() {
  cat <<'EOF'
Usage: register-codex-chrome-devtools-mcp.sh [--force]

Registers chrome-devtools-mcp in the current user's global Codex configuration.
Use --force only to replace a different existing global registration named
chrome-devtools.
EOF
}

case "${1:-}" in
  '') ;;
  --force|-f) force=true ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

for command_name in codex npx; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf "'%s' was not found. Install the Codex CLI and Node.js, then run this script again.\n" "$command_name" >&2
    exit 1
  fi
done

# Query outside the repository so a project-scoped .codex/config.toml cannot be
# mistaken for a global registration.
get_global_server() {
  (
    cd "${TMPDIR:-/tmp}"
    codex mcp get "$server_name" 2>/dev/null
  )
}

if existing="$(get_global_server)"; then
  if grep -Eq '^[[:space:]]*command:[[:space:]]*npx[[:space:]]*$' <<<"$existing" && \
     grep -Eq '^[[:space:]]*args:[[:space:]]*-y chrome-devtools-mcp@latest[[:space:]]*$' <<<"$existing"; then
    printf "'%s' is already registered globally for Codex. No changes were made.\n" "$server_name"
    exit 0
  fi

  if [[ "$force" != true ]]; then
    cat >&2 <<EOF
'$server_name' is already registered globally for Codex with a different configuration.
Inspect it with:
  codex mcp get $server_name
Run this script again with --force only if you want to replace it.
EOF
    exit 1
  fi

  codex mcp remove "$server_name"
fi

codex mcp add "$server_name" -- "$expected_command" "${expected_args[@]}"

registered="$(get_global_server)"
if ! grep -Eq '^[[:space:]]*command:[[:space:]]*npx[[:space:]]*$' <<<"$registered" || \
   ! grep -Eq '^[[:space:]]*args:[[:space:]]*-y chrome-devtools-mcp@latest[[:space:]]*$' <<<"$registered"; then
  printf "Post-registration validation failed. Run 'codex mcp get %s' to inspect it.\n" "$server_name" >&2
  exit 1
fi

printf 'Global Codex MCP registration completed: %s\n' "$config_path"
printf 'Reload the VS Code window, start a new Codex chat, and confirm chrome-devtools with /mcp.\n'
