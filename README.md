# FundPilot

本地基金投研助手：用 AKShare 采集基金净值，用 PostgreSQL 保存数据，用 Pandas 计算指标，用规则模型评分，用 Streamlit 展示看板，并用 Ollama 或规则兜底生成谨慎的 AI 简报。

## 功能

- 自选基金增删查
- 基金历史净值采集和入库
- 收益率、最大回撤、波动率、夏普比率、胜率计算
- 基金评分和推荐排行
- 持仓盈亏估算
- 风险预警
- AI 每日简报和单只基金解释
- FastAPI 接口和 Streamlit 本地看板

## 本地开发

```bash
uv sync
copy .env.example .env
docker compose up -d postgres
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

项目内置了 `.streamlit/config.toml`，会关闭 Streamlit usage stats，避免本地启动时因为访问 `data.streamlit.io` 超时而刷出网络错误。

## 手动任务

这些脚本是本地调试和手动跑批入口，不需要打开网页也能执行完整数据链路。建议按下面顺序运行：

1. 添加自选基金：写入 `watchlist` 表。后续批量同步脚本只会处理这里面的 active 基金。

```bash
uv run python scripts/add_watchlist.py
```

如果你已经有旧数据，可以回填自选基金名称：

```bash
uv run python scripts/backfill_watchlist_names.py
```

同步市场背景数据，供首页市场概览和 AI 日报引用：

```bash
uv run python scripts/sync_market_context.py
```

2. 同步单只基金净值：手动输入基金代码，拉取历史净值并写入 `fund_nav`。注意：这个脚本不会自动加入自选列表。

```bash
uv run python scripts/sync_fund_nav.py
```

3. 同步全部自选基金净值：读取 `watchlist` 中的 active 基金，批量更新净值。如果输出 `{}`，说明 `watchlist` 里没有 active 基金。

```bash
uv run python scripts/sync_watchlist_nav.py
```

4. 计算指标：基于 `fund_nav` 计算收益率、最大回撤、波动率、夏普比率和胜率，写入 `fund_indicator`。

```bash
uv run python scripts/calc_indicators.py
```

5. 计算评分：基于 `fund_indicator` 生成规则评分、评级和推荐理由，写入 `fund_score`。

```bash
uv run python scripts/calc_scores.py
```

6. 生成风险预警：检查大跌、回撤、评分下降和持仓集中度，写入 `alert_event`。

```bash
uv run python scripts/generate_alerts.py
```

7. 生成每日简报：使用 Ollama 生成 AI 简报；如果 Ollama 不可用，会使用规则兜底报告。

```bash
uv run python scripts/generate_daily_report.py
```

如果日报显示 `rule-fallback`，先检查 Ollama 是否可连接、模型是否存在：

```bash
uv run python scripts/check_ollama.py
```

如果模型存在但生成日报超时，可以调大 `.env` 里的 Ollama 超时时间，单位是秒：

```env
OLLAMA_MODEL=qwen3:14b
OLLAMA_TIMEOUT=180
```

RTX 4070 本地优先推荐 `qwen3:14b`；如果更看重速度，可以改成 `qwen3:8b`。大模型首次加载会比较慢。如果还是超时，可以先执行 `ollama run qwen3:14b "你好"` 预热模型，或把 `OLLAMA_TIMEOUT` 调到 `240` / `300`。

查看组合概况和基金相关性：

```bash
uv run python scripts/calc_portfolio_risk.py
uv run python scripts/calc_fund_correlation.py
```

## 数据流

```text
watchlist -> sync_nav -> fund_nav -> indicators -> scores -> dashboard/report
market indexes -> market_index_daily -> market context -> dashboard/report
portfolio_position + latest nav -> portfolio overview -> alerts/report
fund_nav daily_return -> correlation matrix -> high-correlation alerts
```

## 配置项

常用配置都在 `.env` 中：

```env
BACKEND_PORT=8000
STREAMLIT_PORT=8501
SYNC_NAV_CRON=18:00
OLLAMA_MODEL=qwen3:14b
OLLAMA_TIMEOUT=180
```

如果 `8000` 或 `8501` 被占用，可以改 `BACKEND_PORT` 或 `STREAMLIT_PORT`，Docker Compose 会按配置映射端口。

## API 补充

- `GET /api/v1/data/health`：查看自选基金净值健康状态、断档、缺失涨跌幅、待计算指标数量。
- `GET /api/v1/data/reconcile/{fund_code}`：查看 AKShare 与 Eastmoney 净值对账结果。
- `GET /api/v1/funds/compare?codes=000001,000002`：横向比较 2-5 只基金的指标、评分和相关性。
- `POST /api/v1/funds/{fund_code}/retry-sync`：重试单只基金净值同步。
- `GET /api/v1/scores/trend/{fund_code}`：查看基金评分趋势。
- `GET /api/v1/reports/history`：查看历史日报。
- `GET /api/v1/tasks/logs`：查看最近任务执行日志、耗时和失败原因。
- `POST /api/v1/tasks/run/{task_name}`：手动触发同步、计算、预警或日报任务。
- `GET /api/v1/reports/context/latest`：查看生成 AI 日报所使用的结构化输入摘要。
- `PUT /api/v1/portfolio/{position_id}`：编辑持仓。
- `DELETE /api/v1/portfolio/{position_id}`：删除持仓。
- `POST /api/v1/portfolio/transactions`：新增单笔买入记录，并自动汇总持仓。
- `GET /api/v1/portfolio/transactions`：查看买入记录。
- `DELETE /api/v1/portfolio/transactions/{transaction_id}`：删除买入记录并重新汇总持仓。

## Streamlit 页面补充

- 首页增加“数据状态”，用于发现净值过旧、断档和待计算指标。
- 数据质量页支持查看健康明细和多数据源对账。
- 基金对比页支持 2-5 只基金横向比较、行业汇总和风险收益散点。
- 评分趋势页支持查看单只基金历史评分变化。
- 我的持仓支持按每次买入金额和成交净值录入，自动汇总份额、投入金额和平均成本；也保留手动汇总持仓入口。
- AI 简报展示生成模型、生成时间、是否规则兜底、失败原因和输入数据摘要。
- 报告历史页支持查看历史日报和当时输入数据。
- 任务中心展示最近任务日志，并支持按任务名称手动触发。

## 数据库迁移

项目已加入 Alembic 脚手架。当前本地开发仍保留 `create_all()` 以方便快速启动；后续新增表和字段建议走迁移：

```bash
uv run alembic upgrade head
```

如果要生成新迁移：

```bash
uv run alembic revision --autogenerate -m "describe change"
```

## Docker 启动

```bash
copy .env.example .env
docker compose up --build
```

- FastAPI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Streamlit: http://127.0.0.1:8501

如果修改了端口，请访问 `.env` 中对应的 `BACKEND_PORT` 和 `STREAMLIT_PORT`。

## 作品集演示

建议参考 [docs/demo_script.md](docs/demo_script.md) 进行 5 分钟演示，重点展示数据链路、规则评分、风险预警和 AI 兜底能力。

补充文档：

- [架构说明](docs/architecture.md)
- [数据库说明](docs/database.md)
- [评分模型说明](docs/scoring_model.md)
- [AI 安全边界](docs/ai_safety.md)

## 重要边界

FundPilot 只做数据监控、规则评分和解释总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
