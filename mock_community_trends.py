"""
Task 1 · 外部社区趋势 Mock 数据
模拟小红书/抖音过去 14 天的美甲风格讨论热度，作为闭环的"外部信号源"。
写入 SQLite 表 community_trends，供 Task 2 多源聚合按 style_tag 归并到站内分类。

造数手法参考 populate_plaza.py / generate_mock_data.py：加权、带噪声、长尾、非均匀。
分布刻意做出 3 个快速爬升款、2 个衰退款、其余平稳，方便后台一眼看出升/降。

用法（本地或服务器）:
    cd /opt/jiaqu && source venv/bin/activate && python3 mock_community_trends.py
重跑幂等：先清空旧 mock 再插入，行数恒为 14 × 2 × 10 = 280。
"""
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from services.style_taxonomy import FINE_TAGS

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{BASE_DIR}/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = f"{DATA_DIR}/jiaqu.db"

BJT = timezone(timedelta(hours=8))
DAYS = 14
PLATFORMS = ["小红书", "抖音"]
# 抖音体量更大，让同一标签在两平台量级不同但走向一致
PLATFORM_MULT = {"小红书": 1.0, "抖音": 2.2}

# 每个细标签的轨迹：(类型, 小红书日基线, 日斜率)
#   rising   : mention = base * (1 + slope*day)   —— 快速爬升
#   declining: mention = base * (1 - slope*day)   —— 衰退（有下限）
#   stable   : mention = base * (1 ± 小噪声)       —— 平稳
TREND_PROFILES = {
    "美拉德":     ("rising", 60, 0.16),
    "冰透":       ("rising", 95, 0.12),
    "多巴胺撞色": ("rising", 48, 0.18),
    "碎钻":       ("declining", 180, 0.055),
    "草莓甜心":   ("declining", 130, 0.045),
    "奶咖":       ("stable", 150, 0.0),
    "奶油裸色":   ("stable", 110, 0.0),
    "镭射极光":   ("stable", 90, 0.0),
    "暗黑金属":   ("stable", 70, 0.0),
    "雪花":       ("stable", 55, 0.0),
}

SAMPLE_POST_TEMPLATES = [
    "{tag}美甲教程｜本季必抄作业",
    "去做了爆火的{tag}，回头率绝了",
    "{tag}配色合集，手残党也能驾驭",
    "美甲师都在推的{tag}，到底值不值",
    "{tag} vs 上头风格，谁更出片",
    "我的{tag}美甲三周实拍，掉不掉色",
    "新手别踩雷｜{tag}避坑指南",
    "{tag}短甲方案，通勤也能戴",
]


def main():
    rng = random.Random()  # 不固定种子，每次重跑分布略有差异
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS community_trends (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT NOT NULL,
            platform      TEXT NOT NULL,
            style_tag     TEXT NOT NULL,
            mention_count INTEGER NOT NULL,
            growth_rate   REAL NOT NULL,
            sample_posts  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ct_date ON community_trends(date);
        CREATE INDEX IF NOT EXISTS idx_ct_tag  ON community_trends(style_tag);
    """)
    conn.execute("DELETE FROM community_trends")  # 幂等：清旧 mock

    today = datetime.now(BJT).date()
    dates = [(today - timedelta(days=DAYS - 1 - i)).isoformat() for i in range(DAYS)]

    rows = []
    summary = {}  # tag -> (首日量, 末日量, 类型)

    for tag in FINE_TAGS:
        trend_type, base_xhs, slope = TREND_PROFILES[tag]
        for platform in PLATFORMS:
            base = base_xhs * PLATFORM_MULT[platform]
            prev = None
            for day, date in enumerate(dates):
                if trend_type == "rising":
                    val = base * (1 + slope * day) * (1 + rng.uniform(-0.07, 0.07))
                elif trend_type == "declining":
                    val = base * max(0.2, 1 - slope * day) * (1 + rng.uniform(-0.06, 0.06))
                else:
                    val = base * (1 + rng.uniform(-0.10, 0.10))
                mc = max(1, int(round(val)))

                if prev is None:
                    # 首日给一个符合走向的小幅基线增长率
                    seed = {"rising": 0.06, "declining": -0.04, "stable": 0.0}[trend_type]
                    gr = round(seed + rng.uniform(-0.02, 0.02), 4)
                else:
                    gr = round((mc - prev) / prev, 4)
                prev = mc

                posts = rng.sample(SAMPLE_POST_TEMPLATES, 3)
                sample_posts = json.dumps([p.format(tag=tag) for p in posts], ensure_ascii=False)
                rows.append((date, platform, tag, mc, gr, sample_posts))

                # 记录小红书侧首末日用于汇总
                if platform == "小红书" and day == 0:
                    summary.setdefault(tag, [mc, mc, trend_type])[0] = mc
                if platform == "小红书" and day == DAYS - 1:
                    summary.setdefault(tag, [mc, mc, trend_type])[1] = mc
                    summary[tag][2] = trend_type

    conn.executemany(
        "INSERT INTO community_trends(date, platform, style_tag, mention_count, growth_rate, sample_posts) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    print(f"已写入 {len(rows)} 行 community_trends（{DAYS} 天 × {len(PLATFORMS)} 平台 × {len(FINE_TAGS)} 标签）→ {DB_PATH}")
    print(f"{'标签':<8}{'走向':<10}{'小红书首日':>10}{'末日':>8}{'变化':>9}")
    for tag in sorted(summary, key=lambda t: summary[t][1] - summary[t][0], reverse=True):
        first, last, ttype = summary[tag]
        pct = (last - first) / first * 100 if first else 0
        print(f"{tag:<8}{ttype:<10}{first:>10}{last:>8}{pct:>8.0f}%")


if __name__ == "__main__":
    main()
