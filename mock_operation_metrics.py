"""
Task 2.5 · GMV 驱动运营看板 — mock 数据生成器
反推法：先设计理想 GMV 曲线 → 反推订单数/AOV/浏览/CVR → 分配到款式
幂等：同日期范围重复跑会先 DELETE 再 INSERT
"""
import sqlite3
import random
import os
from datetime import date, timedelta

random.seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"

START = date(2026, 5, 6)
END = date(2026, 6, 4)
DAYS = (END - START).days + 1  # 30

# ── 款式 → (category, tag, base_weight) ──────────────────────
STYLE_META = {
    # A 简约清透 → 冰透 + 奶油裸色
    "nail_01": ("A", "冰透", 1.0),
    "nail_10": ("A", "冰透", 0.8),
    "nail_13": ("A", "冰透", 0.6),
    "nail_14": ("A", "奶油裸色", 0.7),
    "nail_23": ("A", "奶油裸色", 0.5),
    # B 甜美可爱 → 奶咖 + 草莓甜心
    "nail_02": ("B", "奶咖", 1.0),
    "nail_05": ("B", "奶咖", 0.8),
    "nail_15": ("B", "奶咖", 0.6),
    "nail_16": ("B", "草莓甜心", 0.7),
    "nail_25": ("B", "草莓甜心", 0.5),
    # C 华丽璀璨 → 碎钻 + 镭射极光
    "nail_06": ("C", "碎钻", 1.0),
    "nail_11": ("C", "碎钻", 0.8),
    "nail_17": ("C", "碎钻", 0.6),
    "nail_18": ("C", "镭射极光", 0.7),
    "nail_19": ("C", "镭射极光", 0.5),
    # D 暗黑酷飒 → 美拉德 + 暗黑金属
    "nail_03": ("D", "美拉德", 1.0),
    "nail_08": ("D", "美拉德", 0.8),
    "nail_09": ("D", "暗黑金属", 0.7),
    "nail_12": ("D", "暗黑金属", 0.5),
    # E 潮流前卫 → 雪花 + 多巴胺撞色
    "nail_04": ("E", "多巴胺撞色", 1.0),
    "nail_07": ("E", "多巴胺撞色", 0.9),
    "nail_20": ("E", "多巴胺撞色", 0.7),
    "nail_21": ("E", "雪花", 0.6),
    "nail_22": ("E", "雪花", 0.5),
    "nail_24": ("E", "雪花", 0.4),
}

# ── 运营动作（6 个 promo events）──────────────────────
PROMOS = [
    ("2026-05-13", "banner_promo", "冰透", "nail_01", 2.5, 3, 80000,
     "AI 识别冰透热度上升 +135%，主推 nail_01"),
    ("2026-05-21", "merchant_invite", "美拉德", None, 1.0, 7, 120000,
     "AI 识别美拉德暗红色缺口，邀请商家上新"),
    ("2026-05-28", "banner_promo", "美拉德", "nail_03", 3.0, 4, 150000,
     "新上美拉德款主推"),
    ("2026-05-30", "category_campaign", None, None, 2.3, 2, 100000,
     "夏日清凉节品类活动"),
    ("2026-06-01", "push_notification", "多巴胺撞色", None, 1.8, 3, 50000,
     "推送给收藏用户"),
    ("2026-06-03", "banner_promo", "多巴胺撞色", "nail_04", 2.8, 3, 80000,
     "多巴胺爆款进入主推位"),
]


def promo_boost(tag, style_code, d):
    """该款式在该日期的运营 boost 倍率"""
    boost = 1.0
    for ev_date, action, tgt_tag, tgt_style, factor, dur, *_ in PROMOS:
        ev = date.fromisoformat(ev_date)
        if ev <= d < ev + timedelta(days=dur):
            if tgt_tag and tag == tgt_tag:
                boost *= factor
            if tgt_style and style_code == tgt_style:
                boost *= factor
    return boost


def trend_heat(tag, d, trend_cache):
    """从 community_trends 获取该 tag 在当日的相对热度 (1.0 基准)"""
    key = (d.isoformat(), tag)
    if key in trend_cache:
        growth = trend_cache[key]
        return 1.0 + growth  # growth_rate ≈ -0.16 ~ 0.25, 映射为 0.84 ~ 1.25
    return 1.0


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── 幂等：清除同日期范围数据 ──
    cur.execute("DELETE FROM operation_metrics WHERE metric_date BETWEEN ? AND ?",
                (START.isoformat(), END.isoformat()))
    cur.execute("DELETE FROM gmv_targets")
    cur.execute("DELETE FROM promo_events")

    # ── 加载社区趋势热度 ──
    trend_cache = {}
    rows = cur.execute(
        "SELECT date, style_tag, growth_rate FROM community_trends"
    ).fetchall()
    for r_date, tag, growth in rows:
        trend_cache[(r_date, tag)] = growth

    # ── Step 1: 设计每日品类 GMV 曲线 ──
    daily_category = {}  # date → {gmv, aov, is_campaign}

    all_dates = []
    d = START
    while d <= END:
        all_dates.append(d)
        d += timedelta(days=1)

    for d in all_dates:
        # 基线 25-30k
        gmv = random.uniform(25000, 30000)

        # 周末 +15%
        if d.weekday() >= 5:
            gmv *= 1.15

        # 运营 boost（取最大值，防止多活动叠加失控）
        boost = 1.0
        for ev_date, action, tgt_tag, tgt_style, factor, dur, *_ in PROMOS:
            ev = date.fromisoformat(ev_date)
            if ev <= d < ev + timedelta(days=dur):
                boost = max(boost, factor)
        gmv *= boost

        # 随机扰动 ±8%
        gmv *= random.uniform(0.92, 1.08)

        # 判断是否高价日（有 banner/category promo）
        is_campaign = any(
            date.fromisoformat(ev_date) <= d < date.fromisoformat(ev_date) + timedelta(days=dur)
            for ev_date, action, *_, dur, _ in PROMOS
            if action in ("banner_promo", "category_campaign")
        )

        aov = random.uniform(230, 280) if is_campaign else random.uniform(180, 220)
        daily_category[d] = {"gmv": round(gmv), "aov": round(aov, 2), "is_campaign": is_campaign}

    # ── Step 2 & 3: 反推并分配到款式 ──
    category_rows = []
    style_rows = []

    for d in all_dates:
        cat = daily_category[d]
        gmv = cat["gmv"]
        aov = cat["aov"]
        order_count = max(1, int(gmv / aov))

        # CVR
        cvr = random.uniform(0.05, 0.07) if cat["is_campaign"] else random.uniform(0.03, 0.045)
        views = max(order_count, int(order_count / cvr))
        actual_cvr = round(order_count / views, 4)

        # 品类级写入
        for mtype, val in [
            ("category_gmv", gmv),
            ("category_order_count", order_count),
            ("category_aov", aov),
            ("category_view_count", views),
            ("category_cvr", actual_cvr),
        ]:
            category_rows.append((d.isoformat(), mtype, val))

        # ── 款式分配 ──
        weights = {}
        for style_code, (cat_code, tag, base_w) in STYLE_META.items():
            w = base_w * trend_heat(tag, d, trend_cache) * promo_boost(tag, style_code, d)
            weights[style_code] = w

        total_w = sum(weights.values())

        for style_code, (cat_code, tag, base_w) in STYLE_META.items():
            w = weights[style_code]
            share = w / total_w

            s_gmv = round(gmv * share)
            s_views = max(1, int(views * share))
            s_cvr = round(random.uniform(0.03, 0.08), 4)
            s_orders = max(0, int(s_views * s_cvr))
            s_tryon = max(0, int(s_views * random.uniform(0.15, 0.35)))
            s_fav = max(0, int(s_tryon * random.uniform(0.08, 0.25)))

            for mtype, val in [
                ("style_gmv", s_gmv),
                ("style_view_count", s_views),
                ("style_cvr", s_cvr),
                ("style_tryon_count", s_tryon),
                ("style_favorite_count", s_fav),
            ]:
                style_rows.append((d.isoformat(), mtype, val, style_code, tag, None, cat_code))

    # ── 写入 ──
    all_rows = category_rows + style_rows
    cur.executemany(
        "INSERT INTO operation_metrics(metric_date, metric_type, metric_value, style_code, style_tag, color_family, style_category) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        [(d, t, v, None, None, None, None) for d, t, v in category_rows] +
        [(d, t, v, sc, st, None, cat) for d, t, v, sc, st, _, cat in style_rows],
    )

    # ── GMV 目标 ──
    cur.execute(
        "INSERT INTO gmv_targets(period_type, period_start, period_end, target_value) VALUES(?, ?, ?, ?)",
        ("monthly", "2026-06-01", "2026-06-30", 1500000),
    )

    # ── 运营动作 ──
    for ev_date, action, tgt_tag, tgt_style, factor, dur, lift, desc in PROMOS:
        cur.execute(
            "INSERT INTO promo_events(event_date, action_type, target_tag, target_style, boost_factor, duration_days, expected_gmv_lift, description) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ev_date, action, tgt_tag, tgt_style, factor, dur, lift, desc),
        )

    conn.commit()

    # ── 验证 ──
    total_gmv = cur.execute(
        "SELECT SUM(metric_value) FROM operation_metrics WHERE metric_type='category_gmv'"
    ).fetchone()[0]
    row_cnt = cur.execute("SELECT COUNT(*) FROM operation_metrics").fetchone()[0]

    print(f"品类 GMV 累计: ¥{total_gmv:,.0f}")
    print(f"日均 GMV: ¥{total_gmv/DAYS:,.0f}")
    print(f"总行数: {row_cnt}")
    print(f"日期范围: {START} → {END} ({DAYS} 天)")
    print(f"已写入 → {DB_PATH}")

    # 拆解一致性检查
    check = cur.execute(
        "SELECT metric_type, metric_value FROM operation_metrics "
        "WHERE metric_date='2026-06-03' AND metric_type IN ('category_gmv','category_order_count','category_aov')"
    ).fetchall()
    if check:
        vals = {r[0]: r[1] for r in check}
        gmv_v = vals.get("category_gmv", 0)
        orders_v = vals.get("category_order_count", 0)
        aov_v = vals.get("category_aov", 0)
        derived = orders_v * aov_v
        err = abs(gmv_v - derived) / gmv_v * 100 if gmv_v else 0
        print(f"2026-06-03 验证: GMV={gmv_v}, orders×AOV={orders_v}×{aov_v}={derived:.0f}, 误差={err:.1f}%")

    conn.close()


if __name__ == "__main__":
    main()
