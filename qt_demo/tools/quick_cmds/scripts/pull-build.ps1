<#
.SYNOPSIS
    Pull a build/code directory from remote or local, organize by project under
    D:\Work\1_Soft, and extract any .tar.gz files inside.

.DESCRIPTION
    Accepts paths like:
      - UNC:      \\172.30.10.183\code\temp\24111C\24111C_5.0_master_20260702_145627_tp_test
      - Local:    D:\somewhere\24111C\24111C_5.0_master_20260702_145627_tp_test
      - Mixed:    /code/temp/24111C/24111C_5.0_master_20260702_145627_tp_test

    Copies the leaf directory to D:\Work\1_Soft\<ProjectName>\<DirName>\
    then extracts all .tar.gz / .tgz files found inside.

    Usage:
      .\pull-build.ps1                                    (interactive, paste path)
      .\pull-build.ps1 "\\172.30.10.183\code\temp\..."
#>

param(
    [Parameter(Position = 0)]
    [string]$SourcePath,
    [string]$TargetBase = "D:\Work\1_Soft",
    [switch]$Yes,      # 跳过"确认复制/覆盖/删除"提问
    [switch]$NoOpen    # 跳过"是否打开资源管理器"
)

$ErrorActionPreference = "Stop"

# ---- 1. Get input path ----
if (-not $SourcePath) {
    $SourcePath = Read-Host "Paste source path"
}

$SourcePath = $SourcePath.Trim().Trim('"').Trim("'")
if (-not $SourcePath) {
    Write-Host "[ERROR] No path provided." -ForegroundColor Red
    exit 1
}

# Auto-convert old server IP to new one
if ($SourcePath -match '^\\\\172\.30\.1\.98\\') {
    $SourcePath = $SourcePath -replace '^\\\\172\.30\.1\.98\\', '\\172.30.9.98\'
    Write-Host "[INFO] Auto-converted \\172.30.1.98 -> \\172.30.9.98" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "===== INPUT =====" -ForegroundColor Cyan
Write-Host "Raw    : $SourcePath"

# ---- 2. Normalize path ----
$normalized = $SourcePath -replace '/', '\'

# Strip leading \\server\share\  ->  keep everything after share
if ($normalized -match '^\\\\([^\\]+)\\([^\\]+)\\(.+)$') {
    $relativePath = $Matches[3]
}
# Drive letter already
elseif ($normalized -match '^[A-Za-z]:\\(.+)$') {
    $relativePath = $Matches[1]
}
# Bare path (no server prefix)
elseif ($normalized -match '^\\\\(.+)$') {
    $relativePath = $Matches[1]
}
else {
    $relativePath = $normalized
}

# ---- 3. Extract project name & leaf dir ----
$pathParts = $relativePath -split '\\' | Where-Object { $_ }
if ($pathParts.Count -lt 2) {
    Write-Host "[ERROR] Path too shallow (need at least 2 levels for project name)." -ForegroundColor Red
    exit 1
}

$leafDir      = $pathParts[-1]
$projectName  = $pathParts[-2]
$sourceFull   = $SourcePath   # keep original as-is (works for UNC too)

$targetProjectDir = Join-Path $TargetBase $projectName
$targetFull       = Join-Path $targetProjectDir $leafDir

Write-Host ""
Write-Host "===== RESOLVED =====" -ForegroundColor Cyan
Write-Host "Source  : $sourceFull"        -ForegroundColor Yellow
Write-Host "Project : $projectName"       -ForegroundColor Green
Write-Host "DirName : $leafDir"           -ForegroundColor Green
Write-Host "Target  : $targetFull"        -ForegroundColor Yellow

# ---- 4. Verify source exists ----
if (-not (Test-Path -LiteralPath $sourceFull)) {
    Write-Host ""
    Write-Host "[ERROR] Source not found: $sourceFull" -ForegroundColor Red
    exit 1
}

# ---- 5. Confirm ----
if (-not $Yes) {
    $confirm = Read-Host "`nProceed with copy? [Y/n]"
    if ($confirm -match '^[Nn]') {
        Write-Host "Cancelled." -ForegroundColor Red
        exit 0
    }
}

# ---- 6. Create target & copy ----
if (-not (Test-Path -LiteralPath $targetProjectDir)) {
    New-Item -ItemType Directory -Path $targetProjectDir -Force | Out-Null
    Write-Host "Created project dir: $targetProjectDir" -ForegroundColor Green
}

if (Test-Path -LiteralPath $targetFull) {
    $overwrite = if ($Yes) { "Y" } else { Read-Host "Target already exists. Overwrite? [y/N]" }
    if ($overwrite -notmatch '^[Yy]') {
        Write-Host "Cancelled." -ForegroundColor Red
        exit 0
    }
    Remove-Item -LiteralPath $targetFull -Recurse -Force
    Write-Host "Removed old directory." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Copying (robocopy /MT:8)..." -ForegroundColor Cyan

$robocopyArgs = @(
    $sourceFull,
    $targetFull,
    "/E",
    "/COPY:DAT",
    "/DCOPY:T",
    "/R:3",
    "/W:3",
    "/MT:8",
    "/NP",
    "/NJH",
    "/NJS"
)

& robocopy @robocopyArgs

$exitCode = $LASTEXITCODE
if ($exitCode -ge 8) {
    Write-Host ""
    Write-Host "[ERROR] robocopy exit code: $exitCode" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "===== EXTRACT =====" -ForegroundColor Cyan

# ---- 7. Find & extract .tar.gz / .tgz files ----
$archives = Get-ChildItem -LiteralPath $targetFull -Recurse -File |
    Where-Object { $_.Name -match '\.(tar\.gz|tgz)$' }

if (-not $archives) {
    Write-Host "No .tar.gz / .tgz files found." -ForegroundColor Yellow
}
else {
    Write-Host "Found $($archives.Count) archive(s) to extract:" -ForegroundColor White

    foreach ($a in $archives) {
        $relPath = $a.FullName.Substring($targetFull.Length).TrimStart('\')
        Write-Host "  [$($a.Name)]  ($([math]::Round($a.Length/1MB,2)) MB)" -ForegroundColor White

        $extractDir = $a.DirectoryName

        Write-Host "    Extracting to: $extractDir" -ForegroundColor DarkGray
        tar -xzf $a.FullName -C $extractDir

        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] $($a.Name) extracted." -ForegroundColor Green

            $del = if ($Yes) { "Y" } else { Read-Host "    Delete the archive file? [Y/n]" }
            if ($del -notmatch '^[Nn]') {
                Remove-Item -LiteralPath $a.FullName -Force
                Write-Host "    Deleted: $($a.Name)" -ForegroundColor Yellow
            }
        }
        else {
            Write-Host "    [FAIL] tar exited with code $LASTEXITCODE" -ForegroundColor Red
        }
    }
}

# ---- 8. Done ----
Write-Host ""
Write-Host "===== DONE =====" -ForegroundColor Green
Write-Host "Path: $targetFull" -ForegroundColor Green

Write-Host ""
if (-not $NoOpen) {
    $open = Read-Host "Open in Explorer? [Y/n]"
    if ($open -notmatch '^[Nn]') {
        Start-Process explorer.exe -ArgumentList $targetFull
    }
}
