"""
批量生成 mock 用户的试戴数据并分享到广场
使用现有的 3 张真实手图，为 mock 用户生成真实试戴结果

用法: cd /opt/jiaqu && source venv/bin/activate && source .env && python3 populate_plaza.py
"""
import base64
import json
import os
import random
import time
import requests as http_requests
import sqlite3
from datetime import datetime, timedelta, timezone

BJT = timezone(timedelta(hours=8))
BASE_URL = "http://127.0.0.1:5000"

# Mock 用户，每人关联一张真实手图
MOCK_USERS = [
    ("小美", "u_xcwt2px8"),
    ("甜甜", "u_xcwt2px8"),
    ("芳芳", "u_tkr5dbvr"),
    ("小雅", "u_tkr5dbvr"),
    ("花花", "boris"),
    ("珍妮", "boris"),
]

# 每个 mock 用户试戴的款式数量
TRYONS_PER_USER = 2

# 可用款式
ALL_STYLES = [f"nail_{str(i).zfill(2)}" for i in range(1, 26)]

HANDS_DIR = "/opt/jiaqu/static/uploads/hands"

def get_hand_b64(old_uid):
    path = os.path.join(HANDS_DIR, f"{old_uid}.png")
    if not os.path.exists(path):
        print(f"  手图不存在: {path}")
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def main():
    db = sqlite3.connect("/opt/jiaqu/data/jiaqu.db")
    db.row_factory = sqlite3.Row

    used_styles = {}
    total = 0
    failed = 0

    for user_name, hand_source in MOCK_USERS:
        print(f"\n=== {user_name} (手图来源: {hand_source}) ===")
        hand_b64 = get_hand_b64(hand_source)
        if not hand_b64:
            continue

        available = [s for s in ALL_STYLES if s not in used_styles.get(user_name, set())]
        styles = random.sample(available, min(TRYONS_PER_USER, len(available)))

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

                # 分享到广场
                db.execute(
                    "INSERT INTO plaza(user_id, request_id, style_id, result_image_url, caption, likes, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (user_name, request_id, style_id, result_url, "",
                     random.randint(0, 15),
                     datetime.now(BJT).isoformat()),
                )
                db.commit()
                print(f"  -> 已分享到广场")
                total += 1

                used_styles.setdefault(user_name, set()).add(style_id)

                # 间隔一下避免 API 压力
                time.sleep(2)

            except Exception as e:
                print(f"异常: {e}")
                failed += 1

    print(f"\n=== 完成 ===")
    print(f"成功: {total} 条")
    print(f"失败: {failed} 条")
    db.close()


if __name__ == "__main__":
    main()
