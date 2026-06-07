"""本地模拟商家数据，让 GMV 看板能跑起来"""
import sqlite3, os, random
from datetime import date, timedelta

random.seed(42)
DB = f"{os.path.dirname(os.path.abspath(__file__))}/data/jiaqu.db"

CATEGORIES = ["A", "B", "C", "D", "E"]
TAGS = {"A": "冰透", "B": "奶咖", "C": "碎钻", "D": "美拉德", "E": "多巴胺撞色"}
SHOPS = [f"shop_{i:03d}" for i in range(1, 21)]  # 20 shops
STYLES_PER_SHOP = 15

start = date(2026, 5, 9)
end = date(2026, 6, 7)
days = (end - start).days + 1  # 30

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 建表
cur.executescript("""
    CREATE TABLE IF NOT EXISTS merchant_shop_daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id TEXT NOT NULL, date TEXT NOT NULL,
        search_volume INTEGER, click_volume INTEGER, consultation_volume INTEGER,
        group_buy_orders INTEGER, revenue REAL, ad_spend REAL,
        repeat_orders INTEGER, refund_orders INTEGER, favorites_added INTEGER, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS merchant_style_daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id TEXT NOT NULL, style_id TEXT NOT NULL, date TEXT NOT NULL,
        search_volume INTEGER, click_volume INTEGER, group_buy_orders INTEGER,
        favorites_added INTEGER, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS merchant_style_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id TEXT NOT NULL, style_id TEXT NOT NULL, style_name TEXT NOT NULL,
        category TEXT, price INTEGER, cost INTEGER, duration_minutes INTEGER,
        search_volume_30d INTEGER, click_volume_30d INTEGER, cart_volume_30d INTEGER,
        group_buy_orders_30d INTEGER, ctr REAL, conversion_rate REAL,
        refund_orders_30d INTEGER, favorite_count_30d INTEGER, share_count_30d INTEGER,
        impression_volume_30d INTEGER, cpc REAL, gmv_30d INTEGER,
        inventory_status TEXT, launch_stage TEXT, trend_signal TEXT, title_tags TEXT,
        created_at TEXT, updated_at TEXT
    );
""")

# 清旧数据
for t in ["merchant_shop_daily_metrics", "merchant_style_daily_metrics", "merchant_style_catalog"]:
    cur.execute(f"DELETE FROM {t}")

# 仿小红书风格标题
STYLE_NAMES = [
    "冰透裸感", "清透琉璃", "奶油裸肌", "裸感丝绒", "冰晶雾面",
    "奶咖丝滑", "焦糖玛奇朵", "拿铁艺术", "草莓甜心", "蜜桃甜吻",
    "碎钻星河", "钻光涟漪", "碎钻星雨", "极光幻境", "镭射虹彩",
    "暗夜美拉德", "摩卡暗涌", "黑金铬影", "暗夜鎏金", "焦糖摩卡",
    "霓虹多巴胺", "幻彩碰撞", "撞色狂欢", "雪花秘语", "初雪轻吻",
]

cat_prices = {"A": (120, 200), "B": (150, 250), "C": (250, 400), "D": (180, 320), "E": (200, 380)}
promos = [
    ("2026-05-13", 3, 2.5), ("2026-05-21", 7, 1.8), ("2026-05-28", 4, 3.0),
    ("2026-05-30", 2, 2.3), ("2026-06-01", 3, 2.0), ("2026-06-03", 3, 2.8),
]

# 款式目录
style_rows = []
for shop in SHOPS:
    for i in range(STYLES_PER_SHOP):
        sid = f"{shop}_sku_{i+1:03d}"
        cat = CATEGORIES[i % 5]
        pmin, pmax = cat_prices[cat]
        price = random.randint(pmin, pmax)
        name = random.choice(STYLE_NAMES)
        style_rows.append((shop, sid, name, cat, price, price // 3, 45, 0, 0, 0, 0,
                           0.0, 0.0, 0, 0, 0, 0, 0.0, 0, "in_stock", "active", "stable", "", "2026-05-01", "2026-05-01"))
cur.executemany(
    "INSERT INTO merchant_style_catalog(shop_id,style_id,style_name,category,price,cost,duration_minutes,"
    "search_volume_30d,click_volume_30d,cart_volume_30d,group_buy_orders_30d,ctr,conversion_rate,"
    "refund_orders_30d,favorite_count_30d,share_count_30d,impression_volume_30d,cpc,gmv_30d,"
    "inventory_status,launch_stage,trend_signal,title_tags,created_at,updated_at) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", style_rows)

# 日指标
shop_daily = []
style_daily = []
all_styles = [(r[0], r[1], r[4]) for r in style_rows]  # shop, sid, price

d = start
while d <= end:
    ds = d.isoformat()
    for shop in SHOPS:
        # 基线 + 波动
        base_rev = random.uniform(8000, 12000)
        base_orders = random.randint(30, 60)
        base_sv = random.randint(200, 500)
        base_cv = random.randint(80, 200)
        base_cons = random.randint(15, 40)

        boost = 1.0
        for ev_date, dur, factor in promos:
            ev = date.fromisoformat(ev_date)
            if ev <= d < ev + timedelta(days=dur):
                boost = max(boost, factor)
        if d.weekday() >= 5:
            boost *= random.uniform(1.15, 1.25)
        boost *= random.uniform(0.88, 1.12)

        rev = round(base_rev * boost)
        orders = max(1, round(base_orders * boost))
        sv = round(base_sv * boost)
        cv = round(base_cv * boost)
        cons = round(base_cons * boost)

        shop_daily.append((shop, ds, sv, cv, cons, orders, rev, 0, 0, 0, 0, "2026-05-01"))

    # 每个店铺取 5 个款式写入日指标
    shop_styles = [s for s in all_styles if s[0] == shop]
    random.shuffle(shop_styles)
    for shop, sid, price in shop_styles[:5]:
        so = random.randint(2, 15)
        sd_views = random.randint(30, 150)
        sd_favs = random.randint(0, 5)
        style_daily.append((shop, sid, ds, sd_views, sd_views//2, so, sd_favs, "2026-05-01"))

    d += timedelta(days=1)

cur.executemany(
    "INSERT INTO merchant_shop_daily_metrics(shop_id,date,search_volume,click_volume,consultation_volume,group_buy_orders,revenue,ad_spend,repeat_orders,refund_orders,favorites_added,created_at) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", shop_daily)
cur.executemany(
    "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,click_volume,group_buy_orders,favorites_added,created_at) "
    "VALUES(?,?,?,?,?,?,?,?)", style_daily)

conn.commit()

# 验证
gmv = cur.execute("SELECT date, SUM(revenue) FROM merchant_shop_daily_metrics GROUP BY date ORDER BY date LIMIT 5").fetchall()
print("GMV 日曲线 (前5天):")
for d, g in gmv:
    print(f"  {d}: ¥{g:,.0f}")

total = cur.execute("SELECT SUM(revenue), COUNT(*) FROM merchant_shop_daily_metrics").fetchone()
print(f"总计: ¥{total[0]:,.0f}, {total[1]} rows")
print(f"款式日指标: {len(style_daily)} rows")
print(f"款式目录: {len(style_rows)} rows")
conn.close()
print("完成")
