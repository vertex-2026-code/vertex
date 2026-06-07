"""
Skill: shop_ranking — 商家月营收 / 复购 / 退款率 Top/Bottom 排行

数据源: merchant_profiles + merchant_shop_daily_metrics
"""


def shop_ranking(db, metric="monthly_revenue", direction="top", limit=10, city=""):
    """按指定指标对 1005 商家做排行

    metric:    monthly_revenue / repeat_customer_rate / refund_rate /
               complaint_rate / rating / avg_ticket
    direction: top（高到低） / bottom（低到高）
    limit:     10 / 20 / 50
    city:      可选 ↔ 单城（北京/上海/深圳/杭州/广州…），空则全国
    """
    allow_metric = {
        "monthly_revenue", "repeat_customer_rate", "refund_rate",
        "complaint_rate", "rating", "avg_ticket",
    }
    if metric not in allow_metric:
        metric = "monthly_revenue"
    order = "DESC" if direction == "top" else "ASC"
    limit = max(3, min(int(limit or 10), 100))

    where = ""
    params = []
    if city:
        where = "WHERE city = ?"
        params.append(city)

    rows = db.execute(f"""
        SELECT shop_id, shop_name, city, district, style, style_name,
               style_persona_name, rating, review_count, avg_ticket,
               monthly_revenue, repeat_customer_rate, refund_rate,
               complaint_rate, store_status
        FROM merchant_profiles
        {where}
        ORDER BY {metric} {order}
        LIMIT ?
    """, (*params, limit)).fetchall()

    shops = [{
        "shop_id": r[0], "shop_name": r[1], "city": r[2], "district": r[3],
        "style": r[4], "style_name": r[5], "style_persona_name": r[6],
        "rating": r[7], "review_count": r[8], "avg_ticket": r[9],
        "monthly_revenue": r[10], "repeat_customer_rate": r[11],
        "refund_rate": r[12], "complaint_rate": r[13], "store_status": r[14],
    } for r in rows]

    overall = db.execute(f"""
        SELECT AVG({metric}), MIN({metric}), MAX({metric}), COUNT(*)
        FROM merchant_profiles {where}
    """, params).fetchone()

    return {
        "metric": metric,
        "direction": direction,
        "limit": limit,
        "city": city or "全国",
        "shops": shops,
        "benchmark": {
            "avg": overall[0],
            "min": overall[1],
            "max": overall[2],
            "total_shops": overall[3],
        },
    }
