<#
.SYNOPSIS
    Instalador kiro-dash para Windows 11.

.DESCRIPTION
    Automatiza a instalação do kiro-dash em Windows 11 sem exigir
    Python pré-instalado. Faz:
      1. Verifica/instala Python 3.13 via winget (se necessário).
      2. Instala pipx no escopo do usuário.
      3. Adiciona pipx bin ao PATH do usuário (idempotente).
      4. Instala kiro-dash via pipx a partir do GitHub.
      5. Verifica que `kiro-dash --version` responde.
      6. Imprime instruções para registrar MCP server no Kiro IDE.

    Idempotente — pode ser re-executado sem efeito colateral.
    Logs claros para troubleshooting.

.PARAMETER Version
    Tag do GitHub a instalar. Default: latest stable (v0.8.0).
    Use "main" para instalar a branch principal.

.PARAMETER Force
    Força reinstalação mesmo se kiro-dash já está instalado.

.PARAMETER Local
    Instala a partir de um clone local em vez do GitHub. Aponta para
    o caminho do clone via $env:KIRO_DASH_LOCAL_PATH.

.EXAMPLE
    iwr -useb https://raw.githubusercontent.com/mencoding/kiro-dashboard/main/scripts/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Version v0.8.0

.EXAMPLE
    .\install.ps1 -Force

.NOTES
    Wave 10 (v0.8.0). Requer PowerShell 5.1+ (Windows 10/11 default).
#>

[CmdletBinding()]
param(
    [string]$Version = "v0.8.0",
    [switch]$Force,
    [switch]$Local
)

# ── Helpers ────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "▶ $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "  ⚠ $msg" -ForegroundColor Yellow
}

function Write-Fail($msg) {
    Write-Host "  ✗ $msg" -ForegroundColor Red
}

function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Add-ToUserPath($dir) {
    $current = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($current -split ";" -notcontains $dir) {
        $new = if ($current) { "$current;$dir" } else { $dir }
        [Environment]::SetEnvironmentVariable("PATH", $new, "User")
        $env:PATH = "$env:PATH;$dir"
        Write-OK "Adicionado ao PATH do usuário: $dir"
    }
    else {
        Write-OK "Já está no PATH: $dir"
    }
}

# ── Banner ─────────────────────────────────────────────────────────

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  kiro-dash — Instalador Windows 11" -ForegroundColor Magenta
Write-Host "  Versão: $Version" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta

# ── Step 1: Python ────────────────────────────────────────────────

Write-Step "Verificando Python 3.10+"

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    if (Test-Command $candidate) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 10) {
                    $pythonCmd = $candidate
                    Write-OK "$ver encontrado ($candidate)"
                    break
                }
            }
        }
        catch {
            # Ignore e tenta o próximo
        }
    }
}

if (-not $pythonCmd) {
    Write-Warn "Python 3.10+ não encontrado. Tentando instalar via winget..."

    if (-not (Test-Command "winget")) {
        Write-Fail "winget não disponível. Instale manualmente:"
        Write-Host "    https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "    Marque 'Add to PATH' durante a instalação." -ForegroundColor Yellow
        exit 1
    }

    & winget install --id Python.Python.3.13 -e --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Falha ao instalar Python via winget."
        exit 1
    }

    # Refresh PATH na sessão atual
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("PATH", "User")

    if (Test-Command "python") {
        $pythonCmd = "python"
        Write-OK "Python 3.13 instalado via winget"
    }
    elseif (Test-Command "py") {
        $pythonCmd = "py"
        Write-OK "Python 3.13 instalado via winget (use 'py')"
    }
    else {
        Write-Fail "Python instalado mas não está no PATH. Reinicie o terminal e re-execute."
        exit 1
    }
}

# ── Step 2: pipx ───────────────────────────────────────────────────

Write-Step "Verificando pipx"

if (Test-Command "pipx" -and -not $Force) {
    Write-OK "pipx já instalado"
}
else {
    Write-Host "  Instalando pipx no escopo do usuário..."
    & $pythonCmd -m pip install --user --upgrade pipx
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Falha ao instalar pipx."
        exit 1
    }

    # Adicionar bin do user ao PATH
    $userBase = & $pythonCmd -m site --user-base
    $userScripts = Join-Path $userBase "Scripts"
    Add-ToUserPath $userScripts

    & $pythonCmd -m pipx ensurepath
    Write-OK "pipx instalado"
}

# ── Step 3: Instalar kiro-dash ─────────────────────────────────────

Write-Step "Instalando kiro-dash"

$source = if ($Local -and $env:KIRO_DASH_LOCAL_PATH) {
    $env:KIRO_DASH_LOCAL_PATH
}
else {
    "git+https://github.com/mencoding/kiro-dashboard.git@$Version"
}

$installArgs = @("install", $source)
if ($Force) { $installArgs += "--force" }

& pipx @installArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Tentando via 'python -m pipx'..."
    & $pythonCmd -m pipx @installArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Falha ao instalar kiro-dash. Source: $source"
        exit 1
    }
}

Write-OK "kiro-dash instalado de $source"

# ── Step 4: Verificação ────────────────────────────────────────────

Write-Step "Verificando instalação"

# Refresh PATH na sessão atual
$env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("PATH", "User")

if (Test-Command "kiro-dash") {
    $installedVer = & kiro-dash --version 2>&1
    Write-OK "kiro-dash respondendo: $installedVer"
}
else {
    Write-Warn "kiro-dash não está no PATH na sessão atual."
    Write-Host "    Abra um NOVO terminal e teste: kiro-dash --version" -ForegroundColor Yellow
}

# ── Step 5: Instruções MCP ─────────────────────────────────────────

Write-Step "Próximos passos"

$agentDir = Join-Path $env:USERPROFILE ".kiro\agents"
$agentExample = Join-Path $agentDir "kiro-dash-example.json"

Write-Host @"

  Para usar o kiro-dash como MCP server no Kiro IDE:

  1. Edite o arquivo de agent que vai consumir o MCP:
       $agentDir\<seu-agent>.json

  2. Adicione o bloco mcpServers:
       {
         ""mcpServers"": {
           ""kiro-dash"": {
             ""command"": ""kiro-dash-mcp"",
             ""timeout_ms"": 30000
           }
         }
       }

  3. Reinicie a sessão Kiro IDE.

  4. Tools disponíveis no agent:
       usage_state, today_summary, active_sessions, session_details,
       top_models, top_projects, account_info.

  Comandos rápidos:
    kiro-dash whoami           # identidade + fontes detectadas
    kiro-dash today            # agregado de hoje
    kiro-dash tui              # dashboard interativa
    kiro-dash --help

  Documentação:
    https://github.com/mencoding/kiro-dashboard

"@ -ForegroundColor Cyan

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  Instalação concluída." -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""
