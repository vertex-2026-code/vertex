"""skills 包"""
from services.skills.get_gmv_status import get_gmv_status
from services.skills.breakdown_gmv import breakdown_gmv
from services.skills.rank_styles import rank_styles
from services.skills.detect_risk import detect_risks
from services.skills.recommend_actions import recommend_actions
from services.skills.generate_promo_copy import generate_promo_copy
from services.skills.validate_prediction import validate_prediction
from services.skills.whatif_simulator import simulate as whatif_simulate
from services.skills.trend_mapper import map_trends_to_inventory
from services.skills.vton_recovery import analyze_vton_funnel

SKILL_MAP = {
    "get_gmv_status": get_gmv_status,
    "breakdown_gmv": breakdown_gmv,
    "rank_styles": rank_styles,
    "detect_risk": detect_risks,
    "recommend_actions": recommend_actions,
    "generate_promo_copy": generate_promo_copy,
    "validate_prediction": validate_prediction,
    "whatif": whatif_simulate,
    "trend_mapper": map_trends_to_inventory,
    "vton_recovery": analyze_vton_funnel,
}
