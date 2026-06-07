"""GMV 数据诊断 —— 查清每个数据源有什么、缺什么"""
import sqlite3
import os

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE_DIR}/data/jiaqu.db"

def diag():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. 日期范围
    print("=" * 50)
    print("1. 日期范围")
    print("=" * 50)
    for tbl in ["merchant_shop_daily_metrics", "merchant_style_daily_metrics", "merchant_style_catalog"]:
        try:
            r = cur.execute(f"SELECT MIN(date), MAX(date), COUNT(*) FROM {tbl}").fetchone()
            print(f"  {tbl}: {r[0]} → {r[1]} ({r[2]} rows)")
        except Exception as e:
            print(f"  {tbl}: ERROR - {e}")

    # 2. 品类 GMV 预览
    print("\n" + "=" * 50)
    print("2. GMV 日曲线 (最近5天 + 峰值)")
    print("=" * 50)
    rows = cur.execute("""
        SELECT date, SUM(revenue) AS gmv, SUM(group_buy_orders) AS orders,
               SUM(search_volume+click_volume+consultation_volume) AS views
        FROM merchant_shop_daily_metrics
        GROUP BY date ORDER BY date DESC LIMIT 5
    """).fetchall()
    for d, g, o, v in reversed(rows):
        aov = g/o if o else 0
        cvr = o/v*100 if v else 0
        print(f"  {d}: GMV=¥{g:,.0f}, 订单={o}, 浏览={v:,}, AOV=¥{aov:,.0f}, CVR={cvr:.1f}%")

    total = cur.execute("SELECT SUM(revenue), SUM(group_buy_orders) FROM merchant_shop_daily_metrics").fetchone()
    print(f"\n  全量: GMV=¥{total[0]:,.0f}, 订单={total[1]}")

    # 3. 款式数据核对
    print("\n" + "=" * 50)
    print("3. 款式数据 JOIN 测试")
    print("=" * 50)
    # 款式日指标样例
    sty = cur.execute("""
        SELECT style_id, COUNT(DISTINCT date) AS days, SUM(group_buy_orders) AS orders
        FROM merchant_style_daily_metrics
        GROUP BY style_id ORDER BY orders DESC LIMIT 5
    """).fetchall()
    print("  merchant_style_daily_metrics Top 5 款式:")
    for sid, days, orders in sty:
        print(f"    {sid}: {days}天, {orders}单")

    # JOIN 测试
    join_test = cur.execute("""
        SELECT COUNT(*) FROM merchant_style_daily_metrics d
        JOIN merchant_style_catalog c ON d.style_id = c.style_id
    """).fetchone()[0]
    total_daily = cur.execute("SELECT COUNT(*) FROM merchant_style_daily_metrics").fetchone()[0]
    total_cat = cur.execute("SELECT COUNT(*) FROM merchant_style_catalog").fetchone()[0]
    print(f"\n  merchant_style_daily_metrics: {total_daily} rows")
    print(f"  merchant_style_catalog: {total_cat} rows")
    print(f"  JOIN match: {join_test} / {total_daily} ({join_test*100//max(total_daily,1)}%)")

    # 款式 GMV 排行（TOP 10）
    print("\n" + "=" * 50)
    print("4. 款式 GMV 排行 TOP 10")
    print("=" * 50)
    rank = cur.execute("""
        SELECT d.style_id, c.style_name, c.category, c.price,
               SUM(d.group_buy_orders) AS orders,
               ROUND(SUM(d.group_buy_orders * c.price)) AS gmv
        FROM merchant_style_daily_metrics d
        JOIN merchant_style_catalog c ON d.style_id = c.style_id
        GROUP BY d.style_id ORDER BY gmv DESC LIMIT 10
    """).fetchall()
    if not rank:
        print("  ⚠ 款式排行为空！检查 JOIN")
    for sid, sname, scat, price, orders, gmv in (rank or []):
        print(f"  {sid}: {sname} ({scat}) ¥{price} × {orders}单 = ¥{gmv:,}")

    # 5. 目标
    print("\n" + "=" * 50)
    print("5. GMV 目标")
    print("=" * 50)
    targets = cur.execute("SELECT * FROM gmv_targets ORDER BY id DESC LIMIT 1").fetchall()
    for t in targets:
        print(f"  {t}")

    conn.close()


if __name__ == "__main__":
    diag()
