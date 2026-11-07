#requires -Version 5.1
<# Only Reworkl localisation is updated. No launch/settings/save changes. #>
[CmdletBinding()]
param([string]$ModDir, [string]$BaseDir, [switch]$CheckOnly, [switch]$LibraryOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$script:RuRoot = $PSScriptRoot
$script:RuVersion = 'RU2-2026-11-07'
$script:RuAllowed = @(
    'localisation/replace/reworkl_countries_l_russian.yml',
    'localisation/replace/reworkl_loading_l_russian.yml',
    'localisation/russian/reworkl_integration_l_russian.yml',
    'localisation/russian/reworkl_missing_l_russian.yml',
    'localisation/russian/reworkl_music_l_russian.yml',
    'localisation/russian/reworkl_serbia_l_russian.yml',
    'localisation/russian/y89_mod_l_russian.yml',
    'localisation/replace/zzzzzz_reworkl_russian_for_english_l_english.yml'
)
function Ru-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('/','\'))
}
function Ru-PlainPath([string]$Path) {
    $current = $Path
    while ($current) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Links/junctions are not supported: $current"
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Ru-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Ru-Target([string]$Requested, [string]$Base) {
    if (-not $Requested) {
        if (-not $Base) {
            if (-not $env:PUBLIC) { throw 'PUBLIC is unavailable. Pass -ModDir with the installed Reworkl folder.' }
            $Base = Join-Path $env:PUBLIC 'HOI4MODS'
        }
        $Base = Ru-FullPath $Base
        Ru-PlainPath $Base
        $Requested = Join-Path $Base 'reworkl'
        $statePath = Join-Path $Base 'reworkl-bat-state.json'
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            $state = [IO.File]::ReadAllText($statePath, [Text.Encoding]::UTF8) | ConvertFrom-Json
            if ($state.schema -ne 1 -or -not ([string]$state.target).Equals($Requested, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'The BAT installation record does not match this folder. No files changed. Use -ModDir explicitly.'
            }
        }
    }
    $target = Ru-FullPath $Requested
    if ($target.Length -le 3) { throw 'A disk root cannot be a mod folder.' }
    Ru-PlainPath $target
    foreach ($required in @('descriptor.mod','common/bookmarks/Y89_bookmarks.txt','common/national_focus/serbia_tree1.txt')) {
        $path = Join-Path $target $required
        Ru-PlainPath $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Installed Reworkl not found: $path. No empty mod folder will be created." }
    }
    $descriptor = [IO.File]::ReadAllText((Join-Path $target 'descriptor.mod'), [Text.Encoding]::UTF8)
    if ($descriptor -notmatch '(?mi)^\s*name\s*=\s*"Reworkl\b') { throw 'The target is not a recognised Reworkl installation.' }
    return $target
}
function Ru-Package([string]$PackageRoot) {
    $manifestPath = Join-Path $PackageRoot 'russian-manifest.json'
    Ru-PlainPath $manifestPath
    $manifest = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.revision -ne $script:RuVersion -or @($manifest.files).Count -ne $script:RuAllowed.Count) {
        throw 'Wrong/incomplete RU2 package. Extract the WHOLE new ZIP before running APPLY_RUSSIAN.bat.'
    }
    $seen = @{}
    foreach ($file in $manifest.files) {
        $relative = [string]$file.path
        if ($script:RuAllowed -cnotcontains $relative -or $seen.ContainsKey($relative) -or [string]$file.sha256 -cnotmatch '^[a-f0-9]{64}$') {
            throw "Invalid/duplicate localisation manifest entry: $relative"
        }
        $seen[$relative] = $true
        $source = Join-Path $PackageRoot $relative
        Ru-PlainPath $source
        if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or (Ru-Hash $source) -cne [string]$file.sha256) {
            throw "Missing/damaged package file: $relative. Extract the whole new ZIP. No files changed."
        }
    }
    return $manifest
}
function Ru-CopyFile([string]$Source, [string]$Destination) {
    # The game must be closed. Every original file has already been backed up;
    # a failed copy/hash verification rolls back the whole localisation update.
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Destination))
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}
function Invoke-RussianUpdate([string]$PackageRoot, [string]$RequestedMod, [string]$RequestedBase, [bool]$ReadOnly) {
    $report = [Collections.Generic.List[string]]::new()
    $report.Add("[RU_FIX_VERSION] $script:RuVersion")
    $report.Add('[ENGINE_TEST] NOT_PERFORMED; file checks are not proof of in-game loading.')
    $backup = $null
    $changed = @()
    try {
        $manifest = Ru-Package $PackageRoot
        $target = Ru-Target $RequestedMod $RequestedBase
        $report.Add("[TARGET_MOD] $target")
        $report.Add('[LANGUAGES] Mod texts: Russian and English display layers -> Russian.')
        $report.Add('[BASE_GAME_MENU] Unchanged. An English main menu can remain English.')
        foreach ($file in $manifest.files) { Ru-PlainPath (Join-Path $target ([string]$file.path)) }
        if (-not $ReadOnly) {
            if (Get-Process -Name 'hoi4','dowser','Paradox Launcher','ParadoxLauncher' -ErrorAction SilentlyContinue) {
                throw 'Close HOI4 and Paradox Launcher first. No processes were stopped and no mod files changed.'
            }
            $backup = Join-Path ([IO.Path]::GetDirectoryName($target)) ('reworkl-russian-backups/' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
            Ru-PlainPath $backup
            [void][IO.Directory]::CreateDirectory($backup)
            $records = @()
            foreach ($file in $manifest.files) {
                $relative = [string]$file.path
                $dest = Join-Path $target $relative
                if (Test-Path -LiteralPath $dest -PathType Container) { throw "A destination is a directory: $dest" }
                $existed = Test-Path -LiteralPath $dest -PathType Leaf
                $oldHash = $null
                if ($existed) {
                    $oldHash = Ru-Hash $dest
                    $saved = Join-Path $backup ('files/' + $relative)
                    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved))
                    Copy-Item -LiteralPath $dest -Destination $saved
                    if ((Ru-Hash $saved) -cne $oldHash) { throw "Backup verification failed: $relative. No mod files changed." }
                }
                $records += [pscustomobject]@{ path = $relative; existed = $existed; old_sha256 = $oldHash; patch_sha256 = [string]$file.sha256 }
            }
            $backupInfo = [pscustomobject]@{ schema = 1; target = $target; revision = $script:RuVersion; files = @($records) }
            [IO.File]::WriteAllText((Join-Path $backup 'backup.json'), (ConvertTo-Json -InputObject $backupInfo -Depth 8), [Text.UTF8Encoding]::new($true))
            $report.Add("[BACKUP] $backup")
            foreach ($record in $records) {
                $changed += $record
                Ru-CopyFile (Join-Path $PackageRoot $record.path) (Join-Path $target $record.path)
                if ((Ru-Hash (Join-Path $target $record.path)) -cne $record.patch_sha256) { throw "Installed hash mismatch: $($record.path)" }
            }
        }
        $allMatch = $true
        foreach ($file in $manifest.files) {
            $dest = Join-Path $target ([string]$file.path)
            if ((Test-Path -LiteralPath $dest -PathType Leaf) -and (Ru-Hash $dest) -ceq [string]$file.sha256) {
                $report.Add("[MATCH] $($file.path)")
            } else { $allMatch = $false; $report.Add("[MISSING_OR_OLD] $($file.path)") }
        }
        if (-not $allMatch) { throw 'Some localisation files are missing or old. Read the report.' }
        $report.Add('[RESULT] LOCALISATION_FILES_VERIFIED')
        $report.Add('[UNCHANGED] Game mechanics, saves, launch BAT, descriptor, settings, DLC, userdir.')
        $report.Add('[VISIBLE_CHECK] In Serbia 1936, the worker bonus focus should have its Russian name.')
        return 0
    } catch {
        $failure = $_.Exception.Message
        if ($changed.Count -gt 0) {
            $rolledBack = $true
            for ($i = $changed.Count - 1; $i -ge 0; $i--) {
                $record = $changed[$i]
                $dest = Join-Path $target $record.path
                try {
                    if ($record.existed) {
                        Copy-Item -LiteralPath (Join-Path $backup ('files/' + $record.path)) -Destination $dest -Force
                        if ((Ru-Hash $dest) -cne $record.old_sha256) { throw 'Restored hash mismatch' }
                    } elseif (Test-Path -LiteralPath $dest -PathType Leaf) {
                        # Only the known new YML paths from this transaction.
                        Remove-Item -LiteralPath $dest -Force
                    }
                } catch { $rolledBack = $false; $report.Add("[RESTORE_ERROR] $($record.path): $($_.Exception.Message)") }
            }
            if ($rolledBack) { $report.Add('[ROLLBACK] Previous localisation files restored.') }
            else { $report.Add("[RECOVERY_REQUIRED] Backups retained at $backup. Do not reinstall the game.") }
        }
        $report.Add("[ERROR] $failure")
        return 1
    } finally {
        $report | ForEach-Object { Write-Host $_ }
        try {
            [IO.File]::WriteAllLines((Join-Path $PackageRoot 'REWORKL_RUSSIAN_REPORT.txt'), $report.ToArray(), [Text.UTF8Encoding]::new($true))
        } catch { Write-Host "[REPORT_WARNING] $($_.Exception.Message)" }
    }
}
if (-not $LibraryOnly) {
    exit (Invoke-RussianUpdate $script:RuRoot $ModDir $BaseDir ([bool]$CheckOnly))
}
