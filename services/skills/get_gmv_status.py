"""
Skill 1: get_gmv_status — GMV 现状速读

触发场景：运营问"今天/本周/本月 GMV 怎么样"
输入: period (today/this_week/this_month), compare_to (yesterday/last_week/last_month/target)
输出: current_gmv, target_gmv, completion_rate, gap, vs_compare, days_remaining, projected_final, status
"""
from services.skills._base import (
    parse_period, prev_period, days_remaining, sum_metric, safe_div, TODAY, query_one,
)


def get_gmv_status(db, period="this_month", compare_to="target"):
    start, end = parse_period(period)

    # 当期 GMV
    current_gmv = sum_metric(db, "category_gmv", start, end)

    # 目标
    target_row = query_one(
        db,
        "SELECT target_value FROM gmv_targets WHERE period_type='monthly' AND period_start <= ? AND period_end >= ?",
        (start.isoformat(), end.isoformat()),
    )
    target_gmv = target_row.get("target_value", 0) if target_row else 0

    # 对比值
    vs_compare = 0
    vs_compare_pct = 0.0
    if compare_to == "target":
        vs_compare = target_gmv
        vs_compare_pct = safe_div(current_gmv, target_gmv) * 100
    else:
        cmp_map = {
            "yesterday": ("yesterday",),
            "last_week": ("last_week",),
            "last_month": ("last_month",),
        }
        if compare_to in cmp_map:
            c_start, c_end = parse_period(cmp_map[compare_to][0])
        else:
            c_start, c_end = prev_period(start, end)
        vs_compare = sum_metric(db, "category_gmv", c_start, c_end)
        vs_compare_pct = safe_div(current_gmv - vs_compare, vs_compare) * 100

    # 完成率
    completion_rate = round(safe_div(current_gmv, target_gmv) * 100, 1) if target_gmv else 0
    gap = target_gmv - current_gmv

    # 剩余天数 + 预测
    remaining = days_remaining(end)
    days_elapsed = (end - start).days + 1
    daily_avg = safe_div(current_gmv, days_elapsed)
    projected_final = round(current_gmv + daily_avg * remaining) if remaining > 0 else current_gmv

    # 状态判定
    if target_gmv:
        if completion_rate >= 95:
            status = "on_track"
        elif completion_rate >= 80:
            status = "at_risk"
        else:
            status = "off_track"
    else:
        status = "unknown"

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "current_gmv": round(current_gmv),
        "target_gmv": round(target_gmv) if target_gmv else None,
        "completion_rate": completion_rate,
        "gap": round(gap),
        "vs_compare": round(vs_compare),
        "vs_compare_pct": round(vs_compare_pct, 1),
        "days_remaining": remaining,
        "projected_final": round(projected_final),
        "status": status,
    }
