"""
融合商家 mock 数据到 operation_metrics
数据源: merchant_shop_daily_metrics → 品类级（category_*）
      merchant_style_daily_metrics + merchant_style_catalog → 款式级（style_*）
幂等: 同日期范围先 DELETE 再 INSERT
"""
import sqlite3
import os

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"

CAT_TO_TAGS = {
    "A": ["冰透", "奶油裸色"],
    "B": ["奶咖", "草莓甜心"],
    "C": ["碎钻", "镭射极光"],
    "D": ["美拉德", "暗黑金属"],
    "E": ["多巴胺撞色", "雪花"],
}


def guess_cat(style_name, category, price):
    n = (style_name or "").lower()
    c = (category or "").lower()
    if any(w in c for w in ["清透", "裸", "冰", "简约"]): return "A"
    if any(w in c for w in ["可爱", "甜", "粉", "奶", "咖"]): return "B"
    if any(w in c for w in ["华丽", "钻", "镭射", "璀璨", "闪"]): return "C"
    if any(w in c for w in ["暗黑", "酷", "金属", "棕"]): return "D"
    if any(w in c for w in ["潮流", "撞色", "雪花", "前卫"]): return "E"
    if price and price < 150: return "A"
    if price and price < 220: return "B"
    if price and price >= 300: return "C"
    return "D"


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

    # 3. 品类级聚合（一次查询）
    cat_rows = cur.execute("""
        SELECT date, SUM(revenue), SUM(group_buy_orders),
               SUM(search_volume + click_volume + consultation_volume)
        FROM merchant_shop_daily_metrics GROUP BY date ORDER BY date
    """).fetchall()

    # 4. 款式级聚合（一次查询，按 date + style_id）
    sty_rows = cur.execute("""
        SELECT date, style_id, SUM(search_volume), SUM(click_volume),
               SUM(group_buy_orders), SUM(favorites_added)
        FROM merchant_style_daily_metrics GROUP BY date, style_id ORDER BY date
    """).fetchall()

    # 5. 款式目录映射
    style_meta = {}
    for sid, sname, scat, sprice in cur.execute(
        "SELECT style_id, style_name, category, price FROM merchant_style_catalog"
    ).fetchall():
        style_meta[sid] = (guess_cat(sname, scat, sprice), sname or sid, sprice or 200)

    # 6. 组织款式数据: date → [(style_id, cat, tag, views, orders, fav)]
    from collections import defaultdict
    daily_styles = defaultdict(list)
    for d, sid, sv, cv2, gbo, fav in sty_rows:
        sv, cv2, gbo, fav = (x or 0 for x in (sv, cv2, gbo, fav))
        cat, sname, price = style_meta.get(sid, ("D", sid, 200))
        tags = CAT_TO_TAGS.get(cat, ["美拉德", "暗黑金属"])
        tag = tags[hash(sid) % len(tags)]
        views = sv + cv2
        est_gmv = gbo * price
        daily_styles[d].append((sid, cat, tag, sname, price, views, gbo, fav, est_gmv))

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

        # 取当日 Top 15 款式（按 est_gmv）
        day_styles = sorted(daily_styles.get(d, []), key=lambda x: -x[8])[:15]
        for sid, cat, tag, sname, price, s_views, s_orders, s_fav, s_gmv in day_styles:
            if s_views == 0: s_views = 1
            s_cvr = round(s_orders / s_views, 4)
            s_tryon = int(s_views * 0.3)
            sty_inserts.extend([
                (d, "style_gmv", s_gmv, sid, tag, None, cat),
                (d, "style_view_count", s_views, sid, tag, None, cat),
                (d, "style_cvr", s_cvr, sid, tag, None, cat),
                (d, "style_tryon_count", s_tryon, sid, tag, None, cat),
                (d, "style_favorite_count", s_fav, sid, tag, None, cat),
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

    days = len(cat_rows)
    print(f"品类 GMV: ¥{total_gmv:,.0f}（{days} 天，日均 ¥{total_gmv/days:,.0f}）")
    print(f"款式行数: {len(sty_inserts)}（每天 Top 15 款 × 5 指标）")
    print(f"总写入: {len(cat_inserts) + len(sty_inserts)} 行")
    print(f"月目标: ¥{target:,.0f}")
    print(f"→ {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
