"""券商 CSV 导入：读取 → 结构检测 → 解析 → 预览（只读重放模拟）→ 单事务提交。

字段映射是数据（csv_profiles.py + 用户覆盖），没有真实样例时也能用：
预览返回检测到的列映射，界面改列后重新预览即可校准。
去重：有券商编号用编号；没有则用「内容哈希 + 文件内同内容出现序号」，
同一文件里同日同额的真实不同交易各自唯一，重复导入同一文件则全部判重。
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    FundInfo,
    PortfolioCashEvent,
    PortfolioImportBatch,
    PortfolioTransaction,
)
from app.services import account_service, asset_service, portfolio_service
from app.services.csv_profiles import (
    CITIC_DELIVERY_PROFILE,
    CITIC_STATEMENT_PROFILE,
    IGNORE_REASON,
    PROFILES,
)

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5000
MAX_ERRORS_STORED = 50
_HEADER_SCAN_LINES = 15
_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")
_DELIMITERS = (",", "\t", ";", "|")
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d", "%Y年%m月%d日")
_NUMBER_STRIP = re.compile(r"[￥¥$,\s元份股手'\"]+")

FUND_PREFIXES = ("00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "16", "17", "18")
ETF_PREFIXES = ("51", "56", "58", "15")
STOCK_PREFIXES = ("60", "68", "90", "20", "30", "8", "4")

TRADE_FIELDS = ("trade_date", "asset_code", "trade_type", "price", "quantity", "amount", "fee", "net_amount")
CASH_FIELDS = ("event_date", "event_type", "amount")


# ------------------------------------------------------------------ 读取与解析原语


def read_csv_rows(content: bytes) -> tuple[list[list[str]], str, str]:
    """解码 + 分列，返回 (行, 编码, 分隔符)。"""
    if len(content) > MAX_CSV_BYTES:
        raise ValueError(f"文件超过 {MAX_CSV_BYTES // (1024 * 1024)}MB 上限")
    text = None
    used_encoding = ""
    for encoding in _ENCODINGS:
        try:
            text = content.decode(encoding)
            used_encoding = encoding
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise ValueError("无法识别文件编码（尝试过 utf-8 / gb18030）")

    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows = [[cell.strip() for cell in row] for row in reader]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        raise ValueError("文件没有可解析的内容")
    if len(rows) > MAX_CSV_ROWS:
        raise ValueError(f"行数超过 {MAX_CSV_ROWS} 上限，请拆分文件")
    return rows, used_encoding, delimiter


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:_HEADER_SCAN_LINES])
    best, best_score = ",", -1.0
    for delimiter in _DELIMITERS:
        counts = [len(next(csv.reader([line], delimiter=delimiter))) for line in sample.splitlines() if line.strip()]
        if not counts:
            continue
        modal = max(set(counts), key=counts.count)
        if modal < 2:
            continue
        score = counts.count(modal) / len(counts) + modal / 100
        if score > best_score:
            best, best_score = delimiter, score
    return best


def parse_decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    cleaned = unicodedata.normalize("NFKC", str(text)).strip()
    if cleaned in {"", "-", "--", "—", "/"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = _NUMBER_STRIP.sub("", cleaned).replace("%", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_date(text: str | None) -> date | None:
    if text is None:
        return None
    cleaned = unicodedata.normalize("NFKC", str(text)).strip().split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def normalize_header(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).replace("﻿", "").strip()


def infer_asset_type(db: Session, code: str, default: str = "auto") -> str:
    if default in {"fund", "stock", "etf"}:
        return default
    fund = db.scalar(select(FundInfo.fund_code).where(FundInfo.fund_code == code).limit(1))
    if fund:
        return "fund"
    listed = asset_service.get_asset(db, code)
    if listed is not None and listed.asset_type in {"stock", "etf"}:
        return listed.asset_type
    if code.startswith(ETF_PREFIXES):
        return "etf"
    if code.startswith(STOCK_PREFIXES):
        return "stock"
    if code.startswith(FUND_PREFIXES):
        return "fund"
    return "fund"


# ------------------------------------------------------------------ 结构检测


def _profile_candidates(source_kind: str | None) -> list[dict]:
    if source_kind and source_kind in PROFILES:
        return [PROFILES[source_kind]]
    return [CITIC_DELIVERY_PROFILE, CITIC_STATEMENT_PROFILE]


def _match_columns(cells: list[str], profile: dict) -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {}
    for canonical, candidates in profile["header_candidates"].items():
        matches: list[int] = []
        exact: list[int] = []
        for index, cell in enumerate(cells):
            if not cell:
                continue
            if cell in candidates:
                exact.append(index)
            elif any(candidate and candidate in cell for candidate in candidates):
                matches.append(index)
        chosen = exact or matches
        if chosen:
            mapping[canonical] = sorted(set(chosen))
    return mapping


def detect_structure(rows: list[list[str]], source_kind: str | None = None) -> dict:
    """在前若干行里找出表头行与画像，返回列映射（规范字段 → 列下标列表）。"""
    best: dict | None = None
    for row_index, row in enumerate(rows[:_HEADER_SCAN_LINES]):
        cells = [normalize_header(cell) for cell in row]
        for profile in _profile_candidates(source_kind):
            mapping = _match_columns(cells, profile)
            score = len(mapping)
            required_any = profile.get("required_any")
            if required_any and not any(key in mapping for key in required_any):
                score -= 3  # 用户显式指定 source_kind 时也降权，帮助排序而非排除
            has_date = any(key in mapping for key in ("trade_date", "event_date"))
            has_identity = any(key in mapping for key in ("asset_code", "trade_type", "event_type", "amount"))
            if not (has_date and has_identity):
                continue
            if best is None or score > best["score"]:
                best = {
                    "header_row": row_index,
                    "profile": profile,
                    "columns": mapping,
                    "score": score,
                }
    if best is None:
        return {"header_row": None, "profile": None, "columns": {}, "score": 0}
    profile = best["profile"]
    header = [normalize_header(cell) for cell in rows[best["header_row"]]]
    best["column_headers"] = {
        canonical: [header[index] for index in indexes] for canonical, indexes in best["columns"].items()
    }
    best["source_kind"] = profile["source_kind"]
    best["label"] = profile["label"]
    best["kind"] = profile["kind"]
    return best


def apply_mapping_override(detection: dict, header: list[str], override: dict | None) -> dict:
    """应用用户的列映射覆盖：{"columns": {canonical: "表头原文" 或 [表头原文…]}}。"""
    if not override:
        return detection
    normalized = [normalize_header(cell) for cell in header]
    mapping = dict(detection["columns"])
    for canonical, wanted in (override.get("columns") or {}).items():
        names = wanted if isinstance(wanted, list) else [wanted]
        indexes = [normalized.index(name) for name in names if name in normalized]
        if indexes:
            mapping[canonical] = sorted(indexes)
        else:
            mapping.pop(canonical, None)
    detection = dict(detection)
    detection["columns"] = mapping
    header_cells = [normalize_header(cell) for cell in header]
    detection["column_headers"] = {
        canonical: [header_cells[index] for index in indexes] for canonical, indexes in mapping.items()
    }
    return detection


def _cell(cells: list[str], mapping: dict, canonical: str) -> str | None:
    indexes = mapping.get(canonical)
    if not indexes:
        return None
    values = [cells[index] for index in indexes if index < len(cells) and cells[index]]
    return "；".join(values) if values else None


def _number_cell(cells: list[str], mapping: dict, canonical: str) -> Decimal | None:
    raw = _cell(cells, mapping, canonical)
    return parse_decimal(raw)


def _sum_cells(cells: list[str], mapping: dict, canonical: str) -> Decimal | None:
    indexes = mapping.get(canonical)
    if not indexes:
        return None
    total = Decimal("0")
    found = False
    for index in indexes:
        if index < len(cells):
            value = parse_decimal(cells[index])
            if value is not None:
                total += value
                found = True
    return total if found else None


# ------------------------------------------------------------------ 行解析


def _value_map(profile: dict, key: str, override: dict | None) -> dict[str, str]:
    mapping = dict((profile.get("value_maps") or {}).get(key) or {})
    mapping.update(((override or {}).get("value_maps") or {}).get(key) or {})
    return mapping


def build_row(db: Session, cells: list[str], detection: dict, row_index: int,
              default_asset_type: str = "auto", override: dict | None = None) -> dict:
    """把一行原始单元格解析为规范行；返回 {status, reason?, parsed?, target?}。"""
    profile = detection["profile"]
    mapping = detection["columns"]
    row: dict[str, Any] = {"row_index": row_index, "raw": {str(i): cell for i, cell in enumerate(cells)}}
    if profile is None:
        row.update(status="error", reason="未识别出表头，请手动指定列映射")
        return row

    if profile["kind"] == "trades":
        trade_date = parse_date(_cell(cells, mapping, "trade_date"))
        if trade_date is None:
            row.update(status="error", reason="缺少或无法解析成交日期")
            return row
        type_raw = _cell(cells, mapping, "trade_type")
        direction = _value_map(profile, "trade_type", override).get(type_raw or "")
        if direction is None:
            row.update(status="error", reason=f"无法识别的业务名称：{type_raw or '（空）'}（可在映射中补充）")
            return row
        if direction == "ignore":
            row.update(status="ok", target="ignore", reason=IGNORE_REASON, trade_date=trade_date)
            return row

        code_raw = _cell(cells, mapping, "asset_code")
        if not code_raw:
            row.update(status="error", reason="缺少证券代码")
            return row
        asset_type = infer_asset_type(db, code_raw.strip(), default_asset_type)
        code = asset_service.normalize_asset_code(code_raw.strip(), asset_type)

        quantity = _number_cell(cells, mapping, "quantity")
        price = _number_cell(cells, mapping, "price")
        amount = _number_cell(cells, mapping, "amount")
        fee = _sum_cells(cells, mapping, "fee")
        net_amount = _number_cell(cells, mapping, "net_amount")
        warnings: list[str] = []

        if direction == "split":
            amount = Decimal("0")
            fee = Decimal("0")
            if quantity is None or quantity == 0:
                row.update(status="error", reason="拆分/送股行缺少份额变动")
                return row
        else:
            if amount is None and quantity is not None and price is not None:
                amount = portfolio_service._quantize(quantity * price, "0.0001")
            if amount is None and net_amount is not None:
                amount = abs(net_amount)
                warnings.append("成交金额缺失，取自发生额")
            if amount is None or amount <= 0:
                row.update(status="error", reason="缺少成交金额（且无法由数量×价格推出）")
                return row
            if fee is None:
                if net_amount is not None:
                    fee = portfolio_service._quantize(abs(amount - abs(net_amount)), "0.0001")
                    warnings.append("手续费缺失，按成交金额与发生额之差估算")
                else:
                    fee = Decimal("0")
            if quantity is not None and price is not None and abs(quantity * price - amount) > Decimal("0.01"):
                warnings.append("成交金额与数量×价格不一致，已按金额入账")
            if direction in portfolio_service.SELL_TYPES and quantity is None and price is None:
                row.update(status="error", reason="卖出/赎回行缺少数量与价格")
                return row

        parsed = {
            "trade_date": trade_date,
            "asset_type": asset_type,
            "asset_code": code,
            "asset_name": _cell(cells, mapping, "asset_name"),
            "trade_type": direction,
            "price": price,
            "quantity": quantity,
            "amount": portfolio_service._quantize(amount, "0.0001"),
            "fee": portfolio_service._quantize(fee or Decimal("0"), "0.0001"),
            "broker_ref": _cell(cells, mapping, "broker_ref"),
            "note": _cell(cells, mapping, "note"),
        }
        row.update(status="ok", target="trade", parsed=parsed, warnings=warnings)
        return row

    # 资金流水（cash）
    event_date = parse_date(_cell(cells, mapping, "event_date"))
    if event_date is None:
        row.update(status="error", reason="缺少或无法解析发生日期")
        return row
    type_raw = _cell(cells, mapping, "event_type")
    event_type = _value_map(profile, "event_type", override).get(type_raw or "")
    if event_type is None:
        row.update(status="error", reason=f"无法识别的业务名称：{type_raw or '（空）'}（可在映射中补充）")
        return row
    if event_type == "ignore":
        row.update(status="ok", target="ignore", reason=IGNORE_REASON, trade_date=event_date)
        return row
    amount = _number_cell(cells, mapping, "amount")
    if amount is None or amount == 0:
        row.update(status="error", reason="缺少发生金额或金额为 0")
        return row

    code_raw = _cell(cells, mapping, "asset_code")
    asset_type = None
    code = None
    if code_raw:
        asset_type = infer_asset_type(db, code_raw.strip(), "auto")
        code = asset_service.normalize_asset_code(code_raw.strip(), asset_type)
    parsed = {
        "event_date": event_date,
        "event_type": event_type,
        "amount": amount,
        "asset_type": asset_type,
        "asset_code": code,
        "asset_name": _cell(cells, mapping, "asset_name"),
        "broker_ref": _cell(cells, mapping, "broker_ref"),
        "note": _cell(cells, mapping, "note"),
    }
    row.update(status="ok", target="cash", parsed=parsed, warnings=[])
    return row


# ------------------------------------------------------------------ 去重


def _content_key(row: dict) -> str:
    parsed = row["parsed"]
    if row["target"] == "trade":
        parts = [
            parsed["trade_date"].isoformat(),
            parsed["asset_type"],
            parsed["asset_code"],
            parsed["trade_type"],
            f"{parsed['price'] or 0:.6f}",
            f"{parsed['quantity'] or 0:.4f}",
            f"{parsed['amount']:.4f}",
            f"{parsed['fee']:.4f}",
        ]
    else:
        parts = [
            parsed["event_date"].isoformat(),
            parsed["event_type"],
            f"{parsed['amount']:.4f}",
            parsed["asset_code"] or "",
        ]
    return "|".join(parts)


def content_ref(key: str, occurrence: int) -> str:
    digest = hashlib.sha256(f"{key}|{occurrence}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def assign_refs(rows: list[dict]) -> None:
    """按最终值重算每行的 external_ref（券商编号优先，否则内容哈希 + 出现序号）。"""
    occurrences: dict[str, int] = {}
    for row in rows:
        if row.get("target") == "ignore" or "parsed" not in row:
            continue
        broker_ref = (row["parsed"].get("broker_ref") or "").strip()[:120]
        if broker_ref:
            row["external_ref"] = broker_ref
            continue
        key = _content_key(row)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        row["external_ref"] = content_ref(key, occurrence)


def _existing_transaction_refs(db: Session, refs: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(refs), 500):
        chunk = refs[start : start + 500]
        found.update(
            db.scalars(
                select(PortfolioTransaction.external_ref).where(PortfolioTransaction.external_ref.in_(chunk))
            )
        )
    return found


def _existing_cash_refs(db: Session, refs: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(refs), 500):
        chunk = refs[start : start + 500]
        found.update(
            db.scalars(select(PortfolioCashEvent.external_ref).where(PortfolioCashEvent.external_ref.in_(chunk)))
        )
    return found


def classify_rows(db: Session, rows: list[dict]) -> None:
    """标注 ok/duplicate/suspect（重复判定：引用已存在；无编号且疑似已入账）。"""
    assign_refs(rows)
    refs = [row["external_ref"] for row in rows if row.get("target") in {"trade", "cash"}]
    existing_tx = _existing_transaction_refs(db, refs)
    existing_cash = _existing_cash_refs(db, refs)
    seen_in_file: set[str] = set()
    for row in rows:
        if row.get("status") == "error":
            continue
        ref = row.get("external_ref")
        if ref is None:
            continue
        if ref in existing_tx or ref in existing_cash:
            row["status"] = "duplicate"
            row["reason"] = "已存在相同引用，跳过"
            continue
        if ref in seen_in_file:
            row["status"] = "duplicate"
            row["reason"] = "文件内外部编号重复"
            continue
        seen_in_file.add(ref)
        if row["external_ref"].startswith("sha256:") and _looks_like_existing(db, row):
            row["status"] = "suspect"
            row["reason"] = "与已有流水内容相同，但缺少外部编号，无法确认重复"
        else:
            row["status"] = "ok"


def _looks_like_existing(db: Session, row: dict) -> bool:
    parsed = row["parsed"]
    if row["target"] == "trade":
        found = db.scalar(
            select(PortfolioTransaction.id)
            .where(
                PortfolioTransaction.trade_date == parsed["trade_date"],
                PortfolioTransaction.asset_code == parsed["asset_code"],
                PortfolioTransaction.trade_type == parsed["trade_type"],
                PortfolioTransaction.amount == parsed["amount"],
            )
            .limit(1)
        )
    else:
        found = db.scalar(
            select(PortfolioCashEvent.id)
            .where(
                PortfolioCashEvent.event_date == parsed["event_date"],
                PortfolioCashEvent.event_type == parsed["event_type"],
                PortfolioCashEvent.amount == parsed["amount"],
            )
            .limit(1)
        )
    return found is not None


# ------------------------------------------------------------------ 只读重放模拟


def _load_asset_transactions(db: Session) -> dict[tuple[str, str], list[PortfolioTransaction]]:
    grouped: dict[tuple[str, str], list[PortfolioTransaction]] = {}
    for transaction in db.scalars(
        select(PortfolioTransaction).order_by(
            PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc()
        )
    ):
        key = (
            transaction.asset_type or "fund",
            transaction.asset_code or transaction.fund_code,
        )
        grouped.setdefault(key, []).append(transaction)
    return grouped


def simulate_ledger_rows(db: Session, rows: list[dict]) -> None:
    """对将入账的交易行做只读重放；会卖超的行标为 error（提交前就暴露）。"""
    existing = _load_asset_transactions(db)
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row.get("status") != "ok" or row.get("target") != "trade":
            continue
        parsed = row["parsed"]
        groups.setdefault((parsed["asset_type"], parsed["asset_code"]), []).append(row)

    for key, group in groups.items():
        events: list[tuple] = [(t.trade_date, 0, t.id, t) for t in existing.get(key, [])]
        for row in group:
            parsed = row["parsed"]
            share = parsed["quantity"] if parsed["quantity"] is not None else (
                parsed["amount"] / parsed["price"] if parsed["price"] else Decimal("0")
            )
            event = SimpleNamespace(
                trade_type=parsed["trade_type"],
                share=share,
                amount=parsed["amount"],
                fee=parsed["fee"],
                trade_date=parsed["trade_date"],
            )
            events.append((parsed["trade_date"], 1, row["row_index"], event))
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        try:
            portfolio_service.replay_ledger_events([item[3] for item in events])
        except ValueError as exc:
            # 定位真正触发问题的新行：逐行增量重放
            sequence: list = [(item[3]) for item in events if item[1] == 0]
            for item in [entry for entry in events if entry[1] == 1]:
                sequence.append(item[3])
                try:
                    portfolio_service.replay_ledger_events(sequence)
                except ValueError as inner:
                    for row in group:
                        if row["row_index"] == item[2]:
                            row["status"] = "error"
                            row["reason"] = str(inner)
                    break
            else:
                for row in group:
                    if row.get("status") == "ok":
                        row["status"] = "error"
                        row["reason"] = str(exc)
                    break


# ------------------------------------------------------------------ 预览与提交


def _counts(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "importable": sum(1 for row in rows if row.get("status") in {"ok", "suspect"} and row.get("target") in {"trade", "cash"}),
        "duplicate": sum(1 for row in rows if row.get("status") == "duplicate"),
        "suspect": sum(1 for row in rows if row.get("status") == "suspect"),
        "ignored": sum(1 for row in rows if row.get("target") == "ignore"),
        "error": sum(1 for row in rows if row.get("status") == "error"),
    }


def _existing_manual_positions(db: Session, rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("target") != "trade" or "parsed" not in row:
            continue
        parsed = row["parsed"]
        key = (parsed["asset_type"], parsed["asset_code"])
        if key in seen:
            continue
        seen.add(key)
        position = db.scalar(
            select(portfolio_service.PortfolioPosition).where(
                *portfolio_service._position_criteria(*key)
            )
        )
        if position is None:
            continue
        has_transactions = db.scalar(
            select(PortfolioTransaction.id)
            .where(*portfolio_service._transaction_criteria(*key))
            .limit(1)
        )
        if has_transactions is None and Decimal(position.holding_share or 0) > 0:
            if portfolio_service.opening_values(position) is None:
                warnings.append(
                    f"{parsed['asset_code']} 的手工持仓缺少成本信息，导入会失败；请先补全成本或删除该持仓"
                )
            else:
                warnings.append(
                    f"{parsed['asset_code']} 已有手工/截图持仓 {position.holding_share} 份，"
                    "导入的成交会在其基础上累加；若截图已包含这些成交，请先删除该持仓再导入"
                )
    return warnings


def preview_import(
    db: Session,
    *,
    file_name: str,
    content: bytes,
    source_kind: str | None = None,
    mapping_override: dict | None = None,
    header_row: int | None = None,
    default_asset_type: str = "auto",
) -> dict:
    rows_raw, encoding, delimiter = read_csv_rows(content)
    if header_row is not None and 0 <= header_row < len(rows_raw):
        detection = {"header_row": header_row, "profile": None, "columns": {}, "score": 0}
        header_cells = [normalize_header(cell) for cell in rows_raw[header_row]]
        for profile in _profile_candidates(source_kind):
            mapping = _match_columns(header_cells, profile)
            if len(mapping) > detection["score"]:
                detection = {
                    "header_row": header_row,
                    "profile": profile,
                    "columns": mapping,
                    "score": len(mapping),
                    "source_kind": profile["source_kind"],
                    "label": profile["label"],
                    "kind": profile["kind"],
                }
    else:
        detection = detect_structure(rows_raw, source_kind)

    if detection["profile"] is not None:
        header = [normalize_header(cell) for cell in rows_raw[detection["header_row"]]]
        detection = apply_mapping_override(detection, header, mapping_override)

    file_hash = hashlib.sha256(content).hexdigest()
    parsed_rows: list[dict] = []
    data_start = (detection["header_row"] + 1) if detection["header_row"] is not None else 0
    for index in range(data_start, len(rows_raw)):
        parsed_rows.append(
            build_row(db, rows_raw[index], detection, index, default_asset_type, mapping_override)
        )

    if detection["profile"] is not None:
        classify_rows(db, parsed_rows)
        simulate_ledger_rows(db, parsed_rows)

    counts = _counts(parsed_rows)
    warnings = _existing_manual_positions(db, parsed_rows)
    previous = db.scalar(
        select(PortfolioImportBatch)
        .where(PortfolioImportBatch.file_hash == file_hash, PortfolioImportBatch.status != "failed")
        .order_by(PortfolioImportBatch.id.desc())
        .limit(1)
    )
    if previous is not None:
        warnings.insert(0, f"该文件此前已导入过（批次 #{previous.id}），重复行将自动跳过")

    error_notes = [
        {"row_index": row["row_index"], "reason": row.get("reason")}
        for row in parsed_rows
        if row.get("status") == "error"
    ][:MAX_ERRORS_STORED]

    batch = PortfolioImportBatch(
        source_kind=(detection.get("source_kind") or source_kind or "unknown"),
        file_name=file_name,
        file_hash=file_hash,
        status="previewed",
        mapping_json={
            "columns": detection.get("column_headers") or {},
            "header_row": detection.get("header_row"),
            "profile": detection.get("source_kind"),
        },
        total_count=counts["total"],
        duplicate_count=counts["duplicate"],
        error_count=counts["error"],
        notes_json={"warnings": warnings, "errors": error_notes, "encoding": encoding, "delimiter": delimiter},
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    return {
        "batch_id": batch.id,
        "file_name": file_name,
        "file_hash": file_hash,
        "encoding": encoding,
        "delimiter": delimiter,
        "detected": {
            "source_kind": detection.get("source_kind"),
            "label": detection.get("label"),
            "kind": detection.get("kind"),
            "header_row": detection.get("header_row"),
            "columns": detection.get("column_headers") or {},
        },
        "counts": counts,
        "warnings": warnings,
        "rows": parsed_rows,
    }


def _normalize_commit_row(row: dict) -> dict:
    """提交入口的类型归一化：HTTP 往返后日期是字符串、数字可能是浮点。"""
    parsed = dict(row.get("parsed") or {})
    for key in ("trade_date", "event_date"):
        if isinstance(parsed.get(key), str):
            parsed[key] = parse_date(parsed[key])
    for key in ("amount", "price", "quantity", "fee"):
        if parsed.get(key) is not None and not isinstance(parsed[key], Decimal):
            parsed[key] = parse_decimal(str(parsed[key]))
    normalized = dict(row)
    normalized["parsed"] = parsed
    return normalized


def _validate_commit_rows(db: Session, rows: list[dict]) -> list[dict]:
    validated: list[dict] = []
    for raw_row in rows:
        row = _normalize_commit_row(raw_row)
        target = row.get("target")
        if target not in {"trade", "cash"}:
            continue
        parsed = dict(row.get("parsed") or {})
        if target == "trade":
            if parsed.get("trade_type") not in portfolio_service.ALL_TRADE_TYPES:
                raise ValueError(f"第 {row.get('row_index')} 行：未知交易类型 {parsed.get('trade_type')}")
            if parsed.get("trade_date") is None or not parsed.get("asset_code"):
                raise ValueError(f"第 {row.get('row_index')} 行：缺少日期或代码")
        else:
            if parsed.get("event_type") not in account_service.CASH_EVENT_TYPES:
                raise ValueError(f"第 {row.get('row_index')} 行：未知现金事件类型 {parsed.get('event_type')}")
            if parsed.get("event_date") is None:
                raise ValueError(f"第 {row.get('row_index')} 行：缺少日期")
        row["parsed"] = parsed
        validated.append(row)
    return validated


def commit_import(db: Session, *, batch_id: int, rows: list[dict]) -> dict:
    batch = db.get(PortfolioImportBatch, batch_id)
    if batch is None:
        raise ValueError("导入批次不存在")
    if batch.status == "committed":
        raise ValueError("该批次已入账；如需修正请删除对应流水后重新导入")

    try:
        accepted = _validate_commit_rows(db, rows)
        for row in accepted:
            row["_was_suspect"] = row.get("status") == "suspect"
            if row.get("status") in {None, "ok", "suspect"}:
                row["status"] = "ok"
        assign_refs(accepted)
        simulate_ledger_rows(db, accepted)
        broken = [row for row in accepted if row.get("status") == "error"]
        if broken:
            raise ValueError(f"第 {broken[0]['row_index']} 行无法入账：{broken[0].get('reason')}")
        existing_tx = _existing_transaction_refs(db, [row["external_ref"] for row in accepted if row.get("target") == "trade"])
        existing_cash = _existing_cash_refs(db, [row["external_ref"] for row in accepted if row.get("target") == "cash"])
        seen: set[str] = set()

        inserted = 0
        duplicates = 0
        forced = 0
        affected: set[tuple[str, str]] = set()
        for row in accepted:
            target = row["target"]
            parsed = row["parsed"]
            ref = row["external_ref"]
            if row.get("_was_suspect") and not row.get("force_import"):
                # 疑似重复（无外部编号但库中已有同内容流水）：默认跳过，勾选强制导入才入账
                duplicates += 1
                continue
            if ref in existing_tx or ref in existing_cash or ref in seen:
                if not row.get("force_import"):
                    duplicates += 1
                    continue
                forced += 1
                ref = f"{ref}#force{batch.id}-{forced}"
                row["external_ref"] = ref
            seen.add(ref)
            if target == "trade":
                asset_type = parsed["asset_type"]
                asset_code = parsed["asset_code"]
                affected.add((asset_type, asset_code))
                row["_insert"] = ("trade", asset_type, asset_code, ref)
            else:
                row["_insert"] = ("cash", ref)

        # 受影响资产：锁 + 期初物化（缺成本会在此报错并整批回滚）
        for asset_type, asset_code in sorted(affected):
            portfolio_service._ensure_listed_asset(db, asset_type, asset_code)
            position = portfolio_service._position_row(db, asset_type, asset_code, for_update=True)
            portfolio_service.ensure_opening_transaction(db, position)

        for row in sorted(
            (item for item in accepted if item.get("_insert")),
            key=lambda item: (
                item["parsed"].get("trade_date") or item["parsed"].get("event_date"),
                item["row_index"],
            ),
        ):
            target = row["_insert"][0]
            parsed = row["parsed"]
            if target == "trade":
                _, asset_type, asset_code, ref = row["_insert"]
                share = parsed.get("quantity")
                if share is None:
                    share = parsed["amount"] / parsed["price"] if parsed.get("price") else Decimal("0")
                db.add(
                    PortfolioTransaction(
                        fund_code=asset_code,
                        asset_type=asset_type,
                        asset_code=asset_code,
                        trade_date=parsed["trade_date"],
                        trade_type=parsed["trade_type"],
                        amount=portfolio_service._quantize(Decimal(parsed["amount"]), "0.0001"),
                        nav=portfolio_service._quantize(Decimal(parsed["price"] or 1), "0.000001"),
                        share=portfolio_service._quantize(Decimal(share), "0.0001"),
                        fee=portfolio_service._quantize(Decimal(parsed["fee"] or 0), "0.0001"),
                        note=parsed.get("note"),
                        external_ref=ref,
                        source=batch.source_kind,
                        import_batch_id=batch.id,
                    )
                )
            else:
                values = account_service.normalize_cash_event(
                    db,
                    {
                        "event_date": parsed["event_date"],
                        "event_type": parsed["event_type"],
                        "amount": parsed["amount"],
                        "asset_type": parsed.get("asset_type"),
                        "asset_code": parsed.get("asset_code"),
                        "note": parsed.get("note"),
                        "source": batch.source_kind,
                        "external_ref": row["_insert"][1],
                        "import_batch_id": batch.id,
                    },
                )
                db.add(PortfolioCashEvent(**values))
            inserted += 1

        db.flush()
        for asset_type, asset_code in sorted(affected):
            portfolio_service._rebuild_position_from_transactions(db, asset_type, asset_code)

        skipped = batch.total_count - inserted - duplicates - batch.error_count
        skipped = max(skipped, 0)
        batch.imported_count = inserted
        batch.duplicate_count = duplicates
        batch.skipped_count = skipped
        batch.status = "partial" if (inserted and (duplicates or skipped)) else "committed"
        batch.committed_at = datetime.now()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _mark_batch_failed(db, batch_id, f"重复数据冲突：{exc.orig}")
        raise ValueError(f"重复数据冲突：{exc.orig}") from exc
    except Exception as exc:
        db.rollback()
        _mark_batch_failed(db, batch_id, str(exc))
        raise

    effects = []
    for asset_type, asset_code in sorted(affected):
        positions = portfolio_service.list_positions(db)
        position = next(
            (item for item in positions if portfolio_service._identity(item) == (asset_type, asset_code)),
            None,
        )
        if position is None:
            continue
        realized = db.scalar(
            select(func.coalesce(func.sum(PortfolioTransaction.realized_pnl), 0)).where(
                *portfolio_service._transaction_criteria(asset_type, asset_code)
            )
        )
        effects.append(
            {
                "asset_type": asset_type,
                "asset_code": asset_code,
                "holding_share": position.holding_share,
                "holding_amount": position.holding_amount,
                "cost_nav": position.cost_nav,
                "realized_pnl_total": realized or Decimal("0"),
            }
        )

    return {
        "batch_id": batch_id,
        "status": batch.status,
        "counts": {
            "imported": inserted,
            "duplicate": duplicates,
            "skipped": batch.skipped_count,
            "error": batch.error_count,
        },
        "position_effects": effects,
    }


def _mark_batch_failed(db: Session, batch_id: int, reason: str) -> None:
    """失败留痕：主事务已回滚，用同一会话补写批次状态（不新开连接，测试内存库也适用）。"""
    try:
        batch = db.get(PortfolioImportBatch, batch_id)
        if batch is None:
            return
        batch.status = "failed"
        notes = dict(batch.notes_json or {})
        notes["failure_reason"] = reason[:500]
        batch.notes_json = notes
        db.commit()
    except Exception:  # noqa: BLE001 - 留痕失败不能再掩盖原始异常
        db.rollback()
