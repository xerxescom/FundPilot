# FundPilot 数据库说明

## 核心表

- `fund_info`：基金基础信息。
- `fund_nav`：基金历史净值，按 `(fund_code, nav_date)` 去重。
- `watchlist`：自选基金，包含基金名称、行业/主题、分组和状态。
- `fund_indicator`：收益、回撤、波动率、夏普、胜率等指标。
- `fund_score`：规则评分、评级、分项分和推荐理由。
- `portfolio_position`：本地汇总持仓。
- `portfolio_transaction`：单笔买入记录，用于自动汇总份额、投入金额和平均成本净值。
- `alert_event`：风险预警。
- `ai_report`：AI 或规则兜底生成的日报和单基金解释。
- `market_index_daily`：主要市场指数日行情。
- `task_run_log`：同步、计算、报告生成等任务日志。

## 迁移策略

正式路径优先使用 Alembic：

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

开发环境可以保留 `AUTO_CREATE_TABLES=true` 快速启动。`APP_ENV=dev` 时，系统会执行少量兼容性补列逻辑，用于早期本地库从 `create_all()` 迁移到 Alembic 的过渡。
