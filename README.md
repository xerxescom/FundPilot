# FundPilot

FundPilot 是一个本地基金投研助手：用 AKShare/Eastmoney 采集基金净值，用 PostgreSQL 保存数据，用 Pandas 计算指标，用规则模型评分，用 Streamlit 展示看板，并用 Ollama 或规则兜底生成谨慎的 AI 简报。

## 功能

- 自选基金增删查
- 基金历史净值采集和入库
- 收益率、最大回撤、波动率、夏普比率、胜率计算
- 基金评分、评级和推荐关注列表
- 持仓盈亏估算
- 风险预警
- AI 每日简报和单只基金解释
- FastAPI 接口和 Streamlit 本地看板

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

启动看板：

```bash
uv run streamlit run dashboard/streamlit_app.py
```

运行交付 smoke check：

```bash
uv run python scripts/run_smoke_check.py
```

## 配置

常用配置在 `.env` 中：

```env
APP_ENV=dev
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/fund_watcher
BACKEND_PORT=8000
STREAMLIT_PORT=8501
SYNC_NAV_CRON=18:00
ENABLE_SCHEDULER=false
AUTO_CREATE_TABLES=true
OLLAMA_MODEL=qwen3:14b
OLLAMA_TIMEOUT=180
```

- `ENABLE_SCHEDULER=false`：默认不自动跑定时任务，避免本地启动后立刻拉取外部数据；需要自动任务时改为 `true`。
- `AUTO_CREATE_TABLES=true`：开发期允许快速建表；正式路径建议先执行 `uv run alembic upgrade head`，并按需关闭自动建表。
- 项目内置 `.streamlit/config.toml`，用于关闭 Streamlit usage stats，避免本地启动时访问统计服务导致网络超时噪声。

## 手动任务

建议按下面顺序跑完整数据链路：

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

如果需要调试单只基金：

```bash
uv run python scripts/sync_fund_nav.py
uv run python scripts/reconcile_fund_data.py
```

如果日报显示 `rule-fallback`，先检查 Ollama 是否可连接、模型是否存在：

```bash
uv run python scripts/check_ollama.py
```

## 数据流

```text
watchlist -> sync_nav -> fund_nav -> indicators -> scores -> dashboard/report
market indexes -> market_index_daily -> market context -> dashboard/report
portfolio_position + latest nav -> portfolio overview -> alerts/report
fund_nav daily_return -> correlation matrix -> high-correlation alerts
task execution -> task_run_log -> task center
```

## API 补充

- `GET /api/v1/data/health`：查看自选基金净值健康状态、断档、缺失涨跌幅、待计算指标数量。
- `GET /api/v1/data/reconcile/{fund_code}`：查看 AKShare 与 Eastmoney 净值对账结果。
- `GET /api/v1/funds/compare?codes=000001,000002`：横向比较 2-5 只基金的指标、评分和相关性。
- `POST /api/v1/funds/{fund_code}/retry-sync`：重试单只基金净值同步。
- `GET /api/v1/scores/trend/{fund_code}`：查看基金评分趋势。
- `GET /api/v1/reports/history`：查看历史日报。
- `GET /api/v1/tasks/available`：查看可手动触发的任务。
- `GET /api/v1/tasks/logs`：查看最近任务执行日志、耗时和失败原因。
- `POST /api/v1/tasks/run/{task_name}`：手动触发同步、计算、预警或日报任务。
- `GET /api/v1/reports/context/latest`：查看生成 AI 日报所使用的结构化输入摘要。
- `POST /api/v1/portfolio/transactions`：新增单笔买入记录，并自动汇总持仓。

## 数据库迁移

项目已加入 Alembic。推荐正式初始化和结构变更都走迁移：

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

开发期仍保留 `AUTO_CREATE_TABLES=true` 方便快速启动；`APP_ENV=dev` 时会执行少量兼容性补列逻辑，用于早期本地库平滑升级。

## Docker 启动

```bash
copy .env.example .env
docker compose up --build
```

- FastAPI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Streamlit: http://127.0.0.1:8501

## 作品集演示

建议参考 [docs/demo_script.md](docs/demo_script.md) 做 5 分钟演示，重点展示数据链路、规则评分、风险预警、AI 兜底和任务中心。

补充文档：

- [架构说明](docs/architecture.md)
- [数据库说明](docs/database.md)
- [评分模型说明](docs/scoring_model.md)
- [AI 安全边界](docs/ai_safety.md)

## 重要边界

FundPilot 只做数据监控、规则评分和解释性总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
