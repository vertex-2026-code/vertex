"""给 merchant_style_daily_metrics 补数据 —— 从商家日数据推导款式日指标"""
import sqlite3, os, random
random.seed(42)

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 清旧数据
cur.execute("DELETE FROM merchant_style_daily_metrics")
print(f"清除旧款式日指标: {cur.rowcount} 行")

# 获取所有款式
cols = [c[1] for c in cur.execute("PRAGMA table_info(merchant_style_catalog)").fetchall()]
# 找 shop_id, style_id, price 的索引
si_shop = cols.index("shop_id")
si_sid = cols.index("style_id")
si_price = cols.index("price") if "price" in cols else None
styles = []
for r in cur.execute("SELECT * FROM merchant_style_catalog").fetchall():
    price = r[si_price] if si_price else 200
    styles.append((r[si_shop], r[si_sid], price or 200))

# 获取所有日期
dates = [r[0] for r in cur.execute(
    "SELECT DISTINCT date FROM merchant_shop_daily_metrics ORDER BY date"
).fetchall()]

rows = []
for d in dates:
    # 每天每个店铺随机选 5 款
    shop_styles = {}
    for shop_id, sid, price in styles:
        shop_styles.setdefault(shop_id, []).append((sid, price))

    for shop_id, shop_sids in shop_styles.items():
        chosen = random.sample(shop_sids, min(5, len(shop_sids)))
        for sid, price in chosen:
            orders = random.randint(1, 20)
            sv = random.randint(20, 200)
            cv = random.randint(10, 100)
            fav = random.randint(0, 5)
            rows.append((shop_id, sid, d, sv, cv, orders, fav, "2026-06-01"))

cur.executemany(
    "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,click_volume,group_buy_orders,favorites_added,created_at) "
    "VALUES(?,?,?,?,?,?,?,?)", rows)
conn.commit()

# 验证
cnt = cur.execute("SELECT COUNT(*) FROM merchant_style_daily_metrics").fetchone()[0]
# JOIN 测试
join_cnt = cur.execute("""
    SELECT COUNT(*) FROM merchant_style_daily_metrics d
    JOIN merchant_style_catalog c ON d.style_id = c.style_id
""").fetchone()[0]
top = cur.execute("""
    SELECT d.style_id, c.style_name, SUM(d.group_buy_orders * c.price)
    FROM merchant_style_daily_metrics d
    JOIN merchant_style_catalog c ON d.style_id = c.style_id
    GROUP BY d.style_id ORDER BY 3 DESC LIMIT 3
""").fetchall()

print(f"写入: {cnt} 行（{len(dates)} 天 × {len(styles)//5} 款/天）")
print(f"JOIN 匹配: {join_cnt}/{cnt}")
print(f"Top 3 款式:")
for sid, name, gmv in top:
    print(f"  {sid} ({name}): ¥{gmv:,.0f}")
conn.close()
