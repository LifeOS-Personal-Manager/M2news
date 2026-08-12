@echo off
chcp 65001 >nul
title M2news - 一键推送 & 运行 & 自检
echo ==========================================
echo  M2news 一键操作脚本
echo  1. 提交所有修改
echo  2. 推送到 GitHub
echo  3. 运行采集管线
echo  4. 输出采集统计
echo ==========================================
echo.

cd /d e:\AI\Codex\LifeOS\M2news

echo [1/4] 提交代码...
git add -A
git commit -m "fix: add error handling, update DEFAULT_SOURCES to 19, harden CI" 2>nul
git push origin main
echo.

echo [2/4] 运行采集管线（约需 3-5 分钟）...
echo.
.\.venv\Scripts\python.exe -c "import json,os,sys; sys.path.insert(0,'.'); from src.config import load_settings; from src.collector.collector import NewsCollector; from src.llm.digest_analyzer import DigestAnalyzer; from src.generator.digest_generator import DigestGenerator; from src.storage.file_store import FileStore; settings=load_settings(); print(f'Sources: {len(settings.news_sources)}'); [print(f'  [{s.name}] {s.region} {s.type} {s.url[:60]}') for s in settings.news_sources if s.enabled]; c=NewsCollector(settings); items=c.collect_all(); print(f'\nCollected: {len(items)} raw items'); a=DigestAnalyzer(settings); d=a.analyze(target_date=__import__('datetime').date.today().isoformat(), period_from=(__import__('datetime').date.today()-__import__('datetime').timedelta(days=1)).isoformat(), period_to=__import__('datetime').date.today().isoformat(), items=items); fs=FileStore(settings.output_dir); g=DigestGenerator(fs); jp,hp=g.generate(d); total=sum(len(d.sections[r][c]) for r in d.sections for c in d.sections[r]); print(f'Digest: {total} articles, {len(d.top_highlights)} highlights'); print(f'JSON: {jp}'); print(f'HTML: {hp}'); print('\nTop highlights:'); [print(f'  - {h}') for h in d.top_highlights[:5]]"
set EXIT=%errorlevel%
echo.

if %EXIT%==0 (
    echo [3/4] 管线运行成功！
) else (
    echo [3/4] 管线退出码: %EXIT%
)

echo.
echo [4/4] 验证输出文件...
if exist "public\news\latest.json" (
    echo   latest.json 存在
    for %%A in ("public\news\latest.json") do echo   文件大小: %%~zA 字节
) else (
    echo   latest.json 不存在!
)
if exist "public\news\latest.html" (
    echo   latest.html 存在
    for %%A in ("public\news\latest.html") do echo   文件大小: %%~zA 字节
) else (
    echo   latest.html 不存在!
)

echo.
echo ==========================================
echo  完成！
echo  局域网: http://10.5.2.31:5000/news/latest
echo  公网:   https://lifeos-personal-manager.github.io/m2news/news/latest
echo  GitHub: https://github.com/LifeOS-Personal-Manager/M2news/actions
echo ==========================================
pause
