"""为 OpenClaw/DeepSeek 构建分析 prompt — 数据驾驶舱 + 趋势雷达 + 试戴漏斗"""
from services.gmv_data import get_gmv_overview, get_gmv_breakdown, get_styles_ranking


def build_analysis_prompt(db, user_msg: str) -> str:
    try:
        ov = get_gmv_overview(db)
        bd = get_gmv_breakdown(db)
        rk = get_styles_ranking(db, 5)
    except Exception:
        return user_msg

    style_tags = set()
    for s in rk.get("styles", []):
        style_tags.add(s.get("style_tag", ""))
    tags = "、".join(sorted(style_tags)[:8]) if style_tags else "暂无"

    top_text = ""
    for i, s in enumerate(rk.get("styles", [])[:5]):
        top_text += f"\n  {i+1}. {s['style_code']} ({s.get('style_tag','')}) ¥{s['gmv']:,} 占比{s['gmv_share_pct']}%"

    curve_text = ""
    for c in ov.get("curve", [])[-10:]:
        curve_text += f"\n  {c['date']}  ¥{int(c['gmv']/1000)}k"

    trend_text = ""
    try:
        from services.skills.trend_mapper import map_trends_to_inventory
        tm = map_trends_to_inventory(db)
        for t in tm.get("trends", [])[:3]:
            n = len(t.get("matched_styles", []))
            trend_text += f"\n  {t['tag']} +{t['growth_pct']}% → {n}款可组专题页"
    except:
        pass

    vton_text = ""
    try:
        from services.skills.vton_recovery import analyze_vton_funnel
        vf = analyze_vton_funnel(db)
        vton_text = f"\n  试戴 {vf['tryon_total']}次 → 收藏率 {vf['fav_rate']}% → 分享率 {vf['plaza_rate']}%"
        if vf['leaking_styles'] > 0:
            vton_text += f"\n  ⚠ {vf['leaking_styles']}款试戴流失严重，需视觉摩擦力诊断"
    except:
        pass

    return f"""你是 Vertex 甲趣平台首席运营分析师 + 策略顾问。基于实时数据给出精准可执行的分析。

【数据驾驶舱 — 实时快照】

▸ GMV: ¥{ov['month_gmv']:,} / 目标 ¥{ov['target']:,} ({ov['completion_pct']}%)  缺口 ¥{ov['gap']:,}  预测 ¥{ov['forecast_end_of_month']:,}

▸ 归因: {bd['narrative']}
  订单{'+' if bd['orders_change_pct']>=0 else ''}{bd['orders_change_pct']}%(¥{bd['order_contrib']:,}) AOV{'+' if bd['aov_change_pct']>=0 else ''}{bd['aov_change_pct']}%(¥{bd['aov_contrib']:,}) 浏览{'+' if bd['views_change_pct']>=0 else ''}{bd['views_change_pct']}%(¥{bd['view_contrib']:,}) CVR{'+' if bd['cvr_change_pct']>=0 else ''}{bd['cvr_change_pct']}%(¥{bd['cvr_contrib']:,})

▸ 款式 Top 5 ({tags}):{top_text}

▸ 10天曲线:{curve_text}

▸ 趋势雷达:{trend_text}

▸ 试戴漏斗:{vton_text}

---
你是数据分析师 + 策略顾问，需:
1. 一句话总结 GMV 现状，指出最大增长动力和拖累因素
2. 如果问 What-If (打折/缺货/加预算)，给出具体预测数字
3. 如果问趋势，推荐匹配库存款组成专题页
4. 如果问试戴流失，分析视觉摩擦力 + 给出挽回策略
5. 回答简洁，每条结论跟数字依据

用户问题: {user_msg}"""
