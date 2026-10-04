# 数据库说明

FundPilot 使用 SQLAlchemy ORM 和 Alembic 管理数据库结构。开发期可以使用 `AUTO_CREATE_TABLES=true` 快速建表，正式路径建议执行 `uv run alembic upgrade head`。

## 核心表

- `fund_info`：基金基础信息。
- `fund_nav`：基金净值和日涨跌幅。
- `fund_indicator`：收益、回撤、波动、夏普比率、胜率等指标。
- `fund_score`：规则评分、评级、分项分和推荐理由。
- `watchlist`：自选基金，包含基金名称、行业/主题、分组和状态。
- `asset_info`：股票与 ETF 的基础信息，包含资产类型、市场、币种和数据源。
- `asset_price_daily`：股票与 ETF 的日线收盘价和日涨跌幅。
- `portfolio_position`：本地汇总持仓；保留 `fund_code` 兼容历史数据，新增 `asset_type` 与 `asset_code` 统一表示基金、股票和 ETF。
- `portfolio_transaction`：统一交易流水，支持买入、卖出、申购、赎回、红利再投、拆分与期初事件；按资产类型重算剩余成本与数量，卖出时确定性写入 `realized_pnl`（已实现盈亏）；`external_ref`（券商编号或内容哈希，唯一索引）、`source`、`import_batch_id` 支持去重与批次追溯。
- `portfolio_cash_event`：账户级现金事件（出入金/分红/利息/费用/调整/期初现金），金额带符号；现金余额不落库，按事件 + 交易现金流推导。
- `portfolio_import_batch`：CSV 导入批次（来源、文件指纹、列映射、导入/重复/跳过/错误计数、失败原因），导入行通过 `import_batch_id` 关联。
- `alert_event`：风险预警，包含未读、已读、已处理、忽略等状态。
- `ai_report`：日报和基金解释；`batch_id`/`trade_date` 关联每日批次，`(report_type, batch_id)` 唯一约束保证同一批次只有一份日报。
- `market_index_daily`：市场指数数据。
- `task_run_log`：同步、计算、报告生成等任务日志；`result_json` 保存结构化子项结果，`batch_id` 关联所属批次。
- `task_batch`：每日更新批次（幂等键 `daily_update:{交易日}`、状态、计数、覆盖率、租约与心跳）。
- `task_batch_item`：批次步骤项（步骤、资产、状态含 `pending` 暂未发布与 `interrupted` 中断、错误分类、重试次数、租约）。
- `trade_calendar`：缓存的交易日历；覆盖范围内无记录的日期视为休市，范围外回退周末规则。

## 初始化策略

- 开发环境：允许 `create_all()` 和兼容性补列，方便快速启动。
- 正式环境：使用 Alembic 迁移，避免隐式改表。
- 数据源可能延迟或字段变化，业务服务需要保留空值和失败提示。
- 从旧版本升级时，执行 `uv run alembic upgrade head`；`0006_unified_assets` 会将已有基金持仓和交易回填为 `asset_type=fund`、`asset_code=fund_code`。
