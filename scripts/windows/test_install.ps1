param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [switch]$CheckWindow
)

$ErrorActionPreference = "Stop"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\finamt"
if (Test-Path $uninstallKey) {
    throw "Run this test in a fresh Windows user profile or a disposable VM."
}

$setup = (Resolve-Path -LiteralPath $Installer).Path
$testRoot = Join-Path $env:LOCALAPPDATA ("finamt-test-" + [guid]::NewGuid().ToString("N"))
$window = $null
try {
    $installed = Start-Process -FilePath $setup -ArgumentList "/S /D=$testRoot" -Wait -PassThru
    if ($installed.ExitCode -ne 0) { throw "Installer exit code $($installed.ExitCode)" }
    $entry = Get-ItemProperty -LiteralPath $uninstallKey
    if ($entry.InstallLocation -ne $testRoot) { throw "Unexpected installation directory" }
    $startupLink = Join-Path ([Environment]::GetFolderPath("Programs")) "finamt.lnk"
    if (-not (Test-Path -LiteralPath $startupLink)) { throw "Start menu shortcut missing" }

    $release = $entry.ReleaseDirectory
    $python = Join-Path $release ".venv\Scripts\python.exe"
    $probe = @'
from pathlib import Path
from sys import argv
from urllib.request import urlopen
from finamt.tax.est import EmployeeCase, draft_annual_return
from finamt.ui.desktop import _local_workspace

sample = Path(argv[1]) / "beispielfall"
case = EmployeeCase.model_validate_json((sample / "fall-vollstaendig.json").read_text(encoding="utf-8"))
result = draft_annual_return(case, sample)
assert result["intake"]["status"] == "supported"
assert "tax_balance" in result["assessment"]["values"]
with _local_workspace() as url:
    for suffix, expected in (("", b"Steuerassistent"), ("/api/intake", b"residence"), ("/workspace.js", b"scope-intake")):
        with urlopen(url + suffix, timeout=5) as response:
            assert expected in response.read()
print("Installed Windows runtime, tax example and UI endpoints verified")
'@
    $probeFile = Join-Path $testRoot "probe.py"
    Set-Content -LiteralPath $probeFile -Value $probe -Encoding utf8
    & $python $probeFile $release
    if ($LASTEXITCODE -ne 0) { throw "Installed finamt failed its smoke test" }

    if ($CheckWindow) {
        $pythonw = Join-Path $release ".venv\Scripts\pythonw.exe"
        $launchScript = Join-Path $release "launch.pyw"
        $window = Start-Process -FilePath $pythonw -ArgumentList "`"$launchScript`"" -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(40)
        do {
            Start-Sleep -Milliseconds 250
            $window.Refresh()
        } until ($window.HasExited -or $window.MainWindowTitle -like "finamt*Einkommensteuer" -or [DateTime]::UtcNow -ge $deadline)
        if ($window.HasExited -or $window.MainWindowTitle -notlike "finamt*Einkommensteuer") {
            throw "The WebView2 window did not open. Check the installed WebView2 Runtime."
        }
        if (-not $window.CloseMainWindow() -or -not $window.WaitForExit(10000)) {
            throw "finamt window did not exit after closing"
        }
    }
}
finally {
    if ($window -and -not $window.HasExited) { Stop-Process -Id $window.Id }
    $uninstaller = Join-Path $testRoot "uninstall.exe"
    if (Test-Path -LiteralPath $uninstaller) {
        $removed = Start-Process -FilePath $uninstaller -ArgumentList "/S _?=$testRoot" -Wait -PassThru
        if ($removed.ExitCode -ne 0 -or (Test-Path $uninstallKey)) {
            throw "finamt uninstall did not complete"
        }
    }
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
