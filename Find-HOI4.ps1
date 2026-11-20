$ErrorActionPreference = 'SilentlyContinue'
$roots = New-Object System.Collections.Generic.List[string]
$steam = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam').InstallPath
if (-not $steam) { $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath }
if ($steam) {
    $roots.Add($steam)
    $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
        $raw = Get-Content $vdf -Raw
        foreach ($match in [regex]::Matches($raw, '"path"\s+"([^"]+)"')) {
            $path = $match.Groups[1].Value -replace '\\\\', '\'
            if ($path) { $roots.Add($path) }
        }
    }
}
@('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam', 'D:\Steam', 'D:\Games\Steam') | ForEach-Object { $roots.Add($_) }
foreach ($root in ($roots | Select-Object -Unique)) {
    $candidate = Join-Path $root 'steamapps\common\Hearts of Iron IV\hoi4.exe'
    if (Test-Path $candidate) {
        Write-Output $candidate
        exit 0
    }
}
exit 1
