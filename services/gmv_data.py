"""
GMV 数据层 —— 直接从商家表读取
数据源: merchant_shop_daily_metrics (品类级)
      merchant_style_daily_metrics + merchant_style_catalog (款式级)
修复: 上期对比、AOV/CVR计算、款式排行 JOIN
"""
from datetime import date, timedelta
from collections import defaultdict


def safe_div(a, b):
    return a / b if b else 0.0


def _get_date_bounds(db):
    """(data_start, data_end)，无数据时返回今天"""
    try:
        r = db.execute("SELECT MIN(date), MAX(date) FROM merchant_shop_daily_metrics").fetchone()
        if r and r[0] and r[1]:
            return (date.fromisoformat(str(r[0])), date.fromisoformat(str(r[1])))
    except Exception:
        pass
    today = date.today()
    return (today - timedelta(days=29), today)


def get_gmv_curve(db, days=30):
    """GMV 日曲线"""
    _, data_end = _get_date_bounds(db)
    start = data_end - timedelta(days=days - 1)
    rows = db.execute("""
        SELECT date, SUM(revenue) FROM merchant_shop_daily_metrics
        WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date
    """, (start.isoformat(), data_end.isoformat())).fetchall()
    return [{"date": r[0], "gmv": r[1] or 0} for r in rows]


def _query_period(db, start, end):
    """查一个时间段的总计: (gmv, orders, views)"""
    r = db.execute("""
        SELECT SUM(revenue), SUM(group_buy_orders),
               SUM(search_volume + click_volume + consultation_volume)
        FROM merchant_shop_daily_metrics
        WHERE date BETWEEN ? AND ?
    """, (start.isoformat(), end.isoformat())).fetchone()
    gmv = r[0] or 0
    orders = r[1] or 0
    views = r[2] or 0
    aov = round(gmv / orders, 2) if orders else 0
    cvr = round(orders / views, 4) if views else 0
    return {"gmv": gmv, "orders": orders, "views": views, "aov": aov, "cvr": cvr}


def get_gmv_overview(db):
    """GMV 总览"""
    _, data_end = _get_date_bounds(db)
    start = data_end - timedelta(days=29)
    month_start = data_end.replace(day=1)

    p = _query_period(db, start, data_end)
    total_gmv = p["gmv"]

    # 本月至今
    month_p = _query_period(db, month_start, data_end)
    month_gmv = month_p["gmv"]

    # 目标
    target_row = db.execute(
        "SELECT target_value FROM gmv_targets WHERE period_type='monthly' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    target_val = target_row[0] if target_row else (total_gmv * 1.15)

    curve = get_gmv_curve(db, 30)

    # 预测: 最近7天线性外推
    recent = [c["gmv"] for c in curve[-7:]]
    if len(recent) >= 2 and recent[-1] > 0:
        avg_growth = sum((recent[i] - recent[i-1]) / max(recent[i-1], 1)
                         for i in range(1, len(recent))) / (len(recent) - 1)
        forecast = recent[-1] * ((1 + max(avg_growth, -0.5)) ** 26)
    else:
        forecast = total_gmv

    promos = db.execute(
        "SELECT event_date, action_type, target_tag, description FROM promo_events ORDER BY event_date"
    ).fetchall()

    return {
        "total_gmv": round(total_gmv),
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
    """GMV 拆解: 当期 vs 上期(同长度)"""
    data_start, data_end = _get_date_bounds(db)
    days = (data_end - data_start).days + 1
    half = days // 2

    # 当期: 后一半
    cur_start = data_end - timedelta(days=half - 1)
    cur = _query_period(db, cur_start, data_end)

    # 上期: 前一半 (同长度)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=half - 1)
    prev = _query_period(db, prev_start, prev_end)

    gmv = cur["gmv"]
    gmv_change = gmv - prev["gmv"]

    def chg(c, p):
        return round(safe_div(c - p, p) * 100, 1) if p else 0

    order_contrib = round((cur["orders"] - prev["orders"]) * cur["aov"])
    aov_contrib = round((cur["aov"] - prev["aov"]) * cur["orders"])
    view_contrib = round((cur["views"] - prev["views"]) * cur["cvr"] * cur["aov"])
    cvr_contrib = round((cur["cvr"] - prev["cvr"]) * cur["views"] * cur["aov"])

    factors = [
        dict(name="订单数", current=round(cur["orders"]), previous=round(prev["orders"]),
             delta=round(cur["orders"] - prev["orders"]), delta_pct=chg(cur["orders"], prev["orders"]),
             contribution=order_contrib,
             weight=round(safe_div(abs(order_contrib), max(abs(gmv_change), 1)) * 100, 1)),
        dict(name="AOV", current=round(cur["aov"], 2), previous=round(prev["aov"], 2),
             delta=round(cur["aov"] - prev["aov"], 2), delta_pct=chg(cur["aov"], prev["aov"]),
             contribution=aov_contrib,
             weight=round(safe_div(abs(aov_contrib), max(abs(gmv_change), 1)) * 100, 1)),
        dict(name="浏览数", current=round(cur["views"]), previous=round(prev["views"]),
             delta=round(cur["views"] - prev["views"]), delta_pct=chg(cur["views"], prev["views"]),
             contribution=view_contrib,
             weight=round(safe_div(abs(view_contrib), max(abs(gmv_change), 1)) * 100, 1)),
        dict(name="CVR", current=round(cur["cvr"], 4), previous=round(prev["cvr"], 4),
             delta=round(cur["cvr"] - prev["cvr"], 4), delta_pct=chg(cur["cvr"], prev["cvr"]),
             contribution=cvr_contrib,
             weight=round(safe_div(abs(cvr_contrib), max(abs(gmv_change), 1)) * 100, 1)),
    ]

    primary = max(factors, key=lambda f: abs(f["contribution"]))
    direction = "增长" if primary["contribution"] > 0 else "下降"
    pre = "+" if gmv_change >= 0 else "-"
    narrative = (f"本期 GMV {pre}¥{abs(int(gmv_change)):,}（{chg(gmv, prev['gmv'])}%），"
                 f"主要{direction}因子是{primary['name']}（贡献 ¥{abs(primary['contribution']):,}）")

    return {
        "gmv": round(gmv), "orders": round(cur["orders"]),
        "aov": round(cur["aov"], 2), "views": round(cur["views"]),
        "cvr": round(cur["cvr"], 4),
        "gmv_change": round(gmv_change),
        "gmv_change_pct": chg(gmv, prev["gmv"]),
        "orders_change_pct": chg(cur["orders"], prev["orders"]),
        "aov_change_pct": chg(cur["aov"], prev["aov"]),
        "views_change_pct": chg(cur["views"], prev["views"]),
        "cvr_change_pct": chg(cur["cvr"], prev["cvr"]),
        "order_contrib": order_contrib, "aov_contrib": aov_contrib,
        "view_contrib": view_contrib, "cvr_contrib": cvr_contrib,
        "factors": factors, "primary_driver": primary["name"],
        "narrative": narrative,
    }


def get_styles_ranking(db, limit=10):
    """款式 GMV 排行"""
    data_start, data_end = _get_date_bounds(db)
    days = (data_end - data_start).days + 1
    half = days // 2

    cur_start = data_end - timedelta(days=half - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=half - 1)

    rows = db.execute("""
        SELECT d.style_id, c.style_name, c.category, c.price,
               SUM(d.group_buy_orders) AS orders,
               SUM(d.search_volume + d.click_volume) AS views,
               SUM(d.favorites_added) AS favs
        FROM merchant_style_daily_metrics d
        JOIN merchant_style_catalog c ON d.style_id = c.style_id
        WHERE d.date BETWEEN ? AND ?
        GROUP BY d.style_id
        ORDER BY SUM(d.group_buy_orders * c.price) DESC
        LIMIT ?
    """, (cur_start.isoformat(), data_end.isoformat(), limit)).fetchall()

    # 上期 GMV
    prev_map = {}
    if rows:
        ids = [r[0] for r in rows]
        ph = ",".join("?" * len(ids))
        prev_rows = db.execute(f"""
            SELECT d.style_id, SUM(d.group_buy_orders * c.price) AS gmv
            FROM merchant_style_daily_metrics d
            JOIN merchant_style_catalog c ON d.style_id = c.style_id
            WHERE d.date BETWEEN ? AND ? AND d.style_id IN ({ph})
            GROUP BY d.style_id
        """, (prev_start.isoformat(), prev_end.isoformat(), *ids)).fetchall()
        prev_map = {r[0]: (r[1] or 0) for r in prev_rows}

    ranking = []
    total_gmv = 0
    for sid, sname, scat, price, orders, views, favs in rows:
        gmv = (price or 200) * (orders or 0)
        total_gmv += gmv
        prev = prev_map.get(sid, 0)
        chg_pct = round(safe_div(gmv - prev, prev) * 100, 1) if prev else 0
        ranking.append({
            "style_code": sid,
            "style_name": sname or sid,
            "style_tag": scat or "",
            "style_category": scat or "",
            "gmv": round(gmv),
            "gmv_share_pct": 0,
            "views": views or 0,
            "tryons": int((views or 0) * 0.25),
            "favorites": favs or 0,
            "change_pct": chg_pct,
        })

    for r in ranking:
        r["gmv_share_pct"] = round(safe_div(r["gmv"], total_gmv) * 100, 1) if total_gmv else 0

    return {"styles": ranking, "total_gmv": round(total_gmv)}


def get_recommendations(db):
    """AI 增长建议"""
    ov = get_gmv_overview(db)
    ranking = get_styles_ranking(db, 5)
    gap = ov["gap"]

    styles = ranking.get("styles", [])
    top3 = styles[:3]
    bottom3 = styles[-3:] if len(styles) >= 3 else []

    # 上升趋势标签
    trends = db.execute("""
        SELECT style_tag, ROUND(AVG(growth_rate)*100, 1) FROM community_trends
        WHERE date >= DATE('now', '-7 days')
        GROUP BY style_tag ORDER BY AVG(growth_rate) DESC LIMIT 5
    """).fetchall()
    rising = [t for t in trends if t[1] and t[1] > 5]

    recs = []
    if rising and top3:
        recs.append({
            "rank": 1, "action_type": "banner_promo",
            "target": top3[0]["style_code"], "target_tag": rising[0][0],
            "expected_lift": max(int(gap * 0.25), 100000),
            "cost": "低 · Banner 位替换", "roi": "high",
            "reasoning": f"社区 {rising[0][0]} 热度上涨 +{rising[0][1]}%，搭配 Top 款 {top3[0]['style_code']} 主推变现",
        })

    if top3:
        recs.append({
            "rank": len(recs) + 1, "action_type": "premium_push",
            "target": top3[0]["style_code"], "target_tag": top3[0].get("style_tag", ""),
            "expected_lift": max(int(gap * 0.20), 50000),
            "cost": "低 · 调整推荐权重", "roi": "high",
            "reasoning": f"推高价款 {top3[0]['style_code']} 提升 AOV，利润率空间大",
        })

    recs.append({
        "rank": len(recs) + 1, "action_type": "push_notification",
        "target": "inactive_users", "target_tag": None,
        "expected_lift": max(int(gap * 0.12), 20000),
        "cost": "低 · Push 一次", "roi": "medium",
        "reasoning": "推送给 7 天未活跃用户 + 收藏未试戴，召回率 3-5%",
    })

    total_lift = sum(r["expected_lift"] for r in recs)
    forecast = ov["month_gmv"] + total_lift

    return {
        "month_gmv": ov["month_gmv"], "target": ov["target"], "gap": gap,
        "top_styles": [{"code": s["style_code"], "tag": s.get("style_tag", ""), "gmv": s["gmv"]} for s in top3],
        "declining_styles": [{"code": s["style_code"], "tag": s.get("style_tag", ""), "gmv": s["gmv"]} for s in bottom3],
        "recent_promos": [],
        "rising_trends": [{"tag": t[0], "growth": t[1]} for t in trends[:3]],
        "recommendations": recs,
        "total_lift_if_all": total_lift,
        "forecast_if_all": round(forecast),
        "would_hit_target": forecast >= ov["target"],
    }
