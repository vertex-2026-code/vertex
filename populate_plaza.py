"""
批量生成 mock 用户手图 + 试戴 + 发广场
使用 static/hands_stock/ 里的真实手图，每个用户试戴 2 款发到广场

用法: cd /opt/jiaqu && source venv/bin/activate && source .env && python3 populate_plaza.py
"""
import base64
import os
import random
import shutil
import time
import sqlite3
import requests as http_requests
from datetime import datetime, timedelta, timezone

BJT = timezone(timedelta(hours=8))
BASE_URL = "http://127.0.0.1:5000"
HANDS_DIR = "/opt/jiaqu/static/uploads/hands"
HANDS_STOCK_DIR = "/opt/jiaqu/static/hands_stock"
DB_PATH = "/opt/jiaqu/data/jiaqu.db"

MOCK_USERS = [
    ("mia",   "hand_02"),
    ("az",    "hand_07"),
    ("Carol", "hand_01"),
    ("tina",  "hand_11"),
    ("Ella",  "hand_03"),
    ("fiona", "hand_05"),
    ("yara",  "hand_10"),
    ("hana",  "hand_06"),
    ("Ivy",   "hand_09"),
    ("jenny", "hand_08"),
]

ALL_STYLES = [f"nail_{str(i).zfill(2)}" for i in range(1, 26)]
TRYONS_PER_USER = 2


def setup_hand(user_name, stock_id):
    """从 hands_stock 复制真实手图"""
    dest = os.path.join(HANDS_DIR, f"{user_name}.png")
    if os.path.exists(dest):
        print(f"  手图已存在，跳过")
        return True

    src = os.path.join(HANDS_STOCK_DIR, f"{stock_id}.png")
    if not os.path.exists(src):
        print(f"  源图 {src} 不存在!")
        return False

    os.makedirs(HANDS_DIR, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"  已复制 {stock_id}.png -> {user_name}.png")

    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO hand_originals(user_id, image_path, updated_at) "
        "VALUES(?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
        "image_path=excluded.image_path, updated_at=excluded.updated_at",
        (user_name, f"/static/uploads/hands/{user_name}.png",
         datetime.now(BJT).isoformat()),
    )
    db.commit()
    db.close()
    return True


def get_hand_b64(user_name):
    path = os.path.join(HANDS_DIR, f"{user_name}.png")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    total_hands = 0
    total_tryons = 0
    failed = 0

    for user_name, stock_id in MOCK_USERS:
        print(f"\n{'='*40}")
        print(f"用户: {user_name} (手图: {stock_id})")
        print(f"{'='*40}")

        if setup_hand(user_name, stock_id):
            total_hands += 1
        else:
            print(f"  跳过试戴（无手图）")
            continue

        time.sleep(2)

        hand_b64 = get_hand_b64(user_name)
        if not hand_b64:
            continue

        styles = random.sample(ALL_STYLES, TRYONS_PER_USER)
        for style_id in styles:
            print(f"  试戴 {style_id}...", end=" ", flush=True)
            try:
                r = http_requests.post(f"{BASE_URL}/api/tryon", json={
                    "user_id": user_name,
                    "nickname": user_name,
                    "hand_image": hand_b64,
                    "style_id": style_id,
                }, timeout=120)
                data = r.json()
                if "error" in data:
                    print(f"失败: {data['error']}")
                    failed += 1
                    continue

                request_id = data["request_id"]
                result_url = data["result_url"]
                latency = data.get("latency_ms", 0)
                print(f"成功 ({latency/1000:.1f}s)")

                # 发广场，随机点赞数 + 随机时间（过去3天内）
                random_time = datetime.now(BJT) - timedelta(
                    hours=random.uniform(1, 72))
                db.execute(
                    "INSERT INTO plaza(user_id, request_id, style_id, "
                    "result_image_url, caption, likes, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (user_name, request_id, style_id, result_url, "",
                     random.randint(1, 20), random_time.isoformat()),
                )
                db.commit()
                print(f"  -> 已分享到广场")
                total_tryons += 1

                time.sleep(2)

            except Exception as e:
                print(f"异常: {e}")
                failed += 1

    print(f"\n{'='*40}")
    print(f"全部完成!")
    print(f"手图生成: {total_hands}")
    print(f"试戴成功: {total_tryons}")
    print(f"失败: {failed}")
    print(f"{'='*40}")
    db.close()


if __name__ == "__main__":
    main()
