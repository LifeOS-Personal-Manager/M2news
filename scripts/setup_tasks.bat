@echo off
chcp 65001 >nul
echo === M2news Windows 任务计划安装 ===
echo (需以管理员身份运行)
echo.

REM 1. 每日 08:00 采集任务
schtasks /create /tn "M2news Daily Digest" /tr "powershell.exe -ExecutionPolicy Bypass -NoProfile -File \"e:\AI\Codex\LifeOS\M2news\scripts\run_once.ps1\"" /sc daily /st 08:00 /f
echo.

REM 2. 开机自启 Flask API
schtasks /create /tn "M2news Flask API" /tr "powershell.exe -ExecutionPolicy Bypass -NoProfile -File \"e:\AI\Codex\LifeOS\M2news\scripts\start_api.ps1\"" /sc onlogon /f
echo.

REM 3. 防火墙放行 TCP 5000
netsh advfirewall firewall add rule name="M2news Flask API (TCP 5000)" dir=in action=allow protocol=TCP localport=5000 profile=private,domain
echo.

echo === 安装完成 ===
echo 局域网访问: http://10.5.2.31:5000/news/latest
echo.
pause
