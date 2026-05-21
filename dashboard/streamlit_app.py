import pandas as pd
import plotly.express as px
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

st.set_page_config(page_title="FundPilot", layout="wide")
init_db()


def db_session():
    return SessionLocal()


st.title("FundPilot 本地基金投研助手")
page = st.sidebar.radio(
    "导航",
    ["首页概览", "自选基金", "基金详情", "评分排行", "AI 简报", "系统设置"],
)

if page == "首页概览":
    with db_session() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        scores = score_service.top_scores(db, limit=5)
        alerts = alert_service.unread_alerts(db)

    c1, c2, c3 = st.columns(3)
    c1.metric("自选基金", len(watchlist))
    c2.metric("推荐 Top 5", len(scores))
    c3.metric("未读预警", len(alerts))

    st.subheader("推荐关注 Top 5")
    st.dataframe(
        [
            {
                "基金代码": item.fund_code,
                "总分": float(item.total_score) if item.total_score is not None else None,
                "评级": item.rating,
                "理由": item.reason,
            }
            for item in scores
        ],
        use_container_width=True,
    )

    st.subheader("风险提醒")
    st.dataframe(
        [
            {
                "基金代码": item.fund_code,
                "等级": item.alert_level,
                "标题": item.title,
                "内容": item.content,
            }
            for item in alerts
        ],
        use_container_width=True,
    )

elif page == "自选基金":
    st.subheader("添加自选基金")
    with st.form("add_watchlist"):
        fund_code = st.text_input("基金代码", placeholder="例如 000001")
        note = st.text_input("备注")
        submitted = st.form_submit_button("添加")
    if submitted and fund_code:
        with db_session() as db:
            watchlist_service.add_watchlist_item(db, fund_code, note=note or None)
        st.success("已添加")

    with db_session() as db:
        items = watchlist_service.list_watchlist_items(db)
    st.dataframe(
        [{"基金代码": item.fund_code, "分组": item.group_name, "备注": item.note} for item in items],
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    sync_code = col1.text_input("同步单只基金净值")
    if col1.button("同步") and sync_code:
        with db_session() as db:
            count = nav_service.sync_fund_nav(db, sync_code)
        st.success(f"已同步 {count} 条净值")
    if col2.button("同步全部自选基金"):
        with db_session() as db:
            result = nav_service.sync_watchlist_nav(db)
        st.write(result)

elif page == "基金详情":
    fund_code = st.text_input("基金代码", placeholder="例如 000001")
    if fund_code:
        with db_session() as db:
            nav_rows = nav_service.list_fund_nav(db, fund_code)
            indicator = indicator_service.latest_indicator(db, fund_code)
            score = score_service.latest_score(db, fund_code)
        if nav_rows:
            df = pd.DataFrame(
                [
                    {
                        "日期": row.nav_date,
                        "单位净值": float(row.unit_nav) if row.unit_nav is not None else None,
                    }
                    for row in nav_rows
                ]
            )
            st.plotly_chart(px.line(df, x="日期", y="单位净值"), use_container_width=True)
        else:
            st.info("还没有净值数据，请先同步。")

        st.subheader("指标")
        st.json(indicator.__dict__ if indicator else {})
        st.subheader("评分")
        st.json(score.__dict__ if score else {})

elif page == "评分排行":
    with db_session() as db:
        scores = score_service.top_scores(db, limit=50)
    st.dataframe(
        [
            {
                "基金代码": item.fund_code,
                "日期": item.score_date,
                "总分": float(item.total_score) if item.total_score is not None else None,
                "评级": item.rating,
                "推荐理由": item.reason,
            }
            for item in scores
        ],
        use_container_width=True,
    )

elif page == "AI 简报":
    if st.button("生成每日简报"):
        with db_session() as db:
            report = generate_daily_report(db)
        st.success("已生成")
        st.markdown(report.content)
    else:
        with db_session() as db:
            report = latest_report(db)
        if report:
            st.markdown(report.content)
        else:
            st.info("暂无简报。")

elif page == "系统设置":
    st.subheader("手动批处理")
    c1, c2, c3 = st.columns(3)
    if c1.button("计算全部指标"):
        with db_session() as db:
            st.write(indicator_service.calculate_watchlist_indicators(db))
    if c2.button("计算全部评分"):
        with db_session() as db:
            st.write(score_service.calculate_watchlist_scores(db))
    if c3.button("生成风险预警"):
        with db_session() as db:
            st.write([alert.title for alert in alert_service.generate_alerts(db)])
