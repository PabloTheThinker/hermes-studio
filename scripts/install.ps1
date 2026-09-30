# Hermes Studio installer for Windows. One line in PowerShell, no admin:
#
#   irm https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.ps1 | iex
#
# Downloads the latest installer from GitHub Releases, checks its SHA-256, and
# installs per-user (Start menu + desktop shortcut). Adds the `hermes-studio`
# command for your user. Run it again to update. Your clips are never touched.
#
# Options: set these first, e.g.  $env:HERMES_STUDIO_VERSION = "v0.5.2"
#   HERMES_STUDIO_VERSION   install that release instead of the latest
#   HERMES_STUDIO_NO_PATH   "1" = don't add the command to your PATH
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the built-in progress bar makes downloads ~10x slower

& {
  $repo = if ($env:HERMES_STUDIO_REPO) { $env:HERMES_STUDIO_REPO } else { "PabloTheThinker/hermes-studio" }
  function Say([string]$m) { Write-Host "-> $m" -ForegroundColor Yellow }
  function Ok([string]$m) { Write-Host "[OK] $m" -ForegroundColor Green }
  function Fail([string]$m) { Write-Host "[X] $m" -ForegroundColor Red; throw $m }

  if (-not [Environment]::Is64BitOperatingSystem) { Fail "Hermes Studio needs 64-bit Windows." }
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

  $ver = $env:HERMES_STUDIO_VERSION
  if ($env:HERMES_STUDIO_DOWNLOAD_BASE) {          # a mirror, or the test harness
    $base = $env:HERMES_STUDIO_DOWNLOAD_BASE.TrimEnd("/")
  } elseif ($ver) {
    if (-not $ver.StartsWith("v")) { $ver = "v$ver" }
    $base = "https://github.com/$repo/releases/download/$ver"
  } else {
    $base = "https://github.com/$repo/releases/latest/download"
  }

  Write-Host ""
  Write-Host "Hermes Studio" -NoNewline -ForegroundColor White
  Write-Host "  local video tools for people and AI agents" -ForegroundColor DarkGray
  Write-Host ""

  Say "Finding the $(if ($ver) { $ver } else { 'latest' }) release"
  try {
    $sums = (Invoke-WebRequest -UseBasicParsing "$base/SHA256SUMS.txt").Content
    if ($sums -is [byte[]]) { $sums = [Text.Encoding]::UTF8.GetString($sums) }
  } catch { Fail "Couldn't reach GitHub Releases ($base). Check your connection and try again." }
  $line = ($sums -split "`n") | Where-Object { $_ -match '\s(Hermes-Studio-Setup-[^\s]+\.exe)\s*$' } | Select-Object -First 1
  if (-not $line) { Fail "That release has no Windows installer listed in SHA256SUMS.txt." }
  $want, $name = ($line.Trim() -split '\s+', 2)
  $want = $want.ToLowerInvariant()

  $tmp = Join-Path $env:TEMP "hermes-studio-install"
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $file = Join-Path $tmp $name
  $have = if (Test-Path $file) { (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
  if ($have -ne $want) {
    Say "Downloading $name"
    try {
      if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
        Start-BitsTransfer -Source "$base/$name" -Destination $file -DisplayName "Hermes Studio"
      } else {
        Invoke-WebRequest -UseBasicParsing "$base/$name" -OutFile $file
      }
    } catch {
      Invoke-WebRequest -UseBasicParsing "$base/$name" -OutFile $file
    }
    $have = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($have -ne $want) {
      Remove-Item -Force $file -ErrorAction SilentlyContinue
      Fail "The download doesn't match its published checksum. Nothing was installed. Run the installer again."
    }
  }
  Ok "Checksum verified"

  # Close a running copy so the files can be replaced.
  Get-Process -Name "Hermes Studio" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

  Say "Installing for your user (no admin needed)"
  $p = Start-Process -FilePath $file -ArgumentList "/S", "/currentuser" -Wait -PassThru
  if ($p.ExitCode -ne 0) { Fail "The installer stopped with code $($p.ExitCode)." }
  $appDir = Join-Path $env:LOCALAPPDATA "Programs\Hermes Studio"
  $engine = Join-Path $appDir "resources\engine"
  if (-not (Test-Path (Join-Path $appDir "Hermes Studio.exe"))) { Fail "Install finished but the app isn't at $appDir." }
  Ok "Installed to $appDir"

  # The command: a tiny .cmd beside the engine, so it runs the Python that ships inside the app.
  $cmd = Join-Path $engine "hermes-studio.cmd"
  if (-not (Test-Path $cmd)) {
    Set-Content -Encoding ascii -Path $cmd -Value @(
      "@echo off",
      "setlocal",
      "set `"PATH=%~dp0bin;%~dp0python;%PATH%`"",
      "set `"HERMES_STUDIO_EXE=%~f0`"",
      "set PYTHONNOUSERSITE=1",
      "set PYTHONUTF8=1",
      "set PYTHONHOME=",
      "set PYTHONPATH=",
      "`"%~dp0python\python.exe`" -m hermes_studio %*"
    )
  }
  $v = (& $cmd --version 2>$null | Select-Object -Last 1)
  if (-not $v) { Fail "Installed, but the engine didn't start. Run: `"$cmd`" doctor" }

  if ($env:HERMES_STUDIO_NO_PATH -ne "1") {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    if (($userPath -split ";") -notcontains $engine) {
      [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(";") + ";" + $engine).TrimStart(";")), "User")
      Ok "Added the hermes-studio command to your PATH"
    }
    if (($env:Path -split ";") -notcontains $engine) { $env:Path = "$env:Path;$engine" }
  }
  Remove-Item -Force $file -ErrorAction SilentlyContinue

  Write-Host ""
  Write-Host "[OK] Hermes Studio is ready ($v)" -ForegroundColor Green
  Write-Host ""
  Write-Host "  Open the app      Start menu or desktop: Hermes Studio   (or: hermes-studio app)"
  Write-Host "  Check the setup   hermes-studio doctor"
  Write-Host "  Make shorts       hermes-studio run talk.mp4"
  Write-Host "  Use with your AI  hermes-studio mcp install claude   (or grok, codex, cursor, hermes)"
  Write-Host "  Update later      hermes-studio update   (or run this line again)"
  Write-Host ""
  Write-Host "  New terminals pick up the command automatically." -ForegroundColor DarkGray
  Write-Host ""
}
