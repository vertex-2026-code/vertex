"""
为 OpenClaw/DeepSeek 构建分析 prompt
取代原来 app.py 里的 _inject_skill_context
"""
from services.gmv_data import get_gmv_overview, get_gmv_breakdown, get_styles_ranking


def build_analysis_prompt(db, user_msg: str) -> str:
    """基于实时数据构建送给 DeepSeek 的分析 prompt"""
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

    return f"""你是 Vertex 甲趣平台的首席运营分析师。基于实时运营数据给出精准、可执行的分析建议。

【数据驾驶舱 — 实时快照】

▸ GMV 总览
  本月 GMV: ¥{ov['month_gmv']:,}
  月目标: ¥{ov['target']:,}
  完成率: {ov['completion_pct']}%
  缺口: ¥{ov['gap']:,}
  月末预测: ¥{ov['forecast_end_of_month']:,}

▸ GMV 归因拆解 (vs 上期)
  GMV 变化: {bd['gmv_change_pct']}%
  {bd['narrative']}
  因子贡献: 订单数{'+' if bd['orders_change_pct']>=0 else ''}{bd['orders_change_pct']}% (¥{bd['order_contrib']:,}), AOV{'+' if bd['aov_change_pct']>=0 else ''}{bd['aov_change_pct']}% (¥{bd['aov_contrib']:,}), 浏览{'+' if bd['views_change_pct']>=0 else ''}{bd['views_change_pct']}% (¥{bd['view_contrib']:,}), CVR{'+' if bd['cvr_change_pct']>=0 else ''}{bd['cvr_change_pct']}% (¥{bd['cvr_contrib']:,})

▸ 款式 GMV 排行 Top 5 (风格覆盖: {tags}){top_text}

▸ 最近 10 天 GMV 日曲线{curve_text}

---
【分析要求】
1. 一句话总结当前 GMV 状况
2. 指出最大增长动力和最大拖累因素（具体数字）
3. 给出 2-3 条最值得关注的发现或建议，用数据说话
4. 简洁有力，不要重复数据驾驶舱的所有数字

用户问题: {user_msg}"""
