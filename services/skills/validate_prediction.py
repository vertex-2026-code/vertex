"""
Skill 7: validate_prediction — 预测准确性验证

触发场景：运营周复盘 / 问"上周 AI 建议效果如何"
数据源: promo_events 的 expected_gmv_lift vs actual_gmv_lift
"""
from services.skills._base import parse_period, query_all, safe_div


def validate_prediction(db, period="this_month"):
    start, end = parse_period(period)

    promos = query_all(
        db,
        "SELECT event_date, action_type, target_tag, target_style, description, "
        "expected_gmv_lift, actual_gmv_lift FROM promo_events "
        "WHERE event_date BETWEEN ? AND ? ORDER BY event_date",
        (start.isoformat(), end.isoformat()),
    )

    if not promos:
        return {
            "period": period,
            "predictions_total": 0,
            "predictions_hit": 0,
            "accuracy": None,
            "details": [],
            "narrative": f"{start} 至 {end} 无运营动作记录，无法验证预测",
        }

    details = []
    hits = 0
    total_expected = 0
    total_actual = 0

    for p in promos:
        expected = p.get("expected_gmv_lift") or 0
        actual = p.get("actual_gmv_lift") or 0
        total_expected += expected
        total_actual += (actual or 0)

        if expected > 0 and actual is not None:
            acc = min(100, round(safe_div(actual, expected) * 100, 1))
            if acc >= 70:
                verdict = "accurate"
                hits += 1
            elif acc >= 40:
                verdict = "partial"
            else:
                verdict = "miss"
        elif actual is None:
            acc = None
            verdict = "pending"
        else:
            acc = 0
            verdict = "miss"

        details.append({
            "action": p.get("description", ""),
            "action_type": p.get("action_type", ""),
            "target_tag": p.get("target_tag", ""),
            "expected_gmv_lift": round(expected),
            "actual_gmv_lift": round(actual) if actual else None,
            "accuracy_pct": acc,
            "verdict": verdict,
        })

    total = len(promos)
    accuracy = round(safe_div(hits, total) * 100, 1)

    if accuracy >= 80:
        narrative = f"预测表现优秀：{total} 次预测中 {hits} 次准确（{accuracy}%），AI 运营建议可靠"
    elif accuracy >= 50:
        narrative = f"预测表现一般：{total} 次预测中 {hits} 次准确（{accuracy}%），建议结合人工判断"
    else:
        narrative = f"预测表现较差：仅 {hits}/{total} 准确（{accuracy}%），建议检查数据质量或调整模型"

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "predictions_total": total,
        "predictions_hit": hits,
        "accuracy": accuracy,
        "total_expected_lift": round(total_expected),
        "total_actual_lift": round(total_actual) if total_actual else 0,
        "details": details,
        "narrative": narrative,
    }
