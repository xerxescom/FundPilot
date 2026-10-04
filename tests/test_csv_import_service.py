from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import PortfolioCashEvent, PortfolioPosition, PortfolioTransaction
from app.services import account_service, csv_import_service, portfolio_service

DELIVERY_HEADER = "成交日期,证券代码,证券名称,业务名称,成交价格,成交数量,成交金额,手续费,成交编号"
DELIVERY_ROWS = (
    "2026-01-05,600519,贵州茅台,证券买入,1500,10,15000,5,C001\n"
    "2026-02-01,600519,贵州茅台,证券卖出,1600,2,3200,1,C002\n"
)
STATEMENT_HEADER = "发生日期,业务名称,发生金额,证券代码,备注,流水号"
STATEMENT_ROWS = (
    "2026-01-03,银证转入,10000,,入金,S001\n"
    "2026-02-02,股息入账,20,600519,分红,S002\n"
    "2026-02-03,手续费,-1,,,S003\n"
)


def _delivery_content(rows: str = DELIVERY_ROWS, header: str = DELIVERY_HEADER) -> bytes:
    return f"{header}\n{rows}".encode("utf-8")


def _statement_content(rows: str = STATEMENT_ROWS) -> bytes:
    return f"{STATEMENT_HEADER}\n{rows}".encode("utf-8")


def _importable(preview: dict) -> list[dict]:
    return [
        row
        for row in preview["rows"]
        if row.get("status") in {"ok", "suspect"} and row.get("target") in {"trade", "cash"}
    ]


def _transaction_count(db_session) -> int:
    return len(list(db_session.scalars(select(PortfolioTransaction.id))))


# ---------------------------------------------------------------- 解析原语


def test_parse_decimal_matrix():
    assert csv_import_service.parse_decimal("1,234.56") == Decimal("1234.56")
    assert csv_import_service.parse_decimal("￥1,234") == Decimal("1234")
    assert csv_import_service.parse_decimal("１２３４．５６") == Decimal("1234.56")
    assert csv_import_service.parse_decimal("(123.45)") == Decimal("-123.45")
    assert csv_import_service.parse_decimal("100股") == Decimal("100")
    assert csv_import_service.parse_decimal("--") is None
    assert csv_import_service.parse_decimal("") is None
    assert csv_import_service.parse_decimal("abc") is None


def test_parse_date_matrix():
    assert csv_import_service.parse_date("2026-10-04") == date(2026, 10, 4)
    assert csv_import_service.parse_date("2026/10/04") == date(2026, 10, 4)
    assert csv_import_service.parse_date("20261004") == date(2026, 10, 4)
    assert csv_import_service.parse_date("2026.10.4") == date(2026, 10, 4)
    assert csv_import_service.parse_date("2026年10月4日") == date(2026, 10, 4)
    assert csv_import_service.parse_date("26-10-04") is None  # 两位年份拒绝
    assert csv_import_service.parse_date("") is None


def test_read_csv_handles_gbk_tab_and_preamble(db_session):
    content = ("中信证券资金流水\n" + STATEMENT_HEADER.replace(",", "\t") + "\n"
               + STATEMENT_ROWS.replace(",", "\t") + "\n").encode("gb18030")

    preview = csv_import_service.preview_import(db_session, file_name="s.csv", content=content)

    assert preview["encoding"] == "gb18030"
    assert preview["detected"]["header_row"] == 1  # 前置标题行被跳过
    assert preview["detected"]["source_kind"] == "citic_statement"
    assert preview["counts"]["total"] == 3
    assert preview["counts"]["importable"] == 3


def test_mapping_override_remaps_columns(db_session):
    content = "日期,方向,代码,价格,数量,金额\n2026-03-01,买入,600519,1500,10,15000\n".encode("utf-8")

    preview = csv_import_service.preview_import(
        db_session,
        file_name="x.csv",
        content=content,
        source_kind="citic_delivery",
        mapping_override={
            "columns": {
                "trade_date": "日期",
                "asset_code": "代码",
                "trade_type": "方向",
                "price": "价格",
                "quantity": "数量",
                "amount": "金额",
            },
            "value_maps": {"trade_type": {"买入": "buy"}},
        },
    )

    assert preview["counts"]["importable"] == 1
    parsed = preview["rows"][0]["parsed"]
    assert parsed["asset_code"] == "600519"
    assert parsed["trade_type"] == "buy"


# ---------------------------------------------------------------- 预览与提交


def test_preview_and_commit_delivery_then_reimport_is_idempotent(db_session):
    preview = csv_import_service.preview_import(
        db_session, file_name="delivery.csv", content=_delivery_content()
    )
    assert preview["counts"]["importable"] == 2

    result = csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))
    assert result["counts"]["imported"] == 2
    assert result["status"] == "committed"
    assert _transaction_count(db_session) == 2

    position = db_session.scalar(
        select(PortfolioPosition).where(PortfolioPosition.asset_code == "600519")
    )
    assert position.holding_share == Decimal("8.0000")
    # 买入成本 15000+5=15005，均价 1500.5；卖出 2 份扣 3001 → 剩 12004
    assert position.holding_amount == Decimal("12004.0000")
    effect = result["position_effects"][0]
    assert effect["asset_code"] == "600519"
    assert effect["realized_pnl_total"] == Decimal("198.0000")  # (3200-1) - 1500.5×2

    again = csv_import_service.preview_import(db_session, file_name="delivery.csv", content=_delivery_content())
    assert again["counts"]["duplicate"] == 2
    assert any("此前已导入过" in warning for warning in again["warnings"])
    second = csv_import_service.commit_import(db_session, batch_id=again["batch_id"], rows=_importable(again))
    assert second["counts"]["imported"] == 0
    assert _transaction_count(db_session) == 2


def test_statement_imports_cash_events_and_ignores_trade_rows(db_session):
    preview = csv_import_service.preview_import(
        db_session, file_name="statement.csv", content=_statement_content()
    )
    parsed_types = [row["parsed"]["event_type"] for row in preview["rows"] if row.get("parsed")]
    assert parsed_types == ["deposit", "dividend", "fee"]

    result = csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))

    assert result["counts"]["imported"] == 3
    assert account_service.cash_balance(db_session) == Decimal("10019.0000")
    dividend = db_session.scalar(
        select(PortfolioCashEvent).where(PortfolioCashEvent.event_type == "dividend")
    )
    assert dividend.asset_code == "600519"


def test_unmapped_business_name_is_error_with_reason(db_session):
    content = _delivery_content(rows="2026-01-05,600519,贵州茅台,融资买入,1500,10,15000,5,C009\n")

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)

    row = preview["rows"][0]
    assert row["status"] == "error"
    assert "融资买入" in row["reason"]


def test_simulated_sell_overflow_marks_row_error_before_commit(db_session):
    rows = (
        "2026-02-01,600519,贵州茅台,证券卖出,1600,10,16000,1,C010\n"  # 没有任何持仓就卖出
    )
    content = _delivery_content(rows=rows)

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)

    row = preview["rows"][0]
    assert row["status"] == "error"
    assert "可用持仓" in row["reason"]


def test_same_day_same_amount_distinct_trades_both_import_then_both_duplicate(db_session):
    rows = (
        "2026-03-01,600519,贵州茅台,证券买入,100,10,1000,0,\n"
        "2026-03-01,600519,贵州茅台,证券买入,50,20,1000,0,\n"  # 同日同额，价格数量不同
    )
    content = _delivery_content(header=DELIVERY_HEADER.rsplit(",", 1)[0], rows=rows)  # 去掉成交编号列

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    assert preview["counts"]["importable"] == 2

    result = csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))
    assert result["counts"]["imported"] == 2
    assert _transaction_count(db_session) == 2

    again = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    assert again["counts"]["duplicate"] == 2


def test_identical_rows_in_one_file_each_get_unique_refs(db_session):
    rows = (
        "2026-03-02,600519,贵州茅台,证券买入,100,10,1000,0,\n"
        "2026-03-02,600519,贵州茅台,证券买入,100,10,1000,0,\n"  # 完全相同的两笔
    )
    content = _delivery_content(header=DELIVERY_HEADER.rsplit(",", 1)[0], rows=rows)

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    refs = [row["external_ref"] for row in preview["rows"]]
    assert len(set(refs)) == 2  # 同内容不同出现序号 → 引用唯一
    assert preview["counts"]["importable"] == 2

    csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))
    again = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    assert again["counts"]["duplicate"] == 2


def test_legacy_row_without_ref_is_suspect_and_force_import_works(db_session):
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "600519",
            "asset_type": "stock",
            "trade_date": date(2026, 4, 1),
            "trade_type": "buy",
            "amount": Decimal("500"),
            "nav": Decimal("50"),
            "share": Decimal("10"),
        },
    )
    rows = "2026-04-01,600519,贵州茅台,证券买入,50,10,500,0,\n"
    content = _delivery_content(header=DELIVERY_HEADER.rsplit(",", 1)[0], rows=rows)

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    row = preview["rows"][0]
    assert row["status"] == "suspect"
    assert "缺少外部编号" in row["reason"]

    skipped = csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=[row])
    assert skipped["counts"]["imported"] == 0
    assert skipped["counts"]["duplicate"] == 1

    preview2 = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    forced_row = preview2["rows"][0]
    forced_row["force_import"] = True
    forced = csv_import_service.commit_import(db_session, batch_id=preview2["batch_id"], rows=[forced_row])
    assert forced["counts"]["imported"] == 1
    assert _transaction_count(db_session) == 2


def test_commit_rolls_back_entire_batch_when_opening_cannot_materialize(db_session):
    # 手工持仓缺成本：提交时 ensure_opening 会失败，整批回滚且留痕
    db_session.add(
        PortfolioPosition(
            fund_code="600519", asset_type="stock", asset_code="600519",
            holding_share=Decimal("100"), holding_amount=None, cost_nav=None,
        )
    )
    db_session.commit()
    rows = (
        "2026-05-01,600519,贵州茅台,证券买入,1500,10,15000,5,C100\n"
        "2026-05-02,000001,华夏成长,证券买入,10,100,1000,0,C101\n"  # 另一资产本可成功
    )
    content = _delivery_content(rows=rows)
    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=content)
    assert any("缺少成本信息" in warning for warning in preview["warnings"])

    with pytest.raises(ValueError, match="缺少成本信息"):
        csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))

    assert _transaction_count(db_session) == 0  # 整批回滚，另一资产也没有入账
    from app.db.models import PortfolioImportBatch

    stored = db_session.get(PortfolioImportBatch, preview["batch_id"])
    assert stored.status == "failed"
    assert "缺少成本信息" in (stored.notes_json or {}).get("failure_reason", "")


def test_commit_rejects_already_committed_batch(db_session):
    preview = csv_import_service.preview_import(db_session, file_name="d.csv", content=_delivery_content())
    csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))

    with pytest.raises(ValueError, match="已入账"):
        csv_import_service.commit_import(db_session, batch_id=preview["batch_id"], rows=_importable(preview))


def test_manual_position_warning_on_preview(db_session):
    db_session.add(
        PortfolioPosition(
            fund_code="600519", asset_type="stock", asset_code="600519",
            holding_share=Decimal("100"), holding_amount=Decimal("150000"), cost_nav=Decimal("1500"),
        )
    )
    db_session.commit()

    preview = csv_import_service.preview_import(db_session, file_name="x.csv", content=_delivery_content())

    assert any("已有手工/截图持仓" in warning for warning in preview["warnings"])
