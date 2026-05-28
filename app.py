# Egencia 报账助手 - 飞书机器人主服务
# 功能: 接收飞书消息 → 下载PDF → 解析 → 去重写入多维表格 → 回复链接

import os
import json
import sys
import logging
from flask import Flask, request, jsonify
import tempfile

# ============ 自动加载 .env ============
def _load_env():
    """从项目目录的 .env 文件加载环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

_load_env()

# ============ 日志配置 ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 最大50MB

# ============ 配置 ============
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_BITABLE_TOKEN = os.getenv("BITABLE_TOKEN", "") or os.getenv("FEISHU_BITABLE_TOKEN", "")
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "egencia_bot_verify")

logger.info(f"App ID: {FEISHU_APP_ID[:10]}..." if FEISHU_APP_ID else "⚠️ App ID 未配置")
logger.info(f"Bitable Token: {FEISHU_BITABLE_TOKEN[:10]}..." if FEISHU_BITABLE_TOKEN else "⚠️ Bitable Token 未配置")


# ============ 路由 ============

@app.route("/", methods=["GET", "POST"])
def webhook():
    """飞书事件订阅 Webhook 入口"""

    # ---- GET: URL 验证（飞书后台配置事件订阅时触发）----
    if request.method == "GET":
        challenge = request.args.get("challenge")
        token = request.args.get("token", "")
        logger.info(f"[Webhook] URL验证请求 token={token}")

        if token != WEBHOOK_VERIFY_TOKEN:
            return jsonify({"code": 40001, "msg": "token mismatch"}), 400

        return jsonify({"challenge": challenge})

    # ---- POST: 接收事件/消息回调 ----
    body = request.get_json(silent=True)
    if not body:
        logger.warning("[Webhook] 空POST body")
        return jsonify({"code": 0})

    logger.info(f"[Webhook] 收到事件: {json.dumps(body, ensure_ascii=False)[:500]}")

    # 处理 challenge（某些回调格式）
    if "challenge" in body and body.get("challenge"):
        return jsonify({"challenge": body["challenge"]})

    # 异步处理消息（不阻塞飞书回调）
    try:
        _dispatch_event(body)
    except Exception as e:
        logger.error(f"[Webhook] 事件分发异常: {e}", exc_info=True)

    return jsonify({"code": 0})


def _dispatch_event(body):
    """
    分发不同类型的飞书事件。
    支持 im.message.receive_v1 (收到消息) 等事件。
    """
    # 飞书事件格式: { header: { event_type: "xxx" }, event: {...} }
    header = body.get("header", {})
    event_type = header.get("event_type", "")

    if event_type == "im.message.receive_v1":
        event = body.get("event", {})
        _handle_message(event)
    else:
        logger.info(f"[Event] 收到未处理的事件类型: {event_type}")


def _handle_message(event):
    """处理收到的机器人消息"""
    message_id = event.get("message_id", "")
    chat_type = event.get("chat_type", "")       # p2p / group
    sender = event.get("sender", {})
    open_id = sender.get("sender_id", {})
    message = event.get("message", {})

    msg_type = message.get("msg_type", "")
    content_raw = message.get("content", "{}")

    logger.info(
        f"[Message] ID={message_id} type={msg_type} from={open_id} chat={chat_type}"
    )

    # ---- 文件/PDF 消息 ----
    if msg_type in ("file", "attachment", "stream"):
        try:
            content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        except Exception:
            content = {}

        file_key = content.get("file_key", "")
        filename = content.get("file_name", "unknown.pdf")

        logger.info(f"[File] 文件名={filename}, file_key={file_key}")

        if not filename.lower().endswith(".pdf"):
            _reply_to_user(open_id, (
                f"收到文件 [{filename}]，但目前只支持 PDF 格式的 Egencia 账单。\n"
                "请发送 PDF 文件。"
            ))
            return

        # 下载并处理
        _process_pdf(file_key, filename, open_id)
        return

    # ---- 文本消息 ----
    text_content = ""
    try:
        content_obj = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        text_content = content_obj.get("text", "")
    except Exception:
        text_content = str(content_raw)

    if not text_content.strip():
        _reply_to_user(open_id, (
            "📋 **Egencia 报账助手**\n"
            "━━━━━━━━━━━━━━━\n"
            "直接发给我 **PDF 格式** 的 Egencia 差旅账单\n"
            "我会自动解析并登记到多维表格\n"
            "━━━━━━━━━━━━━━━\n"
            "✅ 支持票据：机票 / 酒店 / 费用单"
        ))
    else:
        _reply_to_user(open_id, (
            f"收到：{text_content}\n"
            "\n📎 请直接发送 Egencia 的 **PDF账单文件**，我帮你自动解析登记。"
        ))


def _download_feishu_file(file_key):
    """从飞书服务器下载用户上传的文件，返回本地临时路径"""
    import requests as req

    # 1. 获取 tenant_access_token
    token_resp = req.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=15,
    )
    token_data = token_resp.json()
    if token_data.get("code") != 0:
        raise Exception(f"获取token失败: {token_data.get('msg')}")
    token = token_data["tenant_access_token"]

    # 2. 获取文件下载地址
    headers = {"Authorization": f"Bearer {token}"}
    info_resp = req.get(
        f"https://open.feishu.cn/open-apis/im/v1/files/{file_key}?type=file",
        headers=headers,
        timeout=15,
    )
    info_data = info_resp.json()
    if info_data.get("code") != 0:
        raise Exception(f"获取文件信息失败: {info_data.get('msg')}")

    file_info = info_data["data"]
    download_url = file_info.get("download_url", "")
    filename = file_info.get("file_name", "unknown.pdf")

    # 3. 下载文件内容
    file_resp = req.get(download_url, headers=headers, timeout=120)
    if file_resp.status_code != 200:
        raise Exception(f"下载文件失败 HTTP {file_resp.status_code}")

    # 4. 保存到本地临时目录
    tmp_dir = tempfile.mkdtemp(prefix="egencia_")
    local_path = os.path.join(tmp_dir, filename)
    with open(local_path, "wb") as f:
        f.write(file_resp.content)

    logger.info(f"[Download] 已保存: {local_path} ({len(file_resp.content)} bytes)")
    return local_path


def _process_pdf(file_key, filename, open_id):
    """完整流程: 下载→解析→去重写入→回复"""
    try:
        # 1. 下载
        local_path = _download_feishu_file(file_key)

        # 2. 解析
        from pdf_parser import parse_egencia_pdf
        parsed = parse_egencia_pdf(local_path, filename=filename)

        if not parsed.get("success"):
            _reply_to_user(open_id, (
                f"❌ 解析失败 [{filename}]\n"
                f"\n原因: {parsed.get('error', '未知')}"
                f"\n\n可能原因:\n"
                f"• 不是有效的 PDF 文件\n"
                f"• PDF 是扫描件(无文字层)\n"
                f"• 非 Egencia 格式的账单"
            ))
            return

        # 3. 写入多维表格（含查重）
        from feishu_api import process_and_write
        result = process_and_write(parsed)

        # 4. 回复用户
        _reply_to_user(open_id, result.get("message", "处理完成"))

    except Exception as e:
        logger.error(f"[Process] 处理异常: {e}", exc_info=True)
        _reply_to_user(open_id, (
            f"⚠️ 处理出错 [{filename}]\n"
            f"\n错误: {str(e)}"
            f"\n请联系管理员。"
        ))


def _reply_to_user(open_id, text):
    """通过飞书 API 发送文本回复给用户"""
    import requests as req

    # 获取 token
    token_resp = req.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=15,
    )
    token = token_resp.json().get("tenant_access_token", "")
    if not token:
        logger.error("[Reply] 获取token失败!")
        return

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }

    resp = req.post(url + "?receive_id_type=open_id",
                    headers=headers, json=body, timeout=15)
    data = resp.json()

    if data.get("code") == 0:
        logger.info(f'[Reply] ✓ 已回复 "{text[:60]}"')
    else:
        logger.error(f'[Reply] ✗ 回复失败: {data.get("msg")} code={data.get("code")}')


# ============ 启动入口 ============

if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5000)))
    logger.info("=" * 50)
    logger.info("  Egencia 报账助手 - 飞书机器人")
    logger.info(f"  端口 : {port}")
    logger.info("=" * 50)

    app.run(host="0.0.0.0", port=port, debug=False)
