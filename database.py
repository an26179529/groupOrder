import sqlite3
import json
from datetime import datetime

def init_db():
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()

    # 建立 User 表
    # id： 使用者的 LINE ID
    # name：使用者名稱，created_at：建立時間
    # created_at：建立時間
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS User (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_at TEXT
        );
    """)

    # 建立 Restaurant 表
    # id： 餐廳唯一識別碼
    # name：餐廳名稱
    # menu：餐廳菜單
    # active：是否啟用
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Restaurant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            menu TEXT,  -- 存 JSON 字串
            active BOOLEAN DEFAULT 1
        );
    """)

    # 建立 Order 表
    # id：訂單唯一識別碼
    # user_id：使用者 ID
    # restaurant_id：餐廳 ID
    # item：訂購的餐點
    # quantity：訂購數量
    # created_at：訂單建立時間
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS OrderRecord (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            restaurant_id INTEGER,
            item TEXT,
            quantity INTEGER,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES User(id),
            FOREIGN KEY(restaurant_id) REFERENCES Restaurant(id)
        );
    """)

    conn.commit()
    conn.close()
    print("✅ 資料表建立完成")

def insert_default_restaurants():
    conn = sqlite3.connect("group_order.db")
    cursor = conn.cursor()

    default_restaurants = [
        {
            "name": "貳捌伍",
            "menu": {
                "吊燒雞腿便當": 120,
                "秘製烤雞肉便當": 100,
                "鹽酥魚柳便當": 100,
                "酥炸雞排便當": 110,
                "紅燒豚肉便當": 110,
                "豆乳豚排便當": 100,
            }
        },
        {
            "name": "健康那件小事",
            "menu": {
                "蒜香牛奶嫩雞胸": 115,
                "泰式塔香打拋豬": 110,
                "素香三杯菌菇": 95,
                "豬肉豆腐漢堡排": 115
            }
        },
        {
            "name": "鈴蘭美食",
            "menu": {
                "香酥雞腿飯": 85,
                "排骨飯": 70,
                "肉片飯": 60,
                "雞排飯": 75,
            }
        }
    ]

    for r in default_restaurants:
        cursor.execute(
            "INSERT INTO Restaurant (name, menu) VALUES (?, ?)",
            (r["name"], json.dumps(r["menu"]))
        )

    conn.commit()
    conn.close()
    print("✅ 預設餐廳建立完成")

if __name__ == "__main__":
    init_db()
    insert_default_restaurants()
