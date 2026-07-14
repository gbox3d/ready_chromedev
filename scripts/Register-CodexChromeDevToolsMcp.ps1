[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Force
)

<##
.SYNOPSIS
Registers chrome-devtools-mcp in the current user's global Codex configuration.

.DESCRIPTION
Codex stores user-level MCP servers in $env:USERPROFILE\.codex\config.toml.
This script registers chrome-devtools there, so the server is available even
when VS Code opens a parent folder or a different repository.

If a server with the same name is already registered with the expected command,
the script makes no changes. Use -Force only to replace a different existing
global registration named chrome-devtools.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$serverName = 'chrome-devtools'
$expectedCommand = 'cmd'
$expectedArgs = '/c npx -y chrome-devtools-mcp@latest'
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$configPath = Join-Path $codexHome 'config.toml'

foreach ($commandName in 'codex', 'npx') {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "'$commandName' was not found. Install the Codex CLI and Node.js, then run this script again."
    }
}

# Run inspection outside the repository so a project-scoped .codex/config.toml
# cannot be mistaken for a global registration.
$originalLocation = Get-Location
try {
    Push-Location $env:TEMP
    # A missing server is an expected non-zero result. cmd redirects its
    # diagnostic so PowerShell's ErrorActionPreference does not turn it into
    # an exception before we can inspect the exit code.
    $existing = & cmd /d /c "codex mcp get $serverName 2>nul"
    $existingExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($existingExitCode -eq 0) {
    $existingText = $existing | Out-String
    $isExpectedRegistration =
        $existingText -match '(?m)^\s*command:\s*cmd\s*$' -and
        $existingText -match '(?m)^\s*args:\s*/c npx -y chrome-devtools-mcp@latest\s*$'

    if ($isExpectedRegistration) {
        Write-Host "'$serverName' is already registered globally for Codex. No changes were made."
        exit 0
    }

    if (-not $Force) {
        throw @"
'$serverName' is already registered globally for Codex with a different configuration.
Inspect it with:
  codex mcp get $serverName
Run this script again with -Force only if you want to replace it.
"@
    }

    if ($PSCmdlet.ShouldProcess($configPath, "remove existing global MCP '$serverName'")) {
        & codex mcp remove $serverName
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove the existing global MCP '$serverName'."
        }
    }
}
elseif ($existingExitCode -ne 0) {
    # codex mcp get returns non-zero when this user-level server is absent.
    $existing = $null
}

if ($PSCmdlet.ShouldProcess($configPath, "register global MCP '$serverName'")) {
    & codex mcp add $serverName -- $expectedCommand '/c' 'npx' '-y' 'chrome-devtools-mcp@latest'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register the global MCP '$serverName'."
    }
}

if (-not $WhatIfPreference) {
    try {
        Push-Location $env:TEMP
        $registered = & cmd /d /c "codex mcp get $serverName 2>nul"
        $registeredExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    $registeredText = $registered | Out-String
    if ($registeredExitCode -ne 0 -or
        $registeredText -notmatch '(?m)^\s*command:\s*cmd\s*$' -or
        $registeredText -notmatch '(?m)^\s*args:\s*/c npx -y chrome-devtools-mcp@latest\s*$') {
        throw "Post-registration validation failed. Run 'codex mcp get $serverName' to inspect it."
    }

    Write-Host "Global Codex MCP registration completed: $configPath"
    Write-Host 'Reload the VS Code window, start a new Codex chat, and confirm chrome-devtools with /mcp.'
}
