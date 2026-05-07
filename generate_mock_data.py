"""
生成模拟行为日志 → data/tryon.jsonl
用于 OpenClaw + DeepSeek 分析演示
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{BASE_DIR}/data"
os.makedirs(DATA_DIR, exist_ok=True)
OUT = f"{DATA_DIR}/tryon.jsonl"

USERS = [
    ("u_alice01", "小美"),
    ("u_bob002", "阿哲"),
    ("u_carol3", "Carol"),
    ("u_diana4", "甜甜"),
    ("u_ella05", "Ella"),
    ("u_fangfang", "芳芳"),
    ("u_grace7", "小雅"),
    ("u_hana08", "花花"),
    ("u_ivy009", "Ivy"),
    ("u_jenny10", "珍妮"),
]

STYLES = [f"nail_{i:02d}" for i in range(1, 26)]

# 热门款式权重：nail_03, nail_07, nail_12, nail_18 最热
STYLE_WEIGHTS = []
for s in STYLES:
    if s in ("nail_03", "nail_07", "nail_12", "nail_18"):
        STYLE_WEIGHTS.append(5)
    elif s in ("nail_01", "nail_05", "nail_10", "nail_15", "nail_20"):
        STYLE_WEIGHTS.append(3)
    else:
        STYLE_WEIGHTS.append(1)

SHOPS = ["shop_001", "shop_002", "shop_003", "shop_004", "shop_005"]

now = datetime.now(timezone.utc)
records = []


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


for _ in range(180):
    user_id, nickname = random.choice(USERS)
    style = random.choices(STYLES, weights=STYLE_WEIGHTS, k=1)[0]
    base_time = now - timedelta(hours=random.uniform(1, 72))
    req_id = f"mock_{random.randint(100000, 999999)}"
    latency = random.randint(12000, 28000)

    records.append({
        "ts": iso(base_time),
        "event": "tryon_start",
        "request_id": req_id,
        "user_id": user_id,
        "nickname": nickname,
        "style_id": style,
        "style_kind": "preset",
    })

    t_done = base_time + timedelta(milliseconds=latency)
    records.append({
        "ts": iso(t_done),
        "event": "tryon_success",
        "request_id": req_id,
        "user_id": user_id,
        "nickname": nickname,
        "style_id": style,
        "style_kind": "preset",
        "latency_ms": latency,
        "result_url": f"/static/results/{req_id}.png",
    })

    # 70% 的用户会给反馈
    if random.random() < 0.7:
        fb_time = t_done + timedelta(seconds=random.randint(3, 20))
        action = random.choices(["like", "dislike"], weights=[65, 35], k=1)[0]
        records.append({
            "ts": iso(fb_time),
            "event": "feedback",
            "request_id": req_id,
            "user_id": user_id,
            "nickname": nickname,
            "style_id": style,
            "action": action,
        })

        # 喜欢的用户 40% 会预约
        if action == "like" and random.random() < 0.4:
            book_time = fb_time + timedelta(seconds=random.randint(5, 30))
            # shop_003 异常高（模拟刷量）
            shop_weights = [2, 2, 8, 1, 1]
            shop = random.choices(SHOPS, weights=shop_weights, k=1)[0]
            records.append({
                "ts": iso(book_time),
                "event": "feedback",
                "request_id": req_id,
                "user_id": user_id,
                "nickname": nickname,
                "style_id": style,
                "action": "book",
                "shop_id": shop,
            })

# 按时间排序
records.sort(key=lambda r: r["ts"])

with open(OUT, "w") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"已生成 {len(records)} 条记录 → {OUT}")
