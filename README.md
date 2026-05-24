# FundPilot

FundPilot 是一个本地基金投研助手。它用 AKShare/Eastmoney 采集基金与市场数据，用 PostgreSQL 保存净值、指标、评分、持仓、预警和报告，用 FastAPI 提供结构化接口，用 Vue 3 构建日常使用的前端工作台，并用 Ollama 或规则兜底生成谨慎的 AI 简报。

## 核心能力

- 自选基金管理：添加、移除、同步单只或全部自选基金。
- 数据健康检查：识别净值过旧、断档、缺失涨跌幅和待计算指标。
- 基金分析：净值、回撤、日涨跌幅、收益率、波动率、夏普比率、胜率和评分。
- 横向对比：2-5 只基金指标对比、风险收益散点、行业/主题汇总。
- 持仓管理：买入记录、自动汇总份额和成本、组合收益与持仓占比。
- 风险提醒：大跌、回撤、评分下降、持仓集中和高相关重复配置。
- AI 简报：基于结构化数据生成每日总结，失败时使用规则兜底。
- 任务中心：手动触发同步、指标、评分、预警、市场数据和日报任务。

## 技术架构

```mermaid
flowchart LR
    Vue["Vue 3 + Element Plus + ECharts"] --> API["FastAPI /api/v1"]
    API --> Services["业务服务层 app/services"]
    Services --> DB[("PostgreSQL")]
    Services --> DataSources["AKShare / Eastmoney"]
    Services --> Ollama["Ollama"]
    Jobs["APScheduler 可选定时任务"] --> Services
    Scripts["scripts 手动任务"] --> Services
```

- 前端：`frontend/`，Vue 3 + TypeScript + Vite + Element Plus + ECharts。
- 后端 API：`app/api/v1`，负责给 Vue 提供稳定接口。
- 业务服务：`app/services`，集中处理同步、指标、评分、组合、预警、相关性和报告逻辑。
- 数据源：`app/data_source`，封装 AKShare 与 Eastmoney。
- 数据库：SQLAlchemy ORM + Alembic 迁移。
- 定时任务：`app/jobs`，默认关闭，可用 `ENABLE_SCHEDULER=true` 开启。

## 项目结构

```text
FundPilot/
├── app/
│   ├── api/v1/          # FastAPI 路由
│   ├── core/            # 配置和日志
│   ├── data_source/     # 外部数据源客户端
│   ├── db/              # SQLAlchemy session 和模型
│   ├── jobs/            # 可选定时任务
│   ├── schemas/         # Pydantic 出入参模型
│   └── services/        # 核心业务逻辑
├── frontend/            # Vue 3 前端工作台
│   ├── src/api/         # API client、类型和字段标签
│   ├── src/components/  # 通用组件
│   ├── src/pages/       # 业务页面
│   └── src/router/      # Vue Router
├── alembic/             # 数据库迁移
├── docs/                # 架构、数据库、评分、AI 安全和前端说明
├── scripts/             # 手动任务入口
├── tests/               # 后端服务和 API 契约测试
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## 本地启动

```bash
uv sync
copy .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

启动 Vue 前端：

```bash
cd frontend
npm install
npm run dev
```

访问地址：

- FastAPI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Vue: http://127.0.0.1:5173

如果本机没有可用 Node.js/npm，可以用 Docker 启动前端：

```bash
docker compose up frontend
```

## 配置

常用配置在 `.env` 中：

```env
APP_ENV=dev
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/fund_watcher
BACKEND_PORT=8000
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

## 开发校验

后端：

```bash
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
```

前端：

```bash
cd frontend
npm run typecheck
npm run build
```

## 产品边界

FundPilot 只做数据监控、规则评分和解释性总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
