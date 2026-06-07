"""
融合商家 mock 数据到 operation_metrics
数据源: merchant_shop_daily_metrics → 品类级（category_*）
      merchant_style_daily_metrics + merchant_style_catalog → 款式级（style_*）
标签: 直接使用 merchant_style_catalog.category 原值，不做映射
幂等: 同日期范围先 DELETE 再 INSERT
"""
import sqlite3
import os
from collections import defaultdict

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. 日期范围
    r = cur.execute("SELECT MIN(date), MAX(date) FROM merchant_shop_daily_metrics").fetchone()
    if not r or not r[0]:
        print("错误: merchant_shop_daily_metrics 为空")
        conn.close()
        return
    start_str, end_str = r
    print(f"日期范围: {start_str} → {end_str}")

    # 2. 清除旧数据
    cur.execute("DELETE FROM operation_metrics WHERE metric_date BETWEEN ? AND ?", (start_str, end_str))
    print(f"清除: {cur.rowcount} 行")

    # 3. 品类级聚合
    cat_rows = cur.execute("""
        SELECT date, SUM(revenue), SUM(group_buy_orders),
               SUM(search_volume + click_volume + consultation_volume)
        FROM merchant_shop_daily_metrics GROUP BY date ORDER BY date
    """).fetchall()

    # 4. 款式级聚合
    sty_rows = cur.execute("""
        SELECT date, style_id, SUM(search_volume), SUM(click_volume),
               SUM(group_buy_orders), SUM(favorites_added)
        FROM merchant_style_daily_metrics GROUP BY date, style_id ORDER BY date
    """).fetchall()

    # 5. 款式目录 → {style_id: (category_tag, price)}
    style_meta = {}
    for sid, sname, scat, sprice in cur.execute(
        "SELECT style_id, style_name, category, price FROM merchant_style_catalog"
    ).fetchall():
        tag = (scat or sname or sid)  # 直接用商家 category，空则用 style_name
        style_meta[sid] = (tag, sprice or 200)

    # 6. 按日期组织，每天取 Top 15
    daily_styles = defaultdict(list)
    for d, sid, sv, cv2, gbo, fav in sty_rows:
        sv, cv2, gbo, fav = (x or 0 for x in (sv, cv2, gbo, fav))
        meta = style_meta.get(sid, (sid, 200))
        tag, price = meta
        views = sv + cv2
        est_gmv = gbo * price
        daily_styles[d].append((sid, tag, price, views, gbo, fav, est_gmv))

    # 7. 构建写入数据
    cat_inserts = []
    sty_inserts = []
    total_gmv = 0

    for d, gmv, orders, views in cat_rows:
        gmv, orders, views = (x or 0 for x in (gmv, orders, views))
        if views == 0: views = 1
        aov = round(gmv / orders, 2) if orders else 0
        cvr = round(orders / views, 4)
        total_gmv += gmv

        cat_inserts.extend([
            (d, "category_gmv", gmv, None, None, None, None),
            (d, "category_order_count", orders, None, None, None, None),
            (d, "category_aov", aov, None, None, None, None),
            (d, "category_view_count", views, None, None, None, None),
            (d, "category_cvr", cvr, None, None, None, None),
        ])

        day_styles = sorted(daily_styles.get(d, []), key=lambda x: -x[6])[:15]
        for sid, tag, price, s_views, s_orders, s_fav, s_gmv in day_styles:
            if s_views == 0: s_views = 1
            s_cvr = round(s_orders / s_views, 4)
            s_tryon = int(s_views * 0.3)
            sty_inserts.extend([
                (d, "style_gmv", s_gmv, sid, tag, None, tag),
                (d, "style_view_count", s_views, sid, tag, None, tag),
                (d, "style_cvr", s_cvr, sid, tag, None, tag),
                (d, "style_tryon_count", s_tryon, sid, tag, None, tag),
                (d, "style_favorite_count", s_fav, sid, tag, None, tag),
            ])

    # 8. 写入
    cur.executemany(
        "INSERT INTO operation_metrics(metric_date, metric_type, metric_value, style_code, style_tag, color_family, style_category) "
        "VALUES(?,?,?,?,?,?,?)",
        cat_inserts + sty_inserts,
    )
    conn.commit()

    # 9. 目标
    target = round(total_gmv * 1.15)
    cur.execute("DELETE FROM gmv_targets")
    cur.execute("INSERT INTO gmv_targets(period_type, period_start, period_end, target_value) VALUES(?,?,?,?)",
                ("monthly", start_str, end_str, target))
    conn.commit()

    # 10. 报告
    days = len(cat_rows)
    tag_dist = cur.execute("""
        SELECT style_tag, COUNT(DISTINCT style_code) AS styles
        FROM operation_metrics WHERE metric_type='style_gmv' AND style_code IS NOT NULL
        GROUP BY style_tag ORDER BY styles DESC LIMIT 15
    """).fetchall()
    print(f"品类 GMV: ¥{total_gmv:,.0f}（{days} 天，日均 ¥{total_gmv/days:,.0f}）")
    print(f"款式行数: {len(sty_inserts)}（每天 Top 15 款 × 5 指标）")
    print(f"月目标: ¥{target:,.0f}")
    print(f"标签分布: {[(t, c) for t, c in tag_dist]}")
    print(f"→ {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
