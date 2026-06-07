"""
GMV 数据层 —— 直接从商家表读，不经过 operation_metrics
数据源: merchant_shop_daily_metrics (品类级)
      merchant_style_daily_metrics + merchant_style_catalog (款式级)
"""
from datetime import date, timedelta

TODAY = date.today()

CATEGORY_NAMES = {
    "A": "简约清透", "B": "甜美可爱", "C": "华丽璀璨",
    "D": "暗黑酷飒", "E": "潮流前卫",
}


def safe_div(a, b):
    return a / b if b else 0.0


def date_range(db, period="30d"):
    """返回 (start, end) date 对象"""
    r = db.execute("SELECT MIN(date), MAX(date) FROM merchant_shop_daily_metrics").fetchone()
    if not r or not r[0]:
        return TODAY, TODAY
    data_end = date.fromisoformat(r[1])
    if period == "today":
        return (data_end, data_end)
    if period == "7d":
        return (data_end - timedelta(days=6), data_end)
    if period == "30d":
        return (data_end - timedelta(days=29), data_end)
    if period == "month":
        return (data_end.replace(day=1), data_end)
    if period == "all":
        return (date.fromisoformat(r[0]), data_end)
    return (data_end - timedelta(days=29), data_end)


def get_gmv_curve(db, days=30):
    """30 天 GMV 日曲线"""
    end = date.fromisoformat(
        db.execute("SELECT MAX(date) FROM merchant_shop_daily_metrics").fetchone()[0]
    )
    start = end - timedelta(days=days - 1)
    rows = db.execute("""
        SELECT date, SUM(revenue) FROM merchant_shop_daily_metrics
        WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date
    """, (start.isoformat(), end.isoformat())).fetchall()
    return [{"date": r[0], "gmv": r[1] or 0} for r in rows]


def get_gmv_overview(db):
    """GMV 总览: 当期GMV + 目标 + 曲线"""
    start, end = date_range(db, "30d")
    month_start = end.replace(day=1)

    total = db.execute("""
        SELECT SUM(revenue) FROM merchant_shop_daily_metrics
        WHERE date BETWEEN ? AND ?
    """, (start.isoformat(), end.isoformat())).fetchone()[0] or 0

    month_gmv = db.execute("""
        SELECT SUM(revenue) FROM merchant_shop_daily_metrics
        WHERE date BETWEEN ? AND ?
    """, (month_start.isoformat(), end.isoformat())).fetchone()[0] or 0

    target = db.execute("""
        SELECT target_value FROM gmv_targets
        WHERE period_type='monthly' ORDER BY id DESC LIMIT 1
    """).fetchone()
    target_val = target[0] if target else (total * 1.15)

    curve = get_gmv_curve(db, 30)

    # 预测：最近 7 天线性外推
    recent = [c["gmv"] for c in curve[-7:]]
    if len(recent) >= 2:
        avg_growth = sum((recent[i] - recent[i-1]) / max(recent[i-1], 1)
                         for i in range(1, len(recent))) / (len(recent) - 1)
        forecast = recent[-1] * ((1 + avg_growth) ** 26)
    else:
        forecast = total

    promos = db.execute("""
        SELECT event_date, action_type, target_tag, description
        FROM promo_events ORDER BY event_date
    """).fetchall()

    return {
        "total_gmv": round(total),
        "month_gmv": round(month_gmv),
        "target": round(target_val),
        "completion_pct": round(safe_div(month_gmv, target_val) * 100, 1),
        "gap": round(target_val - month_gmv),
        "forecast_end_of_month": round(min(forecast, target_val * 2)),
        "forecast_pct": round(safe_div(forecast, target_val) * 100, 1),
        "curve": curve,
        "promo_events": [{"date": r[0], "action_type": r[1],
                          "target_tag": r[2], "description": r[3]} for r in promos],
    }


def get_gmv_breakdown(db):
    """GMV 拆解: 订单×AOV = 浏览×CVR"""
    start, end = date_range(db, "30d")
    prev_start = start - timedelta(days=30)
    prev_end = start - timedelta(days=1)

    def query(ps, pe):
        r = db.execute("""
            SELECT SUM(revenue), SUM(group_buy_orders),
                   SUM(search_volume + click_volume + consultation_volume)
            FROM merchant_shop_daily_metrics
            WHERE date BETWEEN ? AND ?
        """, (ps.isoformat(), pe.isoformat())).fetchone()
        gmv = r[0] or 0
        orders = r[1] or 0
        views = r[2] or 1
        aov = round(gmv / orders, 2) if orders else 0
        cvr = round(orders / views, 4) if views else 0
        return gmv, orders, aov, views, cvr

    gmv, orders, aov, views, cvr = query(start, end)
    prev_gmv, prev_orders, prev_aov, prev_views, prev_cvr = query(prev_start, prev_end)

    gmv_change = gmv - prev_gmv

    def chg(cur, prev):
        return round(safe_div(cur - prev, prev) * 100, 1) if prev else 0

    order_contrib = round((orders - prev_orders) * aov)
    aov_contrib = round((aov - prev_aov) * orders)
    view_contrib = round((views - prev_views) * cvr * aov)
    cvr_contrib = round((cvr - prev_cvr) * views * aov)

    factors = [
        dict(name="订单数", current=round(orders), previous=round(prev_orders),
             delta=round(orders - prev_orders), delta_pct=chg(orders, prev_orders),
             contribution=order_contrib,
             weight=round(safe_div(abs(order_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0),
        dict(name="AOV", current=round(aov, 2), previous=round(prev_aov, 2),
             delta=round(aov - prev_aov, 2), delta_pct=chg(aov, prev_aov),
             contribution=aov_contrib,
             weight=round(safe_div(abs(aov_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0),
        dict(name="浏览数", current=round(views), previous=round(prev_views),
             delta=round(views - prev_views), delta_pct=chg(views, prev_views),
             contribution=view_contrib,
             weight=round(safe_div(abs(view_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0),
        dict(name="CVR", current=round(cvr, 4), previous=round(prev_cvr, 4),
             delta=round(cvr - prev_cvr, 4), delta_pct=chg(cvr, prev_cvr),
             contribution=cvr_contrib,
             weight=round(safe_div(abs(cvr_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0),
    ]

    primary = max(factors, key=lambda f: abs(f["contribution"]))
    direction = "增长" if primary["contribution"] > 0 else "下降"

    return {
        "gmv": round(gmv), "orders": round(orders), "aov": round(aov, 2),
        "views": round(views), "cvr": round(cvr, 4),
        "gmv_change": round(gmv_change), "gmv_change_pct": chg(gmv, prev_gmv),
        "orders_change_pct": chg(orders, prev_orders),
        "aov_change_pct": chg(aov, prev_aov),
        "views_change_pct": chg(views, prev_views),
        "cvr_change_pct": chg(cvr, prev_cvr),
        "order_contrib": order_contrib, "aov_contrib": aov_contrib,
        "view_contrib": view_contrib, "cvr_contrib": cvr_contrib,
        "factors": factors, "primary_driver": primary["name"],
        "narrative": (f"本期 GMV {'+¥' + str(int(gmv_change)) if gmv_change >= 0 else '-¥' + str(int(abs(gmv_change)))}，"
                      f"主要{direction}因子是{primary['name']}（贡献 ¥{abs(primary['contribution']):,}）"),
    }


def get_styles_ranking(db, limit=10):
    """款式 GMV 排行: 从 merchant_style_daily_metrics + catalog 聚合"""
    start, end = date_range(db, "30d")
    prev_start, prev_end = start - timedelta(days=30), start - timedelta(days=1)

    # 当期
    rows = db.execute("""
        SELECT d.style_id, c.style_name, c.category, c.price,
               SUM(d.group_buy_orders) AS orders,
               SUM(d.search_volume + d.click_volume) AS views,
               SUM(d.favorites_added) AS favs
        FROM merchant_style_daily_metrics d
        JOIN merchant_style_catalog c ON d.style_id = c.style_id
        WHERE d.date BETWEEN ? AND ?
        GROUP BY d.style_id ORDER BY SUM(d.group_buy_orders * c.price) DESC
        LIMIT ?
    """, (start.isoformat(), end.isoformat(), limit)).fetchall()

    # 上期
    prev_map = {}
    if rows:
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        prev_rows = db.execute(f"""
            SELECT style_id, SUM(group_buy_orders * c.price) AS gmv
            FROM merchant_style_daily_metrics d
            JOIN merchant_style_catalog c ON d.style_id = c.style_id
            WHERE d.date BETWEEN ? AND ? AND d.style_id IN ({placeholders})
            GROUP BY d.style_id
        """, (prev_start.isoformat(), prev_end.isoformat(), *ids)).fetchall()
        prev_map = {r[0]: r[1] or 0 for r in prev_rows}

    total_gmv = sum((r[3] or 200) * (r[4] or 0) for r in rows)
    ranking = []
    for sid, sname, scat, price, orders, views, favs in rows:
        gmv = (price or 200) * (orders or 0)
        prev = prev_map.get(sid, 0)
        chg_pct = round(safe_div(gmv - prev, prev) * 100, 1) if prev else 0
        ranking.append({
            "style_code": sid,
            "style_name": sname or sid,
            "style_tag": scat or "",
            "style_category": scat or "",
            "gmv": round(gmv),
            "gmv_share_pct": round(safe_div(gmv, total_gmv) * 100, 1) if total_gmv else 0,
            "views": views or 0,
            "tryons": int((views or 0) * 0.25),
            "favorites": favs or 0,
            "change_pct": chg_pct,
        })

    return {"styles": ranking, "total_gmv": round(total_gmv)}


def get_recommendations(db):
    """AI 增长建议"""
    ov = get_gmv_overview(db)
    ranking = get_styles_ranking(db, 5)
    gap = ov["gap"]

    # 上升标签
    trends = db.execute("""
        SELECT style_tag, ROUND(AVG(growth_rate)*100, 1) FROM community_trends
        WHERE date >= DATE('now', '-7 days')
        GROUP BY style_tag ORDER BY AVG(growth_rate) DESC LIMIT 5
    """).fetchall()

    recs = []
    rising = [t[0] for t in trends if t[1] and t[1] > 5]

    if rising and ranking["styles"]:
        recs.append({
            "rank": 1, "action_type": "banner_promo",
            "target": ranking["styles"][0]["style_code"],
            "target_tag": rising[0],
            "expected_lift": int(gap * 0.25),
            "cost": "低 · Banner 位替换",
            "roi": "high",
            "reasoning": f"社区 {rising[0]} 热度上涨 +{trends[0][1]}%，搭配 Top 款主推变现",
        })

    recs.append({
        "rank": len(recs) + 1, "action_type": "premium_push",
        "target": ranking["styles"][0]["style_code"] if ranking["styles"] else "",
        "target_tag": ranking["styles"][0]["style_tag"] if ranking["styles"] else "",
        "expected_lift": int(gap * 0.20),
        "cost": "低 · 调整推荐权重",
        "roi": "high",
        "reasoning": f"推高价款提升 AOV，利润率空间大，预计 +¥{int(gap * 0.20):,}",
    })

    recs.append({
        "rank": len(recs) + 1, "action_type": "push_notification",
        "target": "inactive_users",
        "expected_lift": int(gap * 0.12),
        "cost": "低 · Push 一次",
        "roi": "medium",
        "reasoning": f"推送给 7 天未活跃用户 + 收藏未试戴，召回率 3-5%，+¥{int(gap * 0.12):,}",
    })

    total_lift = sum(r["expected_lift"] for r in recs)
    forecast = ov["month_gmv"] + total_lift

    return {
        "month_gmv": ov["month_gmv"], "target": ov["target"], "gap": gap,
        "top_styles": [{"code": s["style_code"], "tag": s["style_tag"],
                         "gmv": s["gmv"]} for s in ranking["styles"][:3]],
        "declining_styles": [{"code": s["style_code"], "tag": s["style_tag"],
                               "gmv": s["gmv"]} for s in ranking["styles"][-3:]],
        "recent_promos": [],
        "rising_trends": [{"tag": t[0], "growth": t[1]} for t in trends[:3]],
        "recommendations": recs,
        "total_lift_if_all": total_lift,
        "forecast_if_all": round(forecast),
        "would_hit_target": forecast >= ov["target"],
    }
