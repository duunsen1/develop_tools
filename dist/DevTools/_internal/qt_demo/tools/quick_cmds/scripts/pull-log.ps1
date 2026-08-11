<#
.SYNOPSIS
    Pull testlog directories from X: drive to local, organized by project.

.DESCRIPTION
    Accepts paths like:
      - UNC:      \\172.30.1.96\testlog\Smartphone\Xian\23112C_17C\ARBOK17C-2322
      - Half:     /Testlog/Smartphone/Xian_Test/24111&24111Pro_17C/ARCA17C-321
      - X-drive:  X:\Smartphone\Xian\23112C_17C\ARBOK17C-2322
      - Generic:  \\server\share\...

    Finds "testlog" (case-insensitive) in the path, replaces everything before it
    with X:\, then copies the directory to D:\Work\2_问题单处理\<ProjectName>\<DirName>\

    Usage:
      .\pull-log.ps1                                  (interactive, paste path)
      .\pull-log.ps1 "\\172.30.1.96\testlog\..."
#>

param(
    [Parameter(Position = 0)]
    [string]$SourcePath,
    [string]$TargetBase = "D:\Work\2_问题单处理",
    [switch]$Yes,      # 跳过"确认复制/覆盖"提问
    [switch]$NoOpen    # 跳过"是否打开资源管理器"
)

$ErrorActionPreference = "Stop"

# ---- Config ----
$XDriveRoot = "X:\"

# ---- 1. Get input path ----
if (-not $SourcePath) {
    $SourcePath = Read-Host "Paste source path"
}

$SourcePath = $SourcePath.Trim().Trim('"').Trim("'")
if (-not $SourcePath) {
    Write-Host "[ERROR] No path provided." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "===== INPUT =====" -ForegroundColor Cyan
Write-Host "Raw    : $SourcePath"

# ---- 2. Normalize & extract relative path ----
$normalized = $SourcePath -replace '/', '\'

$relativePath = $null

# Try: ...\testlog\...  (case-insensitive)
if ($normalized -match '\\testlog\\(.+)$') {
    $relativePath = $Matches[1]
}
# Try: already X:\...
elseif ($normalized -match '^X:\\(.+)$') {
    $relativePath = $Matches[1]
}
# Try: other drive letter
elseif ($normalized -match '^[A-Za-z]:\\(.+)$') {
    $relativePath = $Matches[1]
}
# Try: general UNC \\server\share\...
elseif ($normalized -match '^\\\\([^\\]+)\\([^\\]+)\\(.+)$') {
    $relativePath = $Matches[3]
}

if (-not $relativePath) {
    Write-Host "[ERROR] Cannot parse path. Expected 'testlog' or drive letter or UNC." -ForegroundColor Red
    exit 1
}

$sourceFull = Join-Path $XDriveRoot $relativePath

# ---- 3. Extract project name & leaf dir ----
$pathParts = $relativePath -split '\\' | Where-Object { $_ }
if ($pathParts.Count -lt 2) {
    Write-Host "[ERROR] Path too shallow (need at least 2 levels for project name)." -ForegroundColor Red
    exit 1
}

$leafDir     = $pathParts[-1]
$projectName = $pathParts[-2]

$targetProjectDir = Join-Path $TargetBase $projectName
$targetFull       = Join-Path $targetProjectDir $leafDir

Write-Host ""
Write-Host "===== RESOLVED =====" -ForegroundColor Cyan
Write-Host "Source  : $sourceFull"        -ForegroundColor Yellow
Write-Host "Project : $projectName"       -ForegroundColor Green
Write-Host "LogDir  : $leafDir"           -ForegroundColor Green
Write-Host "Target  : $targetFull"        -ForegroundColor Yellow

# ---- 4. Verify source exists ----
if (-not (Test-Path -LiteralPath $sourceFull)) {
    Write-Host ""
    Write-Host "[ERROR] Source not found: $sourceFull" -ForegroundColor Red
    Write-Host "Check that X: drive is mapped correctly." -ForegroundColor Red
    exit 1
}

# Estimate size
try {
    $files = Get-ChildItem -LiteralPath $sourceFull -Recurse -File -ErrorAction SilentlyContinue
    $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
    $fileCount = $files.Count
    if ($totalSize -gt 0) {
        $sizeMB = [math]::Round($totalSize / 1MB, 2)
        Write-Host "Size    : ${sizeMB} MB ($fileCount files)" -ForegroundColor Magenta
    }
} catch {
    Write-Host "(cannot estimate size)"
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

# ---- 7. Done ----
Write-Host ""
Write-Host "===== DONE =====" -ForegroundColor Green
Write-Host "Copied to: $targetFull" -ForegroundColor Green

Write-Host ""
if (-not $NoOpen) {
    $open = Read-Host "Open in Explorer? [Y/n]"
    if ($open -notmatch '^[Nn]') {
        Start-Process explorer.exe -ArgumentList $targetFull
    }
}
