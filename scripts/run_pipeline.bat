@echo off
cd /d e:\AI\Codex\LifeOS\M2news
e:\AI\Codex\LifeOS\M2news\.venv\Scripts\python.exe -m src.main > e:\AI\Codex\LifeOS\M2news\logs\pipeline_run.log 2>&1
echo EXIT_CODE=%errorlevel%
