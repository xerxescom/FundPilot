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

这些脚本是本地调试和手动跑批入口，不需要打开网页也能执行完整数据链路。建议按下面顺序运行：

1. 添加自选基金：写入 `watchlist` 表。后续批量同步脚本只会处理这里面的 active 基金。

```bash
uv run python scripts/add_watchlist.py
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
