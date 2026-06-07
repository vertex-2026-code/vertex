"""
Skill 5: recommend_gmv_actions — GMV 增长建议（核心）

触发场景：运营问"接下来该做什么 / 怎么完成本月目标"
策略: 融合 Top 款式 + 风险预警 + 社区趋势，输出 3-4 条 ROI 排序建议
"""
from datetime import date, timedelta
from services.skills._base import (
    parse_period, sum_metric, avg_metric, safe_div, query_one, query_all,
    STYLE_META, CAT_TO_TAGS, TAG_TO_CAT, TODAY,
)


def recommend_actions(db, target_gmv_lift=None, time_horizon="this_month"):
    start, end = parse_period(time_horizon)

    # 基础数据
    current_gmv = sum_metric(db, "category_gmv", start, end)
    target_row = query_one(
        db,
        "SELECT target_value FROM gmv_targets WHERE period_type='monthly' "
        "AND period_start <= ? AND period_end >= ?",
        (start.isoformat(), end.isoformat()),
    )
    target = target_row.get("target_value", 0) if target_row else 0
    gap = target - current_gmv if target else (target_gmv_lift or 100000)
    if target_gmv_lift is None:
        target_gmv_lift = gap if gap > 0 else 50000

    # Top 3 款式（按 GMV）
    top_styles = []
    for code in STYLE_META:
        gmv = sum_metric(db, "style_gmv", start, end, style_code=code)
        top_styles.append((code, gmv))
    top_styles.sort(key=lambda x: -x[1])
    top3 = top_styles[:3]

    # 上升趋势标签
    trend_rows = query_all(
        db,
        "SELECT style_tag, ROUND(AVG(growth_rate)*100,1) AS avg_growth FROM community_trends "
        "WHERE date >= ? GROUP BY style_tag ORDER BY avg_growth DESC LIMIT 5",
        (start.isoformat(),),
    )
    rising_tags = [t["style_tag"] for t in trend_rows if t["avg_growth"] > 5]

    # 下降标签
    declining_tags = [t["style_tag"] for t in trend_rows if t["avg_growth"] < -3]

    # 现有 promo 效果
    promo_row = query_one(
        db,
        "SELECT COUNT(*) as cnt, SUM(expected_gmv_lift) as total_lift FROM promo_events "
        "WHERE event_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    )
    recent_promo_lift = promo_row.get("total_lift", 0) or 0

    # 生成建议
    actions = []

    # 建议1: 推上升趋势标签的头号款式
    if rising_tags:
        best_tag = rising_tags[0]
        best_style = None
        best_gmv = 0
        for code, (cat, tag, _) in STYLE_META.items():
            if tag == best_tag:
                sgmv = sum_metric(db, "style_gmv", start, end, style_code=code)
                if sgmv > best_gmv:
                    best_gmv = sgmv
                    best_style = code
        if best_style:
            est_lift = int(target_gmv_lift * 0.3)
            actions.append({
                "rank": 1,
                "action_type": "banner_promo",
                "target": best_style,
                "target_tag": best_tag,
                "expected_lift": est_lift,
                "cost": "低 · Banner 位替换",
                "roi": "high",
                "reasoning": f"社区 {best_tag} 热度上涨，{best_style} 是该标签 GMV Top 款，"
                             f"放到主推位预计带来 +¥{est_lift:,} 增量",
            })

    # 建议2: 清仓下降标签库存
    if declining_tags:
        worst_tag = declining_tags[0]
        worst_style = None
        worst_gmv = float("inf")
        for code, (cat, tag, _) in STYLE_META.items():
            if tag == worst_tag:
                sgmv = sum_metric(db, "style_gmv", start, end, style_code=code)
                if sgmv < worst_gmv and sgmv > 0:
                    worst_gmv = sgmv
                    worst_style = code
        if worst_style:
            est_lift = int(target_gmv_lift * 0.15)
            actions.append({
                "rank": len(actions) + 1,
                "action_type": "clearance",
                "target": worst_style,
                "target_tag": worst_tag,
                "expected_lift": est_lift,
                "cost": "中 · 需商家配合调价",
                "roi": "medium",
                "reasoning": f"社区 {worst_tag} 趋势下行，{worst_style} 做限时折扣清库存，"
                             f"预计回笼 +¥{est_lift:,}",
            })

    # 建议3: 提高 AOV — 推高价款
    est_lift = int(target_gmv_lift * 0.2)
    actions.append({
        "rank": len(actions) + 1,
        "action_type": "premium_push",
        "target": top3[0][0] if top3 else "nail_03",
        "target_tag": STYLE_META.get(top3[0][0], ("", "", ""))[1] if top3 else "美拉德",
        "expected_lift": est_lift,
        "cost": "低 · 调整推荐权重",
        "roi": "high",
        "reasoning": f"推高价款提升 AOV 至 ¥240+，CVR 不输平价款，"
                     f"利润率空间大，预计 +¥{est_lift:,}",
    })

    # 建议4: 召回促活
    est_lift = int(target_gmv_lift * 0.12)
    actions.append({
        "rank": len(actions) + 1,
        "action_type": "push_notification",
        "target": "inactive_users",
        "target_tag": None,
        "expected_lift": est_lift,
        "cost": "低 · Push 一次",
        "roi": "medium",
        "reasoning": "推送给 7 天未活跃用户 + 收藏未试戴用户，"
                     f"召回率预计 3-5%，+¥{est_lift:,}",
    })

    # 排序：ROI 高的在前
    roi_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: roi_order.get(a["roi"], 2))

    for i, a in enumerate(actions):
        a["rank"] = i + 1

    total_lift = sum(a["expected_lift"] for a in actions)
    forecast_after = current_gmv + total_lift

    return {
        "time_horizon": time_horizon,
        "current_gmv": round(current_gmv),
        "target_gmv": round(target) if target else target_gmv_lift,
        "gap": round(gap),
        "actions": actions,
        "total_expected_lift": total_lift,
        "achievement_after": round(forecast_after),
        "would_hit_target": forecast_after >= target if target else True,
    }
