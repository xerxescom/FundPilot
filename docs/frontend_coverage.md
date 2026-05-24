# Vue 前端功能覆盖

Vue 前端位于 `frontend/`，是 FundPilot 后续唯一前端工作台。所有用户交互都应优先在 Vue 中完成，后端通过 `/api/v1` 提供结构化数据。

| Vue 路由 | 主要 API | 覆盖内容 |
| --- | --- | --- |
| `/` | `/api/v1/dashboard/overview` | 核心指标、数据状态、Top 5、未读预警、日报摘要、市场概览 |
| `/data-health` | `/api/v1/data/health`, `/api/v1/data/reconcile/{fund_code}` | 健康指标、基金明细、数据源对账 |
| `/market` | `/api/v1/market/context`, `/api/v1/market/sync` | 指数指标卡、市场表、同步按钮 |
| `/watchlist` | `/api/v1/watchlist`, `/api/v1/funds/{code}/sync-nav` | 添加、列表、移除、同步单只、同步全部 |
| `/portfolio` | `/api/v1/portfolio/*` | 买入记录、交易删除、持仓汇总、持仓删除、组合指标、持仓饼图 |
| `/funds/:fundCode?` | `/api/v1/funds/{code}/*` | 净值同步、指标计算、评分计算、指标卡、净值/回撤/涨跌图、明细表 |
| `/compare` | `/api/v1/funds/compare`, `/api/v1/research/*` | 2-5 只基金对比、风险收益散点、行业汇总 |
| `/scores` | `/api/v1/recommendations/top` | 评级筛选、最低分筛选、评分表、排行图 |
| `/score-trend` | `/api/v1/scores/trend/{fund_code}` | 单基金评分历史、趋势图 |
| `/correlation` | `/api/v1/correlation/*` | 相关矩阵、高相关组合、两基金收益序列、生成相关性预警 |
| `/reports/daily` | `/api/v1/reports/daily`, `/api/v1/reports/latest`, `/api/v1/reports/ollama/status` | 生成日报、最新日报、Ollama 状态 |
| `/reports/history` | `/api/v1/reports/history` | 历史日报选择、报告内容、输入摘要 |
| `/tasks` | `/api/v1/tasks/*`, `/api/v1/data/health` | 快捷任务、按名称运行、任务结果、最近日志 |

## 验收步骤

1. 启动 FastAPI 和 Vue。
2. 打开 Vue 首页，确认数据状态、市场概览、评分和预警可读。
3. 依次进入 13 条路由，确认页面可打开、主要按钮可点击、表格字段中文可读、空状态不崩溃。
4. 执行一次完整数据链路：添加自选 -> 一键同步并分析 -> 评分排行 -> 风险预警 -> AI 简报。
5. 运行后端测试和前端构建，确认接口和页面代码可交付。
