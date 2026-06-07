"""
Skill 4: detect_gmv_risk — GMV 风险预警

触发场景：运营问"有什么风险"或 OpenClaw 主动巡检
风险类型: declining_hero / supply_gap / cvr_drop
"""
from datetime import date, timedelta
from services.skills._base import (
    sum_metric, avg_metric, safe_div, query_all, STYLE_META, CAT_TO_TAGS, TODAY,
)


def detect_risks(db, lookback_days=7, risk_threshold=0.15):
    risks = []

    end = TODAY
    start = end - timedelta(days=lookback_days - 1)

    # ── 1. declining_hero: Top 5 款连续 3 天 GMV 下降超过阈值 ──
    style_gmv_total = {}
    d = start
    all_style_dates = set()
    while d <= end:
        for code in STYLE_META:
            all_style_dates.add(code)
        d += timedelta(days=1)

    top5_codes = []
    for code in STYLE_META:
        gmv = sum_metric(db, "style_gmv", start, end, style_code=code)
        style_gmv_total[code] = gmv
    top5 = sorted(style_gmv_total.items(), key=lambda x: -x[1])[:5]

    for code, total_gmv in top5:
        daily = query_all(
            db,
            "SELECT metric_date, metric_value FROM operation_metrics "
            "WHERE metric_type='style_gmv' AND style_code=? AND metric_date BETWEEN ? AND ? "
            "ORDER BY metric_date",
            (code, start.isoformat(), end.isoformat()),
        )
        if len(daily) < 3:
            continue
        decline_streak = 0
        for i in range(1, len(daily)):
            if daily[i]["metric_value"] < daily[i-1]["metric_value"] * (1 - risk_threshold):
                decline_streak += 1
            else:
                decline_streak = 0
            if decline_streak >= 3:
                cat, tag, _ = STYLE_META[code]
                avg_daily = sum_metric(db, "style_gmv", start, end, style_code=code) / lookback_days
                risks.append({
                    "type": "declining_hero",
                    "target": code,
                    "tag": tag,
                    "issue": f"Top 款 {code} 连续 {decline_streak} 天 GMV 下降超过 {int(risk_threshold*100)}%",
                    "projected_loss": round(avg_daily * decline_streak * 0.15),
                    "suggestion": f"检查 {tag} 标签下替代款，准备替换主推位",
                })
                break

    # ── 2. supply_gap: 外部热度高但平台款式少 ──
    trend_rows = query_all(
        db,
        "SELECT style_tag, AVG(growth_rate) AS avg_growth FROM community_trends "
        "WHERE date >= ? GROUP BY style_tag HAVING AVG(growth_rate) > 0.05",
        (start.isoformat(),),
    )
    for tr in trend_rows:
        tag = tr["style_tag"]
        tag_gmv = sum_metric(db, "style_gmv", start, end)
        # tag_gmv 不是直接可查的，用各款汇总
        tag_total = 0
        tag_styles = [c for c, (_, t, _) in STYLE_META.items() if t == tag]
        for sc in tag_styles:
            tag_total += sum_metric(db, "style_gmv", start, end, style_code=sc)

        all_gmv = sum_metric(db, "category_gmv", start, end)
        tag_share = safe_div(tag_total, all_gmv)

        if tag_share < 0.03 and len(tag_styles) < 4:
            risks.append({
                "type": "supply_gap",
                "target": tag,
                "tag": tag,
                "issue": f"社区 {tag} 热度高（avg growth +{round(tr['avg_growth']*100,1)}%）但平台仅 {len(tag_styles)} 款，GMV 占比 {round(tag_share*100,1)}%",
                "projected_loss": round(all_gmv * 0.05),
                "suggestion": f"邀请商家上 {tag} 新款，或在现有款中加大推荐权重",
            })

    # ── 3. cvr_drop: 某标签 CVR 显著低于品类均值 ──
    avg_cvr = avg_metric(db, "category_cvr", start, end)
    for tag in set(t for _, (_, t, _) in STYLE_META.items()):
        tag_cvr_rows = query_all(
            db,
            "SELECT AVG(metric_value) AS cvr FROM operation_metrics "
            "WHERE metric_type='style_cvr' AND style_tag=? AND metric_date BETWEEN ? AND ?",
            (tag, start.isoformat(), end.isoformat()),
        )
        if not tag_cvr_rows or tag_cvr_rows[0]["cvr"] is None:
            continue
        tag_cvr = tag_cvr_rows[0]["cvr"]
        if avg_cvr > 0 and tag_cvr < avg_cvr * 0.7:
            risks.append({
                "type": "cvr_drop",
                "target": tag,
                "tag": tag,
                "issue": f"{tag} CVR {round(tag_cvr*100,2)}% 低于品类均值 {round(avg_cvr*100,2)}% 超 30%",
                "projected_loss": round(sum_metric(db, "style_gmv", start, end) * 0.1),
                "suggestion": f"优化 {tag} 款式图或降低推荐权重，CVR 回暖后再推",
            })

    return {
        "lookback_days": lookback_days,
        "risk_threshold": risk_threshold,
        "risk_count": len(risks),
        "risks": risks,
    }
