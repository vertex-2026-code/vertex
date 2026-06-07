"""
Skill 2: breakdown_gmv — GMV 拆解归因
"""
from services.gmv_data import get_gmv_breakdown


def breakdown_gmv(db, period="this_month", compare_to="last_month"):
    return get_gmv_breakdown(db)
