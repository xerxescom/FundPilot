from decimal import Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.db.session import SessionLocal, init_db
from app.services import (
    alert_service,
    indicator_service,
    nav_service,
    score_service,
    watchlist_service,
)
from app.services.ai.report_service import generate_daily_report, latest_report

st.set_page_config(page_title="FundPilot", layout="wide", initial_sidebar_state="expanded")
init_db()

RATING_COLORS = {
    "重点关注": "#0f9f6e",
    "可以观察": "#2563eb",
    "一般": "#d97706",
    "暂不关注": "#6b7280",
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
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
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


def section(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="muted">{caption}</div>', unsafe_allow_html=True)


def rating_badge(rating: str | None) -> str:
    label = rating or "未评分"
    color = RATING_COLORS.get(label, "#6b7280")
    return f'<span class="pill" style="background:{color}">{label}</span>'


def load_watchlist_codes() -> list[str]:
    with db_session() as db:
        return [
            f"{item.fund_code} {item.fund_name}" if item.fund_name else item.fund_code
            for item in watchlist_service.list_watchlist_items(db)
        ]


def selected_code(value: str | None) -> str:
    return (value or "").split(" ", 1)[0].strip()


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


def render_nav_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["单位净值"],
            mode="lines",
            name="单位净值",
            line={"color": "#2563eb", "width": 2},
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
    st.plotly_chart(fig, use_container_width=True)


st.sidebar.title("FundPilot")
st.sidebar.caption("本地基金投研助手")
page = st.sidebar.radio(
    "导航",
    ["首页概览", "自选基金", "基金详情", "评分排行", "AI 简报", "系统任务"],
)

st.title("FundPilot 本地基金投研助手")

if page == "首页概览":
    with db_session() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        scores = score_service.top_scores(db, limit=5)
        alerts = alert_service.unread_alerts(db)
        report = latest_report(db)

    best_score = scores[0].total_score if scores and scores[0].total_score is not None else None
    best_rating = scores[0].rating if scores else "暂无"
    latest_report_time = report.created_at.strftime("%Y-%m-%d %H:%M") if report else "暂无"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("自选基金", len(watchlist))
    c2.metric("最高评分", score_value(best_score), best_rating)
    c3.metric("未读预警", len(alerts))
    c4.metric("最近简报", latest_report_time)

    left, right = st.columns([1.35, 1])
    with left:
        section("推荐关注 Top 5", "按最新评分排序，优先查看高分且理由清晰的基金。")
        st.dataframe(score_rows(scores), use_container_width=True, hide_index=True)

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

elif page == "自选基金":
    section("自选基金管理", "添加基金后，可以批量同步净值并进入详情页分析。")
    with st.form("add_watchlist", clear_on_submit=True):
        col1, col2, col3 = st.columns([1, 2, 1])
        fund_code = col1.text_input("基金代码", placeholder="000001")
        fund_name = col2.text_input("基金名称", placeholder="可留空，系统会尝试自动获取")
        note = st.text_input("备注", placeholder="例如：长期观察")
        submitted = col3.form_submit_button("添加自选", use_container_width=True)
    if submitted and fund_code:
        with db_session() as db:
            item = watchlist_service.add_watchlist_item(
                db, fund_code, note=note or None, fund_name=fund_name or None
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
                    "分组": item.group_name,
                    "备注": item.note,
                    "状态": "active" if item.is_active else "inactive",
                }
                for item in items
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("还没有自选基金。先添加一只基金代码开始。")

    section("同步操作")
    col1, col2 = st.columns(2)
    sync_code = col1.text_input("同步单只基金净值", placeholder="000001")
    if col1.button("同步单只", use_container_width=True) and sync_code:
        with db_session() as db:
            count = nav_service.sync_fund_nav(db, sync_code)
        st.success(f"已同步 {sync_code.zfill(6)}，共 {count} 条净值")
    if col2.button("同步全部自选基金", use_container_width=True):
        with db_session() as db:
            result = nav_service.sync_watchlist_nav(db)
        if result:
            st.success("批量同步完成")
            st.json(result)
        else:
            st.info("没有 active 自选基金。")

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
                with db_session() as db:
                    count = nav_service.sync_fund_nav(db, fund_code)
                st.success(f"已同步 {count} 条净值")
            except Exception as exc:
                st.error(f"同步失败：{exc}")

        if action_cols[1].button("计算指标", use_container_width=True):
            try:
                with db_session() as db:
                    indicator = indicator_service.calculate_and_save_indicators(db, fund_code)
                    calc_date = indicator.calc_date
                st.success(f"指标已更新到 {calc_date}")
            except Exception as exc:
                st.error(f"计算指标失败：{exc}")

        if action_cols[2].button("计算评分", use_container_width=True):
            try:
                with db_session() as db:
                    score = score_service.calculate_and_save_score(db, fund_code)
                    total_score = score.total_score
                st.success(f"评分已更新：{total_score}")
            except Exception as exc:
                st.error(f"计算评分失败：{exc}")

        if action_cols[3].button("一键同步并分析", use_container_width=True):
            try:
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
        metric_cols[0].metric("近1月收益", pct(indicator.return_1m if indicator else None))
        metric_cols[1].metric("近3月收益", pct(indicator.return_3m if indicator else None))
        metric_cols[2].metric("近1年收益", pct(indicator.return_1y if indicator else None))
        metric_cols[3].metric("最大回撤", pct(indicator.max_drawdown_1y if indicator else None))
        metric_cols[4].metric("总分", score_value(score.total_score if score else None))

        df = nav_dataframe(nav_rows)
        if df.empty:
            st.info("还没有净值数据，请先同步。")
        else:
            section("净值走势")
            render_nav_chart(df)
            section("回撤曲线")
            render_drawdown_chart(df)

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

elif page == "评分排行":
    with db_session() as db:
        scores = score_service.top_scores(db, limit=100)
    rows = score_rows(scores)
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
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    if filtered:
        chart_df = pd.DataFrame(filtered[:20]).dropna(subset=["总分"])
        fig = px.bar(chart_df, x="基金代码", y="总分", color="评级", text="总分")
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#111827"},
            height=360,
            margin={"l": 10, "r": 10, "t": 20, "b": 10},
        )
        st.plotly_chart(fig, use_container_width=True)

elif page == "AI 简报":
    section("每日基金简报", "基于自选基金、评分和预警生成；Ollama 不可用时使用规则兜底。")
    col1, col2 = st.columns([1, 3])
    if col1.button("生成每日简报", use_container_width=True):
        with db_session() as db:
            report = generate_daily_report(db)
        st.success("已生成")
        st.markdown(report.content)
    else:
        with db_session() as db:
            report = latest_report(db)
        if report:
            st.caption(f"生成时间：{report.created_at:%Y-%m-%d %H:%M}")
            st.markdown(report.content)
        else:
            st.info("暂无简报。")

elif page == "系统任务":
    section("手动批处理", "按数据链路顺序执行：同步净值、计算指标、计算评分、生成预警。")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("同步自选净值", use_container_width=True):
        with db_session() as db:
            st.json(nav_service.sync_watchlist_nav(db))
    if c2.button("计算全部指标", use_container_width=True):
        with db_session() as db:
            st.json(indicator_service.calculate_watchlist_indicators(db))
    if c3.button("计算全部评分", use_container_width=True):
        with db_session() as db:
            st.json(score_service.calculate_watchlist_scores(db))
    if c4.button("生成风险预警", use_container_width=True):
        with db_session() as db:
            st.write([alert.title for alert in alert_service.generate_alerts(db)])
