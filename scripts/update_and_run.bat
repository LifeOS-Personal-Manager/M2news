@echo off
chcp 65001 >nul
title M2news - 更新新闻源 & 推送 & 运行
echo ==========================================
echo  M2news 一键更新脚本
echo  - 提交并推送新源配置到 GitHub
echo  - 立即运行采集管线测试新源
echo ==========================================
echo.

cd /d e:\AI\Codex\LifeOS\M2news

echo [1/4] 修复 PowerShell 执行策略...
powershell -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"
echo done.
echo.

echo [2/4] 提交并推送到 GitHub...
git add -A
git commit -m "Update NEWS_SOURCES to 19 RSS feeds across 6 categories"
git push origin main
echo.
echo git push exit code: %errorlevel%
echo.

echo [3/4] 运行新闻采集管线（19个源，约需2-3分钟）...
.\.venv\Scripts\python.exe -m src.main
echo.
echo pipeline exit code: %errorlevel%
echo.

echo [4/4] 验证结果...
if exist "public\news\latest.json" (
    echo latest.json 已生成
    .\.venv\Scripts\python.exe -c "import json; d=json.load(open('public/news/latest.json','encoding='utf-8')); print('日期:', d['date']); print('生成时间:', d['generated_at']); sources=set(); [sources.add(a['source']) for s in d['sections'].values() for cat in s.values() for a in cat]; print('成功源数:', len(sources)); print('源列表:', ', '.join(sorted(sources)))"
) else (
    echo [ERROR] latest.json 未生成
)

echo.
echo ==========================================
echo  完成！局域网访问: http://10.5.2.31:5000/news/latest
echo  GitHub 仓库: https://github.com/LifeOS-Personal-Manager/M2news
echo ==========================================
pause
