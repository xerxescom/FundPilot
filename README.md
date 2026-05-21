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
uv run uvicorn app.main:app --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

启动看板：

```bash
uv run streamlit run dashboard/streamlit_app.py
```

## 手动任务

```bash
uv run python scripts/sync_fund_nav.py
uv run python scripts/sync_watchlist_nav.py
uv run python scripts/calc_indicators.py
uv run python scripts/calc_scores.py
uv run python scripts/generate_alerts.py
uv run python scripts/generate_daily_report.py
```

## Docker 启动

```bash
copy .env.example .env
docker compose up --build
```

- FastAPI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Streamlit: http://127.0.0.1:8501

## 重要边界

FundPilot 只做数据监控、规则评分和解释总结，不保证收益，不提供直接买入、卖出或重仓建议。免费数据源可能存在延迟、字段变化或不可用，生产使用前应增加多数据源兜底、日志监控和数据校验。
