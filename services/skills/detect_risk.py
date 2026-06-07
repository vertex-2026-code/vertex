"""
Skill 4: detect_gmv_risk — GMV 风险预警
"""
from services.gmv_data import date_range, safe_div, get_styles_ranking


def detect_risks(db, lookback_days=7, risk_threshold=0.15):
    risks = []
    ranking = get_styles_ranking(db, 10)
    styles = ranking.get("styles", [])
    total_gmv = ranking.get("total_gmv", 0)

    # supply_gap: 外部热度高但平台款式少
    trends = db.execute("""
        SELECT style_tag, AVG(growth_rate) FROM community_trends
        WHERE date >= DATE('now', '-? days') GROUP BY style_tag
        HAVING AVG(growth_rate) > 0.05
    """, (lookback_days,)).fetchall()

    for tag, avg_growth in (trends or []):
        tag_styles = [s for s in styles if s.get("style_tag") == tag]
        tag_gmv = sum(s["gmv"] for s in tag_styles)
        tag_share = safe_div(tag_gmv, total_gmv)
        if len(tag_styles) < 4 and tag_share < 0.03:
            risks.append({
                "type": "supply_gap", "target": tag, "tag": tag,
                "issue": f"社区 {tag} 热度高（avg growth +{round(avg_growth*100,1)}%）但平台仅 {len(tag_styles)} 款",
                "projected_loss": round(total_gmv * 0.05),
                "suggestion": f"邀请商家上 {tag} 新款，加大推荐权重",
            })

    # cvr_drop: 某标签 CVR 显著低于均值
    if styles:
        avg_cvr = sum(s.get("views", 0) for s in styles) / len(styles) if styles else 0
        for s in styles:
            if s.get("views", 0) > 0 and avg_cvr > 0:
                s_cvr = (s.get("tryons", 0) or 0) / s["views"]
                if s_cvr < avg_cvr * 0.5:
                    risks.append({
                        "type": "cvr_drop", "target": s["style_code"], "tag": s.get("style_tag", ""),
                        "issue": f"{s['style_code']} 试戴转化低于均值 50%",
                        "projected_loss": round(s["gmv"] * 0.1),
                        "suggestion": "优化款式图或降低推荐权重",
                    })
                    if len(risks) >= 5:
                        break

    return {
        "lookback_days": lookback_days, "risk_threshold": risk_threshold,
        "risk_count": len(risks), "risks": risks,
    }
