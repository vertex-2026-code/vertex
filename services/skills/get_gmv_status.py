"""
Skill 1: get_gmv_status — GMV 现状速读
"""
from services.gmv_data import safe_div, get_gmv_overview


def get_gmv_status(db, period="this_month", compare_to="target"):
    return get_gmv_overview(db)
