$ErrorActionPreference = 'Stop'
$enc = New-Object System.Text.UTF8Encoding -ArgumentList $false
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$report = Join-Path $desktop 'BF1999_LAUNCH_REPORT.txt'
$lines = New-Object 'System.Collections.Generic.List[string]'
function Log([string]$s) { [void]$script:lines.Add($s); Write-Host $s }
function SaveReport { [IO.File]::WriteAllLines($script:report, $script:lines.ToArray(), [Text.Encoding]::UTF8) }
function AddPath([System.Collections.Generic.List[string]]$list,[string]$value) { if (![string]::IsNullOrWhiteSpace($value)) { $v=$value.Trim().Trim([char]34).Replace('/','\'); if (!$list.Contains($v)) { [void]$list.Add($v) } } }
try {
  $here = Split-Path -Parent $MyInvocation.MyCommand.Path
  $docs = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
  $userDir = Join-Path $docs 'Paradox Interactive\Hearts of Iron IV'
  $modDir = Join-Path $userDir 'mod'
  $candidates = New-Object 'System.Collections.Generic.List[string]'
  AddPath $candidates (Join-Path $here 'Balkan_Frontier_1999')
  AddPath $candidates (Join-Path $env:PUBLIC 'Documents\BF1999\Balkan_Frontier_1999')
  AddPath $candidates (Join-Path $env:PUBLIC 'Documents\ParadoxMods\Balkan_Frontier_1999')
  AddPath $candidates (Join-Path $modDir 'Balkan_Frontier_1999')
  AddPath $candidates (Join-Path $env:USERPROFILE 'Desktop\rrr\Balkan_Frontier_1999')
  $src = $null
  foreach ($c in $candidates) { if ((Test-Path (Join-Path $c 'descriptor.mod')) -and (Test-Path (Join-Path $c 'common\bookmarks'))) { $src=$c; break } }
  if (!$src) { $src=(Read-Host 'Full path to extracted Balkan_Frontier_1999 folder').Trim([char]34) }
  if (!(Test-Path (Join-Path $src 'descriptor.mod'))) { throw 'Mod folder or descriptor.mod not found.' }
  $bmDir=Join-Path $src 'common\bookmarks'
  $bmFiles=@(Get-ChildItem -LiteralPath $bmDir -Filter '*.txt' -File)
  $bmText=($bmFiles | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join [Environment]::NewLine
  $has1999=$bmText.Contains('1999.3.24.12')
  $has2001=$bmText.Contains('2001.1.1.12')
  if (!$has1999) { throw 'The extracted mod does not contain the 24 March 1999 bookmark.' }
  $steamRoots=New-Object 'System.Collections.Generic.List[string]'
  foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam','HKLM:\SOFTWARE\Valve\Steam')) { try { $reg=Get-ItemProperty $key -ErrorAction Stop; if ($reg.SteamPath) { AddPath $steamRoots ([string]$reg.SteamPath) }; if ($reg.InstallPath) { AddPath $steamRoots ([string]$reg.InstallPath) } } catch {} }
  AddPath $steamRoots 'D:\SteamLibrary'
  AddPath $steamRoots (Join-Path $env:ProgramFiles 'Steam')
  foreach ($root in @($steamRoots.ToArray())) { $vdf=Join-Path $root 'steamapps\libraryfolders.vdf'; if (Test-Path $vdf) { $txt=[IO.File]::ReadAllText($vdf); foreach ($m in [regex]::Matches($txt,'"path"\s*"([^"]+)"')) { AddPath $steamRoots $m.Groups[1].Value } } }
  $gameExe=$null
  foreach ($root in $steamRoots) { $p=Join-Path $root 'steamapps\common\Hearts of Iron IV\hoi4.exe'; if (Test-Path $p) { $gameExe=(Resolve-Path $p).Path; break } }
  if (!$gameExe) { $gameExe=(Read-Host 'Full path to hoi4.exe').Trim([char]34) }
  if (!(Test-Path -LiteralPath $gameExe -PathType Leaf)) { throw 'hoi4.exe not found.' }
  if (!(Get-Process steam -ErrorAction SilentlyContinue)) {
    $steamExe=$null; foreach ($root in $steamRoots) { $p=Join-Path $root 'steam.exe'; if (Test-Path $p) { $steamExe=$p; break } }
    if (!$steamExe) { throw 'Start Steam first; steam.exe could not be found.' }
    Start-Process $steamExe -ArgumentList '-silent' | Out-Null; Start-Sleep 8
  }
  $targetRoot=Join-Path $env:PUBLIC 'Documents\BF1999'
  $target=Join-Path $targetRoot 'Balkan_Frontier_1999'
  New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
  if ((Resolve-Path $src).Path.TrimEnd('\') -ine $target.TrimEnd('\')) {
    if (Test-Path $target) { Move-Item $target ($target+'.backup_'+(Get-Date -Format 'yyyyMMdd_HHmmss')) }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    & robocopy.exe $src $target /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw ('Copy failed; robocopy exit code '+$LASTEXITCODE) }
  }
  New-Item -ItemType Directory -Path $modDir -Force | Out-Null
  $descName='balkan_frontier_1999.mod'
  $inner=[IO.File]::ReadAllText((Join-Path $target 'descriptor.mod'))
  $inner=[regex]::Replace($inner,'(?m)^\s*path\s*=.*\r?\n?','')
  $pval=$target.Replace('\','/')
  $outer=$inner.Trim()+[Environment]::NewLine+'path="'+$pval+'"'+[Environment]::NewLine
  [IO.File]::WriteAllText((Join-Path $modDir $descName),$outer,$enc)
  $dlc=Join-Path $userDir 'dlc_load.json'
  New-Item -ItemType Directory -Path $userDir -Force | Out-Null
  $disabled=@()
  if (Test-Path $dlc) { $old=[IO.File]::ReadAllText($dlc); [IO.File]::WriteAllText($dlc+'.bf1999_backup_'+(Get-Date -Format 'yyyyMMdd_HHmmss'),$old,$enc); try { $obj=$old | ConvertFrom-Json; if ($obj.disabled_dlcs) { $disabled=@($obj.disabled_dlcs) } } catch { throw 'Existing dlc_load.json is invalid JSON.' } }
  $cfg=[ordered]@{ enabled_mods=@('mod/balkan_frontier_1999.mod'); disabled_dlcs=$disabled }
  [IO.File]::WriteAllText($dlc,(($cfg | ConvertTo-Json -Depth 8)+[Environment]::NewLine),$enc)
  $logs=Join-Path $userDir 'logs'; New-Item -ItemType Directory -Path $logs -Force | Out-Null
  $system=Join-Path $logs 'system.log'
  if (Test-Path $system) { Copy-Item $system ($system+'.bf1999_backup_'+(Get-Date -Format 'yyyyMMdd_HHmmss')) -Force; Remove-Item $system -Force }
  $gameDir=Split-Path $gameExe -Parent
  Log 'BALKAN FRONTIER 1999 - DIRECT START'
  Log ('Game: '+$gameExe); Log ('Mod folder: '+$target)
  Log ('Outer descriptor: '+(Join-Path $modDir $descName)); Log 'Enabled entry: mod/balkan_frontier_1999.mod'
  Log ('Bookmark 1999: '+$has1999); Log ('Bookmark 2001: '+$has2001)
  Log 'Active mod list written to dlc_load.json. Launching hoi4.exe directly.'; SaveReport
  Start-Process -FilePath $gameExe -WorkingDirectory $gameDir | Out-Null
  $deadline=(Get-Date).AddSeconds(90); $count=$null
  while ((Get-Date) -lt $deadline) { Start-Sleep 2; if (Test-Path $system) { $txt=[IO.File]::ReadAllText($system); $m=[regex]::Match($txt,'Active Mod Count:\s*(\d+)'); if ($m.Success) { $count=[int]$m.Groups[1].Value; if ($count -gt 0) { break } } } }
  if ($null -eq $count) { Log 'RESULT: system.log did not report Active Mod Count within 90 seconds.' } elseif ($count -eq 0) { Log 'RESULT: Active Mod Count is 0; the game did not load the mod.' } else { Log ('RESULT: SUCCESS - Active Mod Count: '+$count) }
  SaveReport; Write-Host ('Report: '+$report) -ForegroundColor Cyan
} catch { Log ('ERROR: '+$_.Exception.Message); SaveReport; Write-Host ('Report: '+$report) -ForegroundColor Red; exit 1 }