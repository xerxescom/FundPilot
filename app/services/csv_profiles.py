"""CSV 导入画像：字段映射是数据不是代码。

每个画像给出：规范字段 → 候选表头（按优先级）、业务名称/交易类别 → 目标语义的值映射、
默认值。没有真实样例时先按公开结构内置，用户在预览界面改列映射即可校准，
不需要改代码。

映射结构（可传入 mapping_override 覆盖）：
    {"columns": {canonical: "表头原文"}, "value_maps": {canonical: {原文: 规范值}}}
"""

from __future__ import annotations

CANONICAL_TRADE_FIELDS = (
    "trade_date",
    "asset_code",
    "asset_name",
    "trade_type",
    "price",
    "quantity",
    "amount",
    "fee",
    "net_amount",
    "broker_ref",
    "note",
)
CANONICAL_CASH_FIELDS = (
    "event_date",
    "event_type",
    "amount",
    "asset_code",
    "asset_name",
    "broker_ref",
    "note",
)

# 目标语义：trade → trade_type 为方向；cash → event_type；ignore → 跳过（原因）
CITIC_DELIVERY_PROFILE = {
    "source_kind": "citic_delivery",
    "label": "中信证券成交明细",
    "kind": "trades",
    "header_candidates": {
        "trade_date": ["成交日期", "交易日期", "发生日期", "清算日期", "委托日期", "日期"],
        "asset_code": ["证券代码", "证券编码", "股票代码", "基金代码", "代码"],
        "asset_name": ["证券名称", "证券简称", "股票名称", "基金名称", "名称"],
        "trade_type": ["业务名称", "交易类别", "业务类别", "交易类型", "操作", "摘要"],
        "price": ["成交价格", "成交均价", "成交价", "委托价格", "价格", "净值"],
        "quantity": ["成交数量", "成交股数", "成交份额", "确认份额", "数量"],
        "amount": ["成交金额", "成交额", "确认金额", "金额"],
        "fee": ["手续费", "佣金", "印花税", "过户费", "其他费", "交易费用"],
        "net_amount": ["本次金额", "净收付金额", "收付金额", "发生金额", "发生额", "资金发生额"],
        "broker_ref": ["成交编号", "委托编号", "合同编号", "业务流水号", "流水号", "委托序号"],
        "note": ["备注", "摘要说明"],
    },
    "value_maps": {
        "trade_type": {
            "证券买入": "buy",
            "买入": "buy",
            "基金申购": "subscription",
            "申购": "subscription",
            "证券卖出": "sell",
            "卖出": "sell",
            "基金赎回": "redemption",
            "赎回": "redemption",
            "红利再投": "dividend_reinvest",
            "红利转投": "dividend_reinvest",
            "基金拆分": "split",
            "份额折算": "split",
            "送股": "split",
            "转增": "split",
        }
    },
    # 成交文件几乎必然出现价格/数量；缺失时强力降权，避免抢占资金流水文件的表头
    "required_any": ("price", "quantity"),
    "defaults": {"asset_type": None, "fee": "0"},
}

CITIC_STATEMENT_PROFILE = {
    "source_kind": "citic_statement",
    "label": "中信证券资金流水",
    "kind": "cash",
    "header_candidates": {
        "event_date": ["发生日期", "交易日期", "日期", "记账日期"],
        "event_type": ["业务名称", "摘要", "交易类别", "业务类别"],
        "amount": ["发生金额", "发生额", "本次金额", "金额", "收付金额"],
        "asset_code": ["证券代码", "代码"],
        "asset_name": ["证券名称", "名称"],
        "broker_ref": ["业务流水号", "流水号", "委托编号", "凭证号", "合同编号"],
        "note": ["备注", "说明"],
    },
    "value_maps": {
        "event_type": {
            "银行转入": "deposit",
            "银证转入": "deposit",
            "银行转证券": "deposit",
            "银行转出": "withdraw",
            "银证转出": "withdraw",
            "证券转银行": "withdraw",
            "利息归本": "interest",
            "股息入账": "dividend",
            "红利入账": "dividend",
            "基金分红": "dividend",
            "手续费": "fee",
            "交易手续费": "fee",
            # 成交行默认忽略：成交金额由成交明细文件导入，避免与交易资金流重复
            "证券买入": "ignore",
            "买入": "ignore",
            "证券卖出": "ignore",
            "卖出": "ignore",
            "基金申购": "ignore",
            "申购": "ignore",
            "基金赎回": "ignore",
            "赎回": "ignore",
        }
    },
    "defaults": {"asset_type": None},
}

PROFILES = {
    CITIC_DELIVERY_PROFILE["source_kind"]: CITIC_DELIVERY_PROFILE,
    CITIC_STATEMENT_PROFILE["source_kind"]: CITIC_STATEMENT_PROFILE,
}

IGNORE_REASON = "按画像默认忽略（避免与成交明细重复）；可在映射中改为导入"
