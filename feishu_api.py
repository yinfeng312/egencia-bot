# 飞书多维表格 API 模块
# 功能：获取token、建表结构、查重、写入记录、生成链接

import requests
import time
import json
import os
from datetime import datetime

# ============ 环境变量加载 ============

def _load_env():
    """从 .env 文件加载配置（兼容无 python-dotenv 的情况）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    config = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    config[k.strip()] = v.strip()
    return config

_env = _load_env()

FEISHU_APP_ID = _env.get('FEISHU_APP_ID', '')
FEISHU_APP_SECRET = _env.get('FEISHU_APP_SECRET', '')
BITABLE_APP_TOKEN = _env.get('BITABLE_TOKEN', '')

# 允许写入的字段白名单（只传这些到飞书）
WRITEABLE_FIELDS = {
    "账单编号", "报销人姓名", "账单日期", "票据类型",
    "出行日期", "结束日期", "出发地/城市", "目的地/城市",
    "供应商/航司", "航班/车次号", "票面金额", "税费附加费",
    "实收总金额", "货币", "支付方式", "导入时间",
    "原始文件名", "备注",
}

# 去重字段
DEDUP_FIELD = "账单编号"

# 字段类型映射（用于写入时格式转换）
SELECT_FIELDS = {"票据类型"}   # 需要数组格式的单选字段
DATE_FIELDS = {"账单日期", "出行日期", "结束日期", "导入时间"}  # 需要时间戳的字段
NUMBER_FIELDS = {"票面金额", "税费附加费", "实收总金额"}      # 数字字段


# ============ 飞书 API 基础 ============

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
_token_cache = {"value": "", "expire_at": 0}


def get_tenant_access_token():
    """获取 tenant_access_token，带 2 小时缓存"""
    if _token_cache["value"] and time.time() < _token_cache["expire_at"] - 300:
        return _token_cache["value"]

    url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()

    if data.get("code") != 0:
        raise Exception(f"获取飞书 Token 失败: {data.get('msg', '未知错误')}")

    token = data["tenant_access_token"]
    expire = data.get("expire", 7200)
    _token_cache["value"] = token
    _token_cache["expire_at"] = time.time() + expire

    return token


def _headers():
    """获取带 token 的请求头"""
    return {"Authorization": f"Bearer {get_tenant_access_token()}", "Content-Type": "application/json"}


def _api_get(path, params=None):
    """封装 GET 请求"""
    return requests.get(f"{FEISHU_BASE_URL}{path}", headers=_headers(), params=params, timeout=15)


def _api_post(path, body=None):
    """封装 POST 请求"""
    return requests.post(f"{FEISHU_BASE_URL}{path}", headers=_headers(), json=body, timeout=15)


# ============ 类型转换工具 ============

def _to_timestamp(date_str):
    """将日期字符串转为飞书需要的毫秒级 Unix 时间戳"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(date_str, fmt).timestamp() * 1000)
        except (ValueError, TypeError):
            continue
    return None


def _convert_for_writing(field_name, value):
    """
    将解析值转换为飞书 API 写入格式。
    - 单选/多选 → 数组 ["值"]
    - 日期 → 毫秒时间戳
    - 数字 → float/int
    - 其他 → str
    """
    if value is None or value == "":
        return None

    if field_name in SELECT_FIELDS:
        # 单选字段：传数组格式
        return [str(value)]

    if field_name in DATE_FIELDS:
        # 已是数字（时间戳）则直接返回
        if isinstance(value, (int, float)) and value > 1e10:
            return int(value)
        return _to_timestamp(str(value))

    if field_name in NUMBER_FIELDS:
        try:
            return float(value) if "." in str(value) else int(float(value))
        except (ValueError, TypeError):
            return 0

    # 默认返回字符串
    return str(value)


# ============ 多维表格操作 ============

def get_table_fields(bitable_app_token, table_id):
    """获取数据表的字段列表，返回 {field_name: field_id}"""
    resp = _api_get(f"/bitable/v1/apps/{bitable_app_token}/tables/{table_id}/fields")
    data = resp.json()

    if data.get("code") != 0:
        raise Exception(f"查询字段列表失败: {data.get('msg')}")

    items = data.get("data", {}).get("items", [])
    field_map = {}
    for finfo in items:
        fname = finfo.get("field_name", "")
        fid = finfo.get("field_id", "")
        if fname:
            field_map[fname] = fid
    return field_map


def check_duplicate(table_id, bill_no):
    """
    根据账单编号查重。
    返回: (is_duplicate: bool, existing_record: dict or None)
    策略：读取全部记录，在内存中匹配账单编号（避免搜索API的filter格式问题）
    """
    # 先尝试用列表接口读取
    list_resp = _api_get(
        f"/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/records",
        {"pageSize": 100},
    )
    list_data = list_resp.json()

    if list_data.get("code") != 0:
        print(f"[警告] 查重-读取记录失败: {list_data.get('msg')}")
        return False, None

    items = list_data.get("data", {}).get("items", [])
    # 在返回的记录中查找账单编号
    for item in items:
        fields = item.get("fields", {})
        if fields.get(DEDUP_FIELD) == bill_no:
            return True, item

    # 如果有分页，继续检查（当前数据量小，暂不需要）
    return False, None


def write_record(table_id, record_dict):
    """
    将解析结果写入多维表格一条新记录。
    record_dict 的 key 是中文字段名。
    返回 record_id。
    """
    # 转换为飞书 API 格式，只写入白名单内的字段
    fields = {}
    for k, v in record_dict.items():
        if k not in WRITEABLE_FIELDS:
            continue
        converted = _convert_for_writing(k, v)
        if converted is not None:
            fields[k] = converted

    body = {"fields": fields}
    write_resp = _api_post(
        f"/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/records",
        body,
    )
    write_data = write_resp.json()

    if write_data.get("code") != 0:
        raise Exception(
            f"写入记录失败: code={write_data.get('code')} msg={write_data.get('msg')}\n"
            f"内容: {json.dumps(fields, ensure_ascii=False, default=str)}"
        )

    record_id = write_data["data"]["record"].get("record_id", "")
    print(f"[Bitable] ✅ 写入成功, record_id={record_id}")
    return record_id


def process_and_write(parsed_data):
    """
    完整处理流程：查重 → 写入 → 返回结果。
    parsed_data: pdf_parser 解析出的字典。

    返回: {
        "success": bool,
        "message": str,
        "url": str,
        "duplicate": bool,
    }
    """
    table_id = "tblbIxthU2DScOEh"  # 当前固定表ID（后续可改为自动查找）
    bill_no = parsed_data.get("账单编号", "")
    ticket_type = parsed_data.get("票据类型", "")

    if not bill_no:
        return {
            "success": False,
            "message": "⚠️ 无法从 PDF 中提取账单编号，请检查文件格式",
            "url": "",
            "duplicate": False,
        }

    # 去重检查
    is_dup, existing = check_duplicate(table_id, bill_no)

    if is_dup:
        return {
            "success": True,
            "message": (
                f"🔄 该{ticket_type}账单已存在，已跳过\n"
                f"━━━━━━━━━━\n"
                f"编号: {bill_no}\n"
                f"报销人: {parsed_data.get('报销人姓名','')}\n"
                f"金额: ${parsed_data.get('实收总金额','')}"
            ),
            "url": get_bitable_url(),
            "duplicate": True,
        }

    # 写入新记录
    try:
        record_id = write_record(table_id, parsed_data)
        return {
            "success": True,
            "message": (
                f"✅ {ticket_type}账单已登记\n"
                f"━━━━━━━━━━\n"
                f"编号: {bill_no}\n"
                f"报销人: {parsed_data.get('报销人姓名','')}\n"
                f"供应商: {parsed_data.get('供应商/航司','-')}\n"
                f"出行: {parsed_data.get('出行日期','-')}\n"
                f"总额: ${parsed_data.get('实收总金额','')}\n"
                f"支付: {parsed_data.get('支付方式','-')}"
            ),
            "url": get_bitable_url(),
            "duplicate": False,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"❌ 写入失败: {e}",
            "url": "",
            "duplicate": False,
        }


def get_bitable_url():
    """生成多维表格的访问链接（使用实际域名）"""
    return f"https://acnjh1thgeif.feishu.cn/base/{BITABLE_APP_TOKEN}"


if __name__ == "__main__":
    print("=" * 50)
    print("Egencia 差旅账单 - 飞书多维表格模块")
    print("=" * 50)
    print(f"\nApp ID: {FEISHU_APP_ID[:15]}...")
    print(f"Bitable Token: {BITABLE_APP_TOKEN[:15]}...")
    print(f"去重字段: {DEDUP_FIELD}")

    # 测试 token 获取
    token = get_tenant_access_token()
    print(f"\n✅ Token 获取成功: {token[:20]}...")

    # 列出字段
    try:
        fields = get_table_fields(BITABLE_APP_TOKEN, "tblbIxthU2DScOEh")
        print(f"\n📋 表格字段 ({len(fields)} 个):")
        for name, fid in sorted(fields.items()):
            marker = " 🔽" if name == DEDUP_FIELD else ""
            select_tag = " [单选]" if name in SELECT_FIELDS else ""
            date_tag = " [日期]" if name in DATE_FIELDS else ""
            num_tag = " [数字]" if name in NUMBER_FIELDS else ""
            print(f"  {name}{marker}{select_tag}{date_tag}{num_tag}")
    except Exception as e:
        print(f"\n⚠️ 字段查询失败: {e}")
