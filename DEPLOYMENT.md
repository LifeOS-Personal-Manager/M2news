# M2news 部署指南：方案 B + 方案 C 并行

## 概览

| 方案 | 触发时间 | 访问地址 | 适用场景 |
|------|---------|---------|---------|
| B 本地 Windows | 每日 08:00 | `http://10.5.2.31:5000` | 局域网内快速访问 |
| C GitHub Actions | 每日 08:00 (UTC 00:00) | `https://lifeos-personal-manager.github.io/m2news/` | 对外分享、公网访问 |

两者完全独立、互不干扰，可同时运行。

---

## 方案 B：Windows 任务计划

### 一键安装（管理员）

右键以管理员身份运行以下任一脚本：

```
scripts\setup_tasks.bat        ← 双击运行（.bat 最简单）
scripts\setup_windows_tasks.ps1 ← PowerShell 版（功能更详细）
```

脚本会自动完成三件事：

1. **每日 08:00 采集** — 注册任务 `M2news Daily Digest`，调用 `scripts/run_once.ps1`
2. **开机自启 API** — 注册任务 `M2news Flask API`，调用 `scripts/start_api.ps1`
3. **防火墙放行** — 开放 TCP 5000 端口入站（Private + Domain 配置文件）

### 手动执行（管理员 PowerShell）

如不想用脚本，逐条执行：

```powershell
# 每日 08:00 采集
schtasks /create /tn "M2news Daily Digest" `
  /tr "powershell.exe -ExecutionPolicy Bypass -NoProfile -File 'e:\AI\Codex\LifeOS\M2news\scripts\run_once.ps1'" `
  /sc daily /st 08:00 /f

# 开机自启 Flask
schtasks /create /tn "M2news Flask API" `
  /tr "powershell.exe -ExecutionPolicy Bypass -NoProfile -File 'e:\AI\Codex\LifeOS\M2news\scripts\start_api.ps1'" `
  /sc onlogon /f

# 防火墙放行
netsh advfirewall firewall add rule name="M2news Flask API (TCP 5000)" `
  dir=in action=allow protocol=TCP localport=5000 profile=private,domain
```

### 管理命令

```powershell
schtasks /run  /tn "M2news Daily Digest"   # 手动触发一次采集
schtasks /run  /tn "M2news Flask API"       # 手动启动 API
schtasks /query /tn "M2news Daily Digest" /fo list  # 查看状态
schtasks /delete /tn "M2news Daily Digest" /f       # 删除任务
```

### 日志位置

- 采集日志：`logs/digest_YYYYMMDD.log`
- API 日志：`logs/api.log`

---

## 方案 C：GitHub Actions + Pages

### 前置条件

- Git remote 已配置：`https://github.com/LifeOS-Personal-Manager/M2news.git`
- Workflow 已就绪：`.github/workflows/daily-news.yml`
- `.env` 已在 `.gitignore` 中（不会泄露密钥）

### 步骤 1：配置 GitHub Secrets

进入仓库 `Settings → Secrets and variables → Actions → Secrets`：

| Secret 名称 | 值 | 必填 |
|-------------|---|------|
| `OPENAI_API_KEY` | 你的 OpenRouter API Key | ✅ |
| `SUPABASE_URL` | Supabase 项目 URL | 仅备份时 |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | 仅备份时 |

### 步骤 2：配置 GitHub Variables

进入仓库 `Settings → Secrets and variables → Actions → Variables`：

| Variable 名称 | 值 | 必填 |
|---------------|---|------|
| `NEWS_SOURCES` | `[{"name":"新华网时政","region":"domestic","type":"rss","url":"http://www.xinhuanet.com/politics/news_politics.xml","enabled":true},...]` | ✅ |
| `BASE_URL` | `https://lifeos-personal-manager.github.io/m2news` | ✅ |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | ✅ |
| `OPENAI_MODEL` | `openrouter/free` | ✅ |
| `ENABLE_SUPABASE_BACKUP` | `false` | 可选 |

> `NEWS_SOURCES` 内容可从本地 `.env` 文件第一行复制（移除 `NEWS_SOURCES=` 前缀）。

### 步骤 3：启用 GitHub Pages

1. 进入仓库 `Settings → Pages`
2. Source 选择 **`GitHub Actions`**
3. 保存

### 步骤 4：推送代码（如有新文件）

```powershell
cd e:\AI\Codex\LifeOS\M2news
git add scripts/setup_windows_tasks.ps1 scripts/setup_tasks.bat DEPLOYMENT.md
git commit -m "Add Windows task scheduler setup scripts and deployment guide"
git push origin main
```

### 步骤 5：触发首次构建

进入仓库 `Actions → Daily News Digest → Run workflow`，手动触发一次。

构建成功后访问：

```
https://lifeos-personal-manager.github.io/m2news/
https://lifeos-personal-manager.github.io/m2news/news/latest.html
https://lifeos-personal-manager.github.io/m2news/news/latest.json
```

之后每天北京时间 08:00 自动触发。

---

## 两方案对比

| 维度 | 方案 B (本地) | 方案 C (GitHub) |
|------|-------------|----------------|
| 数据源 | 同一份 `.env` | GitHub Variables |
| LLM Key | 本地 `.env` | GitHub Secrets |
| 运行环境 | 你的电脑 | GitHub 云端 |
| 依赖电脑开机 | ✅ 是 | ❌ 否 |
| 公网可访问 | ❌ 仅局域网 | ✅ 全球可访问 |
| 成本 | 免费 | 免费 (GitHub Actions 免费额度)
