"""
Skill 3: rank_styles — 款式 GMV 贡献排行

触发场景：运营问"哪个款最赚钱/最拖后腿"
"""
from services.skills._base import (
    parse_period, prev_period, sum_metric, safe_div, STYLE_META, STYLE_NAME,
    CATEGORY_NAMES_MAP,
)


def rank_styles(db, period="this_month", rank_type="top", limit=10):
    start, end = parse_period(period)
    p_start, p_end = prev_period(start, end)

    ranking = []
    total_gmv = 0

    for code in STYLE_META:
        gmv = sum_metric(db, "style_gmv", start, end, style_code=code)
        prev_gmv = sum_metric(db, "style_gmv", p_start, p_end, style_code=code)
        change_pct = round(safe_div(gmv - prev_gmv, prev_gmv) * 100, 1) if prev_gmv else 0
        cat, tag, _ = STYLE_META[code]

        ranking.append({
            "style_code": code,
            "style_name": STYLE_NAME.get(code, code),
            "gmv": round(gmv),
            "share_pct": 0.0,
            "change_pct": change_pct,
            "tag": tag,
            "category": cat,
            "category_name": CATEGORY_NAMES_MAP.get(cat, ""),
        })
        total_gmv += gmv

    for r in ranking:
        r["share_pct"] = round(safe_div(r["gmv"], total_gmv) * 100, 1)

    if rank_type == "top":
        ranking.sort(key=lambda x: -x["gmv"])
    elif rank_type == "declining":
        ranking.sort(key=lambda x: x["change_pct"])
    elif rank_type == "rising":
        ranking.sort(key=lambda x: -x["change_pct"])

    result = ranking[:limit]

    best = result[0] if result else None
    worst = result[-1] if result else None
    summary = ""
    if best and worst and rank_type == "top":
        summary = (
            f"Top 1: {best['style_code']}（{best['tag']}）¥{best['gmv']:,}，"
            f"占比 {best['share_pct']}%；"
            f"末位: {worst['style_code']}（{worst['tag']}）¥{worst['gmv']:,}"
        )

    return {
        "period": period,
        "rank_type": rank_type,
        "total_gmv": round(total_gmv),
        "ranking": result,
        "summary": summary,
    }
