[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ComputerName,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory,

    [string]$Python = 'python',
    [string]$UsersRoot
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$collector = Join-Path $PSScriptRoot 'Collect-BrowserHistory.ps1'
$parser = Join-Path $PSScriptRoot 'parse_browser_history.py'
$visualizer = Join-Path $PSScriptRoot 'visualize_browser_history.py'
foreach ($script in @($collector, $parser, $visualizer)) {
    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
        throw "Missing companion script: $script"
    }
}

$pythonPath = (Get-Command -Name $Python -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1).Source
if (-not $pythonPath) {
    throw 'Python 3.9+ is required. Install it on the analyst workstation or pass -Python with the path to python.exe.'
}
& $pythonPath -c 'import sys; sys.exit(sys.version_info < (3, 9))'
if ($LASTEXITCODE -ne 0) { throw "Python 3.9+ is required. Checked $pythonPath." }
& $pythonPath -c "from zoneinfo import ZoneInfo; ZoneInfo('America/New_York')"
if ($LASTEXITCODE -ne 0) {
    throw "Eastern time zone data is required. Run: & '$pythonPath' -m pip install tzdata"
}

$collectArgs = @{ ComputerName = $ComputerName; OutputDirectory = $OutputDirectory }
if ($UsersRoot) { $collectArgs.UsersRoot = $UsersRoot }

Write-Host "[1/3] Collecting browser history from $ComputerName"
$collection = & $collector @collectArgs
if ($LASTEXITCODE -ne 0 -or -not $collection) {
    throw "Collection did not complete. Review the warnings. Copies already collected: $collection"
}

Write-Host '[2/3] Exporting JSON and CSV'
& $pythonPath $parser $collection | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Export did not complete. Review the parser output and collected files in $collection."
}

Write-Host '[3/3] Generating the activity report'
$history = Join-Path $collection 'browser-history.json'
$report = Join-Path $collection 'browser-history-activity.html'
& $pythonPath $visualizer $history --output $report | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Activity report generation failed. The JSON and CSV are in $collection."
}

Write-Host "Collection folder: $collection"
Write-Host "JSON: $history"
Write-Host "CSV: $(Join-Path $collection 'browser-history.csv')"
Write-Host "Report: $report"
Write-Output $collection
