# 数据库说明

FundPilot 使用 SQLAlchemy ORM 和 Alembic 管理数据库结构。开发期可以使用 `AUTO_CREATE_TABLES=true` 快速建表，正式路径建议执行 `uv run alembic upgrade head`。

## 核心表

- `fund_info`：基金基础信息。
- `fund_nav`：基金净值和日涨跌幅。
- `fund_indicator`：收益、回撤、波动、夏普比率、胜率等指标。
- `fund_score`：规则评分、评级、分项分和推荐理由。
- `watchlist`：自选基金，包含基金名称、行业/主题、分组和状态。
- `portfolio_position`：本地汇总持仓。
- `portfolio_transaction`：买入记录。
- `alert_event`：风险预警，包含未读、已读、已处理、忽略等状态。
- `ai_report`：日报和基金解释。
- `market_index_daily`：市场指数数据。
- `task_run_log`：同步、计算、报告生成等任务日志。

## 初始化策略

- 开发环境：允许 `create_all()` 和兼容性补列，方便快速启动。
- 正式环境：使用 Alembic 迁移，避免隐式改表。
- 数据源可能延迟或字段变化，业务服务需要保留空值和失败提示。
