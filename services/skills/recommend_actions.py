"""
Skill 5: recommend_gmv_actions — GMV 增长建议
"""
from services.gmv_data import get_recommendations


def recommend_actions(db, target_gmv_lift=None, time_horizon="this_month"):
    return get_recommendations(db)
