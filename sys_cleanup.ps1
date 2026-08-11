# ============================================================
# Windows System Diagnostic & Cleanup Script
# Usage: Run PowerShell as Administrator, then execute this script
# ============================================================

$ErrorActionPreference = "SilentlyContinue"
$Host.UI.RawUI.WindowTitle = "System Diagnostic & Cleanup"

# ---------- Check Admin Privileges ----------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "WARNING: Not running as Administrator. Some cleanup functions will be skipped." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Windows System Diagnostic & Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Part 1: Diagnostic
# ============================================================
Write-Host "[1/6] Memory Usage" -ForegroundColor Green
Write-Host "----------------------------------------"
$os = Get-CimInstance Win32_OperatingSystem
$totalGB  = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeGB   = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
$usedGB   = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 1)
$usagePct = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 1)

Write-Host "  Total:     $totalGB GB"
Write-Host "  Used:      $usedGB GB  ($usagePct%)"
Write-Host "  Available: $freeGB GB"

if ($usagePct -gt 85) {
    Write-Host "  *** WARNING: Memory usage is high! ***" -ForegroundColor Red
} elseif ($usagePct -gt 65) {
    Write-Host "  * Memory usage is moderate, keep an eye on it." -ForegroundColor Yellow
} else {
    Write-Host "  OK - Memory usage is normal." -ForegroundColor Green
}
Write-Host ""

Write-Host "[2/6] Top 10 Processes by Memory" -ForegroundColor Green
Write-Host "----------------------------------------"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 `
    Name, @{N='Memory(MB)';E={[math]::Round($_.WorkingSet64/1MB,1)}}, `
    @{N='CPU(s)';E={[math]::Round($_.CPU,1)}}, Id | Format-Table -AutoSize
Write-Host ""

Write-Host "[3/6] C: Drive Free Space" -ForegroundColor Green
Write-Host "----------------------------------------"
$cDrive = Get-PSDrive C
$freeGB = [math]::Round($cDrive.Free / 1GB, 1)
$usedGB = [math]::Round($cDrive.Used / 1GB, 1)
$totalGB = [math]::Round(($cDrive.Used + $cDrive.Free) / 1GB, 1)
Write-Host "  C: Total: $totalGB GB"
Write-Host "  Used:     $usedGB GB"
Write-Host "  Free:     $freeGB GB"
if ($freeGB -lt 20) {
    Write-Host "  *** WARNING: C: drive is low on space! Keep at least 20GB free. ***" -ForegroundColor Red
} else {
    Write-Host "  OK - C: drive space is sufficient." -ForegroundColor Green
}
Write-Host ""

Write-Host "[4/6] Startup Programs" -ForegroundColor Green
Write-Host "----------------------------------------"
$startupApps = Get-CimInstance Win32_StartupCommand | Where-Object { $_.User -ne "" -or $_.Location -like "*Startup*" }
if ($startupApps.Count -gt 0) {
    $startupApps | Select-Object Name, Command, User | Format-Table -AutoSize -Wrap
} else {
    Write-Host "  No explicit startup items found."
}
Write-Host "  --- Registry Run Keys ---"
$regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
if (Test-Path $regPath) {
    $items = Get-ItemProperty $regPath
    $items.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object {
        Write-Host "  [HKLM] $($_.Name) => $($_.Value)"
    }
}
$regPath2 = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
if (Test-Path $regPath2) {
    $items = Get-ItemProperty $regPath2
    $items.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object {
        Write-Host "  [HKCU] $($_.Name) => $($_.Value)"
    }
}
Write-Host ""

Write-Host "[5/6] CPU Temperature (if sensor available)" -ForegroundColor Green
Write-Host "----------------------------------------"
try {
    $temp = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop
    if ($temp) {
        $celsius = ($temp.CurrentTemperature / 10) - 273.15
        Write-Host "  CPU Temp: $([math]::Round($celsius, 1)) C"
        if ($celsius -gt 85) { Write-Host "  *** WARNING: High temperature, may cause throttling! ***" -ForegroundColor Red }
    }
} catch {
    Write-Host "  (Cannot read temperature sensor, skipping)" -ForegroundColor DarkGray
}
Write-Host ""

# ============================================================
# Part 2: Confirm Cleanup
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Diagnostic Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$choice = Read-Host "Run cleanup? (y=all / n=skip / s=select)"

if ($choice -eq 'n') {
    Write-Host "Cleanup skipped. Script finished." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

if ($choice -eq 's') {
    Write-Host ""
    Write-Host "Select cleanup items (y/n):" -ForegroundColor Cyan
    $doTemp     = (Read-Host "  Clean temporary files?") -eq 'y'
    $doDns      = (Read-Host "  Flush DNS cache?") -eq 'y'
    $doMem      = (Read-Host "  Trim process working sets?") -eq 'y'
    $doUpdate   = (Read-Host "  Clean Windows Update cache?") -eq 'y'
    $doPrefetch = (Read-Host "  Clean Prefetch?") -eq 'y'
    $doRecycle  = (Read-Host "  Empty Recycle Bin?") -eq 'y'
} else {
    $doTemp = $doDns = $doMem = $doUpdate = $doPrefetch = $doRecycle = $true
}

Write-Host ""
Write-Host "[6/6] Running cleanup..." -ForegroundColor Green
Write-Host "========================================"

# --- Clean Temporary Files ---
if ($doTemp) {
    Write-Host "  > Cleaning temporary files..." -ForegroundColor Yellow
    $paths = @(
        "$env:TEMP",
        "$env:WINDIR\Temp",
        "$env:LOCALAPPDATA\Temp"
    )
    $totalCleaned = 0
    foreach ($p in $paths) {
        if (Test-Path $p) {
            Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
                try {
                    $size = $_.Length
                    Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                    $script:totalCleaned += $size
                } catch {}
            }
        }
    }
    $cleanedMB = [math]::Round($totalCleaned / 1MB, 1)
    Write-Host "    Cleaned ~$cleanedMB MB of temporary files"
}

# --- Flush DNS Cache ---
if ($doDns) {
    Write-Host "  > Flushing DNS cache..." -ForegroundColor Yellow
    ipconfig /flushdns | Out-Null
    Write-Host "    DNS cache flushed"
}

# --- Trim Process Working Sets ---
if ($doMem) {
    Write-Host "  > Trimming process working sets..." -ForegroundColor Yellow
    $beforeFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB

    # P/Invoke: EmptyWorkingSet
    $signature = @'
[DllImport("psapi.dll", SetLastError = true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
'@
    $type = Add-Type -MemberDefinition $signature -Name "Win32EmptyWorkingSet" -Namespace "PSAPI" -PassThru

    $excluded = @('System', 'Idle', 'svchost', 'csrss', 'winlogon', 'lsass', 'services')
    $processes = Get-Process | Where-Object { $_.WorkingSet64 -gt 10MB -and $_.Name -notin $excluded }
    foreach ($proc in $processes) {
        try {
            $type::EmptyWorkingSet($proc.Handle)
        } catch {}
    }

    $afterFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    $freed = [math]::Round($afterFree - $beforeFree, 1)
    Write-Host "    Freed ~$freed MB of memory"
}

# --- Clean Windows Update Cache ---
if ($doUpdate) {
    Write-Host "  > Cleaning Windows Update cache..." -ForegroundColor Yellow
    if ($isAdmin) {
        Stop-Service wuauserv -Force -ErrorAction SilentlyContinue
        Stop-Service bits -Force -ErrorAction SilentlyContinue
        $updatePath = "$env:WINDIR\SoftwareDistribution\Download"
        if (Test-Path $updatePath) {
            $size = (Get-ChildItem $updatePath -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
            Remove-Item "$updatePath\*" -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "    Cleaned ~$([math]::Round($size/1MB,1)) MB of Update cache"
        }
        Start-Service wuauserv -ErrorAction SilentlyContinue
        Start-Service bits -ErrorAction SilentlyContinue
    } else {
        Write-Host "    (Admin rights required, skipping)" -ForegroundColor DarkGray
    }
}

# --- Clean Prefetch ---
if ($doPrefetch) {
    Write-Host "  > Cleaning Prefetch..." -ForegroundColor Yellow
    $prefetchPath = "$env:WINDIR\Prefetch"
    if (Test-Path $prefetchPath) {
        $size = (Get-ChildItem $prefetchPath -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
        Remove-Item "$prefetchPath\*.pf" -Force -ErrorAction SilentlyContinue
        Write-Host "    Cleaned ~$([math]::Round($size/1MB,1)) MB of Prefetch data"
    }
}

# --- Empty Recycle Bin ---
if ($doRecycle) {
    Write-Host "  > Emptying Recycle Bin..." -ForegroundColor Yellow
    $shell = New-Object -ComObject Shell.Application
    $shell.Namespace(0xA).Items() | ForEach-Object { Remove-Item $_.Path -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host "    Recycle Bin emptied"
}

# ============================================================
# Done
# ============================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cleanup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Final memory status
$os = Get-CimInstance Win32_OperatingSystem
$freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
Write-Host "Current available memory: $freeGB GB" -ForegroundColor Green
Write-Host ""
Write-Host "=== Daily Optimization Tips ===" -ForegroundColor Cyan
Write-Host "1. Reduce startup programs: Task Manager > Startup > Disable unnecessary items"
Write-Host "2. Browser tabs: Use OneTab or Tab Suspender extension to freeze inactive tabs"
Write-Host "3. Background apps: Settings > Privacy > Background Apps > Turn off unused ones"
Write-Host "4. Restart regularly: Windows benefits from a weekly restart"
Write-Host "5. Visual effects: Settings > System > About > Advanced System Settings >"
Write-Host "   Performance > Adjust for best performance"
Write-Host "6. Malware scan: Windows Security > Virus & Threat Protection > Quick Scan"
Write-Host ""
Write-Host "Tip: Run 'taskmgr' to open Task Manager and check real-time resource usage."
Write-Host ""

Read-Host "Press Enter to exit"