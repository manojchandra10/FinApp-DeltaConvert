# Local development wrapper: runs Docker Compose with the local overlay.
#
#   .\dev.ps1 up -d --build      start (and build) the local stack
#   .\dev.ps1 logs -f cortex     follow the API logs
#   .\dev.ps1 down               stop it
#
# Compose needs a .env with POSTGRES_PASSWORD. If there is none, this
# script writes one with random secrets the first time it runs. The file
# is for this computer only: never copy it to a server or commit it.
# Works in Windows PowerShell 5.1 and PowerShell 7.

Set-Location -LiteralPath $PSScriptRoot

function New-RandomHex([int]$ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    # A local database created before this script existed was initialised
    # with the old built-in password "localdev", and Postgres keeps the
    # password it was created with. Reuse it for that volume so local data
    # still opens; a new volume gets a random password.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    docker volume inspect deltaconvert_postgres_data *> $null
    $volumeExists = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $previousPreference

    if ($volumeExists) { $dbPassword = 'localdev' } else { $dbPassword = New-RandomHex 24 }

    $lines = @(
        '# Local development settings, written by dev.ps1.',
        '# For this computer only: never copy this file to a server or commit it.',
        'POSTGRES_USER=deltaconvert',
        "POSTGRES_PASSWORD=$dbPassword",
        'POSTGRES_DB=deltaconvert',
        "ADMIN_SECRET=$(New-RandomHex 32)",
        'DOMAIN=deltaconvert.com',
        'APP_BRAND=DeltaConvert'
    )
    # UTF-8 without a byte order mark; Compose would misread the first key.
    [System.IO.File]::WriteAllLines($envFile, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Created .env with random local secrets.'
}

docker compose -f docker-compose.yml -f compose.local.yml @args
exit $LASTEXITCODE
