"""
Skill 8: What-If GMV 沙盘模拟器
输入: 策略动作 + 参数 → 输出预测 GMV 变化 + 风险
"""
from services.gmv_data import _get_date_bounds, _query_period, safe_div, get_gmv_curve


def simulate(db, action="discount", target="", magnitude=10, budget=0):
    """模拟运营动作对 GMV 的影响

    action: discount(折扣) / boost(流量加权) / shortage(缺货) / budget(广告)
    magnitude: 折扣幅度% / 流量加权% / 缺货天数 / 广告预算¥
    target: 目标款式（空=全局）
    """
    d_start, d_end = _get_date_bounds(db)
    cur = _query_period(db, d_start, d_end)
    baseline = cur["gmv"]
    days = (d_end - d_start).days + 1
    daily_avg = baseline / days if days else 0

    # 计算款式权重
    style_weight = 0.05  # default
    if target:
        try:
            r = db.execute("""
                SELECT SUM(d.group_buy_orders * c.price) FROM merchant_style_daily_metrics d
                JOIN merchant_style_catalog c ON d.style_id = c.style_id
                WHERE d.style_id = ?
            """, (target,)).fetchone()
            if r and r[0] and baseline > 0:
                style_weight = min(r[0] / baseline, 0.4)
        except:
            pass

    impact = {}
    if action == "discount":
        # 折扣提升 CVR + 订单数，但拉低 AOV
        discount_pct = magnitude / 100
        cvr_lift = discount_pct * 2.5  # 折扣10% → CVR +25%
        aov_drop = discount_pct * 0.8   # 折扣10% → AOV -8%
        new_orders = cur["orders"] * (1 + cvr_lift * style_weight)
        new_aov = cur["aov"] * (1 - aov_drop * style_weight)
        new_gmv = new_orders * new_aov
        impact = {
            "action": f"对 {target or '全品类'} 打 {magnitude}% 折扣",
            "cvr_change": f"+{round(cvr_lift * style_weight * 100, 1)}%",
            "aov_change": f"-{round(aov_drop * style_weight * 100, 1)}%",
            "orders_change": f"+{round(cvr_lift * style_weight * 100, 1)}%",
            "new_gmv": round(new_gmv),
            "delta": round(new_gmv - baseline),
            "delta_pct": round(safe_div(new_gmv - baseline, baseline) * 100, 1),
            "risk": "AOV 下降可能侵蚀利润，建议搭配高价款交叉销售" if aov_drop * style_weight > 0.03 else "风险可控",
        }

    elif action == "boost":
        # 流量加权 → 浏览数提升 → 订单增加
        boost_pct = magnitude / 100
        views_lift = boost_pct * 1.5
        new_views = cur["views"] * (1 + views_lift * style_weight)
        new_orders_boost = new_views * cur["cvr"]
        new_gmv = new_orders_boost * cur["aov"]
        impact = {
            "action": f"对 {target or '全品类'} 加权 {magnitude}% 流量",
            "views_change": f"+{round(views_lift * style_weight * 100, 1)}%",
            "orders_change": f"+{round(safe_div(new_orders_boost - cur['orders'], cur['orders']) * 100, 1)}%",
            "new_gmv": round(new_gmv),
            "delta": round(new_gmv - baseline),
            "delta_pct": round(safe_div(new_gmv - baseline, baseline) * 100, 1),
            "cost": f"¥{budget:,}" if budget else "Banner 位机会成本",
            "risk": "流量加权仅提升曝光，不保证转化" if style_weight < 0.1 else "TOP 款加权效果显著",
        }

    elif action == "shortage":
        # 缺货 → 直接损失 GMV
        shortage_days = max(1, int(magnitude))
        daily_style_gmv = daily_avg * style_weight
        loss = daily_style_gmv * shortage_days
        impact = {
            "action": f"{target or '爆款'} 缺货 {shortage_days} 天",
            "daily_loss": round(daily_style_gmv),
            "total_loss": round(loss),
            "new_gmv": round(baseline - loss),
            "delta": round(-loss),
            "delta_pct": round(-safe_div(loss, baseline) * 100, 1),
            "suggestion": f"优先补货 {target}，或推同标签替代款分散风险",
        }

    elif action == "budget":
        # 广告预算 → 直接 GMV 增量（ROAS 假设 3-5x）
        roas = 3.5
        lift = budget * roas
        impact = {
            "action": f"追加 ¥{budget:,} 广告预算",
            "expected_roas": f"{roas}x",
            "expected_lift": round(lift),
            "new_gmv": round(baseline + lift),
            "delta": round(lift),
            "delta_pct": round(safe_div(lift, baseline) * 100, 1),
            "risk": "ROAS 基于历史均值，实际受素材质量和竞品影响" if budget > 50000 else "小额测试风险可控",
        }

    # 生成对比曲线
    before_curve = get_gmv_curve(db, 30)
    after_curve = []
    for c in before_curve:
        factor = 1 + safe_div(impact.get("delta", 0), baseline) if baseline else 1
        after_curve.append({"date": c["date"], "gmv": round(c["gmv"] * factor)})

    return {
        "action": action,
        "target": target,
        "magnitude": magnitude,
        "budget": budget,
        "baseline_gmv": round(baseline),
        "daily_avg": round(daily_avg),
        "impact": impact,
        "before_curve": before_curve[-14:],
        "after_curve": after_curve[-14:],
        "summary": f"{impact['action']} → GMV {impact.get('delta_pct', 0):+}% (¥{impact.get('delta', 0):+,})",
    }
