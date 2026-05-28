# Egencia 报账助手 - 飞书机器人
# 配置文件

import os

# ============ 飞书应用配置（从环境变量读取）============
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 飞书多维表格配置
FEISHU_BITABLE_TOKEN = os.getenv("FEISHU_BITABLE_TOKEN", "")  # 多维表格 app_token
FEISHU_TABLE_ID = os.getenv("FEISHU_TABLE_ID", "")            # 数据表 table_id

# Webhook 配置
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "egencia_bot_verify")
WEBHOOK_ENCRYPT_KEY = os.getenv("WEBHOOK_ENCRYPT_KEY", "")    # 可选，留空则不加密

# ============ 多维表格字段定义（与飞书表字段名一致）============
FIELDS = {
    # A · 核心标识
    "bill_no":           {"title": "账单编号",  "type": "text"},
    "employee_name":     {"title": "报销人姓名", "type": "text"},
    "receipt_date":      {"title": "账单日期",   "type": "date"},

    # B · 行程信息
    "ticket_type":       {"title": "票据类型",   "type": "single_select",
                          "options": ["机票", "酒店", "费用单"]},
    "trip_start_date":   {"title": "出行日期",   "type": "date"},
    "trip_end_date":     {"title": "结束日期",   "type": "date"},
    "origin":            {"title": "出发地/城市","type": "text"},
    "destination":       {"title": "目的地/城市","type": "text"},
    "vendor":            {"title": "供应商/航司","type": "text"},
    "flight_train_no":   {"title": "航班/车次号","type": "text"},

    # C · 费用信息
    "base_fare":         {"title": "票面金额",   "type": "number"},
    "taxes_fees":        {"title": "税费附加费", "type": "number"},
    "total_amount":      {"title": "实收总金额", "type": "number"},
    "currency":          {"title": "货币",       "type": "single_select",
                          "options": ["USD", "CNY", "EUR", "HKD"]},
    "payment_method":    {"title": "支付方式",   "type": "text"},

    # D · 系统字段
    "import_time":       {"title": "导入时间",   "type": "datetime"},
    "original_filename": {"title": "原始文件名", "type": "text"},
    "remark":            {"title": "备注",       "type": "text"},
}

# 字段标题列表（按顺序）
FIELD_ORDER = [
    "账单编号", "报销人姓名", "账单日期",
    "票据类型", "出行日期", "结束日期", "出发地/城市", "目的地/城市", "供应商/航司", "航班/车次号",
    "票面金额", "税费附加费", "实收总金额", "货币", "支付方式",
    "导入时间", "原始文件名", "备注",
]

# 票据类型关键词映射
RECEIPT_TYPE_MAP = {
    "Flight Receipt": "机票",
    "Hotel Receipt":  "酒店",
    "Fee Receipt":    "费用单",
}

# 去重键
DEDUP_FIELD = "账单编号"
