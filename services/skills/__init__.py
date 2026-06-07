"""skills 包 - admin AI 助手 skill 集

新 12 矩阵的 key 命名（snake_case，跟 OpenClaw skill 名 jiaqu-* 一一对应）+
保留旧 key（向后兼容已部署 chip 的硬编码 data-skill 值）。
"""
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
from services.skills.shop_ranking import shop_ranking
from services.skills.persona_strategy import persona_strategy

SKILL_MAP = {
    "gmv_status": get_gmv_status,
    "gmv_breakdown": breakdown_gmv,
    "prediction_review": validate_prediction,
    "shop_ranking": shop_ranking,
    "persona_strategy": persona_strategy,
    "style_ranking": rank_styles,
    "whatif_sandbox": whatif_simulate,
    "tryon_funnel": analyze_vton_funnel,
    "trend_radar": map_trends_to_inventory,
    "risk_alert": detect_risks,
    "promo_copy": generate_promo_copy,
    "get_gmv_status": get_gmv_status,
    "breakdown_gmv": breakdown_gmv,
    "rank_styles": rank_styles,
    "detect_risk": detect_risks,
    "recommend_actions": recommend_actions,
    "validate_prediction": validate_prediction,
    "whatif": whatif_simulate,
    "trend_mapper": map_trends_to_inventory,
    "vton_recovery": analyze_vton_funnel,
    "generate_promo_copy": generate_promo_copy,
}
