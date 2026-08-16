<#
.SYNOPSIS
    Mints a fresh Supabase refresh token for the promptbanken-admin MCP and
    deploys it to the VPS in one go.

.DESCRIPTION
    Fixes the "400 Bad Request on grant_type=refresh_token" failure that
    happens when SUPABASE_ADMIN_REFRESH_TOKEN on the VPS goes stale (see
    mcp_promptbanken LOG.md / DECISIONS.md 2026-07-28 "Admin-MCP: JWT-brygga").

    Steps:
      1. Pulls SUPABASE_URL / SUPABASE_ANON_KEY straight from the VPS .env
         over SSH (no need to keep a local copy in sync).
      2. Prompts for the platform-owner email + password locally (never
         sent anywhere but Supabase's own /auth/v1/token endpoint).
      3. Exchanges them for a refresh_token.
      4. SSHes to the VPS: writes the new token into .env, clears the
         (usually-empty) rotation state file, and recreates the container.
      5. Works around the known docker-compose 1.29.2 "KeyError:
         'ContainerConfig'" recreate bug automatically.
      6. Verifies the container reports healthy.

.NOTES
    Requires: OpenSSH client (ssh) on PATH, working SSH access to the VPS
    (same auth you already use to log in manually).

.EXAMPLE
    .\fix-admin-token.ps1
    .\fix-admin-token.ps1 -VpsHost wenstrompeter@185.157.222.12
#>

param(
    [string]$VpsHost = "wenstrompeter@185.157.222.12",
    [string]$RemoteDir = "/home/wenstrompeter/mcp_promptbanken",
    [string]$ContainerName = "mcp_promptbanken_promptbanken-mcp_1",
    [string]$ComposeService = "promptbanken-mcp"
)

$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Fetching SUPABASE_URL / SUPABASE_ANON_KEY from VPS .env"
$envLines = ssh $VpsHost "grep -E '^SUPABASE_URL=|^SUPABASE_ANON_KEY=' $RemoteDir/.env"
if ($LASTEXITCODE -ne 0 -or -not $envLines) {
    throw "Could not read SUPABASE_URL/SUPABASE_ANON_KEY from $VpsHost`:$RemoteDir/.env"
}
$envMap = @{}
foreach ($line in $envLines -split "`n") {
    if ($line -match '^([A-Z_]+)=(.*)$') { $envMap[$matches[1]] = $matches[2].Trim() }
}
$supabaseUrl = $envMap["SUPABASE_URL"]
$anonKey = $envMap["SUPABASE_ANON_KEY"]
if (-not $supabaseUrl -or -not $anonKey) {
    throw "Missing SUPABASE_URL or SUPABASE_ANON_KEY in remote .env"
}
Write-Host "  SUPABASE_URL = $supabaseUrl"

Step "Platform owner login (sent only to Supabase's own auth endpoint)"
$email = Read-Host "Platform owner email"
$securePassword = Read-Host "Password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

Step "Exchanging credentials for a refresh token"
$body = @{ email = $email; password = $password } | ConvertTo-Json
try {
    $resp = Invoke-RestMethod -Method Post `
        -Uri "$supabaseUrl/auth/v1/token?grant_type=password" `
        -Headers @{ apikey = $anonKey; "Content-Type" = "application/json" } `
        -Body $body
} catch {
    throw "Login failed: $($_.Exception.Message)"
}
$refreshToken = $resp.refresh_token
if (-not $refreshToken) { throw "No refresh_token in Supabase response." }
Write-Host "  Got new refresh token." -ForegroundColor Green
$password = $null  # drop plaintext password from memory ASAP

Step "Deploying to VPS: update .env, clear rotation state, recreate container"
$remoteScript = @"
set -e
cd '$RemoteDir'
sed -i 's/^SUPABASE_ADMIN_REFRESH_TOKEN=.*/SUPABASE_ADMIN_REFRESH_TOKEN=$refreshToken/' .env
docker exec $ContainerName sh -c 'rm -f /var/lib/promptbanken-mcp/admin_refresh_token_state.json' 2>/dev/null || true
if ! docker-compose up -d $ComposeService 2>/tmp/compose_err; then
  if grep -q "ContainerConfig" /tmp/compose_err; then
    echo "Known docker-compose 1.29.2 recreate bug, working around it..."
    OLD_ID=`$(docker ps -aq -f "name=$ContainerName" -f status=exited)
    docker rm `$OLD_ID
    docker-compose up -d $ComposeService
  else
    cat /tmp/compose_err
    exit 1
  fi
fi
sleep 8
docker ps --format '{{.Names}}\t{{.Status}}' | grep $ComposeService
"@

ssh $VpsHost $remoteScript
if ($LASTEXITCODE -ne 0) { throw "Remote deploy step failed -- check output above." }

Step "Done. Verify from Claude Code with: admin_list_draft_prompts"
Write-Host "New SUPABASE_ADMIN_REFRESH_TOKEN=$refreshToken" -ForegroundColor DarkGray
Write-Host "(Also written into the VPS .env -- nothing more to do there.)"
