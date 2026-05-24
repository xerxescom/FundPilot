import json
from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from app.db.session import SessionLocal, init_db
from app.services import (
    alert_service,
    correlation_service,
    data_health_service,
    indicator_service,
    market_service,
    nav_service,
    portfolio_service,
    reconcile_service,
    research_service,
    score_service,
    task_log_service,
    task_runner_service,
    watchlist_service,
)
from app.services.ai.report_service import generate_daily_report, latest_report, report_history
from app.services.ai.ollama_client import OllamaClient

st.set_page_config(page_title="FundPilot", layout="wide", initial_sidebar_state="expanded")
init_db()

RATING_COLORS = {
    "重点关注": "#0f9f6e",
    "可以观察": "#2563eb",
    "一般": "#d97706",
    "暂不关注": "#6b7280",
}

PERIOD_OPTIONS = {
    "近1月": 30,
    "近3月": 90,
    "近6月": 180,
    "近1年": 365,
    "全部": None,
}

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background: #f8fafc;
        color: #111827;
    }
    [data-testid="stHeader"] {
        background: rgba(248, 250, 252, 0.92);
    }
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e5e7eb;
    }
    [data-testid="stSidebar"] * {
        color: #111827;
    }
    .main .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
        max-width: 1280px;
    }
    h1, h2, h3, h4, h5, h6, p, label, span {
        color: #111827;
    }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px 16px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        min-height: 116px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    [data-testid="stMetric"] label,
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #111827;
    }
    [data-testid="stMetricDelta"] {
        color: #475569;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
        background: #ffffff;
    }
    div[data-baseweb="input"] input,
    div[data-baseweb="select"] > div,
    div[data-baseweb="textarea"] textarea {
        background: #ffffff;
        color: #111827;
        border-color: #d1d5db;
    }
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #d1d5db;
        background: #ffffff;
        color: #111827;
        font-weight: 600;
    }
    .stButton > button:hover {
        border-color: #2563eb;
        color: #1d4ed8;
        background: #eff6ff;
    }
    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin: 1.1rem 0 0.45rem;
        color: #111827;
    }
    .muted {color: #6b7280; font-size: 0.9rem;}
    .pill {
        display: inline-block;
        border-radius: 999px;
        padding: 3px 9px;
        color: white;
        font-size: 0.78rem;
        font-weight: 650;
    }
    .signal-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 13px 15px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        min-height: 104px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .signal-label {
        color: #64748b;
        font-size: 0.82rem;
        margin-bottom: 4px;
    }
    .signal-value {
        font-size: 1.35rem;
        font-weight: 750;
        line-height: 1.2;
    }
    .signal-hint {
        color: #64748b;
        font-size: 0.78rem;
        margin-top: 4px;
    }
    .task-button-note {
        color: #64748b;
        font-size: 0.82rem;
        margin: -0.4rem 0 0.7rem;
        min-height: 2.2rem;
    }
    .rating-guide {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin: 0.5rem 0 0.9rem;
    }
    .rating-guide-item {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 12px;
        min-height: 72px;
    }
    .rating-guide-title {
        font-size: 0.9rem;
        font-weight: 750;
        margin-bottom: 4px;
    }
    .rating-guide-range {
        color: #64748b;
        font-size: 0.82rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def db_session():
    return SessionLocal()


def as_float(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def pct(value: Decimal | float | int | None) -> str:
    return "-" if value is None else f"{float(value):.2%}"


def score_value(value: Decimal | float | int | None) -> str:
    return "-" if value is None else f"{float(value):.2f}"


def date_value(value) -> str:
    return "暂无" if value is None else str(value)

def section(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="muted">{caption}</div>', unsafe_allow_html=True)


def rating_badge(rating: str | None) -> str:
    label = rating or "未评分"
    color = RATING_COLORS.get(label, "#6b7280")
    return f'<span class="pill" style="background:{color}">{label}</span>'

def rating_guide() -> None:
    items = [
        ("重点关注", "85 分及以上", RATING_COLORS["重点关注"]),
        ("可以观察", "70-84.99 分", RATING_COLORS["可以观察"]),
        ("一般", "60-69.99 分", RATING_COLORS["一般"]),
        ("暂不关注", "60 分以下", RATING_COLORS["暂不关注"]),
    ]
    html = '<div class="rating-guide">'
    for title, score_range, color in items:
        html += (
            '<div class="rating-guide-item">'
            f'<div class="rating-guide-title" style="color:{color}">{title}</div>'
            f'<div class="rating-guide-range">{score_range}</div>'
            "</div>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def metric_card(label: str, value: Decimal | float | int | None, kind: str = "return") -> None:
    if value is None:
        color = "#64748b"
        display = "-"
        hint = "暂无数据"
    else:
        numeric = float(value)
        display = pct(numeric) if kind != "score" else score_value(numeric)
        if kind == "risk":
            color = "#dc2626" if numeric <= -0.20 else "#d97706" if numeric <= -0.08 else "#0f9f6e"
            hint = "越接近 0 越稳"
        elif kind == "score":
            color = "#0f9f6e" if numeric >= 85 else "#2563eb" if numeric >= 70 else "#d97706" if numeric >= 60 else "#6b7280"
            hint = "规则评分"
        else:
            color = "#dc2626" if numeric < 0 else "#0f9f6e"
            hint = "正收益为绿"
    st.markdown(
        f"""
        <div class="signal-card">
            <div class="signal-label">{label}</div>
            <div class="signal-value" style="color:{color}">{display}</div>
            <div class="signal-hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_watchlist_codes() -> list[str]:
    with db_session() as db:
        return [
            f"{item.fund_code} {item.fund_name}" if item.fund_name else item.fund_code
            for item in watchlist_service.list_watchlist_items(db)
        ]


def watchlist_label_map() -> dict[str, str]:
    with db_session() as db:
        return {
            item.fund_code: f"{item.fund_code} {item.fund_name}" if item.fund_name else item.fund_code
            for item in watchlist_service.list_watchlist_items(db)
        }


def watchlist_fund_name_map() -> dict[str, str]:
    with db_session() as db:
        return {
            item.fund_code: item.fund_name or item.fund_code
            for item in watchlist_service.list_watchlist_items(db)
        }


def selected_code(value: str | None) -> str:
    return (value or "").split(" ", 1)[0].strip()


def status_label(is_active: bool) -> str:
    return "启用 ✓" if is_active else "停用 -"


def analyze_fund(db, fund_code: str) -> tuple[object, object]:
    """Calculate indicator and score records for one fund."""

    indicator = indicator_service.calculate_and_save_indicators(db, fund_code)
    score = score_service.calculate_and_save_score(db, fund_code)
    return indicator, score


def score_rows(scores) -> list[dict]:
    return [
        {
            "基金代码": item.fund_code,
            "日期": item.score_date,
            "总分": as_float(item.total_score),
            "评级": item.rating,
            "推荐理由": item.reason,
        }
        for item in scores
    ]


def label_score_rows(rows: list[dict], labels: dict[str, str], column_name: str = "基金") -> list[dict]:
    return [{**row, column_name: labels.get(row["基金代码"], row["基金代码"])} for row in rows]


def money(value: Decimal | float | int | None) -> str:
    return "-" if value is None else f"{float(value):,.2f}"


def market_rows(market_context: list[dict]) -> list[dict]:
    return [
        {
            "指数": item["index_name"],
            "日期": item.get("trade_date"),
            "收盘": item.get("close"),
            "日涨跌": pct(item.get("daily_return")),
            "近1月": pct(item.get("return_1m")),
            "来源": item.get("source") or "-",
        }
        for item in market_context
    ]


def task_log_rows(logs) -> list[dict]:
    return [
        {
            "时间": log.created_at,
            "任务": log.task_name,
            "状态": "成功" if log.status == "success" else "失败",
            "耗时(ms)": log.duration_ms,
            "成功数": log.success_count,
            "失败数": log.failure_count,
            "信息": log.message,
        }
        for log in logs
    ]


def task_result_rows(result: dict | list | str | int) -> list[dict]:
    if isinstance(result, dict):
        return [
            {
                "对象": key,
                "结果": "失败" if isinstance(value, str) and value.startswith("failed:") else "成功",
                "详情": value,
            }
            for key, value in result.items()
        ]
    if isinstance(result, list):
        return [{"序号": index + 1, "结果": value} for index, value in enumerate(result)]
    return [{"结果": result}]


def reconcile_count_rows(counts: dict) -> list[dict]:
    labels = {
        "akshare_missing": "AKShare 缺失日期",
        "eastmoney_missing": "Eastmoney 缺失日期",
        "unit_nav_diff": "单位净值差异",
        "daily_return_diff": "日涨跌幅差异",
    }
    return [{"项目": labels.get(key, key), "数量": value} for key, value in counts.items()]


def reconcile_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "日期": item.get("nav_date"),
            "AKShare 单位净值": item.get("akshare_unit_nav"),
            "Eastmoney 单位净值": item.get("eastmoney_unit_nav"),
            "单位净值差异": item.get("unit_nav_diff"),
            "AKShare 日涨跌幅": item.get("akshare_daily_return"),
            "Eastmoney 日涨跌幅": item.get("eastmoney_daily_return"),
            "日涨跌幅差异": item.get("daily_return_diff"),
            "对账状态": item.get("status"),
        }
        for item in rows
    ]


def display_industry_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "行业/主题": item.get("industry"),
            "基金数量": item.get("fund_count"),
            "平均评分": item.get("avg_score"),
            "持仓市值": item.get("position_value"),
            "持仓占比": pct(item.get("position_weight")),
        }
        for item in rows
    ]


def score_trend_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "基金代码": item.get("fund_code"),
            "评分日期": item.get("score_date"),
            "总分": item.get("total_score"),
            "评级": item.get("rating"),
            "收益分": item.get("return_score"),
            "回撤分": item.get("drawdown_score"),
            "波动分": item.get("volatility_score"),
            "稳定性分": item.get("stability_score"),
            "规模分": item.get("size_score"),
            "交易状态分": item.get("trade_status_score"),
        }
        for item in rows
    ]


def ollama_status_rows(status: dict) -> list[dict]:
    labels = {
        "base_url": "服务地址",
        "configured_model": "配置模型",
        "model_available": "模型是否可用",
        "models": "本地模型列表",
    }
    return [{"项目": labels.get(key, key), "值": value} for key, value in status.items()]


def render_report_metadata(report) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("生成模型", report.model_name or "未知")
    c2.metric("生成时间", f"{report.created_at:%Y-%m-%d %H:%M}")
    c3.metric("兜底状态", "规则兜底" if report.is_fallback else "模型生成")
    if report.fallback_reason:
        st.warning(f"兜底原因：{report.fallback_reason}")
    if report.input_snapshot:
        with st.expander("输入数据摘要"):
            try:
                st.json(json.loads(report.input_snapshot))
            except json.JSONDecodeError:
                st.code(report.input_snapshot)


def nav_dataframe(nav_rows) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "日期": row.nav_date,
                "单位净值": as_float(row.unit_nav),
                "日涨跌幅": as_float(row.daily_return),
            }
            for row in nav_rows
        ]
    )
    if df.empty:
        return df
    df["日期"] = pd.to_datetime(df["日期"])
    df["回撤"] = df["单位净值"] / df["单位净值"].cummax() - 1
    return df


def filter_nav_period(df: pd.DataFrame, period_label: str) -> pd.DataFrame:
    days = PERIOD_OPTIONS[period_label]
    if df.empty or days is None:
        return df
    start = df["日期"].max() - pd.Timedelta(days=days)
    return df[df["日期"] >= start].copy()


def render_nav_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["单位净值"],
            mode="lines",
            name="单位净值",
            line={"color": "#2563eb", "width": 2},
            hovertemplate="日期=%{x|%Y-%m-%d}<br>单位净值=%{y:.4f}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#111827"},
        height=380,
        margin={"l": 10, "r": 10, "t": 25, "b": 10},
        hovermode="x unified",
        xaxis_title=None,
        yaxis_title="单位净值",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7")
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f7")
    st.plotly_chart(fig, use_container_width=True)


def render_drawdown_chart(df: pd.DataFrame) -> None:
    fig = px.area(df, x="日期", y="回撤")
    fig.update_traces(line_color="#dc2626", fillcolor="rgba(220, 38, 38, 0.18)")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#111827"},
        height=260,
        margin={"l": 10, "r": 10, "t": 20, "b": 10},
        xaxis_title=None,
        yaxis_title="回撤",
        yaxis_tickformat=".0%",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7")
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f7")
    fig.update_traces(hovertemplate="日期=%{x|%Y-%m-%d}<br>回撤=%{y:.2%}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)


def render_daily_return_chart(df: pd.DataFrame) -> None:
    if "日涨跌幅" not in df or df["日涨跌幅"].dropna().empty:
        st.info("暂无日涨跌幅数据。")
        return
    chart_df = df.dropna(subset=["日涨跌幅"]).copy()
    colors = chart_df["日涨跌幅"].map(lambda value: "#dc2626" if value < 0 else "#16a34a")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_df["日期"],
            y=chart_df["日涨跌幅"],
            marker_color=colors,
            name="日涨跌幅",
            hovertemplate="日期=%{x|%Y-%m-%d}<br>日涨跌幅=%{y:.2%}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#111827"},
        height=280,
        margin={"l": 10, "r": 10, "t": 20, "b": 10},
        xaxis_title=None,
        yaxis_title="日涨跌幅",
        yaxis_tickformat=".1%",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7")
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f7", zeroline=True, zerolinecolor="#94a3b8")
    st.plotly_chart(fig, use_container_width=True)


def render_aligned_fund_charts(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("暂无可展示的图表数据。")
        return
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.045,
        row_heights=[0.48, 0.28, 0.24],
        subplot_titles=("单位净值", "回撤", "日涨跌幅"),
    )
    fig.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["单位净值"],
            mode="lines",
            name="单位净值",
            line={"color": "#2563eb", "width": 2.2},
            hovertemplate="日期=%{x|%Y-%m-%d}<br>单位净值=%{y:.4f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["回撤"],
            mode="lines",
            fill="tozeroy",
            name="回撤",
            line={"color": "#dc2626", "width": 1.6},
            fillcolor="rgba(220, 38, 38, 0.16)",
            hovertemplate="日期=%{x|%Y-%m-%d}<br>回撤=%{y:.2%}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    return_df = df.dropna(subset=["日涨跌幅"]).copy()
    colors = return_df["日涨跌幅"].map(lambda value: "#dc2626" if value < 0 else "#16a34a")
    fig.add_trace(
        go.Bar(
            x=return_df["日期"],
            y=return_df["日涨跌幅"],
            marker_color=colors,
            name="日涨跌幅",
            hovertemplate="日期=%{x|%Y-%m-%d}<br>日涨跌幅=%{y:.2%}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#111827"},
        height=720,
        margin={"l": 10, "r": 10, "t": 45, "b": 10},
        hovermode="x unified",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7")
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f7", title_text="净值", row=1, col=1)
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f7", tickformat=".0%", title_text="回撤", row=2, col=1)
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#eef2f7",
        zeroline=True,
        zerolinecolor="#94a3b8",
        tickformat=".1%",
        title_text="涨跌幅",
        row=3,
        col=1,
    )
    st.plotly_chart(fig, use_container_width=True)


def label_correlation(corr: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    if corr.empty:
        return corr
    return corr.rename(index=labels, columns=labels)


st.sidebar.title("FundPilot")
st.sidebar.caption("本地基金投研助手")
page = st.sidebar.radio(
    "导航",
    [
        "首页概览",
        "数据质量",
        "市场概览",
        "自选基金",
        "我的持仓",
        "基金详情",
        "基金对比",
        "评分排行",
        "评分趋势",
        "相关性分析",
        "AI 简报",
        "报告历史",
        "任务中心",
    ],
)

st.title("FundPilot 本地基金投研助手")

if page == "首页概览":
    with db_session() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        scores = score_service.top_scores(db, limit=5)
        alerts = alert_service.unread_alerts(db)
        report = latest_report(db)
        market_context = market_service.latest_market_context(db)
        health = data_health_service.data_health_overview(db)
    fund_names = {item.fund_code: item.fund_name or item.fund_code for item in watchlist}

    best_score = scores[0].total_score if scores and scores[0].total_score is not None else None
    best_rating = scores[0].rating if scores else "暂无"
    latest_report_time = report.created_at.strftime("%Y-%m-%d %H:%M") if report else "暂无"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("自选基金", len(watchlist))
    c2.metric("最高评分", score_value(best_score), best_rating)
    c3.metric("未读预警", len(alerts))
    c4.metric("最近简报", latest_report_time)

    section("数据状态", "检查自选基金净值是否过旧、断档，以及指标是否需要重新计算。")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("最新净值日期", date_value(health["latest_nav_date"]))
    h2.metric("需关注基金", health["stale_fund_count"])
    h3.metric("待计算指标", health["pending_indicator_count"])
    h4.metric("净值断档", health["gap_count"])
    problem_rows = [item for item in health["funds"] if item["issues"]]
    if problem_rows:
        st.dataframe(
            [
                {
                    "基金代码": item["fund_code"],
                    "状态": item["status"],
                    "最新净值": item["latest_nav_date"],
                    "净值条数": item["nav_count"],
                    "问题": "；".join(item["issues"]),
                }
                for item in problem_rows[:8]
            ],
            use_container_width=True,
            hide_index=True,
        )

    left, right = st.columns([1.35, 1])
    with left:
        section("推荐关注 Top 5", "按最新评分排序，优先查看高分且理由清晰的基金。")
        rating_guide()
        st.dataframe(
            label_score_rows(score_rows(scores), fund_names, column_name="基金名称"),
            use_container_width=True,
            hide_index=True,
        )

    with right:
        section("风险提醒", "来自大跌、回撤、评分下降和持仓集中度规则。")
        if alerts:
            for alert in alerts[:6]:
                st.warning(f"{alert.title or alert.alert_type}\n\n{alert.content or ''}")
        else:
            st.info("暂无未读风险提醒。")

    if report:
        section("每日简报摘要")
        st.markdown(report.content)

    section("市场概览")
    market_cols = st.columns(4)
    for idx, item in enumerate(market_context[:4]):
        with market_cols[idx % 4]:
            metric_card(item["index_name"], item.get("daily_return"), kind="return")

elif page == "数据质量":
    section("数据质量", "检查净值同步、断档、缺失涨跌幅和多数据源对账结果。")
    with db_session() as db:
        health = data_health_service.data_health_overview(db)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新可用交易日", date_value(health["latest_available_trade_date"]))
    c2.metric("需关注基金", health["stale_fund_count"])
    c3.metric("待计算指标", health["pending_indicator_count"])
    c4.metric("缺失涨跌幅", health["missing_daily_return_count"])
    st.dataframe(
        [
            {
                "基金代码": item["fund_code"],
                "状态": item["status"],
                "最新净值": item["latest_nav_date"],
                "过旧天数": item["stale_days"],
                "最近同步": item["latest_sync_date"],
                "同步状态": item["latest_sync_status"] or "-",
                "失败原因": item["latest_failure_reason"] or "-",
                "问题": "；".join(item["issues"]) if item["issues"] else "正常",
            }
            for item in health["funds"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    section("数据源对账", "比较 AKShare 与 Eastmoney 最近净值数据，发现日期缺失或数值差异。")
    codes = load_watchlist_codes()
    selected = st.selectbox("选择基金", options=codes, index=0 if codes else None)
    if st.button("执行对账", use_container_width=True) and selected:
        with st.spinner("正在拉取两个数据源并对账..."):
            result = reconcile_service.reconcile_fund_nav(selected_code(selected))
        st.info(result["summary"])
        if result.get("counts"):
            st.dataframe(reconcile_count_rows(result["counts"]), use_container_width=True, hide_index=True)
        if result.get("source_errors"):
            st.caption(f"数据源错误：{result['source_errors']}")
        if result.get("rows"):
            st.dataframe(reconcile_rows(result["rows"]), use_container_width=True, hide_index=True)

elif page == "市场概览":
    section("市场概览", "主要指数表现会进入每日简报，作为自选基金变化的背景信息。")
    if st.button("同步市场数据", use_container_width=True):
        with st.spinner("正在同步主要指数数据..."):
            with db_session() as db:
                st.json(market_service.sync_market_context(db))
    with db_session() as db:
        market_context = market_service.latest_market_context(db)
    cols = st.columns(4)
    for idx, item in enumerate(market_context[:4]):
        with cols[idx % 4]:
            metric_card(item["index_name"], item.get("daily_return"), kind="return")
            st.caption(f"近1月：{pct(item.get('return_1m'))} · {item.get('trade_date') or '暂无日期'}")
    st.dataframe(market_rows(market_context), use_container_width=True, hide_index=True)

elif page == "自选基金":
    section("自选基金管理", "添加基金后，可以批量同步净值并进入详情页分析。")
    with st.form("add_watchlist", clear_on_submit=True):
        col1, col2, col3 = st.columns([1, 2, 1])
        fund_code = col1.text_input("基金代码", placeholder="000001")
        fund_name = col2.text_input("基金名称", placeholder="可留空，系统会尝试自动获取")
        industry = col3.text_input("行业/主题", placeholder="例如：医药、宽基")
        note = st.text_input("备注", placeholder="例如：长期观察")
        submitted = st.form_submit_button("添加自选", use_container_width=True)
    if submitted and fund_code:
        with st.spinner("正在添加自选基金并识别行业/主题..."):
            with db_session() as db:
                item = watchlist_service.add_watchlist_item(
                    db,
                    fund_code,
                    note=note or None,
                    fund_name=fund_name or None,
                    industry=industry or None,
                )
        st.success(f"已添加 {item.fund_code} {item.fund_name or ''}".strip())

    with db_session() as db:
        items = watchlist_service.list_watchlist_items(db)

    if items:
        st.dataframe(
            [
                {
                    "基金代码": item.fund_code,
                    "基金名称": item.fund_name,
                    "行业/主题": item.industry,
                    "分组": item.group_name,
                    "备注": item.note,
                    "状态": status_label(item.is_active),
                }
                for item in items
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("还没有自选基金。先添加一只基金代码开始。")

    section("同步操作")
    sync_code = st.text_input("同步单只基金净值", placeholder="000001")
    if st.button("同步单只", use_container_width=True) and sync_code:
        with st.spinner(f"正在同步 {sync_code.zfill(6)} 的净值数据..."):
            with db_session() as db:
                count = nav_service.sync_fund_nav(db, sync_code)
        st.success(f"已同步 {sync_code.zfill(6)}，共 {count} 条净值")
    if st.button("同步全部自选基金", use_container_width=True):
        with st.spinner("正在批量同步自选基金净值..."):
            with db_session() as db:
                result = nav_service.sync_watchlist_nav(db)
        if result:
            st.success("批量同步完成")
            st.json(result)
        else:
            st.info("没有 active 自选基金。")

elif page == "我的持仓":
    section("我的持仓", "优先录入每次买入记录，系统会自动汇总份额、投入金额和平均成本。")
    with st.form("add_transaction", clear_on_submit=True):
        t1, t2, t3, t4 = st.columns(4)
        fund_code = t1.text_input("基金代码", placeholder="000001")
        trade_date = t2.date_input("买入日期", value=date.today())
        amount = t3.number_input("买入金额", min_value=0.0, step=100.0)
        nav = t4.number_input("成交净值", min_value=0.0, step=0.01, format="%.4f")
        fee = st.number_input("手续费", min_value=0.0, step=1.0)
        note = st.text_input("备注", placeholder="例如：定投、补仓")
        submitted = st.form_submit_button("添加买入记录并自动汇总", use_container_width=True)
    if submitted and fund_code:
        try:
            with db_session() as db:
                transaction = portfolio_service.create_transaction(
                    db,
                    {
                        "fund_code": fund_code,
                        "trade_date": trade_date,
                        "amount": Decimal(str(amount)),
                        "nav": Decimal(str(nav)),
                        "fee": Decimal(str(fee)) if fee else None,
                        "note": note or None,
                    },
                )
            st.success(f"买入记录已添加，自动计算份额 {transaction.share}")
            st.rerun()
        except Exception as exc:
            st.error(f"添加买入记录失败：{exc}")

    with st.expander("手动录入汇总持仓"):
        st.caption("如果你已经从其他平台算好了总份额和成本，可以继续用这里直接录入汇总值。")
        with st.form("add_position", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            fund_code = c1.text_input("汇总基金代码", placeholder="000001")
            holding_share = c2.number_input("汇总持有份额", min_value=0.0, step=100.0)
            cost_nav = c3.number_input("汇总成本净值", min_value=0.0, step=0.01)
            holding_amount = c4.number_input("汇总投入金额", min_value=0.0, step=100.0)
            note = st.text_input("汇总备注")
            submitted = st.form_submit_button("添加汇总持仓", use_container_width=True)
        if submitted and fund_code:
            with db_session() as db:
                portfolio_service.create_position(
                    db,
                    {
                        "fund_code": fund_code,
                        "holding_share": Decimal(str(holding_share)) if holding_share else None,
                        "cost_nav": Decimal(str(cost_nav)) if cost_nav else None,
                        "holding_amount": Decimal(str(holding_amount)) if holding_amount else None,
                        "note": note or None,
                    },
                )
            st.success("汇总持仓已添加")

    with db_session() as db:
        overview = portfolio_service.portfolio_overview(db)
        transactions = portfolio_service.list_transactions(db)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("当前市值", money(overview["total_value"]))
    c2.metric("投入成本", money(overview["total_cost"]))
    c3.metric("收益金额", money(overview["profit_amount"]))
    c4.metric("收益率", pct(overview["profit_rate"]))
    c5, c6 = st.columns(2)
    c5.metric("最高单基占比", pct(overview.get("max_weight")))
    c6.metric("组合近1月回撤", pct(overview.get("drawdown_1m")))

    if transactions:
        section("买入记录", "每条记录都会参与自动汇总持仓。删除记录后，对应基金持仓会重新计算。")
        st.dataframe(
            [
                {
                    "ID": item.id,
                    "基金代码": item.fund_code,
                    "买入日期": item.trade_date,
                    "买入金额": float(item.amount),
                    "成交净值": float(item.nav),
                    "份额": float(item.share),
                    "手续费": float(item.fee or 0),
                    "备注": item.note,
                }
                for item in transactions
            ],
            use_container_width=True,
            hide_index=True,
        )
        transaction_options = [f"{item.id} - {item.fund_code} - {item.trade_date}" for item in transactions]
        selected_transaction = st.selectbox("选择要删除的买入记录", transaction_options)
        if st.button("删除买入记录并重新汇总", use_container_width=True):
            transaction_id = int(selected_transaction.split(" - ", 1)[0])
            with db_session() as db:
                portfolio_service.delete_transaction(db, transaction_id)
            st.success("买入记录已删除，持仓已重新汇总")
            st.rerun()

    rows = []
    total_value = overview["total_value"] or Decimal("0")
    for summary in overview["positions"]:
        position = summary["position"]
        current_value = summary["current_value"]
        rows.append(
            {
                "ID": position.id,
                "基金代码": position.fund_code,
                "持有份额": float(position.holding_share) if position.holding_share else None,
                "最新净值": float(summary["latest_nav"]) if summary["latest_nav"] else None,
                "当前市值": float(current_value) if current_value else None,
                "收益金额": float(summary["profit_amount"]) if summary["profit_amount"] else None,
                "收益率": float(summary["profit_rate"]) if summary["profit_rate"] else None,
                "权重": float(current_value / total_value) if current_value and total_value else None,
                "备注": position.note,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        section("编辑持仓", "选择一条持仓后可修改份额、成本和备注，或删除不再跟踪的记录。")
        position_options = [f"{row['ID']} - {row['基金代码']}" for row in rows]
        selected_position = st.selectbox("选择持仓", position_options)
        selected_id = int(selected_position.split(" - ", 1)[0])
        selected_row = next(row for row in rows if row["ID"] == selected_id)
        with st.form("edit_position"):
            e1, e2, e3 = st.columns(3)
            holding_share = e1.number_input(
                "持有份额",
                min_value=0.0,
                step=100.0,
                value=float(selected_row["持有份额"] or 0),
            )
            cost_nav = e2.number_input(
                "成本净值",
                min_value=0.0,
                step=0.01,
                value=float(next(item for item in overview["positions"] if item["position"].id == selected_id)["position"].cost_nav or 0),
            )
            holding_amount = e3.number_input(
                "投入金额",
                min_value=0.0,
                step=100.0,
                value=float(
                    next(item for item in overview["positions"] if item["position"].id == selected_id)[
                        "position"
                    ].holding_amount
                    or 0
                ),
            )
            note = st.text_input("备注", value=selected_row.get("备注") or "")
            save_position = st.form_submit_button("保存修改", use_container_width=True)
        d1, d2 = st.columns([1, 3])
        delete_position = d1.button("删除持仓", use_container_width=True)
        if save_position:
            with db_session() as db:
                portfolio_service.update_position(
                    db,
                    selected_id,
                    {
                        "holding_share": Decimal(str(holding_share)) if holding_share else None,
                        "cost_nav": Decimal(str(cost_nav)) if cost_nav else None,
                        "holding_amount": Decimal(str(holding_amount)) if holding_amount else None,
                        "note": note or None,
                    },
                )
            st.success("持仓已更新")
            st.rerun()
        if delete_position:
            with db_session() as db:
                portfolio_service.delete_position(db, selected_id)
            st.success("持仓已删除")
            st.rerun()
    chart_df = pd.DataFrame([row for row in rows if row.get("当前市值")])
    if not chart_df.empty:
        fig = px.pie(chart_df, names="基金代码", values="当前市值", hole=0.45)
        fig.update_layout(template="plotly_white", height=360, margin={"l": 10, "r": 10, "t": 20, "b": 10})
        st.plotly_chart(fig, use_container_width=True)

elif page == "基金详情":
    codes = load_watchlist_codes()
    selected = st.selectbox("选择基金", options=codes, index=0 if codes else None)
    manual_code = st.text_input("或手动输入基金代码", placeholder="000001")
    fund_code = (manual_code.strip() if manual_code else selected_code(selected))

    if not fund_code:
        st.info("先在自选基金页添加基金，或手动输入基金代码。")
    else:
        section(f"{fund_code.zfill(6)} 基金详情")
        action_cols = st.columns(4)
        if action_cols[0].button("同步净值", use_container_width=True):
            try:
                with st.spinner("正在同步净值数据..."):
                    with db_session() as db:
                        count = nav_service.sync_fund_nav(db, fund_code)
                st.success(f"已同步 {count} 条净值")
            except Exception as exc:
                st.error(f"同步失败：{exc}")

        if action_cols[1].button("计算指标", use_container_width=True):
            try:
                with st.spinner("正在计算收益、回撤和波动指标..."):
                    with db_session() as db:
                        indicator = indicator_service.calculate_and_save_indicators(db, fund_code)
                        calc_date = indicator.calc_date
                st.success(f"指标已更新到 {calc_date}")
            except Exception as exc:
                st.error(f"计算指标失败：{exc}")

        if action_cols[2].button("计算评分", use_container_width=True):
            try:
                with st.spinner("正在计算评分..."):
                    with db_session() as db:
                        score = score_service.calculate_and_save_score(db, fund_code)
                        total_score = score.total_score
                st.success(f"评分已更新：{total_score}")
            except Exception as exc:
                st.error(f"计算评分失败：{exc}")

        if action_cols[3].button("一键同步并分析", use_container_width=True):
            try:
                with st.spinner("正在同步净值、计算指标并生成评分..."):
                    with db_session() as db:
                        count = nav_service.sync_fund_nav(db, fund_code)
                        indicator, score = analyze_fund(db, fund_code)
                        calc_date = indicator.calc_date
                        total_score = score.total_score
                st.success(f"已同步 {count} 条净值，指标日期 {calc_date}，评分 {total_score}")
            except Exception as exc:
                st.error(f"一键分析失败：{exc}")

        with db_session() as db:
            nav_rows = nav_service.list_fund_nav(db, fund_code)
            indicator = indicator_service.latest_indicator(db, fund_code)
            score = score_service.latest_score(db, fund_code)

        if score:
            st.markdown(rating_badge(score.rating), unsafe_allow_html=True)
            st.caption(score.reason or "暂无评分原因")
        elif nav_rows and not indicator:
            st.info("已有净值数据，但还没有计算指标。点击上方“计算指标”或“一键同步并分析”。")
        elif indicator and not score:
            st.info("已有指标数据，但还没有计算评分。点击上方“计算评分”。")

        metric_cols = st.columns(5)
        with metric_cols[0]:
            metric_card("近1月收益", indicator.return_1m if indicator else None)
        with metric_cols[1]:
            metric_card("近3月收益", indicator.return_3m if indicator else None)
        with metric_cols[2]:
            metric_card("近1年收益", indicator.return_1y if indicator else None)
        with metric_cols[3]:
            metric_card("最大回撤", indicator.max_drawdown_1y if indicator else None, kind="risk")
        with metric_cols[4]:
            metric_card("总分", score.total_score if score else None, kind="score")

        df = nav_dataframe(nav_rows)
        if df.empty:
            st.info("还没有净值数据，请先同步。")
        else:
            col_period, col_summary = st.columns([1, 3])
            period_label = col_period.segmented_control(
                "观察区间",
                options=list(PERIOD_OPTIONS.keys()),
                default="近1年",
            )
            filtered_df = filter_nav_period(df, period_label)
            col_summary.caption(
                f"当前区间：{filtered_df['日期'].min():%Y-%m-%d} 至 {filtered_df['日期'].max():%Y-%m-%d}，"
                f"共 {len(filtered_df)} 条净值记录"
            )

            section("净值、回撤与日涨跌幅", "三张图共用同一条时间轴，便于观察净值创新高、回撤扩大和日涨跌之间的关系。")
            render_aligned_fund_charts(filtered_df)

        section("指标明细")
        st.dataframe(
            [
                {
                    "近1周": pct(indicator.return_1w if indicator else None),
                    "近1月": pct(indicator.return_1m if indicator else None),
                    "近3月": pct(indicator.return_3m if indicator else None),
                    "近6月": pct(indicator.return_6m if indicator else None),
                    "近1年": pct(indicator.return_1y if indicator else None),
                    "波动率": pct(indicator.volatility_1y if indicator else None),
                    "夏普比率": score_value(indicator.sharpe_1y if indicator else None),
                    "胜率": pct(indicator.win_rate_1y if indicator else None),
                }
            ],
            use_container_width=True,
            hide_index=True,
        )

elif page == "基金对比":
    section("基金对比", "选择 2-5 只自选基金，横向比较收益、回撤、波动、夏普、评分和行业信息。")
    codes = load_watchlist_codes()
    selected = st.multiselect("选择基金", options=codes, default=codes[: min(3, len(codes))])
    if len(selected) < 2:
        st.info("至少选择两只基金。")
    elif len(selected) > 5:
        st.warning("最多选择 5 只基金，避免图表过于拥挤。")
    else:
        code_list = [selected_code(item) for item in selected]
        with db_session() as db:
            comparison = research_service.compare_funds(db, code_list)
            industry_rows = research_service.industry_overview(db)
            risk_return = research_service.risk_return_points(db)
        rows = comparison["funds"]
        st.dataframe(
            [
                {
                    "基金代码": row["fund_code"],
                    "基金名称": row["fund_name"],
                    "行业/主题": row["industry"],
                    "近1月": pct(row["return_1m"]),
                    "近3月": pct(row["return_3m"]),
                    "近1年": pct(row["return_1y"]),
                    "最大回撤": pct(row["max_drawdown_1y"]),
                    "波动率": pct(row["volatility_1y"]),
                    "夏普": score_value(row["sharpe_1y"]),
                    "胜率": pct(row["win_rate_1y"]),
                    "总分": score_value(row["score"]),
                    "评级": row["rating"],
                }
                for row in rows
            ],
            use_container_width=True,
            hide_index=True,
        )
        chart_df = pd.DataFrame(rows).dropna(subset=["return_1y", "max_drawdown_1y"])
        if not chart_df.empty:
            fig = px.scatter(
                chart_df,
                x="max_drawdown_1y",
                y="return_1y",
                size="score",
                color="industry",
                hover_name="fund_name",
                text="fund_code",
                labels={"max_drawdown_1y": "近1年最大回撤", "return_1y": "近1年收益"},
            )
            fig.update_layout(template="plotly_white", height=420, margin={"l": 10, "r": 10, "t": 20, "b": 10})
            fig.update_xaxes(tickformat=".0%")
            fig.update_yaxes(tickformat=".0%")
            st.plotly_chart(fig, use_container_width=True)
        if comparison["correlation"]:
            section("选择基金相关性")
            st.dataframe(
                [
                    {"基金组合": key, "相关系数": value}
                    for key, value in comparison["correlation"].items()
                ],
                use_container_width=True,
                hide_index=True,
            )

        section("行业/主题汇总", "按自选基金行业聚合数量、平均评分和持仓占比。")
        st.dataframe(display_industry_rows(industry_rows), use_container_width=True, hide_index=True)
        if risk_return:
            section("全自选风险收益散点")
            scatter_df = pd.DataFrame(risk_return).dropna(subset=["return_1y", "volatility_1y"])
            if not scatter_df.empty:
                scatter_df["display_weight"] = scatter_df["position_weight"].clip(lower=0.02)
                fig = px.scatter(
                    scatter_df,
                    x="volatility_1y",
                    y="return_1y",
                    size="display_weight",
                    color="industry",
                    hover_name="fund_name",
                    text="fund_code",
                    labels={"volatility_1y": "近1年波动率", "return_1y": "近1年收益"},
                )
                fig.update_layout(template="plotly_white", height=420, margin={"l": 10, "r": 10, "t": 20, "b": 10})
                fig.update_xaxes(tickformat=".0%")
                fig.update_yaxes(tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)

elif page == "评分排行":
    with db_session() as db:
        scores = score_service.top_scores(db, limit=100)
    labels = watchlist_label_map()
    rows = label_score_rows(score_rows(scores), labels)
    ratings = sorted({row["评级"] for row in rows if row["评级"]})

    col1, col2 = st.columns([1, 1])
    selected_rating = col1.multiselect("评级筛选", ratings, default=ratings)
    min_score = col2.slider("最低分", min_value=0, max_value=100, value=0)

    filtered = [
        row
        for row in rows
        if (not selected_rating or row["评级"] in selected_rating)
        and (row["总分"] is None or row["总分"] >= min_score)
    ]

    section("评分排行", "按规则评分模型排序，结合推荐理由做进一步观察。")
    rating_guide()
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    if filtered:
        chart_df = pd.DataFrame(filtered[:20]).dropna(subset=["总分"]).sort_values("总分")
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=chart_df["总分"],
                y=chart_df["基金"],
                orientation="h",
                text=chart_df["总分"].map(lambda value: f"{value:.1f}"),
                textposition="outside",
                marker={
                    "color": chart_df["总分"],
                    "colorscale": "Viridis",
                    "showscale": True,
                    "colorbar": {"title": "总分"},
                },
                hovertemplate="基金=%{y}<br>总分=%{x:.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#111827"},
            height=max(360, 26 * len(chart_df) + 120),
            margin={"l": 10, "r": 58, "t": 20, "b": 10},
            xaxis_title="总分",
            yaxis_title=None,
        )
        fig.update_xaxes(range=[0, 105], showgrid=True, gridcolor="#eef2f7")
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

elif page == "评分趋势":
    section("评分趋势", "查看单只基金历史评分变化，以及分项分的贡献。")
    codes = load_watchlist_codes()
    selected = st.selectbox("选择基金", options=codes, index=0 if codes else None)
    if not selected:
        st.info("先添加自选基金并计算评分。")
    else:
        with db_session() as db:
            rows = research_service.score_trend(db, selected_code(selected))
        if not rows:
            st.info("暂无评分历史。")
        else:
            trend_df = pd.DataFrame(rows)
            st.dataframe(score_trend_rows(rows), use_container_width=True, hide_index=True)
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=trend_df["score_date"],
                    y=trend_df["total_score"],
                    mode="lines+markers",
                    name="总分",
                    line={"color": "#2563eb", "width": 2},
                )
            )
            fig.update_layout(
                template="plotly_white",
                height=360,
                margin={"l": 10, "r": 10, "t": 20, "b": 10},
                xaxis_title=None,
                yaxis_title="总分",
            )
            fig.update_yaxes(range=[0, 100], showgrid=True, gridcolor="#eef2f7")
            st.plotly_chart(fig, use_container_width=True)

elif page == "相关性分析":
    section("相关性分析", "基于自选基金日收益率计算，用于发现重复配置。")
    labels = watchlist_label_map()
    with db_session() as db:
        corr = correlation_service.calculate_correlation(db)
        pairs = correlation_service.high_correlation_pairs(db)
    if corr.empty:
        st.info("相关性数据不足。至少需要两只自选基金，并同步足够的日涨跌幅数据。")
    else:
        columns = list(corr.columns)
        options = [labels.get(code, code) for code in columns]
        option_to_code = {labels.get(code, code): code for code in columns}

        pair_rows = [
            {
                "基金A": labels.get(pair["fund_a"], pair["fund_a"]),
                "基金B": labels.get(pair["fund_b"], pair["fund_b"]),
                "相关系数": round(pair["correlation"], 3),
                "解读": "高度相似，可能重复配置" if pair["correlation"] >= 0.85 else "可观察",
            }
            for pair in pairs
        ]
        if pair_rows:
            section("高相关组合", "优先看这里：相关系数越接近 1，走势越相似。")
            st.dataframe(pair_rows, use_container_width=True, hide_index=True)
        else:
            st.success("当前未发现相关系数超过 0.85 的基金组合。")

        section("基金对比", "选择两只基金查看相关系数和日涨跌走势，相关系数越接近 1，短期波动越相似。")
        col_a, col_b = st.columns(2)
        selected_a = col_a.selectbox("基金 A", options=options, index=0)
        selected_b = col_b.selectbox("基金 B", options=options, index=1 if len(options) > 1 else 0)
        code_a = option_to_code[selected_a]
        code_b = option_to_code[selected_b]

        if code_a == code_b:
            st.info("请选择两只不同的基金进行对比。")
        else:
            correlation_value = corr.loc[code_a, code_b]
            interpretation = (
                "高度相似，可能存在重复配置"
                if correlation_value >= 0.85
                else "走势有一定相似性"
                if correlation_value >= 0.5
                else "相关性较低，走势差异较明显"
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("相关系数", f"{correlation_value:.3f}")
            c2.metric("解读", interpretation)

            with db_session() as db:
                matrix = correlation_service.fund_return_matrix(db)
            pair_matrix = matrix[[code_a, code_b]].dropna() if not matrix.empty else pd.DataFrame()
            c3.metric("共同交易日", len(pair_matrix))

            if pair_matrix.empty:
                st.info("这两只基金没有足够的重合日涨跌数据。")
            else:
                pair_plot = pair_matrix.tail(180).rename(columns={code_a: selected_a, code_b: selected_b}).reset_index()
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=pair_plot["nav_date"],
                        y=pair_plot[selected_a],
                        mode="lines",
                        name=selected_a,
                        line={"color": "#2563eb", "width": 1.8},
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=pair_plot["nav_date"],
                        y=pair_plot[selected_b],
                        mode="lines",
                        name=selected_b,
                        line={"color": "#f97316", "width": 1.8},
                    )
                )
                fig.update_layout(
                    template="plotly_white",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font={"color": "#111827"},
                    height=380,
                    margin={"l": 10, "r": 10, "t": 20, "b": 10},
                    hovermode="x unified",
                    xaxis_title=None,
                    yaxis_title="日涨跌幅",
                    yaxis_tickformat=".1%",
                )
                fig.update_xaxes(showgrid=True, gridcolor="#eef2f7")
                fig.update_yaxes(showgrid=True, gridcolor="#eef2f7", zeroline=True, zerolinecolor="#94a3b8")
                st.plotly_chart(fig, use_container_width=True)

            related_rows = []
            for other_code in columns:
                if other_code == code_a:
                    continue
                value = corr.loc[code_a, other_code]
                if pd.notna(value):
                    related_rows.append(
                        {
                            "对比基金": labels.get(other_code, other_code),
                            "相关系数": round(float(value), 3),
                            "解读": "高度相似" if value >= 0.85 else "中等相关" if value >= 0.5 else "低相关",
                        }
                    )
            related_rows = sorted(related_rows, key=lambda item: item["相关系数"], reverse=True)
            section("基金 A 的相似度排行", "用于快速找到与当前基金走势最接近的自选基金。")
            st.dataframe(related_rows[:10], use_container_width=True, hide_index=True)

        if st.button("生成高相关预警", use_container_width=True):
            with db_session() as db:
                alerts = correlation_service.generate_correlation_alerts(db)
            st.success(f"已生成或更新 {len(alerts)} 条相关性预警")

elif page == "AI 简报":
    section("每日基金简报", "基于自选基金、评分和预警生成；Ollama 不可用时使用规则兜底。")
    col1, col2, col3 = st.columns([1, 1, 3])
    if col1.button("生成每日简报", use_container_width=True):
        with db_session() as db:
            report = generate_daily_report(db)
        st.success("已生成")
        render_report_metadata(report)
        st.markdown(report.content)
    elif col2.button("测试 Ollama 连接", use_container_width=True):
        try:
            status = OllamaClient().check_model_available()
            if status["model_available"]:
                st.success(f"Ollama 可用，模型已找到：{status['configured_model']}")
            else:
                st.warning(
                    f"Ollama 可连接，但没有找到配置模型：{status['configured_model']}。"
                    "请确认模型名称或先执行 ollama pull。"
                )
            st.dataframe(ollama_status_rows(status), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Ollama 连接失败：{exc}")
    else:
        with db_session() as db:
            report = latest_report(db)
        if report:
            render_report_metadata(report)
            st.markdown(report.content)
        else:
            st.info("暂无简报。")

elif page == "报告历史":
    section("报告历史", "按时间查看历史 AI 日报，并可展开当时的结构化输入摘要。")
    with db_session() as db:
        reports = report_history(db, limit=50)
    if not reports:
        st.info("暂无历史日报。")
    else:
        options = [f"{report.id} - {report.created_at:%Y-%m-%d %H:%M} - {report.model_name}" for report in reports]
        selected_report = st.selectbox("选择日报", options=options)
        report_id = int(selected_report.split(" - ", 1)[0])
        report = next(item for item in reports if item.id == report_id)
        render_report_metadata(report)
        st.markdown(report.content)

elif page == "任务中心":
    section("任务中心", "按数据链路顺序执行：同步净值、计算指标、计算评分、生成预警。")
    with db_session() as db:
        health = data_health_service.data_health_overview(db)
    c0, c00 = st.columns(2)
    c0.metric("待计算指标", health["pending_indicator_count"])
    c00.metric("需关注数据", health["stale_fund_count"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="task-button-note">拉取所有启用自选基金的历史净值。</div>', unsafe_allow_html=True)
        sync_nav_clicked = st.button("同步自选净值", use_container_width=True, type="primary")
    with c2:
        st.markdown('<div class="task-button-note">基于净值计算收益、回撤、波动和胜率。</div>', unsafe_allow_html=True)
        calc_indicator_clicked = st.button("计算全部指标", use_container_width=True, type="primary")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown('<div class="task-button-note">基于最新指标生成评分、评级和理由。</div>', unsafe_allow_html=True)
        calc_score_clicked = st.button("计算全部评分", use_container_width=True, type="primary")
    with c4:
        st.markdown('<div class="task-button-note">生成大跌、回撤、持仓集中度等预警。</div>', unsafe_allow_html=True)
        alert_clicked = st.button("生成风险预警", use_container_width=True, type="primary")

    market_clicked = st.button("同步市场数据", use_container_width=True)
    daily_report_clicked = st.button("生成每日简报", use_container_width=True)

    if sync_nav_clicked:
        with st.spinner("正在同步自选基金净值..."):
            with db_session() as db:
                result = task_log_service.run_logged(db, "manual_sync_watchlist_nav", lambda: nav_service.sync_watchlist_nav(db))
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)
    if calc_indicator_clicked:
        with st.spinner("正在计算全部指标..."):
            with db_session() as db:
                result = task_log_service.run_logged(
                    db,
                    "manual_calc_indicators",
                    lambda: indicator_service.calculate_watchlist_indicators(db),
                )
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)
    if calc_score_clicked:
        with st.spinner("正在计算全部评分..."):
            with db_session() as db:
                result = task_log_service.run_logged(
                    db,
                    "manual_calc_scores",
                    lambda: score_service.calculate_watchlist_scores(db),
                )
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)
    if alert_clicked:
        with st.spinner("正在生成风险预警..."):
            with db_session() as db:
                result = task_log_service.run_logged(
                    db,
                    "manual_generate_alerts",
                    lambda: [alert.title for alert in alert_service.generate_alerts(db)],
                )
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)
    if market_clicked:
        with st.spinner("正在同步市场数据..."):
            with db_session() as db:
                result = task_log_service.run_logged(
                    db,
                    "manual_sync_market_context",
                    lambda: market_service.sync_market_context(db),
                )
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)
    if daily_report_clicked:
        with st.spinner("正在生成每日简报..."):
            with db_session() as db:
                result = task_runner_service.run_task(db, "generate_daily_report")
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)

    section("按名称触发任务", "用于调试和自动化联调。")
    task_options = {
        f"{item['description']}（{item['task_name']}）": item["task_name"]
        for item in task_runner_service.available_tasks()
    }
    selected_task_label = st.selectbox("任务名称", list(task_options.keys()))
    if st.button("运行选中任务", use_container_width=True):
        selected_task = task_options[selected_task_label]
        with st.spinner(f"正在运行 {selected_task_label}..."):
            with db_session() as db:
                result = task_runner_service.run_task(db, selected_task)
            st.dataframe(task_result_rows(result), use_container_width=True, hide_index=True)

    section("最近任务日志", "展示手动任务和定时任务的执行结果、耗时和失败原因。")
    with db_session() as db:
        logs = task_log_service.latest_task_logs(db, limit=30)
    if logs:
        st.dataframe(task_log_rows(logs), use_container_width=True, hide_index=True)
    else:
        st.info("暂无任务日志。")
