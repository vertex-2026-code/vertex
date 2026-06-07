"""
商家数据分析工具 —— 先看数据长什么样，再重新融合到 GMV 看板
Step 1: 分析（只读，不写）
Step 2: 融合（清空 operation_metrics 后重写）
"""
import sqlite3
import os

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"


def analyze(conn):
    """只读分析，搞清楚数据结构和分布"""
    cur = conn.cursor()

    # 1. 各表概览
    tables = [
        "merchant_accounts", "merchant_profiles", "merchant_style_catalog",
        "merchant_shop_daily_metrics", "merchant_style_daily_metrics",
    ]
    print("=" * 60)
    print("STEP 1: 数据概览")
    print("=" * 60)
    for t in tables:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n{t}: {cnt} rows")
        print(f"  columns: {', '.join(cols)}")

    # 2. 店铺日指标抽样
    print("\n" + "=" * 60)
    print("STEP 2: 店铺日指标抽样 (merchant_shop_daily_metrics)")
    print("=" * 60)
    rows = cur.execute("""
        SELECT date, COUNT(DISTINCT shop_id) AS shops,
               SUM(revenue) AS total_revenue,
               SUM(group_buy_orders) AS total_orders,
               SUM(search_volume + click_volume + consultation_volume) AS total_views,
               ROUND(AVG(CAST(revenue AS REAL) / NULLIF(group_buy_orders, 0)), 0) AS avg_item_price
        FROM merchant_shop_daily_metrics
        GROUP BY date ORDER BY date LIMIT 5
    """).fetchall()
    for r in rows:
        aov = r[2] / r[3] if r[3] else 0
        cvr = r[3] / r[4] * 100 if r[4] else 0
        print(f"  {r[0]}: {r[1]}店, revenue=¥{r[2]:,.0f}, orders={r[3]}, views={r[4]:,}, AOV=¥{aov:,.0f}, CVR={cvr:.1f}%")

    # 日期范围
    dr = cur.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM merchant_shop_daily_metrics").fetchone()
    print(f"\n  日期范围: {dr[0]} → {dr[1]} ({dr[2]} 天)")

    # 3. 款式日指标抽样
    print("\n" + "=" * 60)
    print("STEP 3: 款式日指标抽样 (merchant_style_daily_metrics)")
    print("=" * 60)
    rows = cur.execute("""
        SELECT date, COUNT(DISTINCT style_id) AS styles,
               SUM(group_buy_orders) AS total_orders,
               SUM(favorites_added) AS total_favs,
               SUM(search_volume + click_volume) AS total_views
        FROM merchant_style_daily_metrics
        GROUP BY date ORDER BY date LIMIT 5
    """).fetchall()
    for r in rows:
        cvr = r[2] / r[4] * 100 if r[4] else 0
        print(f"  {r[0]}: {r[1]} 款, orders={r[2]}, favs={r[3]}, views={r[4]:,}, CVR={cvr:.1f}%")

    # 4. 款式目录：category 分布 + 价格分布
    print("\n" + "=" * 60)
    print("STEP 4: 款式目录 (merchant_style_catalog)")
    print("=" * 60)
    rows = cur.execute("""
        SELECT category, COUNT(*) AS cnt, ROUND(AVG(price), 0) AS avg_price,
               MIN(price) AS min_p, MAX(price) AS max_p
        FROM merchant_style_catalog
        GROUP BY category ORDER BY cnt DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} 款, avg ¥{r[2]}, range ¥{r[3]}-¥{r[4]}")

    # 价格分位数
    prices = [r[0] for r in cur.execute("SELECT price FROM merchant_style_catalog WHERE price > 0").fetchall()]
    prices.sort()
    n = len(prices)
    for pct, label in [(50, "P50"), (75, "P75"), (90, "P90"), (95, "P95"), (99, "P99")]:
        idx = int(n * pct / 100)
        print(f"  {label}: ¥{prices[idx]:,.0f}")

    # 5. 每个店铺的收入规模
    print("\n" + "=" * 60)
    print("STEP 5: 店铺收入分布")
    print("=" * 60)
    rows = cur.execute("""
        SELECT shop_id, SUM(revenue) AS total_rev, COUNT(*) AS days,
               ROUND(SUM(revenue) / COUNT(*), 0) AS daily_avg
        FROM merchant_shop_daily_metrics
        GROUP BY shop_id ORDER BY total_rev DESC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r[0]}: ¥{r[1]:,.0f} / {r[2]}天 = 日均 ¥{r[3]:,.0f}")

    # 6. GMV 趋势（7 天滑动）
    print("\n" + "=" * 60)
    print("STEP 6: GMV 日趋势 (最近10天)")
    print("=" * 60)
    rows = cur.execute("""
        SELECT date, SUM(revenue) AS gmv, SUM(group_buy_orders) AS orders,
               COUNT(DISTINCT shop_id) AS shops
        FROM merchant_shop_daily_metrics
        GROUP BY date ORDER BY date DESC LIMIT 10
    """).fetchall()
    for r in reversed(rows):
        print(f"  {r[0]}: GMV=¥{r[1]:,.0f}, orders={r[2]}, {r[3]}店")


def fuse(conn):
    """基于分析结果，重新生成 operation_metrics"""
    cur = conn.cursor()
    dr = cur.execute("SELECT MIN(date), MAX(date) FROM merchant_shop_daily_metrics").fetchone()
    start, end = dr

    # 清空
    cur.execute("DELETE FROM operation_metrics WHERE metric_date BETWEEN ? AND ?", (start, end))

    # 品类级: 按日聚合
    cat_rows = cur.execute("""
        SELECT date, SUM(revenue), SUM(group_buy_orders),
               SUM(search_volume + click_volume + consultation_volume)
        FROM merchant_shop_daily_metrics GROUP BY date ORDER BY date
    """).fetchall()

    # 款式级: 按日+款式聚合 (当日 Top 20)
    sty_rows = cur.execute("""
        SELECT d.date, d.style_id, SUM(d.search_volume + d.click_volume) AS views,
               SUM(d.group_buy_orders) AS orders, SUM(d.favorites_added) AS favs,
               c.price, c.category, c.style_name
        FROM merchant_style_daily_metrics d
        JOIN merchant_style_catalog c ON d.style_id = c.style_id
        GROUP BY d.date, d.style_id ORDER BY d.date, orders DESC
    """).fetchall()

    # 款式目录: style_id → (tag, price)
    style_meta = {}
    for sid, scat, sname, sprice in cur.execute(
        "SELECT style_id, category, style_name, price FROM merchant_style_catalog"
    ).fetchall():
        style_meta[sid] = (scat or sname or sid, sprice or 200)

    # 按日期分组款式
    from collections import defaultdict
    daily = defaultdict(list)
    for d, sid, views, orders, favs, price, cat, sname in sty_rows:
        views, orders, favs, price = (x or 0 for x in (views, orders, favs, price))
        tag, _ = style_meta.get(sid, (cat or sname or sid, price))
        est_gmv = orders * price
        daily[d].append((sid, tag, price, views, orders, favs, est_gmv, cat or ""))

    inserts = []
    total_gmv = 0

    for d, gmv, orders, views in cat_rows:
        gmv, orders, views = (x or 0 for x in (gmv, orders, views))
        total_gmv += gmv
        if views == 0: views = 1
        aov = round(gmv / orders, 2) if orders else 0.0
        cvr = round(orders / views, 4)

        # 品类指标
        for mt, mv in [("category_gmv", gmv), ("category_order_count", orders),
                        ("category_aov", aov), ("category_view_count", views),
                        ("category_cvr", cvr)]:
            inserts.append((d, mt, mv, None, None, None, None))

        # 款式 Top 20
        day_top = sorted(daily.get(d, []), key=lambda x: -x[7])[:20]
        for sid, tag, price, s_views, s_orders, s_favs, s_gmv, scat in day_top:
            if s_views == 0: s_views = 1
            s_cvr = round(s_orders / s_views, 4)
            s_tryon = int(s_views * 0.25)
            for mt, mv in [("style_gmv", s_gmv), ("style_view_count", s_views),
                            ("style_cvr", s_cvr), ("style_tryon_count", s_tryon),
                            ("style_favorite_count", s_favs)]:
                inserts.append((d, mt, mv, sid, tag, None, scat))

    cur.executemany(
        "INSERT INTO operation_metrics(metric_date, metric_type, metric_value, style_code, style_tag, color_family, style_category) "
        "VALUES(?,?,?,?,?,?,?)", inserts)
    conn.commit()

    # 目标: 按日均 × 30 天 × 1.1 增长
    days = len(cat_rows)
    daily_avg = total_gmv / days if days else 0
    target = round(daily_avg * 30 * 1.10)
    cur.execute("DELETE FROM gmv_targets")
    cur.execute("INSERT INTO gmv_targets VALUES(?,?,?,?,?,NULL)",
                (None, "monthly", start, end, target))
    conn.commit()

    # 验证
    check = cur.execute("""
        SELECT metric_type, metric_value FROM operation_metrics
        WHERE metric_date = (SELECT MAX(metric_date) FROM operation_metrics WHERE metric_type='category_gmv')
        AND metric_type IN ('category_gmv','category_order_count','category_aov')
    """).fetchall()
    vals = {r[0]: r[1] for r in check}
    aov_check = vals.get("category_gmv", 0) / vals.get("category_order_count", 1)

    print(f"\n融合完成:")
    print(f"  品类 GMV: ¥{total_gmv:,.0f} ({days}天)")
    print(f"  日均 GMV: ¥{daily_avg:,.0f}")
    print(f"  月目标: ¥{target:,.0f}")
    print(f"  款式 Top 20/天 × 5 指标 = ~{days * 20 * 5} 行")
    print(f"  最新日 AOV 验证: store=¥{vals.get('category_aov', 0)}, calc=¥{aov_check:,.0f}")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if mode == "fuse":
        fuse(conn)
    else:
        analyze(conn)
    conn.close()
