# FundPilot

FundPilot 是一个本地基金投研助手：用 AKShare/Eastmoney 采集基金净值，用 PostgreSQL 保存数据，用 Pandas 计算指标，用规则模型评分，用 FastAPI 提供接口，并用 Streamlit 与 Vue 两套前端并行展示。

## 功能

- 自选基金增删查
- 基金历史净值采集和入库
- 收益率、最大回撤、波动率、夏普比率、胜率计算
- 基金评分、评级和推荐关注列表
- 持仓盈亏估算
- 风险预警与相关性分析
- AI 每日简报和单只基金解释
- Streamlit 对照看板与 Vue 3 新前端

## 本地启动

```bash
uv sync
copy .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

启动 Streamlit 对照版：

```bash
uv run streamlit run dashboard/streamlit_app.py
```

启动 Vue 新版：

```bash
cd frontend
npm install
npm run dev
```

访问地址：

- FastAPI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Streamlit: http://127.0.0.1:8501
- Vue: http://127.0.0.1:5173

## Vue 前端

Vue 前端位于 `frontend/`，技术栈为 Vue 3 + TypeScript + Vite + Element Plus + ECharts。它通过 Vite dev server 代理 `/api` 到 FastAPI，因此本地开发不需要额外 CORS 配置。

常用命令：

```bash
cd frontend
npm run typecheck
npm run build
```

当前环境如果没有可用 Node.js/npm，可以用 Docker Compose 启动前端：

```bash
docker compose up frontend
```

## 配置

常用配置在 `.env` 中：

```env
APP_ENV=dev
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/fund_watcher
BACKEND_PORT=8000
STREAMLIT_PORT=8501
FRONTEND_PORT=5173
SYNC_NAV_CRON=18:00
ENABLE_SCHEDULER=false
AUTO_CREATE_TABLES=true
OLLAMA_MODEL=qwen3:14b
OLLAMA_TIMEOUT=180
```

`ENABLE_SCHEDULER=false` 默认不自动跑定时任务，避免本地启动后立刻拉取外部数据。`AUTO_CREATE_TABLES=true` 仅用于开发期快速启动，正式路径建议执行 Alembic 迁移。

## 手动任务

```bash
uv run python scripts/add_watchlist.py
uv run python scripts/sync_market_context.py
uv run python scripts/sync_watchlist_nav.py
uv run python scripts/calc_indicators.py
uv run python scripts/calc_scores.py
uv run python scripts/generate_alerts.py
uv run python scripts/generate_daily_report.py
uv run python scripts/run_smoke_check.py
```

## 数据流

```text
watchlist -> sync_nav -> fund_nav -> indicators -> scores -> dashboard/report
market indexes -> market_index_daily -> market context -> dashboard/report
portfolio_position + latest nav -> portfolio overview -> alerts/report
fund_nav daily_return -> correlation matrix -> high-correlation alerts
task execution -> task_run_log -> task center
```

## Vue 覆盖验收

按 [docs/frontend_coverage.md](docs/frontend_coverage.md) 对照 Streamlit 与 Vue 页面。Vue 覆盖完成前，Streamlit 继续保留为可用版本和对照基线。

## Docker 启动

```bash
copy .env.example .env
docker compose up --build
```

Docker Compose 会启动 PostgreSQL、FastAPI、Streamlit 和 Vue 前端。首次启动 Vue 服务会在容器内执行 `npm install`。

## 重要边界

FundPilot 只做数据监控、规则评分和解释性总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
