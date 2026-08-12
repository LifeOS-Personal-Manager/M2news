@echo off
cd /d e:\AI\Codex\LifeOS\M2news
echo Running M2news pipeline with new chief editor prompts...
echo.
.\.venv\Scripts\python.exe -m src.main
echo.
echo EXIT_CODE=%errorlevel%
echo.
if exist "public\news\latest.json" (
    echo === Result ===
    .\.venv\Scripts\python.exe -c "import json; d=json.load(open('public/news/latest.json','encoding='utf-8')); print('Date:', d['date']); print('Highlights:', len(d['top_highlights'])); [print(f'  {h}') for h in d['top_highlights']]; total=sum(len(d['sections'][r][c]) for r in d['sections'] for c in d['sections'][r]); print(f'Articles: {total}'); print(); [print(f'{r}/{c}: {len(d[\"sections\"][r][c])}') for r in d['sections'] for c in d['sections'][r]]"
)
echo.
echo Done.
pause
