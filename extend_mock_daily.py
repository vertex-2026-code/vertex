"""
续灌 mock daily 数据 — 参数从 5/9-6/7 历史段实测水位精确反推
关键纠错（对比上一版的偏差）：
  - GMV 单店区间 9000-27000 → mean ≈ 18000（历史 17964 ✓）
  - AOV 反推用 125-160 → mean ≈ 142（历史 142.3 ✓）
  - search_volume 3000-5800 → mean ≈ 4400 → views ≈ 6820/店/天（历史 6866 ✓）
  - 抖动只留 ±1.5%（历史 5/30-6/7 实测 ±1.3%，无 weekend / promo 突起）
  - 删除续灌期所有 promo / weekend / month_end boost（历史看不出这些效应）

bugfix：每次 flush 都立刻 conn.commit()，避免 Ctrl+C 时 shop_buf 落后 style_buf
"""
import sqlite3, os, random
from datetime import date, timedelta

DB = f"{os.path.dirname(os.path.abspath(__file__))}/data/jiaqu.db"
END_DATE = date(2026, 7, 31)
SEED = 4242
CHUNK = 50000

HISTORY_CUTOFF = '2026-06-07'  # 这天及之前是 mock_merchant_local 写的真历史，不能动


def main():
    rng = random.Random(SEED)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 1. 清掉所有旧续灌段（6/8 起），保留历史段
    deleted_shop = cur.execute(
        f"DELETE FROM merchant_shop_daily_metrics WHERE date > '{HISTORY_CUTOFF}'"
    ).rowcount
    deleted_style = cur.execute(
        f"DELETE FROM merchant_style_daily_metrics WHERE date > '{HISTORY_CUTOFF}'"
    ).rowcount
    conn.commit()
    print(f"清除旧续灌: shop {deleted_shop:,} 行 / style {deleted_style:,} 行")

    # 2. 确认起点
    shop_max = cur.execute("SELECT MAX(date) FROM merchant_shop_daily_metrics").fetchone()[0]
    style_max = cur.execute("SELECT MAX(date) FROM merchant_style_daily_metrics").fetchone()[0]
    print(f"清除后 max date: shop={shop_max} / style={style_max}")
    start_date = date.fromisoformat(min(shop_max, style_max)) + timedelta(days=1)
    if start_date > END_DATE:
        print("已覆盖完，无需续灌")
        return
    print(f"续灌区间: {start_date} → {END_DATE}（{(END_DATE - start_date).days + 1} 天）")

    # 3. 基础数据
    shops = [r[0] for r in cur.execute("SELECT shop_id FROM merchant_profiles").fetchall()]
    catalog = cur.execute("SELECT shop_id, style_id FROM merchant_style_catalog").fetchall()
    shop_style_map = {}
    for shop_id, style_id in catalog:
        shop_style_map.setdefault(shop_id, []).append(style_id)
    print(f"基础: {len(shops)} 个 shop / {len(catalog)} 条 catalog")

    # 4. 生成
    shop_total, style_total = 0, 0
    shop_buf, style_buf = [], []
    d = start_date

    while d <= END_DATE:
        ds = d.isoformat()
        for shop_id in shops:
            noise = rng.uniform(0.985, 1.015)  # ±1.5%

            # shop 级
            gmv = int(rng.uniform(9000, 27000) * noise)               # 单店 mean ≈ 18000
            orders = max(1, int(gmv / rng.uniform(125, 160)))         # AOV mean ≈ 142
            sv = int(rng.uniform(3000, 5800) * noise)                 # mean ≈ 4400
            cv = int(sv * rng.uniform(0.30, 0.60))                    # mean ≈ 0.45 × sv
            cons = int(sv * rng.uniform(0.05, 0.15))                  # mean ≈ 0.10 × sv
            # views = sv + cv + cons ≈ 4400 × 1.55 ≈ 6820（历史 6866 ✓）
            shop_buf.append((shop_id, ds, sv, cv, cons, orders, gmv, 0, 0, 0, 0, ds))

            # style 级
            sids = shop_style_map.get(shop_id, [])
            if sids:
                chosen = rng.sample(sids, min(12, len(sids)))
                for sid in chosen:
                    s_sv = rng.randint(30, 140)                       # mean ≈ 85（历史 84 ✓）
                    s_cv = int(s_sv * rng.uniform(0.20, 0.30))        # ratio 0.24
                    so = rng.randint(0, 4)                            # mean ≈ 2（历史 2.05 ✓）
                    fav = rng.randint(0, 3)                           # mean ≈ 1.5（历史 1.59 ✓）
                    style_buf.append((shop_id, sid, ds, s_sv, s_cv, so, fav, ds))

        # 每天结束尝试 flush（一旦缓冲过大就立刻持久化）
        if len(shop_buf) >= CHUNK or len(style_buf) >= CHUNK:
            if shop_buf:
                cur.executemany(
                    "INSERT INTO merchant_shop_daily_metrics(shop_id,date,search_volume,click_volume,"
                    "consultation_volume,group_buy_orders,revenue,ad_spend,repeat_orders,refund_orders,"
                    "favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    shop_buf,
                )
                shop_total += len(shop_buf)
                shop_buf = []
            if style_buf:
                cur.executemany(
                    "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,"
                    "click_volume,group_buy_orders,favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    style_buf,
                )
                style_total += len(style_buf)
                style_buf = []
            conn.commit()
            print(f"  写入 → {ds}  shop {shop_total:,}  style {style_total:,}")

        d += timedelta(days=1)

    # 最后一波
    if shop_buf:
        cur.executemany(
            "INSERT INTO merchant_shop_daily_metrics(shop_id,date,search_volume,click_volume,"
            "consultation_volume,group_buy_orders,revenue,ad_spend,repeat_orders,refund_orders,"
            "favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            shop_buf,
        )
        shop_total += len(shop_buf)
    if style_buf:
        cur.executemany(
            "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,"
            "click_volume,group_buy_orders,favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?)",
            style_buf,
        )
        style_total += len(style_buf)
    conn.commit()
    print(f"\n完成 · shop {shop_total:,} 行 / style {style_total:,} 行")

    # 5. 自检：历史 vs 续灌应当对齐
    rows = cur.execute(f"""
      WITH daily AS (
        SELECT date,
          SUM(revenue) AS gmv,
          SUM(group_buy_orders) AS orders,
          SUM(search_volume + click_volume + consultation_volume) AS views,
          SUM(revenue) * 1.0 / NULLIF(SUM(group_buy_orders), 0) AS aov,
          SUM(group_buy_orders) * 100.0 / NULLIF(SUM(search_volume + click_volume + consultation_volume), 0) AS cvr
        FROM merchant_shop_daily_metrics
        GROUP BY date
      )
      SELECT
        CASE WHEN date <= '{HISTORY_CUTOFF}' THEN 'A·历史' ELSE 'B·新续灌' END AS seg,
        COUNT(*) AS days,
        ROUND(AVG(gmv)) AS gmv_mean,
        ROUND(AVG(orders)) AS orders_mean,
        ROUND(AVG(aov), 1) AS aov_mean,
        ROUND(AVG(views)) AS views_mean,
        ROUND(AVG(cvr), 3) AS cvr_pct
      FROM daily GROUP BY seg
    """).fetchall()
    print("\n=== 自检对齐情况 ===")
    print(f"{'seg':<10} {'days':<5} {'gmv':<12} {'orders':<10} {'aov':<8} {'views':<12} {'cvr%'}")
    for r in rows:
        print(f"{r[0]:<10} {r[1]:<5} {int(r[2]):<12,} {int(r[3]):<10,} {r[4]:<8} {int(r[5]):<12,} {r[6]}")

    conn.close()


if __name__ == "__main__":
    main()
