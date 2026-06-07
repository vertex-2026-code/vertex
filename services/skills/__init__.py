"""
skills 包初始化：暴露所有 skill 函数，方便 Flask 路由和测试 import
"""
from services.skills.get_gmv_status import get_gmv_status
from services.skills.breakdown_gmv import breakdown_gmv
from services.skills.rank_styles import rank_styles
from services.skills.detect_risk import detect_risks
from services.skills.recommend_actions import recommend_actions
from services.skills.generate_promo_copy import generate_promo_copy
from services.skills.validate_prediction import validate_prediction

SKILL_MAP = {
    "get_gmv_status": get_gmv_status,
    "breakdown_gmv": breakdown_gmv,
    "rank_styles": rank_styles,
    "detect_risk": detect_risks,
    "recommend_actions": recommend_actions,
    "generate_promo_copy": generate_promo_copy,
    "validate_prediction": validate_prediction,
}
