#requires -Version 5.1
<#
Reworkl BAT workflow. Windows PowerShell 5.1+, no Python/admin by default.
Install/Launch use an isolated ASCII user directory and disable discovered DLC.
Check is read-only except for an explicitly requested report file.
PatchLauncher is OPTIONAL and reversible; normal installation never edits the game.
#>
[CmdletBinding()]
param(
    [ValidateSet('Install','Launch','Start2026','Check','PatchLauncher','RestoreLauncher')][string]$Action = 'Install',
    [string]$Source,
    [string]$GameDir,
    [string]$BaseDir,
    [string]$ReportPath,
    [switch]$DryRun,
    [switch]$NonInteractive,
    [switch]$LibraryOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$script:ToolRoot = $PSScriptRoot
$script:ToolVersion = '2.0.0-alpha3'
$script:Utf8NoBom = [Text.UTF8Encoding]::new($false)
$script:PayloadDirs = @('common','events','gfx','history','interface','localisation','map','music')
$script:PayloadExtensions = @('.txt','.lua','.mod','.gfx','.gui','.yml','.asset','.dds','.tga','.png','.ogg','.bmp','.csv','.map')

$worldLibrary = Join-Path $PSScriptRoot 'Reworkl-World.ps1'
if (Test-Path -LiteralPath $worldLibrary -PathType Leaf) { . $worldLibrary }

function Full-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('/','\'))
}
function Get-Property($Object, [string]$Name, $Default = $null) {
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}
function Set-Property($Object, [string]$Name, $Value) {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
}
function Test-Link([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
}
function Assert-PlainPath([string]$Path) {
    $current = $Path
    while ($current) {
        if (Test-Link $current) { throw "Symbolic link/junction is not supported: $current" }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Is-Within([string]$Child, [string]$Parent) {
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function Get-Layout([string]$Root) {
    if (-not $Root) {
        if (-not $env:PUBLIC) { throw 'PUBLIC is not defined. Pass -BaseDir with an ASCII path.' }
        $Root = Join-Path $env:PUBLIC 'HOI4MODS'
    }
    $Root = Full-Path $Root
    if ($Root -match '[^\x20-\x7E]' -or $Root.Length -le 3) {
        throw 'BaseDir must be a non-root, ASCII-only folder, e.g. C:\Users\Public\HOI4MODS.'
    }
    Assert-PlainPath $Root
    return [pscustomobject]@{
        Base = $Root
        Target = Join-Path $Root 'reworkl'
        User = Join-Path $Root 'reworkl-userdata'
        State = Join-Path $Root 'reworkl-bat-state.json'
        Backups = Join-Path $Root 'reworkl-backups'
        PatchState = Join-Path $Root 'reworkl-plan-b.json'
    }
}
function Assert-Closed {
    if (Get-Process -Name 'hoi4','dowser','Paradox Launcher','ParadoxLauncher' -ErrorAction SilentlyContinue) {
        throw 'Close HOI4 and Paradox Launcher first. Keep Steam running. No processes were killed.'
    }
}
function Read-Json([string]$Path) {
    $value = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ($null -eq $value -or $value -isnot [pscustomobject]) { throw "Expected a JSON object: $Path" }
    return $value
}
function File-Hash([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Write-Atomic([string]$Path, [string]$Text) {
    $parent = [IO.Path]::GetDirectoryName($Path)
    [void][IO.Directory]::CreateDirectory($parent)
    $token = [guid]::NewGuid().ToString('N')
    $temporary = Join-Path $parent ('.reworkl-' + $token + '.tmp')
    $previous = Join-Path $parent ('.reworkl-' + $token + '.previous')
    $replaced = $false
    try {
        [IO.File]::WriteAllText($temporary, $Text, $script:Utf8NoBom)
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            # Windows PowerShell 5.1 can marshal a $null string argument as
            # an empty path. A real same-directory backup avoids that binder
            # ambiguity and retains the original until replacement succeeds.
            [IO.File]::Replace($temporary, $Path, $previous)
            $replaced = $true
        } else { [IO.File]::Move($temporary, $Path) }
    } catch {
        throw "Atomic write failed for '$Path': $($_.Exception.Message). Recovery copy, if created: '$previous'."
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) { [IO.File]::Delete($temporary) }
        if ($replaced -and (Test-Path -LiteralPath $previous -PathType Leaf)) { [IO.File]::Delete($previous) }
    }
}
function Backup-Files($Layout, [string[]]$Paths) {
    $folder = Join-Path $Layout.Backups ((Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($folder)
    $items = @()
    foreach ($path in $Paths) {
        Assert-PlainPath $path
        if (Test-Path -LiteralPath $path -PathType Container) { throw "Expected a file, found a directory: $path" }
        $exists = Test-Path -LiteralPath $path -PathType Leaf
        $backup = Join-Path $folder ($items.Count.ToString() + '.original')
        if ($exists) { [IO.File]::Copy($path, $backup) }
        $items += [pscustomobject]@{ path = $path; existed = [bool]$exists; backup = $backup }
    }
    Write-Atomic (Join-Path $folder 'files.json') (ConvertTo-Json -InputObject $items -Depth 10)
    return [pscustomobject]@{ Folder = $folder; Items = $items }
}
function Restore-Files($Backup) {
    foreach ($item in $Backup.Items) {
        if ($item.existed) { [IO.File]::Copy($item.backup, $item.path, $true) }
        elseif (Test-Path -LiteralPath $item.path -PathType Leaf) { [IO.File]::Delete($item.path) }
    }
}
function Find-Game([string]$Requested, [bool]$NoPrompt) {
    $candidates = @()
    if ($Requested) { $candidates += $Requested.Trim().Trim([char]'"') }
    else {
        if ($env:REWORKL_GAME_DIR) { $candidates += $env:REWORKL_GAME_DIR }
        $registry = @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 394360',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 394360'
        )
        foreach ($key in $registry) {
            $item = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($null -ne $item) {
                $location = Get-Property $item 'InstallLocation'
                if ($location) { $candidates += $location }
            }
        }
        $steamRoots = @()
        $steam = Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
        if ($null -ne $steam) {
            $location = Get-Property $steam 'SteamPath'
            if ($location) { $steamRoots += $location }
        }
        foreach ($variable in @('ProgramFiles(x86)','ProgramFiles')) {
            $folder = [Environment]::GetEnvironmentVariable($variable)
            if ($folder) { $steamRoots += Join-Path $folder 'Steam' }
        }
        foreach ($steamRoot in @($steamRoots | Select-Object -Unique)) {
            $libraries = @($steamRoot)
            $vdf = Join-Path $steamRoot 'steamapps/libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf -PathType Leaf) {
                $text = [IO.File]::ReadAllText($vdf)
                foreach ($match in [regex]::Matches($text, '"(?:path|[0-9]+)"\s*"([^"\r\n]+)"')) {
                    $candidate = $match.Groups[1].Value.Replace('\\','\')
                    if ([IO.Path]::IsPathRooted($candidate)) { $libraries += $candidate }
                }
            }
            foreach ($library in $libraries) {
                $candidates += Join-Path $library 'steamapps/common/Hearts of Iron IV'
                $manifest = Join-Path $library 'steamapps/appmanifest_394360.acf'
                if (Test-Path -LiteralPath $manifest -PathType Leaf) {
                    $match = [regex]::Match([IO.File]::ReadAllText($manifest), '"installdir"\s*"([^"\r\n]+)"')
                    if ($match.Success) { $candidates += Join-Path (Join-Path $library 'steamapps/common') $match.Groups[1].Value }
                }
            }
        }
    }
    foreach ($candidate in $candidates) {
        $path = Full-Path $candidate
        if ([IO.Path]::GetFileName($path) -ieq 'hoi4.exe') { $path = [IO.Path]::GetDirectoryName($path) }
        if (Test-Path -LiteralPath (Join-Path $path 'hoi4.exe') -PathType Leaf) { return $path }
    }
    if ($Requested -or $NoPrompt) { throw 'hoi4.exe not found. Pass -GameDir "folder containing hoi4.exe".' }
    Write-Host 'Drag hoi4.exe into this window, or paste its full path. Steam must remain running.'
    return Find-Game (Read-Host 'hoi4.exe') $true
}
function Get-DlcFiles([string]$Game) {
    foreach ($name in @('dlc','dlc_metadata')) {
        $folder = Join-Path $Game $name
        if (Test-Path -LiteralPath $folder -PathType Container) {
            foreach ($file in @(Get-ChildItem -LiteralPath $folder -Filter '*.dlc' -File -Recurse -Force)) {
                $file.FullName.Substring($Game.Length + 1).Replace('\','/')
            }
        }
    }
}
function Get-Source([string]$Requested) {
    $candidates = @($Requested)
    if (-not $Requested) { $candidates = @((Join-Path $script:ToolRoot 'reworkl'), $script:ToolRoot, (Join-Path $script:ToolRoot '../..')) }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'descriptor.mod') -PathType Leaf)) { return Full-Path $candidate }
    }
    throw 'Extract the WHOLE ZIP. Put the BAT files beside the reworkl folder, or inside an existing reworkl folder.'
}
function Read-Descriptor([string]$Folder) {
    $path = Join-Path $Folder 'descriptor.mod'
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $versions = [regex]::Matches($text, '(?m)^\s*version\s*=\s*"([0-9][A-Za-z0-9_.-]*)"\s*$')
    $names = [regex]::Matches($text, '(?m)^\s*name\s*=\s*"([^"\r\n]+)"\s*$')
    if ($versions.Count -ne 1 -or $names.Count -ne 1 -or $names[0].Groups[1].Value -notmatch '^Reworkl' -or
        $text -match '(?m)^\s*(?:path|remote_file_id|dependencies)\s*=' -or
        $text -notmatch 'replace_path\s*=\s*"common/bookmarks"') { throw 'Invalid portable Reworkl descriptor. No DLC/mod dependencies or embedded path are allowed.' }
    $book = [IO.File]::ReadAllText((Join-Path $Folder 'common/bookmarks/Y89_bookmarks.txt'), [Text.Encoding]::UTF8)
    $world = $book -match '2026\.1\.1' -and $book -match 'RW26_BOOKMARK_2026'
    $legacy = $book -match '1989\.1\.1' -and $book -match 'Y89_BOOKMARK_1989'
    if ($book -notmatch '1936\.1\.1' -or ($world -eq $legacy)) { throw 'The Reworkl bookmarks are missing or incomplete.' }
    if ($versions[0].Groups[1].Value -like '2.*' -and -not $world) { throw 'Reworkl 2.x requires the 2026 world bookmark.' }
    $worldPlan = $null
    if ($world) {
        if (-not (Get-Command Get-ReworklWorldStatePlan -ErrorAction SilentlyContinue)) { throw 'Missing Reworkl-World.ps1. Extract the complete installer repair ZIP beside this BAT.' }
        $worldPlan = Get-ReworklWorldStatePlan $Folder $script:ToolRoot
        foreach ($relative in @('common/bookmarks/the_gathering_storm.txt','common/bookmarks/blitzkrieg.txt','map/provinces.bmp','map/definition.csv','map/default.map','map/terrain.bmp','map/rivers.bmp','map/heightmap.bmp','map/trees.bmp','map/cities.bmp','map/world_normal.bmp','map/unitstacks.txt','map/reworkl_world_manifest.txt','map/reworkl_asset_manifest.txt','licenses/Millennium-Dawn-CC-BY-SA-4.0.txt','licenses/flag-icons-MIT.txt','THIRD_PARTY.txt','WORLD_2026_RU.txt')) {
            if (-not (Test-Path -LiteralPath (Join-Path $Folder $relative) -PathType Leaf)) { throw "Incomplete world map: $relative. Extract the full 2026 ZIP, not the old toolkit." }
        }
    }
    foreach ($name in $script:PayloadDirs) {
        if (-not (Test-Path -LiteralPath (Join-Path $Folder $name) -PathType Container)) { throw "Incomplete mod: missing $name" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'thumbnail.png') -PathType Leaf)) { throw 'Incomplete mod: thumbnail.png is missing.' }
    return [pscustomobject]@{ Text = $text; Version = $versions[0].Groups[1].Value; WorldStates = $worldPlan }
}
function Get-PayloadFiles([string]$Folder, $WorldPlan) {
    Assert-PlainPath $Folder
    foreach ($name in @('descriptor.mod','thumbnail.png','THIRD_PARTY.txt','WORLD_2026_RU.txt')) {
        if ($name -in @('THIRD_PARTY.txt','WORLD_2026_RU.txt') -and -not (Test-Path -LiteralPath (Join-Path $Folder $name) -PathType Leaf)) { continue }
        $file = Join-Path $Folder $name
        Assert-PlainPath $file
        Get-Item -LiteralPath $file
    }
    $queue = [Collections.Generic.Queue[string]]::new()
    foreach ($name in $script:PayloadDirs) { $queue.Enqueue((Join-Path $Folder $name)) }
    if (Test-Path -LiteralPath (Join-Path $Folder 'licenses') -PathType Container) { $queue.Enqueue((Join-Path $Folder 'licenses')) }
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        Assert-PlainPath $current
        if ($WorldPlan -and (Full-Path $current) -ieq (Full-Path (Join-Path $Folder 'history/states'))) { continue }
        foreach ($item in @(Get-ChildItem -LiteralPath $current -Force)) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Link in source: $($item.FullName)" }
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
            elseif ($item.Extension -in $script:PayloadExtensions) {
                $relative = $item.FullName.Substring($Folder.Length + 1).Replace('\','/')
                if (-not $WorldPlan -or $WorldPlan.AllowedPayload.Contains($relative)) { $item }
            }
        }
    }
}
function External-Descriptor($Description, [string]$Target) {
    $label = 'name="Reworkl - Yugoslavia, Serbia and Turbo-folk"'
    if ($Description.Version -like '2.*') { $label = 'name="Reworkl - World 2026 v' + $Description.Version + '"' }
    $text = [regex]::Replace($Description.Text, '(?m)^\s*name\s*=\s*"[^"\r\n]*"\s*$', $label)
    $text = $text.TrimEnd() + "`npath=`"$($Target.Replace('\','/'))`"`n"
    if ($text -match '[^\x00-\x7F]') { throw 'External descriptor must contain only ASCII characters.' }
    return $text
}
function Prepare-LoadState([string]$Path, [string[]]$Dlc) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { $state = Read-Json $Path }
    else { $state = [pscustomobject]@{} }
    $existing = @(Get-Property $state 'disabled_dlcs' @())
    foreach ($entry in $existing) { if ($entry -isnot [string]) { throw 'Invalid disabled_dlcs array. Existing JSON was not changed.' } }
    $disabled = @(@($existing) + @($Dlc) | Where-Object { $_ -is [string] -and $_.Length -gt 0 } | Sort-Object -Unique)
    Set-Property $state 'disabled_dlcs' $disabled
    Set-Property $state 'enabled_mods' @('mod/reworkl.mod')
    return ConvertTo-Json -InputObject $state -Depth 40
}
function Read-State($Layout) {
    $state = Read-Json $Layout.State
    if ((Get-Property $state 'schema') -ne 1 -or
        (Get-Property $state 'target') -ne $Layout.Target -or
        (Get-Property $state 'user_dir') -ne $Layout.User) { throw 'Unexpected BAT state. Run 1_INSTALL.bat with the correct -BaseDir.' }
    return $state
}
function Set-Activation($Layout, [string]$Game, $Description, $State) {
    $dlc = @(Get-DlcFiles $Game | Sort-Object -Unique)
    $load = Join-Path $Layout.User 'dlc_load.json'
    $text = Prepare-LoadState $load $dlc
    Write-Atomic (Join-Path $Layout.User 'mod/reworkl.mod') (External-Descriptor $Description $Layout.Target)
    Write-Atomic $load $text
    Set-Property $State 'game_dir' $Game
    Set-Property $State 'version' $Description.Version
    Set-Property $State 'disabled_dlc_count' $dlc.Count
    Write-Host "[NO_DLC_CONFIG] $($dlc.Count) installed DLC descriptors disabled; no DLC files were removed."
}
function Invoke-Install($Layout, [string]$RequestedSource, [string]$Game, [bool]$Preview) {
    $sourceFolder = Get-Source $RequestedSource
    Assert-PlainPath $sourceFolder
    $description = Read-Descriptor $sourceFolder
    if ((Is-Within $sourceFolder $Layout.Target) -or (Is-Within $Layout.Target $sourceFolder)) {
        if ($sourceFolder -ne $Layout.Target) { throw 'Source and target cannot be nested.' }
    }
    $files = @(Get-PayloadFiles $sourceFolder $description.WorldStates)
    $loadPath = Join-Path $Layout.User 'dlc_load.json'
    [void](Prepare-LoadState $loadPath @(Get-DlcFiles $Game))
    if ($Preview) { Write-Host "[DRY_RUN] Install $($files.Count) files from $sourceFolder to $($Layout.Target); userdata $($Layout.User)"; return }
    [void][IO.Directory]::CreateDirectory($Layout.Base)
    Assert-PlainPath $Layout.User
    [void][IO.Directory]::CreateDirectory((Join-Path $Layout.User 'mod'))
    $backup = Backup-Files $Layout @((Join-Path $Layout.User 'mod/reworkl.mod'), $loadPath, $Layout.State)
    $stage = Join-Path $Layout.Base ('.reworkl-stage-' + [guid]::NewGuid().ToString('N'))
    $oldTarget = Join-Path $backup.Folder 'previous-reworkl'
    $movedOld = $false
    $placedNew = $false
    try {
        if ($sourceFolder -ne $Layout.Target -or $description.WorldStates) {
            [void][IO.Directory]::CreateDirectory($stage)
            foreach ($file in $files) {
                $relative = $file.FullName.Substring($sourceFolder.Length + 1)
                $destination = Join-Path $stage $relative
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
                [IO.File]::Copy($file.FullName, $destination)
                if ((File-Hash $destination) -ne (File-Hash $file.FullName)) { throw "Copy checksum mismatch: $relative" }
            }
            if ($description.WorldStates) { Write-ReworklWorldStates $description.WorldStates $stage }
            Assert-PlainPath $Layout.Target
            if (Test-Path -LiteralPath $Layout.Target -PathType Leaf) { throw 'Target is a file, not a folder.' }
            if (Test-Path -LiteralPath $Layout.Target -PathType Container) { [IO.Directory]::Move($Layout.Target, $oldTarget); $movedOld = $true }
            [IO.Directory]::Move($stage, $Layout.Target)
            $placedNew = $true
        }
        $state = [pscustomobject]@{ schema = 1; target = $Layout.Target; user_dir = $Layout.User; version = $description.Version; last_launch_utc = $null }
        Set-Activation $Layout $Game $description $state
        Write-Atomic $Layout.State (ConvertTo-Json -InputObject $state -Depth 20)
    } catch {
        if ($placedNew) { Remove-Item -LiteralPath $Layout.Target -Recurse -Force }
        if ($movedOld) { [IO.Directory]::Move($oldTarget, $Layout.Target) }
        Restore-Files $backup
        throw
    } finally {
        if (Test-Path -LiteralPath $stage -PathType Container) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
    Write-Host "[INSTALLED] Reworkl $($description.Version): $($Layout.Target)"
    Write-Host "[USER_DIR] $($Layout.User)"
    Write-Host "[BACKUP] $($backup.Folder)"
    Write-Host '[NEXT] Keep Steam running; use 2_LAUNCH.bat, not Play in Paradox Launcher.'
}
function Assert-BundledVersion($Layout, $Installed, [string]$RequestedSource) {
    # A new 2_LAUNCH previously silently reused an installed 1.x/older build.
    # Compare the paired bundle, never re-copy a mod during ordinary Launch.
    $sourceFolder = $null
    if ($RequestedSource) { $sourceFolder = Get-Source $RequestedSource }
    elseif (Test-Path -LiteralPath (Join-Path $script:ToolRoot 'reworkl/descriptor.mod') -PathType Leaf) {
        $sourceFolder = Full-Path (Join-Path $script:ToolRoot 'reworkl')
    }
    elseif (Test-Path -LiteralPath (Join-Path $script:ToolRoot 'descriptor.mod') -PathType Leaf) {
        $sourceFolder = Full-Path $script:ToolRoot
    }
    if (-not $sourceFolder) { return } # Historical standalone toolkit.
    $expected = Read-Descriptor $sourceFolder
    $different = $expected.Version -ne $Installed.Version
    foreach ($relative in @('descriptor.mod','common/bookmarks/Y89_bookmarks.txt','map/reworkl_world_manifest.txt')) {
        $sourceFile = Join-Path $sourceFolder $relative
        if ((Test-Path -LiteralPath $sourceFile -PathType Leaf) -and
            (File-Hash $sourceFile) -ne (File-Hash (Join-Path $Layout.Target $relative))) { $different = $true }
    }
    if ($different) {
        throw "INSTALLED_BUILD_MISMATCH: this ZIP is $($expected.Version), installed mod is $($Installed.Version). Nothing launched. Run 0_START_2026.bat from the FULL new ZIP (or 1_INSTALL.bat first)."
    }
}
function Invoke-Launch($Layout, [string]$Game, [bool]$Preview, [string]$ExpectedSource) {
    $state = Read-State $Layout
    $description = Read-Descriptor $Layout.Target
    Assert-BundledVersion $Layout $description $ExpectedSource
    Write-Host "[LAUNCHING_INSTALLED_VERSION] $($description.Version)"
    Write-Host "[MOD_DIR] $($Layout.Target)"
    $arguments = '-nolauncher "-userdir=' + $Layout.User.Replace('\','/') + '"'
    $executable = Join-Path $Game 'hoi4.exe'
    if ($Preview) { Write-Host "[DRY_RUN] `"$executable`" $arguments"; return }
    $backup = Backup-Files $Layout @((Join-Path $Layout.User 'mod/reworkl.mod'), (Join-Path $Layout.User 'dlc_load.json'), $Layout.State)
    try {
        Set-Activation $Layout $Game $description $state
        Set-Property $state 'previous_setup_hash' (File-Hash (Join-Path $Layout.User 'logs/setup.log'))
        Set-Property $state 'previous_system_hash' (File-Hash (Join-Path $Layout.User 'logs/system.log'))
        Set-Property $state 'last_launch_utc' ([DateTime]::UtcNow.ToString('o'))
        Write-Atomic $Layout.State (ConvertTo-Json -InputObject $state -Depth 20)
        $process = Start-Process -FilePath $executable -WorkingDirectory $Game -ArgumentList $arguments -PassThru
    } catch { Restore-Files $backup; throw }
    Write-Host "[STARTED] PID $($process.Id): $executable $arguments"
    Write-Host "[LOGS] $($Layout.User)\logs"
    if ($description.Version -like '2.*') { Write-Host '[NEXT] New game: World 2026 or Serbia 1936. OLD SAVES ARE NOT MAP-COMPATIBLE. Run 3_CHECK.bat after loading.' }
    else { Write-Host '[NEXT] New game: Yugoslavia 1989 or Serbia 1936. After loading the menu, run 3_CHECK.bat.' }
    Write-Host '[NOTE] Starting the process does not prove the mod or zero-DLC mode loaded; 3_CHECK verifies logs.'
}
function Invoke-Check($Layout, [string]$Report) {
    $lines = [Collections.Generic.List[string]]::new()
    function Status([string]$Text) { Write-Host $Text; $lines.Add($Text) }
    $ok = $true
    try {
        Status "[TOOLS_VERSION] $script:ToolVersion"
        $state = Read-State $Layout
        Status "[USER_DIR] $($Layout.User)"
        Status "[MOD_DIR] $($Layout.Target)"
        $description = Read-Descriptor $Layout.Target
        Status "[INSTALLED_VERSION] $($description.Version)"
        if ($description.Version -like '2.*') { Status '[EXPECTED_CAMPAIGNS] World 2026 / Serbia 1936; not Blitzkrieg 1939.' }
        $external = Join-Path $Layout.User 'mod/reworkl.mod'
        if ([IO.File]::ReadAllText($external) -ne (External-Descriptor $description $Layout.Target)) { $ok = $false; Status '[BAD_DESCRIPTOR] External descriptor differs from the expected single ASCII registration.' }
        $load = Read-Json (Join-Path $Layout.User 'dlc_load.json')
        $enabled = @(Get-Property $load 'enabled_mods' @())
        if ($enabled.Count -ne 1 -or $enabled[0] -ne 'mod/reworkl.mod') { $ok = $false; Status '[BAD_MOD_LIST] enabled_mods must contain only mod/reworkl.mod.' }
        $disabled = @(Get-Property $load 'disabled_dlcs' @())
        $installed = @(Get-DlcFiles (Get-Property $state 'game_dir'))
        foreach ($dlc in $installed) { if ($dlc -notin $disabled) { $ok = $false; Status "[DLC_NOT_DISABLED] $dlc" } }
        $started = Get-Property $state 'last_launch_utc'
        if (-not $started) { $ok = $false; Status '[NO_LAUNCH] Run 2_LAUNCH.bat first. Old logs are not accepted.' }
        $texts = @{}
        foreach ($kind in @('setup','system')) {
            $path = Join-Path $Layout.User "logs/$kind.log"
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $ok = $false; Status "[NO_LOG] $path"; continue }
            $texts[$kind] = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
            if ($started) {
                $time = [DateTime]::Parse($started).ToUniversalTime()
                if ((Get-Item -LiteralPath $path).LastWriteTimeUtc -lt $time.AddSeconds(-3) -or
                    (File-Hash $path) -eq (Get-Property $state "previous_${kind}_hash")) {
                    $ok = $false; Status "[STALE_LOG] $kind.log does not confirm the latest BAT launch."
                }
            }
        }
        if ($texts.ContainsKey('setup')) {
            if ($texts.setup -notmatch 'Bookmarks loaded[^\r\n]*common/bookmarks/Y89_bookmarks\.txt[^\r\n]*Bookmarks #2\b') { $ok = $false; Status '[NO_REWORKL_BOOKMARKS] setup.log did not load both Reworkl campaigns.' }
            if ($texts.setup -match 'Bookmarks loaded[^\r\n]*(blitzkrieg|the_gathering_storm)\.txt[^\r\n]*Bookmarks #[1-9][0-9]*\b') { $ok = $false; Status '[VANILLA_BOOKMARKS] Base-game bookmarks are still being loaded.' }
        }
        if ($texts.ContainsKey('system')) {
            foreach ($match in [regex]::Matches($texts.system, '(?m)^.*(?:Active Mod:|Active Mod Count:|Active DLC Count:)[^\r\n]*')) { Status ('[GAME_LOG] ' + $match.Value.Trim()) }
            if ($description.Version -like '2.*' -and $texts.system -notmatch ('Active Mod:\s*Reworkl - World 2026 v' + [regex]::Escape($description.Version) + '(?:[\r\n]|$)')) {
                $ok = $false; Status '[WRONG_BUILD_OR_PROFILE] Fresh log must identify the installed World 2026 version, not an old Combined/1989 mod.'
            }
            if ($texts.system -notmatch 'Active Mod Count:\s*1\b' -or $texts.system -notmatch 'Active Mod:\s*Reworkl') { $ok = $false; Status '[MOD_NOT_ACTIVE] system.log does not confirm Reworkl as the only active mod.' }
            if ($texts.system -notmatch 'Active DLC Count:\s*0\b') { $ok = $false; Status '[DLC_MODE_UNCONFIRMED] system.log does not confirm zero active DLC.' }
        }
        if ($ok) { Status '[RESULT] REWORKL LOADED; ACTIVE DLC: 0. This is loading verification, not a full gameplay test.' }
        else { Status '[RESULT] NOT CONFIRMED. Send this report and fresh system.log/setup.log from USER_DIR above.' }
    } catch { $ok = $false; Status "[ERROR] $($_.Exception.Message)" }
    finally {
        if ($Report) { Write-Atomic (Full-Path $Report) ($lines -join "`r`n") }
    }
    if ($ok) { return 0 }
    return 2
}
function Export-StartupDiagnostics($Layout, [string]$Report, [switch]$ReportOnly) {
    # Allowlist only. No saves, Steam files, launcher DB, settings or memory dumps.
    $folder = [IO.Path]::GetDirectoryName((Full-Path $Report))
    $token = [guid]::NewGuid().ToString('N')
    $stage = Join-Path ([IO.Path]::GetTempPath()) ('reworkl-diagnostics-' + $token)
    $zip = Join-Path $folder ('REWORKL_DIAGNOSTICS_' + (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + $token.Substring(0,8) + '.zip')
    [void][IO.Directory]::CreateDirectory($stage)
    $manifest = [Collections.Generic.List[string]]::new()
    $manifest.Add('Reworkl startup diagnostics. Times below are UTC. Log tails are at most 1 MiB each.')
    try {
        if (Test-Path -LiteralPath $Report -PathType Leaf) { [IO.File]::Copy($Report, (Join-Path $stage 'START_RESULT.txt')) }
        if ($ReportOnly) { $manifest.Add('PRELAUNCH ERROR: report only. Unrelated old game logs are intentionally excluded.') }
        $kinds = @('system','setup','error')
        if ($ReportOnly) { $kinds = @() }
        foreach ($kind in $kinds) {
            $path = Join-Path $Layout.User "logs/$kind.log"
            Assert-PlainPath $path
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $manifest.Add("MISSING: $path"); continue }
            $item = Get-Item -LiteralPath $path
            $manifest.Add("$kind.log | source=$path | modified_utc=$($item.LastWriteTimeUtc.ToString('o')) | original_bytes=$($item.Length)")
            $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            try {
                [void]$stream.Seek([Math]::Max([long]0, $stream.Length - 1048576), [IO.SeekOrigin]::Begin)
                $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8)
                try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
            } finally { $stream.Dispose() }
            [IO.File]::WriteAllText((Join-Path $stage "$kind.log"), $text, $script:Utf8NoBom)
        }
        [IO.File]::WriteAllText((Join-Path $stage 'SOURCES.txt'), ($manifest -join "`r`n"), $script:Utf8NoBom)
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip)
        Write-Host "[DIAGNOSTICS] $zip"
        Write-Host '[PRIVACY] Review before sharing. Contains selected logs with their paths/times, not saves or crash memory dumps.'
    } finally { if (Test-Path -LiteralPath $stage -PathType Container) { [IO.Directory]::Delete($stage, $true) } }
}
function Invoke-Start2026($Layout, [string]$RequestedSource, [string]$Game, [string]$Report, [bool]$Preview, [bool]$NoPrompt) {
    $sourceFolder = Get-Source $RequestedSource
    $description = Read-Descriptor $sourceFolder
    if ($description.Version -notlike '2.*') { throw 'FULL_2026_ZIP_REQUIRED: this source is not the 2026 world. Nothing changed or launched.' }
    if (-not $Report) { $Report = Join-Path $script:ToolRoot 'REWORKL_START_RESULT.txt' }
    if ($Preview) {
        Invoke-Install $Layout $sourceFolder $Game $true
        Write-Host "[DRY_RUN] Then launch installed World 2026 $($description.Version); save startup report beside this BAT."
        return 0
    }
    # Always finish the complete, staged update BEFORE starting the game.
    # This never overlays the old map or relies on an earlier 1.x install.
    Invoke-Install $Layout $sourceFolder $Game $false
    Invoke-Launch $Layout $Game $false $sourceFolder
    Write-Host '[WORLD_2026] New Game must show World 2026 / Serbia 1936, not 1939.'
    Write-Host '[KEEP_THIS_WINDOW] After the menu appears OR the game crashes, return here.'
    if (-not $NoPrompt) { [void](Read-Host 'Press ENTER then to check this launch and collect the correct logs automatically') }
    $result = Invoke-Check $Layout $Report
    try { Export-StartupDiagnostics $Layout $Report }
    catch { Write-Host "[DIAGNOSTICS_WARNING] $($_.Exception.Message). The text report is still at: $Report" }
    return $result
}
function Invoke-Patch($Layout, [string]$Game, [bool]$Restore, [bool]$Preview) {
    [void](Read-State $Layout)
    if ($Restore) {
        $record = Read-Json $Layout.PatchState
        if ((Full-Path $record.game_dir) -ne $Game -or @($record.files).Count -ne 2) { throw 'Plan B backup belongs to a different game installation.' }
        $allowed = @((Join-Path $Game 'launcher-settings.json'), (Join-Path $Game 'launcher/launcher-settings.json'), (Join-Path $Game 'userdir.txt'))
        foreach ($entry in $record.files) {
            if ($entry.path -notin $allowed -or -not (Is-Within (Full-Path $entry.backup) $Layout.Backups)) { throw 'Invalid Plan B backup path. Nothing was restored.' }
            Assert-PlainPath $entry.path
            Assert-PlainPath $entry.backup
            if ($entry.existed -and -not (Test-Path -LiteralPath $entry.backup -PathType Leaf)) { throw 'Original Plan B backup is missing.' }
            if ((File-Hash $entry.path) -ne $entry.patched_hash) { throw 'A patched file changed after Plan B (e.g. a game update). Refusing to overwrite it. Original backups are retained.' }
        }
        if ($Preview) { Write-Host '[DRY_RUN] Restore only the Plan B files from their exact original backups.'; return }
        Restore-Files ([pscustomobject]@{ Items = @($record.files) })
        [IO.File]::Delete($Layout.PatchState)
        Write-Host '[RESTORED] launcher-settings.json and userdir.txt restored. Saves and DLC files were not touched.'
        return
    }
    if (Test-Path -LiteralPath $Layout.PatchState -PathType Leaf) { throw 'Plan B already has a backup. Use 5_RESTORE_PLAN_B.bat before applying it again.' }
    $settings = Join-Path $Game 'launcher-settings.json'
    if (-not (Test-Path -LiteralPath $settings -PathType Leaf)) { $settings = Join-Path $Game 'launcher/launcher-settings.json' }
    $json = Read-Json $settings
    Set-Property $json 'gameDataPath' $Layout.User.Replace('\','/')
    $userdir = Join-Path $Game 'userdir.txt'
    if ($Preview) { Write-Host "[DRY_RUN] OPTIONAL Plan B: back up and patch $settings and $userdir"; return }
    $backup = Backup-Files $Layout @($settings, $userdir)
    try {
        Write-Atomic $settings (ConvertTo-Json -InputObject $json -Depth 64)
        Write-Atomic $userdir ($Layout.User.Replace('\','/') + "`n")
        foreach ($entry in $backup.Items) { Set-Property $entry 'patched_hash' (File-Hash $entry.path) }
        $record = [pscustomobject]@{ files = @($backup.Items); game_dir = $Game }
        Write-Atomic $Layout.PatchState (ConvertTo-Json -InputObject $record -Depth 20)
    } catch { Restore-Files $backup; throw }
    Write-Host "[PLAN_B] User directory redirected to $($Layout.User). Backup: $($backup.Folder)"
    Write-Host '[NEXT] Continue using 2_LAUNCH.bat. To undo the game-folder changes, run 5_RESTORE_PLAN_B.bat.'
}
function Invoke-Reworkl {
    [CmdletBinding()]
    param([string]$Action='Install', [string]$Source, [string]$GameDir, [string]$BaseDir,
          [string]$ReportPath, [switch]$DryRun, [switch]$NonInteractive)
    if ($Action -ne 'Check') { Write-Host "[TOOLS_VERSION] $script:ToolVersion" }
    $layout = Get-Layout $BaseDir
    if ($Action -eq 'Check') { return Invoke-Check $layout $ReportPath }
    Assert-Closed
    if ($Action -ne 'Install' -and -not $GameDir -and (Test-Path -LiteralPath $layout.State -PathType Leaf)) { $GameDir = Get-Property (Read-State $layout) 'game_dir' }
    $game = Find-Game $GameDir ([bool]$NonInteractive)
    if ((Is-Within $layout.Base $game) -or (Is-Within $game $layout.Base)) { throw 'The BAT base directory must be separate from the game installation.' }
    switch ($Action) {
        'Install' { Invoke-Install $layout $Source $game ([bool]$DryRun) }
        'Launch' { Invoke-Launch $layout $game ([bool]$DryRun) $Source }
        'Start2026' { return Invoke-Start2026 $layout $Source $game $ReportPath ([bool]$DryRun) ([bool]$NonInteractive) }
        'PatchLauncher' { Invoke-Patch $layout $game $false ([bool]$DryRun) }
        'RestoreLauncher' { Invoke-Patch $layout $game $true ([bool]$DryRun) }
        default { throw "Unknown action: $Action" }
    }
    return 0
}
if (-not $LibraryOnly) {
    try { exit (Invoke-Reworkl -Action $Action -Source $Source -GameDir $GameDir -BaseDir $BaseDir -ReportPath $ReportPath -DryRun:$DryRun -NonInteractive:$NonInteractive) }
    catch {
        $message = "[ERROR] $($_.Exception.Message)"
        Write-Host $message
        Write-Host 'No launcher database or DLC files were deleted. Backups, if created, are retained.'
        if ($Action -eq 'Start2026') {
            if (-not $ReportPath) { $ReportPath = Join-Path $script:ToolRoot 'REWORKL_START_RESULT.txt' }
            try {
                Write-Atomic (Full-Path $ReportPath) ("[TOOLS_VERSION] $script:ToolVersion`r`n[ACTION] Start2026`r`n[SOURCE_REQUEST] $Source`r`n[BASE_REQUEST] $BaseDir`r`n$message`r`n[RESULT] NOT CONFIRMED. Installation/start failed; no success is claimed.")
                Export-StartupDiagnostics (Get-Layout $BaseDir) $ReportPath -ReportOnly
            }
            catch { Write-Host '[REPORT_WARNING] Could not save the error report. Photograph this window.' }
        }
        exit 1
    }
}
