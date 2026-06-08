"""
续灌 mock daily 数据到 END_DATE（默认 2030/12/31）
- 不动 merchant_profiles / merchant_style_catalog / promo_events / community_trends
- 自动检测 max(date)：当天行数 < 平均 50% 视为残留，DELETE 当天后从当天起重写
                     否则从 max(date)+1 起灌
- 只 INSERT 历史区间外的数据，不会动到已落数的完整日
- 分块 commit，避免单次事务过大
"""
import sqlite3, os, random
from datetime import date, timedelta

DB = f"{os.path.dirname(os.path.abspath(__file__))}/data/jiaqu.db"
END_DATE = date(2030, 12, 31)
SEED = 4242  # 与 mock_merchant_local.py 的 seed=42 隔离，避免影响未来对照
CHUNK = 50000


def day_boost(d, rng):
    """无 promo 的纯 cycle + 噪声 boost，让续灌段曲线和历史段水位接得上"""
    b = 1.0
    wd = d.weekday()
    if wd >= 5:
        b *= rng.uniform(1.15, 1.30)
    elif wd == 0:
        b *= rng.uniform(0.90, 0.97)
    if d.day >= 25:
        b *= rng.uniform(1.05, 1.15)
    b *= rng.uniform(0.88, 1.12)
    return b


def detect_start_date(cur):
    """找到要从哪天开始续灌
    - 看 shop / style 两张表的 max date，取较小值作为锚
    - 该锚日行数 < 历史平均 50% → 视为残留，清掉，从锚日开始重写
    - 否则从锚日 + 1 天开始
    """
    shop_max = cur.execute("SELECT MAX(date) FROM merchant_shop_daily_metrics").fetchone()[0]
    style_max = cur.execute("SELECT MAX(date) FROM merchant_style_daily_metrics").fetchone()[0]
    if shop_max is None:
        raise SystemExit("merchant_shop_daily_metrics 为空，先跑 mock_merchant_local.py 建基础数据")
    anchor = min(shop_max, style_max)

    shop_anchor_rows = cur.execute(
        "SELECT COUNT(*) FROM merchant_shop_daily_metrics WHERE date=?", (anchor,)
    ).fetchone()[0]
    avg_row = cur.execute(
        "SELECT COUNT(*)*1.0/NULLIF(COUNT(DISTINCT date),0) "
        "FROM merchant_shop_daily_metrics WHERE date < ?", (anchor,)
    ).fetchone()[0] or 0

    if avg_row and shop_anchor_rows < avg_row * 0.5:
        print(f"⚠️  {anchor} 仅 {shop_anchor_rows} 行 < 历史均 {avg_row:.0f} × 50%，判定残留并清除")
        cur.execute("DELETE FROM merchant_shop_daily_metrics WHERE date=?", (anchor,))
        cur.execute("DELETE FROM merchant_style_daily_metrics WHERE date=?", (anchor,))
        return date.fromisoformat(anchor)
    return date.fromisoformat(anchor) + timedelta(days=1)


def main():
    rng = random.Random(SEED)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    start_date = detect_start_date(cur)
    if start_date > END_DATE:
        print(f"现有数据已覆盖到 {start_date - timedelta(days=1)}，超过 END_DATE={END_DATE}，无需续灌")
        return

    n_days = (END_DATE - start_date).days + 1
    print(f"续灌区间: {start_date} → {END_DATE}（{n_days} 天）")

    shops = [r[0] for r in cur.execute("SELECT shop_id FROM merchant_profiles").fetchall()]
    catalog = cur.execute("SELECT shop_id, style_id FROM merchant_style_catalog").fetchall()
    shop_style_map = {}
    for shop_id, style_id in catalog:
        shop_style_map.setdefault(shop_id, []).append(style_id)
    print(f"基础数据: {len(shops)} 个 shop / {len(catalog)} 条 catalog")

    # 跟齐历史的 style/day/shop 抽样数（诊断显示约 12，比脚本默认 6 多一倍）
    sample_per_day = 12

    shop_total = 0
    style_total = 0
    d = start_date
    shop_buf, style_buf = [], []

    while d <= END_DATE:
        ds = d.isoformat()
        for shop_id in shops:
            boost = day_boost(d, rng)
            base_gmv = rng.uniform(8000, 18000)
            gmv = int(base_gmv * boost)
            orders = max(1, int(gmv / rng.uniform(150, 350)))
            sv = int(rng.uniform(200, 600) * boost)
            cv = int(sv * rng.uniform(0.3, 0.6))
            cons = int(sv * rng.uniform(0.05, 0.15))
            shop_buf.append((shop_id, ds, sv, cv, cons, orders, gmv, 0, 0, 0, 0, ds))

            sids = shop_style_map.get(shop_id, [])
            if sids:
                chosen = rng.sample(sids, min(sample_per_day, len(sids)))
                for sid in chosen:
                    so = rng.randint(1, 12)
                    s_sv = rng.randint(20, 200)
                    fav = rng.randint(0, 4)
                    style_buf.append((shop_id, sid, ds, s_sv, s_sv // 2, so, fav, ds))

        if len(shop_buf) >= CHUNK:
            cur.executemany(
                "INSERT INTO merchant_shop_daily_metrics(shop_id,date,search_volume,click_volume,"
                "consultation_volume,group_buy_orders,revenue,ad_spend,repeat_orders,refund_orders,"
                "favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                shop_buf,
            )
            shop_total += len(shop_buf)
            shop_buf = []
        if len(style_buf) >= CHUNK:
            cur.executemany(
                "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,"
                "click_volume,group_buy_orders,favorites_added,created_at) VALUES(?,?,?,?,?,?,?,?)",
                style_buf,
            )
            style_total += len(style_buf)
            style_buf = []
            conn.commit()
            print(f"  写入进度 → {ds}  shop_daily 累计 {shop_total:,}  style_daily 累计 {style_total:,}")

        d += timedelta(days=1)

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

    new_shop_max = cur.execute("SELECT MAX(date) FROM merchant_shop_daily_metrics").fetchone()[0]
    new_style_max = cur.execute("SELECT MAX(date) FROM merchant_style_daily_metrics").fetchone()[0]
    shop_total_rows = cur.execute("SELECT COUNT(*) FROM merchant_shop_daily_metrics").fetchone()[0]
    style_total_rows = cur.execute("SELECT COUNT(*) FROM merchant_style_daily_metrics").fetchone()[0]
    print()
    print(f"完成 · 本次新增 shop {shop_total:,} / style {style_total:,}")
    print(f"shop_daily  max date = {new_shop_max}  总行数 {shop_total_rows:,}")
    print(f"style_daily max date = {new_style_max}  总行数 {style_total_rows:,}")
    conn.close()


if __name__ == "__main__":
    main()
