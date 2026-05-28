# Egencia PDF 账单解析器
# 支持 Flight / Hotel / Fee 三种票据类型

import re
import os
import pdfplumber
from datetime import datetime


def extract_text(pdf_path):
    """提取 PDF 全部文本内容"""
    pdf = pdfplumber.open(pdf_path)
    text = ""
    for page in pdf.pages:
        t = page.extract_text()
        if t:
            text += "\n" + t
    pdf.close()
    return text.strip()


def _parse_money(s):
    """
    从金额字符串中解析数字。
    输入: "$418.17" 或 "418.17"
    输出: 418.17 (float) 或 None
    """
    if not s:
        return None
    m = re.search(r"[\$]?\s*([\d,]+\.?\d*)", s.replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _parse_date(s):
    """
    解析常见日期格式。
    支持: "Jan 28, 2026", "02/08/2026", "2026-01-28" 等
    返回 YYYY-MM-DD 格式字符串，或 None
    """
    if not s:
        return None

    formats = [
        "%b %d, %Y",      # Jan 28, 2026
        "%m/%d/%Y",       # 02/08/2026
        "%Y-%m-%d",       # 2026-01-28
        "%B %d, %Y",      # January 28, 2026
    ]

    s = s.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 尝试从文本中提取日期
    date_patterns = [
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s*(\d{4})",
        r"(\d{2})/(\d{2})/(\d{4})",
        r"(Departure date|Check in|Check out|Transaction date|Purchase date)\s*[-–—]\s*(.+)",
    ]
    for pat in date_patterns:
        m = re.search(pat, s)
        if m:
            if pat == date_patterns[0]:
                month_map = {
                    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                }
                return f"{m.group(3)}-{month_map[m.group(1)]}-{int(m.group(2)):02d}"
            elif pat == date_patterns[1]:
                return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
            elif pat == date_patterns[2]:
                return _parse_date(m.group(2).strip())
    return None


def _detect_receipt_type(text):
    """检测票据类型"""
    if "Flight Receipt" in text:
        return "机票", "Flight Receipt"
    elif "Hotel Receipt" in text:
        return "酒店", "Hotel Receipt"
    elif "Fee Receipt" in text:
        return "费用单", "Fee Receipt"
    else:
        return "其他", ""


def parse_flight(text):
    """解析机票收据"""
    data = {}

    # 行程路线和航司航班
    # 例: LAX-MCO (One Way) (Purchase)
    route_match = re.search(
        r"([A-Z]{3}-[A-Z]{3}|[A-Z]{3}\s*[–\-]\s*[A-Z]{3})\s*\(([^)]+)\)",
        text,
    )
    if route_match:
        route = route_match.group(1)
        parts = re.split(r"[–\-\s]+", route)
        if len(parts) >= 2:
            data["origin"] = parts[0].strip()
            data["destination"] = parts[-1].strip()

    # 例: Delta 867 , Departure date - Jan 28, 2026
    flight_match = re.search(
        r"([A-Za-z\s&]+?)\s+(\d{3,4})\s*,?\s*Departure date\s*[-–—]\s*(.+?)(?:\n|$)",
        text,
    )
    if flight_match:
        data["vendor"] = flight_match.group(1).strip().title()
        data["flight_train_no"] = flight_match.group(2).strip()
        data["trip_start_date"] = _parse_date(flight_match.group(3))

    # 票号
    ticket_match = re.search(r"Ticket\s+(\d+)", text)
    if ticket_match:
        data["ticket_no"] = ticket_match.group(1)

    # 购票日期
    purchase_match = re.search(r"Purchase date\s*[-–—]\s*(.+?)(?:\n|$)", text)
    if purchase_match:
        data["purchase_date"] = _parse_date(purchase_match.group(1))

    # 金额部分
    base_fare_m = re.search(r"Base fare\s+\$?([\d,.]+)", text)
    taxes_m = re.search(r"Taxes & airline fees\s+\$?([\d,.]+)", text)
    total_m = re.search(r"(?<!TOTAL\s)TOTAL\s+\$?([\d,.]+)", text)

    data["base_fare"] = _parse_money(base_fare_m.group(1)) if base_fare_m else None
    data["taxes_fees"] = _parse_money(taxes_m.group(1)) if taxes_m else None
    data["total_amount"] = _parse_money(total_m.group(1)) if total_m else None

    # 总费用（含预订费）
    total_charges_m = re.search(r"TOTAL FLIGHT CHARGES\s+\$?([\d,.]+)", text)
    if total_charges_m:
        data["total_charges"] = _parse_money(total_charges_m.group(1))

    # 预订费
    fee_m = re.search(r"Air booking fee\s+\$?([\d,.]+)", text)
    data["booking_fee"] = _parse_money(fee_m.group(1)) if fee_m else None

    return data


def parse_hotel(text):
    """解析酒店收据"""
    data = {}

    # 酒店名：在 Hotel Receipt 之后，(Purchase) 之前的那行文本
    # 文本格式: Hotel Receipt [图标] \n HOTEL NAME \n (Purchase)
    hotel_match = re.search(
        r"Hotel Receipt\s*\n\s*(.+?)\s*\n\s*\(Purchase\)",
        text,
    )
    if hotel_match:
        data["vendor"] = hotel_match.group(1).strip()

    # 入退房日期
    checkin_m = re.search(r"Check in:\s*(.+?)\s+Check out:\s*(.+?)(?:\n|$)", text)
    if checkin_m:
        data["trip_start_date"] = _parse_date(checkin_m.group(1))
        data["trip_end_date"] = _parse_date(checkin_m.group(2))

    # 地址（(Purchase) 下一行），从中提取城市
    addr_match = re.search(r"\((?:Purchase)\)\s*\n(.+)", text)
    if addr_match:
        addr = addr_match.group(1).strip()
        # 格式: "623 Camp Jordan Parkway , Chattanooga, TN, 37412"
        # 分割后: [street, city, state,zip] — 取倒数第三段为城市
        parts = [p.strip() for p in addr.split(",")]
        if len(parts) >= 3:
            data["destination"] = parts[-3]  # 城市名
            data["origin"] = parts[-3]
        elif len(parts) >= 2:
            data["destination"] = parts[0]  # 回退到第一段
            data["origin"] = parts[0]

    # 清理酒店名：去掉开头的非字母字符（PDF图标残留）
    if "vendor" in data and data["vendor"]:
        cleaned = re.sub(r"^[^A-Za-z]+", "", data["vendor"])
        if cleaned:
            data["vendor"] = cleaned

    # 交易日期
    txn_date_m = re.search(r"Transaction date\s*[-–—]\s*(.+?)(?:\n|$)", text)
    if txn_date_m:
        data["transaction_date"] = _parse_date(txn_date_m.group(1))

    # 每日房价（多行）
    daily_rates = re.findall(r"(\d{2}/\d{2}/\d{4})\s+\$?([\d,.]+)", text)
    if daily_rates:
        data["daily_rates"] = [
            {"date": d, "amount": float(a)} for d, a in daily_rates
        ]
        nights_count = len(daily_rates)

    # 金额
    taxes_m = re.search(r"Taxes and service fees\s+\$?([\d,.]+)", text)
    total_m = re.search(r"(?<!TOTAL\s)TOTAL\s+\$?([\d,.]+)", text)

    data["taxes_fees"] = _parse_money(taxes_m.group(1)) if taxes_m else None
    data["total_amount"] = _parse_money(total_m.group(1)) if total_m else None

    # 总费用（含预订费）
    total_charges_m = re.search(r"TOTAL HOTEL CHARGES\s+\$?([\d,.]+)", text)
    if total_charges_m:
        data["total_charges"] = _parse_money(total_charges_m.group(1))

    # 预订费
    fee_m = re.search(r"Hotel reservation fee online\s+\$?([\d,.]+)", text)
    data["booking_fee"] = _parse_money(fee_m.group(1)) if fee_m else None

    return data


def _parse_city_from_dates(date_str, text):
    """尝试从文本中提取城市信息"""
    # 通常在地址行中包含城市
    addr_match = re.search(r"\((?:Purchase)\)\s*\n(.+)", text)
    if addr_match:
        line = addr_match.group(1)
        city_parts = line.split(",")
        if len(city_parts) >= 1:
            return city_parts[0].strip()
    return None


def parse_fee(text):
    """解析费用单收据"""
    data = {}

    # 购买日期
    purchase_m = re.search(r"Purchase date\s*[-–—]\s*(.+?)(?:\n|$)", text)
    if purchase_m:
        data["purchase_date"] = _parse_date(purchase_m.group(1))

    # 费用类型和金额
    fee_line_m = re.search(r"^([\w\s]+fee[\w\s]*)\$?([\d,.]+)$", text, re.MULTILINE | re.IGNORECASE)
    if fee_line_m:
        data["fee_type"] = fee_line_m.group(1).strip()
        data["base_fare"] = _parse_money(fee_line_m.group(2))

    # 总费用
    total_m = re.search(r"TOTAL FEES CHARGED\s+\$?([\d,.]+)", text)
    if total_m:
        data["total_amount"] = _parse_money(total_m.group(1))

    return data


def parse_common(text):
    """解析所有票据共有的字段"""
    common = {}

    # 行程号（去重主键）
    itin_m = re.search(r"Itinerary\s+(\d+)", text)
    if itin_m:
        common["bill_no"] = itin_m.group(1)

    # 报销人姓名：优先匹配 "Itinerary XXXXX Name" 格式（机票/酒店）
    # 费用单格式特殊，名字在文件末尾，单独处理
    name_m = re.search(
        r"Itinerary\s+\d+\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+|[A-Z]{2,}(?:,\s*[A-Z]+)*)",
        text,
    )
    if not name_m:
        # 尝试匹配中文姓名或全大写英文姓名
        name_m = re.search(
            r"Itinerary\s+\d+\s+([\u4e00-\u9fff]+|[A-Z]+(?:\s+[A-Z]+)+)",
            text,
        )
    if name_m:
        common["employee_name"] = name_m.group(1).strip()
    else:
        # 费用单：名字在文本末尾附近（公司名之前）
        # 例: "\nYating Zhang\nGoFo Inc"
        alt_name_m = re.search(r"\n([A-Z][a-z]+\s+[A-Z][a-z]+)\n[A-Za-z]+ Inc", text)
        if alt_name_m:
            common["employee_name"] = alt_name_m.group(1).strip()

    # 公司名
    if "GoFo Inc" in text or "Gofo" in text:
        common["company"] = "GoFo Inc"

    # 部门
    dept_m = re.search(r"Department\s+([A-Za-z0-9]+)", text)
    if dept_m:
        common["department"] = dept_m.group(1)

    # 支付方式
    payment_m = re.search(
        r"Central Bill:\s*(MasterCard|Visa|AMEX)\s+Ending In\s+(\d{4})", text
    )
    if payment_m:
        card_type = payment_m.group(1)
        card_last4 = payment_m.group(2)
        common["payment_method"] = f"{card_type} ****{card_last4}"
    else:
        payment_alt_m = re.search(
            r"(MasterCard|Visa|AMEX)\s+Ending In\s+(\d{4})", text
        )
        if payment_alt_m:
            card_type = payment_alt_m.group(1)
            card_last4 = payment_alt_m.group(2)
            common["payment_method"] = f"{card_type} ****{card_last4}"

    # 货币（根据金额符号判断）
    if "$" in text:
        common["currency"] = "USD"
    elif "¥" in text or "CNY" in text.upper():
        common["currency"] = "CNY"

    return common


def parse_egencia_pdf(pdf_path, filename=None):
    """
    解析 Egencia PDF 账单的主入口。

    Args:
        pdf_path: PDF 文件路径
        filename: 原始文件名（用于记录）

    Returns:
        dict: 统一结构的解析结果字典，包含所有多维表格字段
    """
    text = extract_text(pdf_path)

    if not text:
        return {
            "success": False,
            "error": "无法提取 PDF 文本内容（可能是扫描件）",
            "raw_text": "",
        }

    # 检测票据类型
    ticket_type_cn, ticket_type_en = _detect_receipt_type(text)

    # 解析公共字段
    result = {
        "success": True,
        "receipt_type_en": ticket_type_en,
        "receipt_type_cn": ticket_type_cn,
        "original_filename": filename or os.path.basename(pdf_path),
        "import_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw_text": text,
    }

    # 公共字段
    common = parse_common(text)
    result.update(common)

    # 根据类型调用专用解析器
    type_specific = {}
    if ticket_type_en == "Flight Receipt":
        type_specific = parse_flight(text)
    elif ticket_type_en == "Hotel Receipt":
        type_specific = parse_hotel(text)
    elif ticket_type_en == "Fee Receipt":
        type_specific = parse_fee(text)

    result.update(type_specific)

    # 映射到统一输出格式（与 config.py 的 FIELDS 对齐）
    output = _map_to_fields(result, ticket_type_cn)
    output["success"] = True
    output["raw_text"] = text

    return output


def _map_to_fields(parsed, ticket_type_cn):
    """
    将原始解析结果映射到多维表格标准字段。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output = {
        "账单编号":          parsed.get("bill_no", ""),
        "报销人姓名":        parsed.get("employee_name", ""),
        "账单日期":         parsed.get("purchase_date") or parsed.get("transaction_date") or parsed.get("receipt_date", ""),
        "票据类型":          ticket_type_cn,
        "出行日期":          parsed.get("trip_start_date", ""),
        "结束日期":          parsed.get("trip_end_date", ""),
        "出发地/城市":        parsed.get("origin", ""),
        "目的地/城市":        parsed.get("destination", ""),
        "供应商/航司":        parsed.get("vendor", ""),
        "航班/车次号":        parsed.get("flight_train_no", ""),
        "票面金额":          parsed.get("base_fare"),
        "税费附加费":         parsed.get("taxes_fees"),
        "实收总金额":        parsed.get("total_amount") or parsed.get("total_charges"),
        "货币":             parsed.get("currency", "USD"),
        "支付方式":          parsed.get("payment_method", ""),
        "导入时间":          now,
        "原始文件名":        parsed.get("original_filename", ""),
        "备注":              "",
    }

    return output


if __name__ == "__main__":
    # 测试模式：直接运行此文件解析一个 PDF
    import sys
    import os

    if len(sys.argv) < 2:
        print("用法: python pdf_parser.py <pdf文件路径>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    result = parse_egencia_pdf(pdf_path)

    print("\n========== 解析结果 ==========")
    for k, v in result.items():
        print(f"{k}: {v}")
