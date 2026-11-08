#requires -Version 5.1
<# Read-only launch/crash collection. Never starts/stops HOI4 or changes its files.
Only selected log tails and small textual crash reports may leave their folders.
#>
[CmdletBinding()]
param([string]$BaseDir, [string]$OutputDir = $PSScriptRoot,
      [string]$DocumentsDir, [switch]$LibraryOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Get-DiagProperty($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}
function Get-DiagPath([string]$Path) { return [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('/','\')) }
function Assert-DiagPlainPath([string]$Path) {
    $current = $Path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "LINK_SKIPPED: $current"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Add-DiagLine($Context, [string]$Text) { Write-Host $Text; $Context.Lines.Add($Text) }
function Read-DiagSmallText([string]$Path, [long]$Limit = 131072) {
    Assert-DiagPlainPath $Path
    if (-not [IO.File]::Exists($Path)) { return $null }
    if ((Get-Item -LiteralPath $Path).Length -gt $Limit) { throw "OVERSIZED_TEXT: $Path" }
    return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
}
function Read-DiagJson($Context, [string]$Path) {
    try {
        $text = Read-DiagSmallText $Path 262144
        if ($null -eq $text) { return $null }
        $object = $text | ConvertFrom-Json
        if ($object -isnot [pscustomobject]) { throw 'Not an object' }
        return $object
    } catch {
        # A JSON parse error can quote secret fields. Never copy its message.
        Add-DiagLine $Context "[JSON_UNAVAILABLE] $Path (missing permission, link, oversized or invalid JSON; contents omitted)"
        return $null
    }
}
function Get-DiagUtc([string]$Value) {
    if (-not $Value) { return $null }
    $value = $Value.Trim().Trim([char]'"').Trim([char]"'")
    $value = [regex]::Replace($value, '([+-][0-9]{2})([0-9]{2})$', '$1:$2')
    $parsed = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse($value, [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$parsed)) { return $parsed.UtcDateTime }
    return $null
}
function Get-DiagProfilePaths($Context, [string]$Expected, [string]$Game, [string]$Documents) {
    $result = [Collections.Generic.List[object]]::new()
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    function Add-Profile([string]$Path, [string]$Label) {
        if (-not $Path -or $result.Count -ge 9) { return }
        try {
            $full = Get-DiagPath $Path
            if ($full.Length -le 3) { return }
            if ($seen.Add($full)) { $result.Add([pscustomobject]@{ Path = $full; Label = $Label }) }
        } catch { Add-DiagLine $Context "[PROFILE_PATH_UNAVAILABLE] $Label" }
    }
    Add-Profile $Expected 'isolated'
    if (-not $Documents) { $Documents = [Environment]::GetFolderPath('MyDocuments') }
    if ($Documents) { Add-Profile (Join-Path $Documents 'Paradox Interactive/Hearts of Iron IV') 'documents' }
    foreach ($variable in @('USERPROFILE','OneDrive','OneDriveConsumer','OneDriveCommercial')) {
        $homePath = [Environment]::GetEnvironmentVariable($variable)
        if ($homePath) { Add-Profile (Join-Path $homePath 'Documents/Paradox Interactive/Hearts of Iron IV') $variable.ToLowerInvariant() }
    }
    if ($Game) {
        $userdir = Join-Path $Game 'userdir.txt'
        try {
            $value = Read-DiagSmallText $userdir 4096
            if ($value) {
                $value = $value.Trim().Trim([char]'"')
                if ($value -notmatch '[\r\n]' -and $value -notmatch '%') {
                    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $Game $value }
                    Add-DiagLine $Context "[USERDIR_SETTING] $userdir -> $value (read only; not proof the engine used it)"
                    Add-Profile $value 'userdir_setting'
                }
            }
        } catch { Add-DiagLine $Context "[USERDIR_SETTING_UNAVAILABLE] $userdir" }
        foreach ($name in @('launcher-settings.json','launcher/launcher-settings.json')) {
            $path = Join-Path $Game $name
            $settings = Read-DiagJson $Context $path
            $value = Get-DiagProperty $settings 'gameDataPath'
            if ($value -is [string] -and $value) {
                Add-DiagLine $Context "[LAUNCHER_DATA_SETTING] $path -> $value (only this field; not proof the engine used it)"
                if ($Documents) { $value = $value.Replace('%USER_DOCUMENTS%', $Documents) }
                if ($value -notmatch '%') {
                    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $Game $value }
                    Add-Profile $value 'launcher_setting'
                }
            }
        }
        Add-Profile $Game 'game_folder'
    }
    return $result.ToArray()
}
function Get-DiagUserdirArgument([string]$CommandLine) {
    foreach ($pattern in @('"--?userdir=([^"]+)"', '--?userdir="([^"]+)"', '--?userdir(?:=|\s+)([^\s"]+)')) {
        $match = [regex]::Match($CommandLine, $pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($match.Success) { return $match.Groups[1].Value }
    }
    return '(not visible)'
}
function Write-DiagProcesses($Context) {
    try {
        $processes = @(Get-Process -Name 'hoi4' -ErrorAction SilentlyContinue)
        Add-DiagLine $Context "[PROCESS_SNAPSHOT_NOW] hoi4_count=$($processes.Count); this cannot recover the exit code of a past process."
        foreach ($process in $processes | Select-Object -First 8) {
            $path = '(unavailable)'
            $started = '(unavailable)'
            try { $path = $process.Path; $started = $process.StartTime.ToUniversalTime().ToString('o') } catch {}
            Add-DiagLine $Context "[PROCESS] pid=$($process.Id); started_utc=$started; exe=$path"
        }
        if ($processes.Count -gt 0 -and (Get-Command Get-CimInstance -ErrorAction SilentlyContinue)) {
            foreach ($entry in @(Get-CimInstance Win32_Process -Filter "Name='hoi4.exe'" -ErrorAction Stop) | Select-Object -First 8) {
                # Never export a complete command line or unrelated processes.
                Add-DiagLine $Context "[PROCESS_USERDIR_ARGUMENT] pid=$($entry.ProcessId); userdir=$(Get-DiagUserdirArgument $entry.CommandLine)"
            }
        }
    } catch { Add-DiagLine $Context '[PROCESS_QUERY_UNAVAILABLE] No elevated privileges are requested.' }
}
function Copy-DiagText($Context, [string]$Source, [string]$Relative, [long]$Limit, [switch]$Tail, [switch]$RedactFields) {
    Assert-DiagPlainPath $Source
    $item = Get-Item -LiteralPath $Source
    if (-not $Tail -and $item.Length -gt $Limit) { Add-DiagLine $Context "[OVERSIZED_TEXT_SKIPPED] $Source"; return }
    $bytes = [Math]::Min([long]$item.Length, $Limit)
    if ($bytes -gt $Context.Remaining) { Add-DiagLine $Context '[SIZE_BUDGET_REACHED] Additional contents omitted.'; return }
    $destination = Join-Path $Context.Stage $Relative
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    if ($RedactFields) {
        $text = Read-DiagSmallText $Source $Limit
        $text = [regex]::Replace($text, '(?mi)^(\s*(?:LaunchArguments|CommandLine|SteamAuthTicket|Access[_-]?Token|Password|Auth[_-]?Token)\s*:)[^\r\n]*(?:\r?\n[ \t]+[^\r\n]*)*', '$1 [omitted]')
        $safe = [Text.Encoding]::UTF8.GetBytes($text)
        if ($safe.Length -gt $Limit -or $safe.Length -gt $Context.Remaining) { Add-DiagLine $Context "[SANITIZED_TEXT_TOO_LARGE] $Source"; return }
        [IO.File]::WriteAllBytes($destination, $safe)
        $Context.Remaining -= $safe.Length
        $Context.Files += 1
        $Context.Sources.Add("$Relative | source=$Source | modified_utc=$($item.LastWriteTimeUtc.ToString('o')) | original_bytes=$($item.Length) | sanitized_fields=true")
        return
    }
    $stream = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        if ($Tail) { [void]$stream.Seek([Math]::Max([long]0, $stream.Length - $Limit), [IO.SeekOrigin]::Begin) }
        $output = [IO.File]::Create($destination)
        try {
            $buffer = New-Object byte[] 16384
            $remaining = $bytes
            while ($remaining -gt 0) {
                $read = $stream.Read($buffer, 0, [int][Math]::Min($buffer.Length, $remaining))
                if ($read -eq 0) { break }
                $output.Write($buffer, 0, $read)
                $remaining -= $read
            }
        } finally { $output.Dispose() }
    } finally { $stream.Dispose() }
    $Context.Remaining -= $bytes
    $Context.Files += 1
    $Context.Sources.Add("$Relative | source=$Source | modified_utc=$($item.LastWriteTimeUtc.ToString('o')) | original_bytes=$($item.Length) | copied_at_most=$bytes")
}
function Collect-DiagProfile($Context, $Profile, [int]$Index) {
    $root = $Profile.Path
    Add-DiagLine $Context "[PROFILE] $($Profile.Label): $root"
    Assert-DiagPlainPath $root
    if (-not [IO.Directory]::Exists($root)) { Add-DiagLine $Context '[PROFILE_MISSING]'; return }
    $load = Read-DiagJson $Context (Join-Path $root 'dlc_load.json')
    if ($load) {
        $mods = @(Get-DiagProperty $load 'enabled_mods' @())
        $disabled = @(Get-DiagProperty $load 'disabled_dlcs' @())
        Add-DiagLine $Context "[PROFILE_CONFIG_ONLY] enabled_mods=$($mods -join ', '); disabled_entries=$($disabled.Count); NOT a runtime confirmation."
    }
    foreach ($directory in @('map','history','common','events','localisation','gfx','interface')) {
        if ([IO.Directory]::Exists((Join-Path $root $directory))) { Add-DiagLine $Context "[CONTENT_DIRECTORY_PRESENT] $root/$directory (metadata only; files are not collected)" }
    }
    foreach ($kind in @('system','setup','error')) {
        $path = Join-Path $root "logs/$kind.log"
        Assert-DiagPlainPath $path
        if (-not [IO.File]::Exists($path)) { Add-DiagLine $Context "[LOG_MISSING] $path"; continue }
        $item = Get-Item -LiteralPath $path
        if ($null -eq $Context.Started -or $item.LastWriteTimeUtc -lt $Context.Started.AddSeconds(-3) -or $item.LastWriteTimeUtc -gt [DateTime]::UtcNow.AddMinutes(2)) {
            Add-DiagLine $Context "[OLD_OR_UNBOUND_LOG_SKIPPED] $path | modified_utc=$($item.LastWriteTimeUtc.ToString('o'))"; continue
        }
        Add-DiagLine $Context "[FRESH_LOG_CANDIDATE] $path (time match only, profile identity must be checked)"
        if ($Profile.Label -ne 'isolated') { Add-DiagLine $Context '[OTHER_LOCATION] Fresh log is outside the requested isolated profile; no automatic redirection or activation is performed.' }
        Copy-DiagText $Context $path ("profiles/{0:D2}_{1}/logs/{2}.log" -f $Index,$Profile.Label,$kind) 1048576 -Tail
    }
    $crashes = Join-Path $root 'crashes'
    Assert-DiagPlainPath $crashes
    if (-not [IO.Directory]::Exists($crashes)) { return }
    $recent = @(Get-ChildItem -LiteralPath $crashes -Directory -Force | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 40)
    foreach ($folder in $recent) {
        if ($Context.Crashes -ge 4) { return }
        Assert-DiagPlainPath $folder.FullName
        $metaPath = Join-Path $folder.FullName 'meta.yml'
        $exceptionPath = Join-Path $folder.FullName 'exception.txt'
        try {
            $meta = Read-DiagSmallText $metaPath
            $exception = Read-DiagSmallText $exceptionPath
        } catch { Add-DiagLine $Context "[CRASH_TEXT_UNAVAILABLE] $($folder.FullName) (permission, link or oversized text)"; continue }
        $declared = $null
        $match = [regex]::Match([string]$meta, '(?m)^DateTime:\s*([^\r\n]+)')
        if (-not $match.Success) { $match = [regex]::Match([string]$exception, '(?m)^Date/Time:\s*([^\r\n]+)') }
        if ($match.Success) { $declared = Get-DiagUtc $match.Groups[1].Value }
        if ($null -eq $Context.Started) { Add-DiagLine $Context "[UNBOUND_CRASH_SKIPPED] $($folder.FullName)"; continue }
        if ($null -ne $declared -and ($declared -lt $Context.Started.AddSeconds(-3) -or $declared -gt [DateTime]::UtcNow.AddMinutes(2))) {
            Add-DiagLine $Context "[OLD_CRASH_EMBEDDED_DATE_SKIPPED] $($folder.FullName) | crash_utc=$($declared.ToString('o'))"; continue
        }
        if (($folder.LastWriteTimeUtc -lt $Context.Started.AddSeconds(-3) -or $folder.LastWriteTimeUtc -gt [DateTime]::UtcNow.AddMinutes(2)) -and $null -eq $declared) {
            Add-DiagLine $Context "[OLD_CRASH_MTIME_SKIPPED] $($folder.FullName)"; continue
        }
        if ($null -eq $meta -and $null -eq $exception) { continue }
        $Context.Crashes += 1
        $prefix = "profiles/{0:D2}_{1}/crash_{2:D2}" -f $Index,$Profile.Label,$Context.Crashes
        Add-DiagLine $Context "[CRASH_CANDIDATE] $($folder.FullName); declared_utc=$declared; this is evidence, not a diagnosed cause."
        if ($null -eq $declared) { Add-DiagLine $Context '[CRASH_DATE_UNVERIFIED] Only the filesystem modification time links this candidate.' }
        foreach ($name in @('meta.yml','exception.txt')) {
            $path = Join-Path $folder.FullName $name
            if ([IO.File]::Exists($path)) { Copy-DiagText $Context $path "$prefix/$name" 131072 -RedactFields }
        }
        foreach ($kind in @('system','setup','error')) {
            $path = Join-Path $folder.FullName "logs/$kind.log"
            if ([IO.File]::Exists($path)) { Copy-DiagText $Context $path "$prefix/logs/$kind.log" 1048576 -Tail }
        }
    }
}
function Export-ReworklCrashDiagnostics([string]$Root, [string]$Output, [string]$Documents) {
    if (-not $Root) {
        if (-not $env:PUBLIC) { throw 'PUBLIC is not defined. Use -BaseDir with your existing BAT installation folder.' }
        $Root = Join-Path $env:PUBLIC 'HOI4MODS'
    }
    $Root = Get-DiagPath $Root
    $Output = Get-DiagPath $Output
    Assert-DiagPlainPath $Output
    [void][IO.Directory]::CreateDirectory($Output)
    $token = (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $stage = Join-Path ([IO.Path]::GetTempPath()) ('reworkl-crash-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($stage)
    $context = [pscustomobject]@{ Stage=$stage; Lines=[Collections.Generic.List[string]]::new(); Sources=[Collections.Generic.List[string]]::new(); Remaining=[long]8388608; Files=0; Crashes=0; Started=$null }
    $report = Join-Path $Output "REWORKL_CRASH_REPORT_$token.txt"
    $zip = Join-Path $Output "REWORKL_CRASH_DIAGNOSTICS_$token.zip"
    try {
        Add-DiagLine $context '[COLLECTOR_VERSION] 1 / READ ONLY. This tool does not launch, install, redirect, repair or stop the game.'
        Add-DiagLine $context "[COLLECTED_UTC] $([DateTime]::UtcNow.ToString('o'))"
        $expected = Join-Path $Root 'reworkl-userdata'
        $state = Read-DiagJson $context (Join-Path $Root 'reworkl-bat-state.json')
        if ($state -and ((Get-DiagProperty $state 'schema') -ne 1 -or
            (Get-DiagProperty $state 'user_dir') -ine $expected -or
            (Get-DiagProperty $state 'target') -ine (Join-Path $Root 'reworkl'))) {
            Add-DiagLine $context '[STATE_LAYOUT_MISMATCH] The receipt is not for this BAT base. No game paths or launch time are trusted.'
            $state = $null
        }
        $game = Get-DiagProperty $state 'game_dir'
        $version = Get-DiagProperty $state 'version' '(unknown)'
        $context.Started = Get-DiagUtc (Get-DiagProperty $state 'last_launch_utc')
        if ($context.Started -and $context.Started -gt [DateTime]::UtcNow.AddMinutes(2)) { $context.Started = $null }
        Add-DiagLine $context "[BAT_EXPECTED_USER_DIR] $expected"
        Add-DiagLine $context "[BAT_INSTALLED_VERSION] $version"
        Add-DiagLine $context "[BAT_GAME_DIR] $game"
        Add-DiagLine $context "[BAT_LAST_LAUNCH_UTC] $($context.Started)"
        if ($null -eq $context.Started) { Add-DiagLine $context '[NO_VALID_LAUNCH_TIME] No log/crash contents can be attributed to the last BAT run; contents will be skipped.' }
        Write-DiagProcesses $context
        $profiles = @(Get-DiagProfilePaths $context $expected $game $Documents)
        for ($i = 0; $i -lt $profiles.Count; $i++) {
            try { Collect-DiagProfile $context $profiles[$i] $i }
            catch { Add-DiagLine $context "[PROFILE_COLLECTION_INCOMPLETE] $($profiles[$i].Path) (permission, link or oversized text; other profiles continue)" }
        }
        Add-DiagLine $context "[COLLECTED_TEXT_FILES] $($context.Files); crash_candidates=$($context.Crashes)"
        Add-DiagLine $context '[RESULT] DIAGNOSTIC COLLECTION ONLY. No successful game load, zero-DLC mode or crash cause is claimed.'
        Add-DiagLine $context '[PRIVACY] Review before sharing: contains selected game/crash text, paths, times and possibly hardware/mod lists; no saves, dumps, account databases or full environment/command lines.'
        $encoding = [Text.UTF8Encoding]::new($false)
        [IO.File]::WriteAllText($report, ($context.Lines -join "`r`n"), $encoding)
        [IO.File]::Copy($report, (Join-Path $stage 'REPORT.txt'))
        [IO.File]::WriteAllText((Join-Path $stage 'SOURCES.txt'), ($context.Sources -join "`r`n"), $encoding)
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip)
        Write-Host "[SEND_THIS_ZIP] $zip"
        Write-Host "[TEXT_REPORT] $report"
        return [pscustomobject]@{ Zip=$zip; Report=$report; Collected=$context.Files }
    } finally { if ([IO.Directory]::Exists($stage)) { [IO.Directory]::Delete($stage, $true) } }
}
if (-not $LibraryOnly) {
    try { [void](Export-ReworklCrashDiagnostics $BaseDir $OutputDir $DocumentsDir); exit 0 }
    catch { Write-Host "[COLLECTOR_ERROR] $($_.Exception.Message)"; Write-Host 'No game or save files were changed. Send a screenshot of this window.'; exit 1 }
}
