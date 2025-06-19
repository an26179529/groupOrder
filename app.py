import os
import json
import sqlite3
import traceback
from flask import Flask, request, abort
from dotenv import load_dotenv
from database import init_db, insert_default_restaurants

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.messaging.models import QuickReply, QuickReplyItem, MessageAction
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# ======== 初始化設定 ========
load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise EnvironmentError("❌ 必須設定 CHANNEL_ACCESS_TOKEN 與 CHANNEL_SECRET")

if not os.path.exists("group_order.db"):
    init_db()
    insert_default_restaurants()

app = Flask(__name__)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(CHANNEL_SECRET)
group_orders = {}  # 暫存訂單資料

# ======== 工具函式區 ========
def get_restaurant_list():
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM Restaurant WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return "目前沒有可用的餐廳喔～"
    return "目前可選餐廳：\n" + "\n".join([f"{idx+1}. {name}" for idx, (_, name) in enumerate(rows)])

def get_restaurant_quickreply():
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Restaurant WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    return QuickReply(items=[QuickReplyItem(action=MessageAction(label=name, text=f"[選擇餐廳] {name}")) for (name,) in rows]) if rows else None

def get_menu_by_name(name):
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()
    cursor.execute("SELECT menu FROM Restaurant WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return "查無此餐廳"
    menu_dict = json.loads(row[0])
    return f"📋「{name}」菜單：\n" + "\n".join([f"- {item}: {price} 元" for item, price in menu_dict.items()])

def get_display_name(event):
    try:
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            if event.source.type == "group":
                profile = line_api.get_group_member_profile(event.source.group_id, event.source.user_id)
            else:
                profile = line_api.get_profile(event.source.user_id)
            return profile.display_name
    except Exception as e:
        print("⚠️ 無法取得使用者名稱：", e)
        return "未知使用者"

def recommend_menu_items(user_id, top_n=3):
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()

    # 先查使用者自己的歷史紀錄
    cursor.execute("""
        SELECT item, COUNT(*) as freq
        FROM OrderRecord
        WHERE user_id = ?
        GROUP BY item
        ORDER BY freq DESC
        LIMIT ?
    """, (user_id, top_n))
    rows = cursor.fetchall()

    if rows:
        conn.close()
        text = "🍽 根據你的歷史訂單，推薦你：\n"
        for item, freq in rows:
            text += f"- {item}（共點過 {freq} 次）\n"
        return text.strip()
    else:
        # 如果沒有個人紀錄 → 查所有人熱門排行
        cursor.execute("""
            SELECT item, COUNT(*) as freq
            FROM OrderRecord
            GROUP BY item
            ORDER BY freq DESC
            LIMIT ?
        """, (top_n,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "📭 資料庫目前沒有任何訂單紀錄，可以先用 /join 嘗試點個餐！"

        text = "🔥 根據大家的點餐紀錄，推薦你：\n"
        for item, freq in rows:
            text += f"- {item}（共被點過 {freq} 次）\n"
        return text.strip()

def recommend_group_items(group_id, top_n=3):
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()

    # 取得該群組所有成員的 user_id
    # 這裡我們先用訂單中 user_id 出現過的代表是此群組成員（簡化版本）
    cursor.execute("""
        SELECT item, COUNT(*) as freq
        FROM OrderRecord
        WHERE user_id IN (
            SELECT DISTINCT user_id
            FROM OrderRecord
            WHERE created_at >= datetime('now', '-30 days')  -- 限定近期30天
        )
        GROUP BY item
        ORDER BY freq DESC
        LIMIT ?
    """, (top_n,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "📭 這個群組最近還沒有人點過餐喔！快用 /order 開團試試吧～"

    text = "👥 群組熱門推薦：\n"
    for item, freq in rows:
        text += f"- {item}（共被點過 {freq} 次）\n"
    return text.strip()



# ======== 路由區 ========
@app.route("/", methods=["GET"])
def index():
    return "LINE Bot is running!", 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print("❌ Webhook 處理錯誤：", e)
        traceback.print_exc()
        abort(500)
    return "OK"

# ======== 主處理邏輯 ========
@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    group_id = event.source.group_id if event.source.type == "group" else event.source.user_id
    user_id = event.source.user_id
    reply_text = ""
    quick_reply = None

    if text == "/order":
        if group_id in group_orders:
            reply_text = "⚠️ 已有訂單進行中，請先 /done 結單或 /list 查詢"
        else:
            group_orders[group_id] = {"restaurant": None, "orders": []}
            reply_text = "請選擇要訂購的餐廳："
            quick_reply = get_restaurant_quickreply()

    elif text.startswith("[選擇餐廳]"):
        selected_name = text.replace("[選擇餐廳]", "").strip()
        if group_id not in group_orders:
            reply_text = "⚠️ 請先用 /order 開啟團購流程"
        else:
            group_orders[group_id]["restaurant"] = selected_name
            menu_text = get_menu_by_name(selected_name)
            reply_text = f"✅ 餐廳「{selected_name}」選擇完成！\n\n{menu_text}\n\n大家可以用 `/join 餐點 數量` 來加入訂單"

    elif text.startswith("/join"):
        if group_id not in group_orders or not group_orders[group_id]["restaurant"]:
            reply_text = "⚠️ 請先用 /order 並選擇餐廳"
        else:
            try:
                parts = text.split()
                item = parts[1]
                qty = int(parts[2])
                user_name = get_display_name(event)
                group_orders[group_id]["orders"].append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "item": item,
                    "qty": qty
                })

                # ✅ 將資料寫入資料庫
                conn = sqlite3.connect("group_order.db")
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO OrderRecord (user_id, restaurant_id, item, quantity, created_at)
                    VALUES (?, (SELECT id FROM Restaurant WHERE name = ?), ?, ?, datetime('now'))
                """, (user_id, group_orders[group_id]["restaurant"], item, qty))
                conn.commit()
                conn.close()

                reply_text = f"✅ 已加入：{user_name} 點了 {item} x{qty}"
            except Exception as e:
                reply_text = "⚠️ 請輸入格式正確，例如：/join 雞腿飯 1"
                print("加入訂單錯誤：", e)

    elif text == "/list":
        if group_id not in group_orders or not group_orders[group_id]["orders"]:
            reply_text = "目前沒有訂單資料"
        else:
            reply_text = f"📦 訂單明細（{group_orders[group_id]['restaurant']}）：\n"
            for o in group_orders[group_id]["orders"]:
                reply_text += f"- 👤 {o['user_name']}：{o['item']} x{o['qty']}\n"

    elif text == "/done":
        if group_id not in group_orders:
            reply_text = "⚠️ 目前沒有進行中的訂單"
        else:
            orders = group_orders[group_id]["orders"]
            if not orders:
                reply_text = "⚠️ 尚未有人點餐"
            else:
                summary = {}
                for o in orders:
                    summary[o["item"]] = summary.get(o["item"], 0) + o["qty"]
                reply_text = f"✅ 訂單結束！{group_orders[group_id]['restaurant']} 統計如下：\n"
                for item, qty in summary.items():
                    reply_text += f"- {item}: {qty} 份\n"
            del group_orders[group_id]

    elif text in ["/restaurants", "查餐廳"]:
        reply_text = get_restaurant_list()

    elif text == "/recommend":
        if event.source.type == "group":
            reply_text = recommend_group_items(group_id)
        else:
            reply_text = recommend_menu_items(user_id)

    else:
        reply_text = f"你說的是：{text}"

    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text, quick_reply=quick_reply)]
                )
            )
    except Exception as e:
        print("❌ 回覆訊息錯誤：", e)
        traceback.print_exc()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
