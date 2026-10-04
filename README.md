# FundPilot

FundPilot 是一个本地单用户投资驾驶舱。它用 AKShare/Eastmoney 采集基金、股票、ETF 与市场数据，用 PostgreSQL 保存行情、指标、评分、持仓、预警和报告，用 FastAPI 提供结构化接口，用 Vue 3 构建日常使用的前端工作台，并用 Ollama、DeepSeek 或规则兜底生成谨慎的 AI 简报。

## 核心能力

- 今日驾驶舱：聚合数据健康、待办事项、关键风险、未读预警、市场背景和最新日报。
- 自选基金管理：添加、移除、同步单只或全部自选基金，并展示分析状态。
- 基金分析：净值、回撤、日涨跌幅、收益率、波动率、夏普比率、胜率和评分；基金解释由 AI 单独生成，避免拖慢快速分析。
- 统一持仓管理：股票、基金和 ETF 共用交易账本，支持买入、卖出、申购、赎回、自动汇总成本和持仓。
- 股票/ETF 行情：可从持仓页同步 A 股股票或 ETF 日线，和基金净值一起计算组合市值与回撤。
- 风险提醒：大跌、回撤、评分下降、持仓集中和高相关重复配置。
- AI 简报：基于结构化数据生成每日复盘，失败时使用规则兜底。
- 任务中心：前台或后台触发同步、指标、评分、预警、市场数据和日报任务。

## 技术架构

```mermaid
flowchart LR
    Vue["Vue 3 + TypeScript + Element Plus + ECharts"] --> API["FastAPI /api/v1"]
    API --> Services["业务服务 app/services"]
    Services --> DB[("PostgreSQL")]
    Services --> DataSources["AKShare / Eastmoney"]
    Services --> AI["Ollama / DeepSeek"]
    Jobs["APScheduler 可选定时任务"] --> Services
    Scripts["scripts 手动任务"] --> Services
```

- 前端：`frontend/`，Vue 3 + TypeScript + Vite + Element Plus + ECharts。
- 后端 API：`app/api/v1`，负责给 Vue 提供稳定接口。
- 业务服务：`app/services`，集中处理同步、指标、评分、组合、预警、相关性和报告逻辑。
- 数据源：`app/data_source`，封装 AKShare 和 Eastmoney。
- 数据库：SQLAlchemy ORM + Alembic 迁移。
- 任务：当前支持手动任务和 APScheduler；后续路线见 [功能路线图](docs/feature_roadmap.md)。

## 项目结构

```text
FundPilot/
├── app/                 # FastAPI 后端、业务服务、数据库模型
├── frontend/            # Vue 3 前端工作台
├── alembic/             # 数据库迁移
├── docs/                # 架构、数据库、评分、AI 安全和路线说明
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

Docker 部署使用独立配置，见 [Docker 配置说明](docs/docker_config.md)。

## 常用配置

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
AI_PROVIDER=ollama
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
```

启用在线 DeepSeek 后，将 `AI_PROVIDER=deepseek`，并在本地 `.env` 配置 `DEEPSEEK_API_KEY`。密钥只应保存在后端环境变量中，不要提交到 Git 或浏览器代码。

`ENABLE_SCHEDULER=false` 默认不自动跑定时任务，避免本地启动后立刻拉取外部数据。`AUTO_CREATE_TABLES=true` 仅用于开发期快速启动，正式路径建议执行 Alembic 迁移。

## 开发校验

后端：

```bash
.venv\Scripts\python -m pytest
.venv\Scripts\ruff.exe check .
```

前端：

```bash
cd frontend
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e    # Playwright，自动起 SQLite 临时库的后端与前端
```

PostgreSQL 集成校验（需要可连接的 PostgreSQL；设置维护库地址后运行）：

```bash
set FUNDPILOT_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres
.venv\Scripts\python scripts\verify_migrations.py   # 全新库/旧库升级/降级幂等，临时库自动清理
.venv\Scripts\python -m pytest -m postgres -q        # 迁移后库上的账本与任务结果链路
```

推送与 PR 由 `.github/workflows/ci.yml` 覆盖：后端测试与 ruff、前端构建、PostgreSQL 迁移矩阵与集成测试、浏览器端到端测试。

## 升级与发布

1. 备份数据库，例如 `docker exec fundpilot_postgres pg_dump -U postgres fund_watcher > fund_watcher_backup.sql`。
2. 安装依赖：`uv sync --frozen`；前端 `npm ci`。
3. 前端构建：`cd frontend && npm run build`（产物在 `frontend/dist/`）。
4. 执行迁移（与服务启动分开）：`alembic upgrade head`。
5. 启动后端与前端；开发环境 `AUTO_CREATE_TABLES=true` 会自动补附加列，正式环境应关闭并由步骤 4 负责。
6. 存量手工/截图持仓如需变成显式期初账本事件：先 `python scripts/backfill_opening_holdings.py` 预览，确认后 `--apply --yes`。

## 产品边界

FundPilot 只做数据监控、规则评分、风险提示和解释性总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
