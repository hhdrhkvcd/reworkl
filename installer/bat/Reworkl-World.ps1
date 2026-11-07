#requires -Version 5.1
# Shared world-state selection for BOTH Windows installers. No game execution.
$script:RW26LibraryRoot = $PSScriptRoot

function Get-RW26Hash([byte[]]$Bytes) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}
function Get-RW26FileHash([string]$Path) {
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}
function Assert-RW26PlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "WORLD_STATE_LINK_REFUSED: $current"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Read-RW26ZipBytes($Entry, [long]$Limit) {
    if ($null -eq $Entry -or $Entry.Length -gt $Limit) { throw 'WORLD_STATE_ARCHIVE_INVALID: missing or oversized entry.' }
    $stream = $Entry.Open()
    $memory = [IO.MemoryStream]::new()
    try {
        $buffer = [byte[]]::new(8192)
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($memory.Length + $read -gt $Limit) { throw 'WORLD_STATE_ARCHIVE_INVALID: entry exceeds its allowed size.' }
            $memory.Write($buffer, 0, $read)
        }
        return ,($memory.ToArray())
    } finally { $stream.Dispose(); $memory.Dispose() }
}
function Get-RW26RecoveryBundle([string]$Source, [string]$HelperRoot) {
    $candidates = @(
        [pscustomobject]@{ Zip = (Join-Path $HelperRoot 'Reworkl-World-States.zip'); Sha = (Join-Path $HelperRoot 'Reworkl-World-States.sha256') },
        [pscustomobject]@{ Zip = (Join-Path ([IO.Path]::GetDirectoryName($Source)) 'Reworkl-World-States.zip'); Sha = (Join-Path ([IO.Path]::GetDirectoryName($Source)) 'Reworkl-World-States.sha256') }
    )
    # Only the developer checkout itself may use its source asset. Never mix
    # another extracted mod or a test fixture with this repository's world.
    $repository = [IO.Path]::GetFullPath((Join-Path $script:RW26LibraryRoot '../..'))
    if ($Source -ieq $repository) {
        $candidates += [pscustomobject]@{ Zip = (Join-Path $repository 'assets/world_2026/states.zip'); Sha = (Join-Path $repository 'assets/world_2026/states.sha256') }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate.Zip -PathType Leaf) {
            Assert-RW26PlainPath $candidate.Zip
            Assert-RW26PlainPath $candidate.Sha
            if (-not (Test-Path -LiteralPath $candidate.Sha -PathType Leaf)) { throw "WORLD_STATE_CHECKSUM_MISSING: $($candidate.Sha)" }
            $value = [IO.File]::ReadAllText($candidate.Sha).Trim()
            $match = [regex]::Match($value, '^([a-fA-F0-9]{64})(?:\s+[^\r\n]+)?$')
            if (-not $match.Success -or (Get-Item -LiteralPath $candidate.Zip).Length -gt 16777216 -or
                (Get-RW26FileHash $candidate.Zip) -ne $match.Groups[1].Value.ToLowerInvariant()) {
                throw "WORLD_STATE_ARCHIVE_CORRUPT: $($candidate.Zip). Source: $Source. Existing installation not changed."
            }
            return $candidate.Zip
        }
    }
    return $null
}
function Get-ReworklWorldStatePlan([string]$Source, [string]$HelperRoot) {
    $Source = [IO.Path]::GetFullPath($Source)
    Assert-RW26PlainPath $Source
    $stateFolder = Join-Path $Source 'history/states'
    Assert-RW26PlainPath $stateFolder
    $found = @()
    if ([IO.Directory]::Exists($stateFolder)) {
        # No provider -Filter, no reliance on a directory's total file count.
        $found = @([IO.Directory]::EnumerateFiles($stateFolder) | Where-Object { [IO.Path]::GetExtension($_) -ieq '.txt' })
    }
    Write-Host "[WORLD_SOURCE] $Source"
    Write-Host "[WORLD_STATES_FOUND] $($found.Count) loose TXT files; expected payload: 1255 exact manifest entries."
    $archivePath = Get-RW26RecoveryBundle $Source $HelperRoot
    $archive = $null
    try {
        if ($archivePath) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
            $rawManifest = Read-RW26ZipBytes ($archive.GetEntry('manifest.json')) 2097152
        } else {
            $manifestPath = Join-Path $Source 'map/reworkl_state_manifest.json'
            Assert-RW26PlainPath $manifestPath
            if (-not [IO.File]::Exists($manifestPath)) {
                throw "WORLD_STATE_MANIFEST_MISSING: source=$Source; found_txt=$($found.Count); expected=1255. Apply the small installer repair ZIP beside 0_START_2026.bat. Missing: map/reworkl_state_manifest.json or Reworkl-World-States.zip. No installed files changed."
            }
            if ((Get-Item -LiteralPath $manifestPath).Length -gt 2097152) { throw 'WORLD_STATE_MANIFEST_INVALID: manifest too large.' }
            $rawManifest = [IO.File]::ReadAllBytes($manifestPath)
        }
        $manifest = [Text.Encoding]::UTF8.GetString($rawManifest) | ConvertFrom-Json
        if ($null -eq $manifest -or $manifest.schema -ne 1 -or $manifest.scenario -ne 'world_2026' -or
            $manifest.expected_count -ne 1255 -or @($manifest.files).Count -ne 1255) {
            throw 'WORLD_STATE_MANIFEST_INVALID: expected schema 1, world_2026 and 1255 entries.'
        }
        $worldManifest = Join-Path $Source 'map/reworkl_world_manifest.txt'
        Assert-RW26PlainPath $worldManifest
        if (-not [IO.File]::Exists($worldManifest) -or (Get-RW26FileHash $worldManifest) -ne $manifest.world_manifest_sha256) {
            throw "WORLD_STATE_MAP_MISMATCH: $worldManifest does not match the recovery payload. Source: $Source. No installed files changed."
        }
        $expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        [long]$total = 0
        foreach ($entry in $manifest.files) {
            if ($entry.path -isnot [string] -or $entry.path -cnotmatch '^history/states/[1-9][0-9]*-Reworkl\.txt$' -or
                -not $expected.Add($entry.path) -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
                [long]$entry.size -lt 1 -or [long]$entry.size -gt 131072) { throw 'WORLD_STATE_MANIFEST_INVALID: unsafe, duplicate or malformed state entry.' }
            $total += [long]$entry.size
        }
        if ($total -gt 33554432) { throw 'WORLD_STATE_MANIFEST_INVALID: excessive payload size.' }
        $allowed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $missingPayload = [Collections.Generic.List[string]]::new()
        foreach ($relative in $manifest.payload_paths) {
            if ($relative -isnot [string] -or $relative -cmatch '(?:^/|\\|:|(?:^|/)\.\.(?:/|$))' -or
                $relative -cnotmatch '^(?:(?:common|events|gfx|history|interface|localisation|map|music|licenses)/[A-Za-z0-9_ .()/-]+|descriptor\.mod|thumbnail\.png|THIRD_PARTY\.txt|WORLD_2026_RU\.txt)$' -or
                -not $allowed.Add($relative)) { throw 'WORLD_PAYLOAD_MANIFEST_INVALID: unsafe or duplicate payload path.' }
            if (-not $expected.Contains($relative) -and $relative -cne 'map/reworkl_state_manifest.json' -and -not [IO.File]::Exists((Join-Path $Source $relative))) { $missingPayload.Add($relative) }
        }
        if ($allowed.Count -lt 1255 -or $allowed.Count -gt 10000) { throw 'WORLD_PAYLOAD_MANIFEST_INVALID: unexpected path count.' }
        if ($missingPayload.Count -gt 0) {
            $sample = @($missingPayload.ToArray() | Select-Object -First 8) -join ', '
            throw "WORLD_PAYLOAD_MISSING: source=$Source; missing_files=$($missingPayload.Count). Files: $sample. No installed files changed."
        }
        if ($archive) {
            $zipNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($entry in $archive.Entries) {
                if (-not $zipNames.Add($entry.FullName) -or
                    (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960 -or
                    (-not $expected.Contains($entry.FullName) -and ($entry.FullName -cne 'manifest.json' -and $entry.FullName -cne 'LICENSE.txt' -and $entry.FullName -cne 'ATTRIBUTION.txt'))) {
                    throw 'WORLD_STATE_ARCHIVE_INVALID: duplicate, linked, unexpected or unsafe path.'
                }
            }
            if ($archive.Entries.Count -ne 1258) { throw 'WORLD_STATE_ARCHIVE_INVALID: incomplete entry set.' }
        }
        $states = [Collections.Generic.List[object]]::new()
        $missing = [Collections.Generic.List[string]]::new()
        $changed = [Collections.Generic.List[string]]::new()
        foreach ($entry in $manifest.files) {
            $path = Join-Path $Source $entry.path
            # Parent directories and canonical relative paths are validated
            # once above; avoid thousands of redundant provider traversals.
            $exists = [IO.File]::Exists($path)
            if ($exists -and (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "WORLD_STATE_LINK_REFUSED: $path" }
            if (-not $exists) { $missing.Add($entry.path) }
            elseif ((Get-RW26FileHash $path) -ne $entry.sha256) { $changed.Add($entry.path) }
            if ($archive) {
                $bytes = Read-RW26ZipBytes ($archive.GetEntry($entry.path)) 131072
            } elseif ($exists -and -not $changed.Contains($entry.path)) {
                $bytes = [IO.File]::ReadAllBytes($path)
            } else { continue }
            if ($bytes.Length -ne [long]$entry.size -or (Get-RW26Hash $bytes) -ne $entry.sha256) {
                throw "WORLD_STATE_CHECKSUM_FAILED: $($entry.path). No installed files changed."
            }
            $states.Add([pscustomobject]@{ Path = $entry.path; Bytes = $bytes; Sha256 = $entry.sha256 })
        }
        $extra = @($found | Where-Object { -not $expected.Contains('history/states/' + [IO.Path]::GetFileName($_)) })
        if ($states.Count -ne 1255) {
            $sample = @(@($missing.ToArray()) + @($changed.ToArray()) | Select-Object -First 8) -join ', '
            throw "WORLD_STATES_INCOMPLETE: source=$Source; found_txt=$($found.Count); expected=1255; missing=$($missing.Count); changed=$($changed.Count); extra=$($extra.Count). Files: $sample. Apply the small installer repair ZIP beside 0_START_2026.bat. Existing installation not changed."
        }
        Write-Host "[WORLD_STATES_SELECTED] 1255 verified files; missing_loose=$($missing.Count); changed_loose=$($changed.Count); extra_ignored=$($extra.Count); recovery_bundle=$([bool]$archive)."
        return [pscustomobject]@{ States = $states.ToArray(); ManifestBytes = $rawManifest; ExtraCount = $extra.Count; RestoredCount = ($missing.Count + $changed.Count); SourceCount = $found.Count; AllowedPayload = $allowed }
    } finally { if ($archive) { $archive.Dispose() } }
}
function Write-ReworklWorldStates($Plan, [string]$Destination) {
    if ($null -eq $Plan -or @($Plan.States).Count -ne 1255) { throw 'WORLD_STATE_PLAN_INVALID: refusing incomplete installation.' }
    foreach ($entry in $Plan.States) {
        $path = Join-Path $Destination $entry.Path
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
        [IO.File]::WriteAllBytes($path, $entry.Bytes)
        if ((Get-RW26FileHash $path) -ne $entry.Sha256) { throw "WORLD_STATE_COPY_FAILED: $($entry.Path)" }
    }
    $path = Join-Path $Destination 'map/reworkl_state_manifest.json'
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
    [IO.File]::WriteAllBytes($path, $Plan.ManifestBytes)
}
