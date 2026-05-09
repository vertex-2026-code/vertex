"""
批量生成 mock 用户手图 + 试戴 + 发广场
每个用户先用 Seedream 生成独特手图，再试戴 2 款发到广场

用法: cd /opt/jiaqu && source venv/bin/activate && source .env && python3 populate_plaza.py
"""
import base64
import os
import random
import time
import sqlite3
import requests as http_requests
from datetime import datetime, timedelta, timezone
from openai import OpenAI

BJT = timezone(timedelta(hours=8))
BASE_URL = "http://127.0.0.1:5000"
HANDS_DIR = "/opt/jiaqu/static/uploads/hands"
DB_PATH = "/opt/jiaqu/data/jiaqu.db"

ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=ARK_API_KEY,
)

MOCK_USERS = [
    ("小美", "年轻女性的手，皮肤白皙细腻，指甲修长椭圆形，放在粉色桌面上"),
    ("阿哲", "年轻男性的手，肤色偏古铜，手指粗壮有力，放在深色木桌上"),
    ("Carol", "年轻女性的手，小麦色皮肤，指甲短圆形，放在白色大理石桌面上"),
    ("甜甜", "年轻女性的手，皮肤粉嫩，手指纤细，指甲中等长度方形，放在浅灰色桌面上"),
    ("Ella", "年轻女性的手，皮肤白皙偏冷白，指甲细长尖形，放在米色布料上"),
    ("芳芳", "中年女性的手，皮肤自然偏黄，指甲短方形，放在浅木色桌面上"),
    ("小雅", "年轻女性的手，皮肤白皙透粉，手指修长，指甲中长椭圆形，放在白色桌面上"),
    ("花花", "年轻女性的手，健康小麦肤色，指甲中等长度圆形，放在淡蓝色桌面上"),
    ("Ivy", "年轻女性的手，皮肤白皙，手指纤细骨感，指甲短椭圆形，放在白色纸张上"),
    ("珍妮", "年轻女性的手，皮肤自然亮白，指甲修长方圆形，戴一枚细银戒指，放在奶白色桌面上"),
]

ALL_STYLES = [f"nail_{str(i).zfill(2)}" for i in range(1, 26)]
TRYONS_PER_USER = 2


def generate_hand(user_name, hand_desc):
    """用 Seedream 生成手图"""
    path = os.path.join(HANDS_DIR, f"{user_name}.png")
    if os.path.exists(path):
        print(f"  手图已存在，跳过生成")
        return True

    prompt = (
        f"一只中国人的手，自然张开五指，{hand_desc}，"
        "俯拍角度，指甲未涂甲油，自然光线，真实摄影风格，高清细节，8K"
    )
    print(f"  生成手图中...", end=" ", flush=True)
    try:
        resp = client.images.generate(
            model="doubao-seedream-5-0-260128",
            prompt=prompt,
            size="2k",
            extra_body={"watermark": False},
            n=1,
        )
        img_url = resp.data[0].url
        img_data = http_requests.get(img_url, timeout=30).content
        with open(path, "wb") as f:
            f.write(img_data)
        print(f"成功 ({len(img_data)//1024}KB)")

        # 写入 hand_originals 表
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
    except Exception as e:
        print(f"失败: {e}")
        return False


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

    for user_name, hand_desc in MOCK_USERS:
        print(f"\n{'='*40}")
        print(f"用户: {user_name}")
        print(f"{'='*40}")

        # 第一步：生成手图
        if generate_hand(user_name, hand_desc):
            total_hands += 1
        else:
            print(f"  跳过试戴（无手图）")
            continue

        time.sleep(2)

        # 第二步：试戴
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
