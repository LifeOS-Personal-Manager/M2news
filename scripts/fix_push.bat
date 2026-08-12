@echo off
cd /d e:\AI\Codex\LifeOS\M2news
git add pyproject.toml .github\workflows\daily-news.yml
git commit -m "fix: correct pyproject.toml build-backend to setuptools.build_meta"
git push origin main
echo EXIT_CODE=%errorlevel%
