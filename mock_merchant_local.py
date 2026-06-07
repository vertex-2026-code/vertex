"""
高质量商家 mock 数据 — 有波动/周期/运营事件
生成 merchant_shop_daily_metrics + merchant_style_daily_metrics + merchant_style_catalog + merchant_profiles
"""
import sqlite3, os, random, math
from datetime import date, timedelta

random.seed(42)
DB = f"{os.path.dirname(os.path.abspath(__file__))}/data/jiaqu.db"

# ── 配置 ──
CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "南京", "西安"]
DISTRICTS = ["朝阳区", "海淀区", "浦东新区", "天河区", "南山区", "西湖区", "武侯区", "江北区", "武昌区", "鼓楼区"]
STYLE_PERSONAS = ["韩系纯欲", "日系甜酷", "法式复古", "欧美辣妹", "新中式国风", "Y2K千禧", "多巴胺撞色", "极简裸感"]
PRIMARY_STYLES = ["冰透清透", "碎钻闪耀", "猫眼磁石", "渐变晕染", "镜面金属", "磨砂雾面", "果冻质感", "法式描边"]
NAIL_SHAPES = ["杏仁形", "方圆形", "芭蕾形", "椭圆形", "尖圆形"]
COLORS = ["裸粉色", "冰透白", "酒红", "深蓝", "墨绿", "香槟金", "奶茶色", "黑金", "薰衣草紫", "珊瑚橘"]
TEXTURES = ["镜面", "磨砂", "猫眼", "果冻", "珠光", "丝绒"]

SHOP_COUNT = 30
STYLES_PER_SHOP = 20
DAYS = 30
START_DATE = date(2026, 5, 9)

# ── 运营事件 boost ──
PROMO_BOOSTS = [
    ("2026-05-13", 3, 2.8), ("2026-05-15", 2, 2.0),
    ("2026-05-21", 5, 2.2), ("2026-05-28", 4, 3.5),
    ("2026-05-30", 2, 2.5), ("2026-06-01", 3, 2.2),
    ("2026-06-03", 3, 3.0),
]

def day_boost(d: date) -> float:
    """计算某天的 GMV 倍率"""
    b = 1.0
    # 周期: 周末 +15~25%, 周一 -5%
    wd = d.weekday()
    if wd >= 5: b *= random.uniform(1.15, 1.30)
    elif wd == 0: b *= random.uniform(0.90, 0.97)
    # 运营事件
    for ev, dur, factor in PROMO_BOOSTS:
        ev_d = date.fromisoformat(ev)
        if ev_d <= d < ev_d + timedelta(days=dur):
            b = max(b, factor)
    # 月末冲刺
    if d.day >= 25: b *= random.uniform(1.05, 1.15)
    # 噪声
    b *= random.uniform(0.88, 1.12)
    return b

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 建表 (幂等)
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS merchant_profiles (
            shop_id TEXT PRIMARY KEY, shop_name TEXT, city TEXT, district TEXT,
            style TEXT, style_name TEXT, rating REAL, review_count INTEGER,
            avg_ticket INTEGER, monthly_revenue INTEGER, repeat_customer_rate REAL,
            refund_rate REAL, complaint_rate REAL, store_status TEXT,
            hero_sku_id TEXT, hero_sku_name TEXT, owner_name TEXT,
            created_at TEXT, updated_at TEXT,
            style_persona_id TEXT, style_persona_name TEXT,
            style_keywords TEXT, target_audiences TEXT
        );
        CREATE TABLE IF NOT EXISTS merchant_style_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT, style_id TEXT,
            style_name TEXT, category TEXT, price INTEGER, cost INTEGER,
            duration_minutes INTEGER, search_volume_30d INTEGER, click_volume_30d INTEGER,
            cart_volume_30d INTEGER, group_buy_orders_30d INTEGER, ctr REAL,
            conversion_rate REAL, refund_orders_30d INTEGER, favorite_count_30d INTEGER,
            share_count_30d INTEGER, impression_volume_30d INTEGER, cpc REAL, gmv_30d INTEGER,
            inventory_status TEXT, launch_stage TEXT, trend_signal TEXT, title_tags TEXT,
            created_at TEXT, updated_at TEXT,
            style_persona_id TEXT, style_persona_name TEXT,
            primary_style TEXT, secondary_style TEXT,
            nail_shape TEXT, nail_length TEXT, primary_color TEXT, accent_colors TEXT,
            transparency TEXT, texture_finish TEXT, base_coat TEXT,
            core_techniques TEXT, support_techniques TEXT,
            element_tags TEXT, occasion_tags TEXT, complexity_tier TEXT,
            merchant_generation_mode TEXT, design_prompt TEXT,
            style_image_url TEXT, style_image_prompt TEXT,
            style_image_status TEXT, style_image_error TEXT
        );
        CREATE TABLE IF NOT EXISTS merchant_shop_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT, date TEXT,
            search_volume INTEGER, click_volume INTEGER, consultation_volume INTEGER,
            group_buy_orders INTEGER, revenue INTEGER, ad_spend INTEGER,
            repeat_orders INTEGER, refund_orders INTEGER, favorites_added INTEGER, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS merchant_style_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT, style_id TEXT, date TEXT,
            search_volume INTEGER, click_volume INTEGER, group_buy_orders INTEGER,
            favorites_added INTEGER, created_at TEXT
        );
    """)

    # 清旧数据
    for t in ["merchant_profiles", "merchant_style_catalog",
              "merchant_shop_daily_metrics", "merchant_style_daily_metrics"]:
        cur.execute(f"DELETE FROM {t}")

    # ── 1. 商家 profiles ──
    shops = []
    for i in range(1, SHOP_COUNT + 1):
        sid = f"shop_{i:03d}"
        city = CITIES[i % len(CITIES)]
        persona = STYLE_PERSONAS[i % len(STYLE_PERSONAS)]
        ticket = random.randint(120, 380)
        revenue = random.randint(30000, 120000)
        shops.append((sid, f"{city}{persona}美甲·{DISTRICTS[i%len(DISTRICTS)]}店",
                       city, DISTRICTS[i % len(DISTRICTS)], persona[:2], persona,
                       round(random.uniform(4.0, 5.0), 1), random.randint(10, 500),
                       ticket, revenue,
                       round(random.uniform(0.2, 0.6), 2), round(random.uniform(0.01, 0.08), 2),
                       round(random.uniform(0.0, 0.03), 2), "active",
                       "", "", f"店主{i}", "2026-05-01", "2026-05-01",
                       f"persona_{i}", persona, persona, "年轻女性,职场白领"))
    cur.executemany(
        "INSERT INTO merchant_profiles(shop_id,shop_name,city,district,style,style_name,rating,review_count,"
        "avg_ticket,monthly_revenue,repeat_customer_rate,refund_rate,complaint_rate,store_status,"
        "hero_sku_id,hero_sku_name,owner_name,created_at,updated_at,"
        "style_persona_id,style_persona_name,style_keywords,target_audiences) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", shops)

    # ── 2. 款式 catalog ──
    style_rows = []
    for shop_id, _, _, _, _, persona, *_ in shops:
        for j in range(1, STYLES_PER_SHOP + 1):
            sid = f"{shop_id}_sku_{j:03d}"
            ps = PRIMARY_STYLES[j % len(PRIMARY_STYLES)]
            price = random.randint(128, 428)
            shape = NAIL_SHAPES[j % len(NAIL_SHAPES)]
            color = COLORS[(j + random.randint(0, 3)) % len(COLORS)]
            tex = TEXTURES[j % len(TEXTURES)]
            style_rows.append((
                shop_id, sid, f"{color}{ps}", persona[:2], price, price // 3, 45,
                0, 0, 0, 0, 0.0, 0.0, 0, 0, 0, 0, 0.0, 0,
                "in_stock", "active", "stable", "", "2026-05-01", "2026-05-01",
                f"persona_{j}", persona, ps, ps, shape, "中长",
                color, "", "80%", tex, "底胶", "手绘", "贴钻", "[]", "[]",
                "中度", "AI", "", "", "", "done", ""
            ))
    cols = [c[1] for c in cur.execute("PRAGMA table_info(merchant_style_catalog)").fetchall() if c[1] != 'id']
    ph = ",".join("?" * len(cols))
    cur.executemany(
        f"INSERT INTO merchant_style_catalog({','.join(cols)}) VALUES({ph})",
        style_rows)

    # ── 3. 店铺日指标 ──
    shop_daily = []
    d = START_DATE
    for day_i in range(DAYS):
        ds = d.isoformat()
        for shop_id, _, _, _, _, persona, *_ in shops:
            boost = day_boost(d)
            # 基础: 每家店日 GMV 基线 8k-18k
            base_gmv = random.uniform(8000, 18000)
            gmv = int(base_gmv * boost)
            orders = max(1, int(gmv / random.uniform(150, 350)))
            sv = int(random.uniform(200, 600) * boost)
            cv = int(sv * random.uniform(0.3, 0.6))
            cons = int(sv * random.uniform(0.05, 0.15))
            shop_daily.append((shop_id, ds, sv, cv, cons, orders, gmv, 0, 0, 0, 0, ds))
        d += timedelta(days=1)
    cur.executemany(
        "INSERT INTO merchant_shop_daily_metrics(shop_id,date,search_volume,click_volume,consultation_volume,"
        "group_buy_orders,revenue,ad_spend,repeat_orders,refund_orders,favorites_added,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", shop_daily)

    # ── 4. 款式日指标 ──
    style_daily = []
    all_styles = [(r[0], r[1]) for r in cur.execute("SELECT shop_id, style_id FROM merchant_style_catalog").fetchall()]
    d = START_DATE
    for day_i in range(DAYS):
        ds = d.isoformat()
        shop_day_styles = {}
        for shop_id, sid in all_styles:
            shop_day_styles.setdefault(shop_id, []).append(sid)
        for shop_id, sids in shop_day_styles.items():
            chosen = random.sample(sids, min(6, len(sids)))
            for sid in chosen:
                so = random.randint(1, 12)
                sv = random.randint(20, 200)
                fav = random.randint(0, 4)
                style_daily.append((shop_id, sid, ds, sv, sv // 2, so, fav, ds))
        d += timedelta(days=1)
    cur.executemany(
        "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,click_volume,"
        "group_buy_orders,favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?)", style_daily)

    conn.commit()

    # ── 验证 ──
    total_gmv = cur.execute("SELECT SUM(revenue) FROM merchant_shop_daily_metrics").fetchone()[0]
    daily = cur.execute("SELECT date, SUM(revenue) FROM merchant_shop_daily_metrics GROUP BY date ORDER BY date").fetchall()
    peak = max(daily, key=lambda x: x[1])
    valley = min(daily, key=lambda x: x[1])
    print(f"商家: {SHOP_COUNT} | 款式: {len(style_rows)} | 城市: {len(CITIES)} | 风格人设: {len(STYLE_PERSONAS)}")
    print(f"店铺日指标: {len(shop_daily)} rows | 款式日指标: {len(style_daily)} rows")
    print(f"总 GMV: ¥{total_gmv:,.0f} | 日均: ¥{total_gmv/DAYS:,.0f}")
    print(f"峰值: {peak[0]} ¥{peak[1]:,.0f} | 谷值: {valley[0]} ¥{valley[1]:,.0f}")
    conn.close()
    print("完成")

if __name__ == "__main__":
    main()
