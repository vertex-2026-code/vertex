"""
Skill 4: detect_gmv_risk — GMV 风险预警
"""
from services.gmv_data import safe_div, get_styles_ranking


def detect_risks(db, lookback_days=7, risk_threshold=0.15):
    risks = []
    ranking = get_styles_ranking(db, 10)
    styles = ranking.get("styles", [])
    total_gmv = ranking.get("total_gmv", 0)

    trends = db.execute(f"""
        SELECT style_tag, AVG(growth_rate) FROM community_trends
        WHERE date >= DATE('now', '-{lookback_days} days') GROUP BY style_tag
        HAVING AVG(growth_rate) > 0.05
    """).fetchall() or []

    for tag, avg_growth in trends:
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

    return {
        "lookback_days": lookback_days, "risk_threshold": risk_threshold,
        "risk_count": len(risks), "risks": risks,
    }
