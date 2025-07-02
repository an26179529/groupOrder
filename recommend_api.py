from flask import Flask, request, jsonify
import sqlite3
import json
import traceback

app = Flask(__name__)

# ======== 推薦核心邏輯 ========
def recommend_smart(user_id, restaurant_name, top_n=3):
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()
    cursor.execute("SELECT menu FROM Restaurant WHERE name = ?", (restaurant_name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "❌ 查無此餐廳"

    menu_items = list(json.loads(row[0]).keys())
    if not menu_items:
        conn.close()
        return f"📭 餐廳「{restaurant_name}」目前沒有菜單"

    cursor.execute(f"""
        SELECT item, COUNT(*) as freq
        FROM OrderRecord
        WHERE user_id = ?
        GROUP BY item
        HAVING item IN ({','.join('?' * len(menu_items))})
        ORDER BY freq DESC
        LIMIT ?
    """, (user_id, *menu_items, top_n))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"📭 你在餐廳「{restaurant_name}」沒有相關點餐紀錄"
    text = f"🤖 根據你在「{restaurant_name}」的紀錄，推薦：\n"
    for item, freq in rows:
        text += f"- {item}（共點過 {freq} 次）\n"
    return text.strip()

# ======== API 路由 ========
@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        restaurant_name = data.get("restaurant_name")
        if not user_id or not restaurant_name:
            return jsonify({"error": "缺少 user_id 或 restaurant_name"}), 400

        result = recommend_smart(user_id, restaurant_name)

        return jsonify({
            "user_id": user_id,
            "restaurant": restaurant_name,
            "recommendations": result
        }), 200
    except Exception as e:
        print("❌ 推薦 API 錯誤：", e)
        traceback.print_exc()
        return jsonify({"error": "伺服器內部錯誤"}), 500

@app.route("/", methods=["GET"])
def index():
    return "✅ Recommend API is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)  # 注意：這個 API 用 5001 埠口
