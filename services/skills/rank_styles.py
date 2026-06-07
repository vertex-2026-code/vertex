"""
Skill 3: rank_styles — 款式 GMV 排行
"""
from services.gmv_data import get_styles_ranking


def rank_styles(db, period="this_month", rank_type="top", limit=10):
    return get_styles_ranking(db, limit=limit)
