"""
给商家日指标注入波动，让 GMV 曲线有故事感
- 周末 +15-25%
- 运营事件 boost (promo_events)
- 随机扰动 ±12%
- 幂等: 同日期重跑覆盖
"""
import sqlite3
import os
import random
from datetime import date, timedelta

random.seed(42)

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"

# 运营事件: 给特定日期加 boost
PROMO_BOOSTS = [
    ("2026-05-13", 3, 2.5, "冰透 Banner 主推"),
    ("2026-05-21", 7, 1.8, "美拉德商家邀请"),
    ("2026-05-28", 4, 3.0, "美拉德新上主推"),
    ("2026-05-30", 2, 2.3, "夏日清凉节"),
    ("2026-06-01", 3, 2.0, "多巴胺 Push 推送"),
    ("2026-06-03", 3, 2.8, "多巴胺 Banner 主推"),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 确保 promo_events 有数据
    cur.execute("SELECT COUNT(*) FROM promo_events")
    if cur.fetchone()[0] == 0:
        for ev_date, dur, factor, desc in PROMO_BOOSTS:
            cur.execute(
                "INSERT INTO promo_events(event_date, action_type, target_tag, boost_factor, duration_days, expected_gmv_lift, description) "
                "VALUES(?, 'banner_promo', ?, ?, ?, ?, ?)",
                (ev_date, "", factor, dur, 0, desc))
        conn.commit()
        print(f"写入 {len(PROMO_BOOSTS)} 个运营事件")

    # 获取日期范围
    rows = cur.execute(
        "SELECT date, shop_id, revenue, group_buy_orders, search_volume, click_volume, consultation_volume "
        "FROM merchant_shop_daily_metrics ORDER BY date, shop_id"
    ).fetchall()

    updates = []
    for d_str, shop_id, rev, orders, sv, cv, cons in rows:
        d = date.fromisoformat(d_str)
        rev = rev or 0
        orders = orders or 0
        sv = sv or 0
        cv = cv or 0
        cons = cons or 0

        # 1. 运营 boost
        boost = 1.0
        for ev_date, dur, factor, _ in PROMO_BOOSTS:
            ev = date.fromisoformat(ev_date)
            if ev <= d < ev + timedelta(days=dur):
                boost = max(boost, factor)

        # 2. 周末 +15-25%
        weekend = 1.0
        if d.weekday() >= 5:
            weekend = random.uniform(1.15, 1.25)

        # 3. 随机扰动 ±12%
        noise = random.uniform(0.88, 1.12)

        multiplier = boost * weekend * noise

        new_rev = round(rev * multiplier)
        new_orders = max(1, round(orders * multiplier))
        new_sv = round(sv * multiplier)
        new_cv = round(cv * multiplier)
        new_cons = round(cons * multiplier)

        updates.append((new_rev, new_orders, new_sv, new_cv, new_cons, shop_id, d_str))

    # 批量更新
    cur.executemany(
        "UPDATE merchant_shop_daily_metrics SET revenue=?, group_buy_orders=?, search_volume=?, click_volume=?, consultation_volume=? "
        "WHERE shop_id=? AND date=?",
        updates)
    conn.commit()

    # 验证
    sample = cur.execute("""
        SELECT date, SUM(revenue) FROM merchant_shop_daily_metrics
        GROUP BY date ORDER BY date LIMIT 5
    """).fetchall()
    print("注入后 GMV 日曲线 (前5天):")
    for d, gmv in sample:
        print(f"  {d}: ¥{gmv:,.0f}")

    # 看峰值
    peak = cur.execute("""
        SELECT date, SUM(revenue) AS gmv FROM merchant_shop_daily_metrics
        GROUP BY date ORDER BY gmv DESC LIMIT 3
    """).fetchall()
    print(f"\n峰值日:")
    for d, gmv in peak:
        print(f"  {d}: ¥{gmv:,.0f}")

    conn.close()
    print(f"\n完成 → {DB_PATH}")


if __name__ == "__main__":
    main()
