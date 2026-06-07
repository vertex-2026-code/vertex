"""
Skill 10: VTON 试戴流失深度归因 + 生成式视觉挽回建议
分析试戴历史 → 识别流失 → 给出挽回策略
"""
from services.gmv_data import safe_div


def analyze_vton_funnel(db):
    """分析试戴漏斗: 试戴 → 收藏 → 预约，识别流失点"""

    # 试戴总量
    tryon_total = db.execute("SELECT COUNT(*) FROM tryon_history").fetchone()[0] or 0
    # 收藏总量
    fav_total = db.execute("SELECT COUNT(DISTINCT user_id) FROM favorites").fetchone()[0] or 0
    # 分享到广场
    plaza_total = db.execute("SELECT COUNT(*) FROM plaza").fetchone()[0] or 0

    # 漏斗率
    fav_rate = round(safe_div(fav_total, tryon_total) * 100, 1) if tryon_total else 0
    plaza_rate = round(safe_div(plaza_total, tryon_total) * 100, 1) if tryon_total else 0

    # 各款式试戴排行
    style_tryons = db.execute("""
        SELECT style_id, COUNT(*) AS cnt FROM tryon_history
        WHERE style_id IS NOT NULL AND style_id != '用户上传'
        GROUP BY style_id ORDER BY cnt DESC LIMIT 10
    """).fetchall() or []

    # 流失诊断: 试戴多但收藏少的款式
    style_details = []
    for sid, tryons in style_tryons[:8]:
        style_favs = db.execute(
            "SELECT COUNT(*) FROM favorites WHERE style_id = ?", (sid,)
        ).fetchone()[0] or 0
        rate = round(safe_div(style_favs, tryons) * 100, 1)
        status = "healthy"
        if tryons > 3 and rate < 10:
            status = "leaking"
        elif tryons > 5 and rate < 20:
            status = "warning"
        style_details.append({
            "style_code": sid,
            "tryons": tryons,
            "favorites": style_favs,
            "fav_rate": rate,
            "status": status,
            "diagnosis": (
                f"试戴{tryons}次仅{style_favs}人收藏（{rate}%），"
                "可能存在视觉摩擦力：3D效果不自然、尺寸比例偏差、或款式图与实物差距大"
            ) if status == "leaking" else "",
        })

    leaking = [s for s in style_details if s["status"] == "leaking"]
    warning = [s for s in style_details if s["status"] == "warning"]

    # 总览漏斗
    funnel = [
        {"stage": "AI 试戴", "count": tryon_total, "label": "入口"},
        {"stage": "收藏/喜欢", "count": fav_total, "rate": f"{fav_rate}%", "label": f"收藏率 {fav_rate}%"},
        {"stage": "分享到广场", "count": plaza_total, "rate": f"{plaza_rate}%", "label": f"分享率 {plaza_rate}%"},
    ]

    suggestions = []
    if leaking:
        suggestions.append({
            "priority": "high",
            "action": f"视觉摩擦力诊断: {len(leaking)} 款试戴流失严重",
            "detail": "建议优化这些款的 AI 试戴渲染效果，或更换更贴近实物的款式图",
            "affected_styles": [s["style_code"] for s in leaking[:3]],
            "impact": f"修复后预计可提升收藏转化 15-25%",
        })
    if warning:
        suggestions.append({
            "priority": "medium",
            "action": f"生成式视觉挽回: {len(warning)} 款存在预警",
            "detail": "为试戴过但未收藏的用户生成个性化场景图（法式/职场/户外 3 风格），通过 Push 精准触达",
            "target_users": max(0, tryon_total - fav_total),
            "impact": f"预计挽回率 8-15%，增量 +¥{tryon_total * 50:,}",
        })

    return {
        "funnel": funnel,
        "tryon_total": tryon_total,
        "fav_rate": fav_rate,
        "plaza_rate": plaza_rate,
        "leaking_styles": len(leaking),
        "warning_styles": len(warning),
        "style_details": style_details,
        "suggestions": suggestions,
        "narrative": (
            f"试戴漏斗: {tryon_total} 次试戴 → {fav_total} 次收藏（{fav_rate}%）→ {plaza_total} 次分享（{plaza_rate}%）。"
            f"发现 {len(leaking)} 款存在严重流失，建议优先诊断视觉摩擦力"
        ) if leaking else f"试戴漏斗健康: {tryon_total} 次试戴，收藏率 {fav_rate}%",
    }
