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

STYLE_CATEGORIES = {
    "A": ["nail_01", "nail_10", "nail_13", "nail_14", "nail_23"],
    "B": ["nail_02", "nail_05", "nail_15", "nail_16", "nail_25"],
    "C": ["nail_06", "nail_11", "nail_17", "nail_18", "nail_19"],
    "D": ["nail_03", "nail_08", "nail_09", "nail_12"],
    "E": ["nail_04", "nail_07", "nail_20", "nail_21", "nail_22", "nail_24"],
}

STYLE_TO_CAT = {}
for cat, styles in STYLE_CATEGORIES.items():
    for s in styles:
        STYLE_TO_CAT[s] = cat

ALL_STYLES = list(STYLE_TO_CAT.keys())

# 风格热度权重: C 华丽最热, D 暗黑次之, A/B 中等, E 偏少
CAT_WEIGHTS = {"A": 3, "B": 3, "C": 5, "D": 4, "E": 2}

# 门店对应风格
CAT_TO_SHOP = {
    "A": "shop_001",  # Maison Pureté
    "B": "shop_002",  # Fleur Rosé
    "C": "shop_003",  # Bijou Lumière
    "D": "shop_004",  # Noir Atelier
    "E": "shop_005",  # L'Avant-Garde
}

SHOPS = ["shop_001", "shop_002", "shop_003", "shop_004", "shop_005"]

now = datetime.now(timezone.utc)
records = []


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def pick_style():
    cat = random.choices(list(CAT_WEIGHTS.keys()), weights=list(CAT_WEIGHTS.values()), k=1)[0]
    return random.choice(STYLE_CATEGORIES[cat])


for _ in range(200):
    user_id, nickname = random.choice(USERS)
    style = pick_style()
    cat = STYLE_TO_CAT[style]
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

    # 70% 给反馈
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

        # 喜欢的 40% 会预约
        if action == "like" and random.random() < 0.4:
            book_time = fb_time + timedelta(seconds=random.randint(5, 30))
            # 70% 预约对应风格的门店，30% 随机（模拟跨店预约）
            if random.random() < 0.7:
                shop = CAT_TO_SHOP[cat]
            else:
                shop = random.choice(SHOPS)
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

# 注入异常: Bijou Lumière (shop_003) 额外刷 15 单预约（模拟刷量）
for _ in range(15):
    fake_user = random.choice(USERS)
    fake_time = now - timedelta(hours=random.uniform(1, 48))
    fake_style = random.choice(STYLE_CATEGORIES["C"])
    records.append({
        "ts": iso(fake_time),
        "event": "feedback",
        "request_id": f"mock_{random.randint(900000, 999999)}",
        "user_id": fake_user[0],
        "nickname": fake_user[1],
        "style_id": fake_style,
        "action": "book",
        "shop_id": "shop_003",
    })

records.sort(key=lambda r: r["ts"])

with open(OUT, "w") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"已生成 {len(records)} 条记录 → {OUT}")
