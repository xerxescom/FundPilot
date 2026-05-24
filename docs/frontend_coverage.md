# Vue 前端覆盖矩阵

Vue 前端位于 `frontend/`，Streamlit 对照版保留在 `dashboard/streamlit_app.py`。验收时使用同一套 FastAPI 和数据库，对照两边展示与交互是否一致。

| Streamlit 页面 | Vue 路由 | 主要 API | 覆盖内容 |
| --- | --- | --- | --- |
| 首页概览 | `/` | `/api/v1/dashboard/overview` | 核心指标、数据状态、Top 5、未读预警、日报摘要、市场概览 |
| 数据质量 | `/data-health` | `/api/v1/data/health`, `/api/v1/data/reconcile/{fund_code}` | 健康指标、基金明细、数据源对账 |
| 市场概览 | `/market` | `/api/v1/market/context`, `/api/v1/market/sync` | 指数指标卡、市场表、同步按钮 |
| 自选基金 | `/watchlist` | `/api/v1/watchlist`, `/api/v1/funds/{code}/sync-nav` | 添加、列表、移除、同步单只、同步全部 |
| 我的持仓 | `/portfolio` | `/api/v1/portfolio/*` | 买入记录、交易删除、持仓汇总、持仓删除、组合指标、持仓饼图 |
| 基金详情 | `/funds/:fundCode?` | `/api/v1/funds/{code}/*` | 净值同步、指标计算、评分计算、指标卡、净值/回撤/涨跌图、明细表 |
| 基金对比 | `/compare` | `/api/v1/funds/compare`, `/api/v1/research/*` | 2-5 只基金对比、风险收益散点、行业汇总 |
| 评分排行 | `/scores` | `/api/v1/recommendations/top` | 评级筛选、最低分筛选、评分表、排行图 |
| 评分趋势 | `/score-trend` | `/api/v1/scores/trend/{fund_code}` | 单基金评分历史、趋势图 |
| 相关性分析 | `/correlation` | `/api/v1/correlation/*` | 相关矩阵、高相关组合、两基金收益序列、生成相关性预警 |
| AI 简报 | `/reports/daily` | `/api/v1/reports/daily`, `/api/v1/reports/latest`, `/api/v1/reports/ollama/status` | 生成日报、最新日报、Ollama 状态 |
| 报告历史 | `/reports/history` | `/api/v1/reports/history` | 历史日报选择、报告内容、输入摘要 |
| 任务中心 | `/tasks` | `/api/v1/tasks/*`, `/api/v1/data/health` | 快捷任务、按名称运行、任务结果、最近日志 |

## 验收步骤

1. 启动 FastAPI、Streamlit 和 Vue。
2. 在 Streamlit 执行一条数据链路任务，例如同步市场数据或生成日报。
3. 刷新 Vue，对照对应页面的数据、表格列、图表和空状态。
4. 在 Vue 执行同一类任务，再回到 Streamlit 验证结果一致。
5. 对 13 条路由逐项确认：页面可打开、主要按钮可点击、错误提示可读、空数据状态不崩溃。
