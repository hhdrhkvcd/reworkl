#requires -Version 5.1
<#
Install the extracted standalone ZIP. No administrator rights, Python,
launcher database edits, DLC changes or network access are required.
-CheckOnly is read-only. It describes the LAST launch, not launcher UI state.
#>
[CmdletBinding()]
param(
    [string]$UserDir,
    [string]$Source,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$Utf8 = [System.Text.UTF8Encoding]::new($false)
$PayloadDirs = @('common', 'events', 'gfx', 'history', 'interface', 'localisation', 'map', 'music')
$PayloadExtensions = @('.txt', '.lua', '.mod', '.gfx', '.gui', '.yml', '.asset', '.dds', '.tga', '.png', '.ogg', '.bmp', '.csv', '.map')

function Full-Path([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('/', '\'))
}

function Is-Link([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    $link = $item.PSObject.Properties['LinkType']
    return ($null -ne $link -and $link.Value -in @('SymbolicLink', 'Junction'))
}

function Find-UserDir {
    $candidates = @()
    $documents = [Environment]::GetFolderPath('MyDocuments')
    if ($documents) { $candidates += Join-Path $documents 'Paradox Interactive/Hearts of Iron IV' }
    if ($env:OneDrive) { $candidates += Join-Path $env:OneDrive 'Documents/Paradox Interactive/Hearts of Iron IV' }
    if ($env:USERPROFILE) { $candidates += Join-Path $env:USERPROFILE 'Documents/Paradox Interactive/Hearts of Iron IV' }
    if ($HOME) { $candidates += Join-Path $HOME '.local/share/Paradox Interactive/Hearts of Iron IV' }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) { return (Full-Path $candidate) }
    }
    throw 'Папка данных HOI4 не найдена. Запусти обычную игру один раз либо передай -UserDir "папка с logs и save games".'
}

function Show-Status([string]$DataDir) {
    $target = Join-Path $DataDir 'mod/reworkl'
    $external = Join-Path $DataDir 'mod/reworkl.mod'
    $validPath = $false
    Write-Host "[USER_DIR] $DataDir"
    if ((Test-Path -LiteralPath (Join-Path $target 'descriptor.mod') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $target 'common/bookmarks/Y89_bookmarks.txt') -PathType Leaf) -and
        (Test-Path -LiteralPath $external -PathType Leaf)) {
        $text = [IO.File]::ReadAllText($external, [Text.Encoding]::UTF8)
        $match = [regex]::Match($text, '(?m)^\s*path\s*=\s*"((?:\\.|[^"\\])*)"\s*(?:#.*)?$')
        if ($match.Success) {
            $raw = $match.Groups[1].Value.Replace('\"', '"').Replace('\\', '\').Replace('\', '/')
            if ([IO.Path]::IsPathRooted($raw)) { $resolved = Full-Path $raw }
            else { $resolved = Full-Path (Join-Path $DataDir $raw) }
            $validPath = ($resolved -ieq (Full-Path $target))
        }
        if ($validPath) { Write-Host '[PATH_OK] Файлы мода и путь в reworkl.mod найдены.' }
        else { Write-Host '[WRONG_PATH] reworkl.mod не указывает на установленную папку reworkl.' }
    } else {
        Write-Host '[NOT_INSTALLED] Не найдены папка мода, файл сценариев или внешний reworkl.mod.'
    }

    $enabled = $false
    $launchState = Join-Path $DataDir 'dlc_load.json'
    if (Test-Path -LiteralPath $launchState -PathType Leaf) {
        try {
            $state = [IO.File]::ReadAllText($launchState, [Text.Encoding]::UTF8) | ConvertFrom-Json
            $property = $state.PSObject.Properties['enabled_mods']
            if ($null -eq $property) { throw 'enabled_mods is missing' }
            foreach ($entry in @($property.Value)) {
                if ($entry -isnot [string]) { throw 'enabled_mods must contain strings' }
                $normalized = $entry.Replace('\', '/')
                while ($normalized.StartsWith('./')) { $normalized = $normalized.Substring(2) }
                if ($normalized -ieq 'mod/reworkl.mod' -or $normalized -ieq $external.Replace('\', '/')) {
                    $enabled = $true
                }
            }
            if ($enabled) { Write-Host '[ENABLED_LAST_LAUNCH] Reworkl указан в dlc_load.json.' }
            else { Write-Host '[NOT_ENABLED_LAST_LAUNCH] Reworkl отсутствует в enabled_mods последнего запуска.' }
        } catch {
            Write-Host '[UNREADABLE_LAUNCH_STATE] Не удалось прочитать enabled_mods. dlc_load.json не изменён.'
        }
    } else {
        Write-Host '[NO_LAUNCH_STATE] dlc_load.json отсутствует; список модов последнего запуска неизвестен.'
    }

    $setup = Join-Path $DataDir 'logs/setup.log'
    if (Test-Path -LiteralPath $setup -PathType Leaf) {
        $setupText = [IO.File]::ReadAllText($setup, [Text.Encoding]::UTF8)
        if ($setupText -match 'Bookmarks loaded[^\r\n]*common/bookmarks/Y89_bookmarks\.txt') {
            Write-Host '[SETUP_MOD_FOUND] setup.log содержит сценарии Reworkl.'
        } elseif ($setupText -match 'Bookmarks loaded[^\r\n]*(?:blitzkrieg|the_gathering_storm)\.txt') {
            Write-Host '[SETUP_VANILLA_BOOKMARKS] В setup.log стандартные сценарии, без Y89_bookmarks.txt.'
        } else { Write-Host '[SETUP_INCONCLUSIVE] Этот setup.log не подтверждает загрузку Reworkl.' }
        Write-Host '[NOTE] setup.log и dlc_load.json могут относиться к предыдущему запуску.'
    }
    Write-Host '[ACTION] В лаунчере выбери активный набор, включи только Reworkl и запусти игру из лаунчера.'
    Write-Host '[CHECK] Reworkl 2.x: Мир 2026 и Сербия 1936. Старая 1.x: Югославия 1989 и Сербия 1936.'
    return ($validPath -and $enabled)
}

try {
    if (-not $UserDir) { $UserDir = Find-UserDir }
    $UserDir = Full-Path $UserDir
    if (-not (Test-Path -LiteralPath $UserDir -PathType Container)) {
        throw 'Указанная папка данных не существует. Нужна папка HOI4, содержащая logs, а не папка Steam с hoi4.exe.'
    }
    if ((Test-Path -LiteralPath (Join-Path $UserDir 'hoi4.exe')) -and
        -not (Test-Path -LiteralPath (Join-Path $UserDir 'logs'))) {
        throw 'Это папка установленной игры. Укажи пользовательскую папку с logs и save games.'
    }
    if ($CheckOnly) {
        if (Show-Status $UserDir) { exit 0 }
        exit 2
    }
    if (Get-Process -Name 'hoi4', 'dowser', 'Paradox Launcher', 'ParadoxLauncher' -ErrorAction SilentlyContinue) {
        throw 'Сначала полностью закрой HOI4 и Paradox Launcher. Установщик не закрывает их принудительно.'
    }
    if (-not $Source) {
        $Source = Join-Path $PSScriptRoot 'reworkl'
        if (-not (Test-Path -LiteralPath (Join-Path $Source 'descriptor.mod'))) {
            $Source = $PSScriptRoot
        }
    }
    $Source = Full-Path $Source
    $internal = Join-Path $Source 'descriptor.mod'
    $bookmarks = Join-Path $Source 'common/bookmarks/Y89_bookmarks.txt'
    if (-not (Test-Path -LiteralPath $internal -PathType Leaf) -or
        -not (Test-Path -LiteralPath $bookmarks -PathType Leaf)) {
        throw 'Не найдена распакованная сборка. Распакуй ВЕСЬ ZIP и запусти INSTALL_REWORKL.cmd рядом с папкой reworkl.'
    }
    $description = [IO.File]::ReadAllText($internal, [Text.Encoding]::UTF8)
    $bookmarkText = [IO.File]::ReadAllText($bookmarks, [Text.Encoding]::UTF8)
    if ($description -notmatch '(?m)^\s*name\s*=\s*"Reworkl' -or
        $description -match '(?m)^\s*(?:path|remote_file_id)\s*=' -or
        $bookmarkText -notmatch '1936\.1\.1' -or ($bookmarkText -notmatch '1989\.1\.1' -and $bookmarkText -notmatch '2026\.1\.1')) {
        throw 'Это не готовая объединённая сборка Reworkl. Не используй старый многотомный исходный архив.'
    }
    if ($description -match '(?m)^\s*version\s*=\s*"2\.') {
        if ($bookmarkText -notmatch '2026\.1\.1') { throw 'Reworkl 2.x: отсутствует основной старт 2026.' }
        $states = @(Get-ChildItem -LiteralPath (Join-Path $Source 'history/states') -File -Filter '*.txt')
        if ($states.Count -ne 1255) { throw 'Нужны ровно 1255 регионов. Распакуй полный ZIP 2026 в новую папку, без старых файлов 1989.' }
        foreach ($relative in @('common/bookmarks/the_gathering_storm.txt','common/bookmarks/blitzkrieg.txt','map/provinces.bmp','map/definition.csv','map/default.map','map/unitstacks.txt','licenses/Millennium-Dawn-CC-BY-SA-4.0.txt','licenses/flag-icons-MIT.txt','THIRD_PARTY.txt','WORLD_2026_RU.txt')) {
            if (-not (Test-Path -LiteralPath (Join-Path $Source $relative) -PathType Leaf)) { throw "Неполная карта 2026: $relative" }
        }
    }
    foreach ($directory in $PayloadDirs) {
        if (-not (Test-Path -LiteralPath (Join-Path $Source $directory) -PathType Container)) {
            throw "Сборка распакована не полностью: отсутствует $directory."
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Source 'thumbnail.png') -PathType Leaf)) {
        throw 'Сборка распакована не полностью: отсутствует thumbnail.png.'
    }
    $modDir = Join-Path $UserDir 'mod'
    $target = Full-Path (Join-Path $modDir 'reworkl')
    $external = Join-Path $modDir 'reworkl.mod'
    $sameSource = ($Source -ieq $target)
    if (-not $sameSource -and ($target.StartsWith($Source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        $Source.StartsWith($target + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) {
        throw 'Папки исходной и установленной сборки не должны быть вложены друг в друга.'
    }
    if ((Is-Link $Source) -or (Is-Link $target) -or (Is-Link $external)) {
        throw 'Отказ от замены символьной ссылки/junction. Используй обычные папки и файлы.'
    }
    if ((Test-Path -LiteralPath $target -PathType Leaf) -or (Test-Path -LiteralPath $external -PathType Container)) {
        throw 'Путь назначения занят файлом/папкой неверного типа. Ничего не заменено.'
    }
    $linkCandidates = @((Get-Item -LiteralPath $internal), (Get-Item -LiteralPath (Join-Path $Source 'thumbnail.png')))
    foreach ($directory in $PayloadDirs) {
        $folder = Join-Path $Source $directory
        $linkCandidates += Get-Item -LiteralPath $folder
        $linkCandidates += @(Get-ChildItem -LiteralPath $folder -Recurse -Force)
    }
    $links = @($linkCandidates | Where-Object {
        $link = $_.PSObject.Properties['LinkType']
        $null -ne $link -and $link.Value -in @('SymbolicLink', 'Junction')
    })
    if ($links.Count -gt 0) { throw 'В исходной сборке есть символьные ссылки/junction. Ничего не заменено.' }

    [void][IO.Directory]::CreateDirectory($modDir)
    $stage = Join-Path $modDir ('.reworkl-install-' + [guid]::NewGuid().ToString('N'))
    $stagedTarget = Join-Path $stage 'reworkl'
    $stagedExternal = Join-Path $stage 'reworkl.mod'
    $backup = $null
    $movedTarget = $false
    $movedExternal = $false
    $installedTarget = $false
    $installedExternal = $false
    try {
        [void][IO.Directory]::CreateDirectory($stage)
        if (-not $sameSource) {
            [void][IO.Directory]::CreateDirectory($stagedTarget)
            $files = @((Get-Item -LiteralPath $internal), (Get-Item -LiteralPath (Join-Path $Source 'thumbnail.png')))
            foreach ($directory in $PayloadDirs) {
                $files += @(Get-ChildItem -LiteralPath (Join-Path $Source $directory) -File -Recurse -Force |
                    Where-Object { $_.Extension -in $PayloadExtensions })
            }
            foreach ($name in @('THIRD_PARTY.txt','WORLD_2026_RU.txt')) {
                if (Test-Path -LiteralPath (Join-Path $Source $name) -PathType Leaf) { $files += Get-Item -LiteralPath (Join-Path $Source $name) }
            }
            if (Test-Path -LiteralPath (Join-Path $Source 'licenses') -PathType Container) { $files += @(Get-ChildItem -LiteralPath (Join-Path $Source 'licenses') -File -Recurse -Filter '*.txt') }
            foreach ($file in $files) {
                $relative = $file.FullName.Substring($Source.Length + 1)
                $destination = Join-Path $stagedTarget $relative
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
                [IO.File]::Copy($file.FullName, $destination)
                if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
                    (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash) {
                    throw "Не совпала контрольная сумма: $relative. Старая установка не изменена."
                }
            }
        }
        $escaped = $target.Replace('\', '/').Replace('"', '\"')
        $launcher = $description.TrimEnd() + "`npath=`"$escaped`"`n"
        [IO.File]::WriteAllText($stagedExternal, $launcher, $Utf8)

        if ((Test-Path -LiteralPath $external) -or (-not $sameSource -and (Test-Path -LiteralPath $target))) {
            $backup = Join-Path (Join-Path $UserDir 'reworkl-backups') ((Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N'))
            [void][IO.Directory]::CreateDirectory($backup)
            if (-not $sameSource -and (Test-Path -LiteralPath $target)) {
                [IO.Directory]::Move($target, (Join-Path $backup 'reworkl'))
                $movedTarget = $true
            }
            if (Test-Path -LiteralPath $external) {
                [IO.File]::Move($external, (Join-Path $backup 'reworkl.mod'))
                $movedExternal = $true
            }
        }
        if (-not $sameSource) {
            [IO.Directory]::Move($stagedTarget, $target)
            $installedTarget = $true
        }
        [IO.File]::Move($stagedExternal, $external)
        $installedExternal = $true
    } catch {
        if ($installedExternal) { [IO.File]::Delete($external) }
        if ($installedTarget) { [IO.Directory]::Delete($target, $true) }
        if ($movedTarget) { [IO.Directory]::Move((Join-Path $backup 'reworkl'), $target) }
        if ($movedExternal) { [IO.File]::Move((Join-Path $backup 'reworkl.mod'), $external) }
        throw
    } finally {
        if (Test-Path -LiteralPath $stage) { [IO.Directory]::Delete($stage, $true) }
    }
    Write-Host "[INSTALLED] $target"
    if ($backup) { Write-Host "[BACKUP] $backup" }
    Write-Host '[SAFE] Сохранения, DLC, dlc_load.json и база лаунчера не изменены.'
    [void](Show-Status $UserDir)
    Write-Host '[IMPORTANT] Установка файлов НЕ включает мод в наборе лаунчера автоматически.'
    exit 0
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message)
    exit 1
}
