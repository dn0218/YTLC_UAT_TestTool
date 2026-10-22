@echo off
rem ============================================================
rem  Preprod TestTool - customer environment preflight check
rem  NOTHING needs to be installed: PreprodTestTool.exe already
rem  bundles Python + all libraries (onefile build).
rem  This script only verifies: files present, SmartScreen mark
rem  removed, and network reachability of every endpoint in
rem  config_ocs.json.
rem ============================================================
setlocal EnableExtensions
title Preprod TestTool - Environment Check
cd /d "%~dp0"

echo.
echo ===== Preprod TestTool : Environment Preflight =====
echo.

if not exist "PreprodTestTool.exe" (
    echo [FAIL] PreprodTestTool.exe NOT found in this folder.
    echo        Keep PreprodTestTool.exe + config_ocs.json + this .bat in the SAME folder.
    goto :finish
)
echo [OK]   PreprodTestTool.exe

if not exist "config_ocs.json" (
    echo [FAIL] config_ocs.json NOT found in this folder.
    goto :finish
)
echo [OK]   config_ocs.json

rem Remove the Mark-of-the-Web (set when a file is downloaded / forwarded
rem by chat tools), so Windows SmartScreen does not block the first start.
powershell -NoProfile -Command "Unblock-File -Path '.\PreprodTestTool.exe','.\config_ocs.json' -ErrorAction SilentlyContinue" >nul 2>&1
echo [OK]   SmartScreen mark removed (if any)

echo.
echo Network reachability (endpoints from config_ocs.json, 3s timeout each):
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg = Get-Content -Raw 'config_ocs.json' | ConvertFrom-Json; $targets = @(); $targets += ,@('Oracle DB', $cfg.db.host, [int]$cfg.db.port); if ($cfg.crm_db) { $targets += ,@('CRM DB', $cfg.crm_db.host, [int]$cfg.crm_db.port) }; $targets += ,@('SSH (ocs)', $cfg.ssh.host, 22); if ($cfg.api.base_url) { $u = [uri]($cfg.api.base_url.Trim()); $targets += ,@('Job API', $u.Host, $u.Port) }; if ($cfg.redis) { foreach ($n in $cfg.redis.nodes) { $targets += ,@('Redis', $n[0], [int]$n[1]) } }; $fail = 0; foreach ($t in $targets) { $c = New-Object Net.Sockets.TcpClient; $ar = $c.BeginConnect($t[1], $t[2], $null, $null); $ok = $ar.AsyncWaitHandle.WaitOne(3000); if ($ok -and $c.Connected) { $st = 'OK  ' } else { $st = 'FAIL'; $fail = 1 }; $c.Close(); Write-Host ('  [' + $st + '] ' + $t[0] + '   ' + $t[1] + ':' + $t[2]) }; exit $fail"

if errorlevel 1 (
    echo.
    echo [WARN] Some endpoints are NOT reachable - the tool cannot work
    echo        without them. Check VPN / firewall / routing first.
) else (
    echo.
    echo [OK] All endpoints reachable.
)

echo.
set "LAUNCH="
set /p "LAUNCH=Launch PreprodTestTool.exe now? [y/N]: "
if /i "%LAUNCH%"=="y" start "" PreprodTestTool.exe

:finish
echo.
pause
endlocal
