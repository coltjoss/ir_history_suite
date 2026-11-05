[CmdletBinding()]
param(
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9.-]*$')]
    [string]$ComputerName = $env:COMPUTERNAME,
    [string]$OutputDirectory = (Get-Location).Path,
    [string]$UsersRoot
)

$ErrorActionPreference = 'Stop'
$OutputDirectory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if (-not $UsersRoot) {
    $UsersRoot = if ($ComputerName -in @($env:COMPUTERNAME, 'localhost')) {
        Join-Path $env:SystemDrive 'Users'
    } else {
        '\\{0}\C$\Users' -f $ComputerName
    }
}
$users = Get-ChildItem -LiteralPath $UsersRoot -Directory -Force |
    Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }
$browsers = [ordered]@{
    Chrome = 'AppData\Local\Google\Chrome\User Data'
    Edge   = 'AppData\Local\Microsoft\Edge\User Data'
}
$names = 'History', 'History-wal', 'History-shm', 'History-journal'
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$collection = Join-Path $OutputDirectory "$ComputerName-$stamp"
$count = 0
$failed = 0

function Get-HistoryFiles($Directory) {
    Get-ChildItem -LiteralPath $Directory -File -Force |
        Where-Object { $_.Name -in $names }
}

function Get-FileState($Files) {
    ($Files | Sort-Object Name | ForEach-Object {
        '{0}:{1}:{2}' -f $_.Name, $_.Length, $_.LastWriteTimeUtc.Ticks
    }) -join '|'
}

function Copy-SharedFile($Source, $Destination) {
    $sharing = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $inputFile = [IO.File]::Open($Source, 'Open', 'Read', $sharing)
    try {
        $outputFile = [IO.File]::Create($Destination)
        try { $inputFile.CopyTo($outputFile) }
        finally { $outputFile.Dispose() }
    } finally { $inputFile.Dispose() }
}

foreach ($user in $users) {
    foreach ($browser in $browsers.Keys) {
        $root = Join-Path $user.FullName $browsers[$browser]
        try {
            if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
            $profiles = Get-ChildItem -LiteralPath $root -Directory -Force
        } catch {
            Write-Warning "Cannot enumerate ${root}: $_"
            $failed++
            continue
        }

        foreach ($profile in $profiles) {
            $parent = Join-Path (Join-Path $collection $user.Name) $browser
            $destination = Join-Path $parent $profile.Name
            $incomplete = Join-Path $destination '.incomplete'
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                try {
                    $files = @(Get-HistoryFiles $profile.FullName)
                    if ($files.Name -notcontains 'History') {
                        if ($attempt -eq 1) { break }
                        throw 'History disappeared during collection.'
                    }
                    $before = Get-FileState $files
                    $null = [IO.Directory]::CreateDirectory($destination)
                    [IO.File]::WriteAllText($incomplete, '')
                    foreach ($file in $files) {
                        Copy-SharedFile $file.FullName (Join-Path $destination $file.Name)
                    }
                    if ($before -ne (Get-FileState @(Get-HistoryFiles $profile.FullName))) {
                        throw 'History files changed during collection.'
                    }
                    [IO.File]::Delete($incomplete)
                    Write-Host "$($user.Name) / $browser / $($profile.Name)"
                    $count++
                    break
                } catch {
                    if ([IO.File]::Exists($incomplete)) {
                        foreach ($name in $names) { [IO.File]::Delete((Join-Path $destination $name)) }
                    }
                    if ($attempt -eq 3) {
                        Write-Warning "Could not collect $($profile.FullName): $_"
                        $failed++
                    } else { Start-Sleep -Milliseconds 200 }
                }
            }
        }
    }
}

Write-Host "Collected $count database(s). Collection errors: $failed."
if ($count) { Write-Output $collection }
if ($failed -or -not $count) { exit 1 }
exit 0
