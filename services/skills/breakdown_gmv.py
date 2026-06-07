"""
Skill 2: breakdown_gmv — GMV 拆解归因

触发场景：运营问"GMV 涨/跌是什么原因"
计算逻辑: GMV = 订单数 × AOV = (浏览数 × CVR) × AOV
"""
from services.skills._base import (
    parse_period, prev_period, sum_metric, avg_metric, safe_div,
)


def breakdown_gmv(db, period="this_month", compare_to="last_month"):
    start, end = parse_period(period)
    p_start, p_end = prev_period(start, end)

    # 当期 — AOV 和 CVR 从 GMV/订单/浏览 实时计算，不依赖存储值
    gmv = sum_metric(db, "category_gmv", start, end)
    orders = sum_metric(db, "category_order_count", start, end)
    views = sum_metric(db, "category_view_count", start, end)
    aov = safe_div(gmv, orders)
    cvr = safe_div(orders, views)

    # 上期
    prev_gmv = sum_metric(db, "category_gmv", p_start, p_end)
    prev_orders = sum_metric(db, "category_order_count", p_start, p_end)
    prev_views = sum_metric(db, "category_view_count", p_start, p_end)
    prev_aov = safe_div(prev_gmv, prev_orders)
    prev_cvr = safe_div(prev_orders, prev_views)

    gmv_change = gmv - prev_gmv

    # 因子贡献（元）
    order_contrib = (orders - prev_orders) * aov
    aov_contrib = (aov - prev_aov) * orders
    view_contrib = (views - prev_views) * cvr * aov
    cvr_contrib = (cvr - prev_cvr) * views * aov

    factors = [
        {
            "name": "订单数",
            "current": round(orders),
            "previous": round(prev_orders),
            "delta": round(orders - prev_orders),
            "delta_pct": round(safe_div(orders - prev_orders, prev_orders) * 100, 1),
            "contribution": round(order_contrib),
            "weight": round(safe_div(abs(order_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0,
        },
        {
            "name": "AOV",
            "current": round(aov, 2),
            "previous": round(prev_aov, 2),
            "delta": round(aov - prev_aov, 2),
            "delta_pct": round(safe_div(aov - prev_aov, prev_aov) * 100, 1),
            "contribution": round(aov_contrib),
            "weight": round(safe_div(abs(aov_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0,
        },
        {
            "name": "浏览数",
            "current": round(views),
            "previous": round(prev_views),
            "delta": round(views - prev_views),
            "delta_pct": round(safe_div(views - prev_views, prev_views) * 100, 1),
            "contribution": round(view_contrib),
            "weight": round(safe_div(abs(view_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0,
        },
        {
            "name": "CVR",
            "current": round(cvr, 4),
            "previous": round(prev_cvr, 4),
            "delta": round(cvr - prev_cvr, 4),
            "delta_pct": round(safe_div(cvr - prev_cvr, prev_cvr) * 100, 1),
            "contribution": round(cvr_contrib),
            "weight": round(safe_div(abs(cvr_contrib), abs(gmv_change)) * 100, 1) if gmv_change else 0,
        },
    ]

    # 主驱动因子
    primary = max(factors, key=lambda f: abs(f["contribution"]))
    direction = "增长" if primary["contribution"] > 0 else "下降"

    narrative = (
        f"本期 GMV {'+¥' + str(int(gmv_change)) if gmv_change >= 0 else '-¥' + str(int(abs(gmv_change)))}，"
        f"主要{direction}因子是{primary['name']}（贡献 ¥{abs(primary['contribution']):,}）"
    )

    return {
        "period": period,
        "compare_to": compare_to,
        "gmv": round(gmv),
        "gmv_change": round(gmv_change),
        "gmv_change_pct": round(safe_div(gmv_change, prev_gmv) * 100, 1),
        "factors": factors,
        "primary_driver": primary["name"],
        "narrative": narrative,
    }
