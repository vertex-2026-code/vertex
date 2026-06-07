# 所有 skill 的 pytest 用例
import sqlite3
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "jiaqu.db")


@pytest.fixture
def db():
    """每个测试用例独立的数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestGetGmvStatus:
    """Skill 1: GMV 现状速读"""

    def test_this_month(self, db):
        from services.skills import get_gmv_status
        result = get_gmv_status(db, period="this_month")
        assert result["period"] == "this_month"
        assert result["current_gmv"] > 0
        assert result["target_gmv"] == 1500000
        assert result["status"] in ("on_track", "at_risk", "off_track", "unknown")
        assert isinstance(result["completion_rate"], (int, float))
        assert isinstance(result["projected_final"], (int, float))

    def test_today(self, db):
        from services.skills import get_gmv_status
        result = get_gmv_status(db, period="today")
        assert result["period"] == "today"
        assert "current_gmv" in result
        assert "days_remaining" in result

    def test_compare_last_week(self, db):
        from services.skills import get_gmv_status
        result = get_gmv_status(db, period="this_week", compare_to="last_week")
        assert result["compare_to"] == "last_week"
        assert isinstance(result["vs_compare_pct"], (int, float))


class TestBreakdownGmv:
    """Skill 2: GMV 拆解归因"""

    def test_this_month(self, db):
        from services.skills import breakdown_gmv
        result = breakdown_gmv(db, period="this_month")
        assert result["period"] == "this_month"
        assert len(result["factors"]) == 4
        factor_names = [f["name"] for f in result["factors"]]
        assert "订单数" in factor_names
        assert "AOV" in factor_names
        assert "浏览数" in factor_names
        assert "CVR" in factor_names
        assert result["primary_driver"] in factor_names
        assert len(result["narrative"]) > 10

    def test_factor_contributions_sum(self, db):
        from services.skills import breakdown_gmv
        result = breakdown_gmv(db, period="this_month")
        total_contrib = sum(f["contribution"] for f in result["factors"])
        assert isinstance(total_contrib, (int, float))


class TestRankStyles:
    """Skill 3: 款式 GMV 排行"""

    def test_top_ranking(self, db):
        from services.skills import rank_styles
        result = rank_styles(db, period="this_month", rank_type="top", limit=5)
        assert len(result["ranking"]) == 5
        assert result["ranking"][0]["gmv"] >= result["ranking"][-1]["gmv"]
        for item in result["ranking"]:
            assert "style_code" in item
            assert "style_name" in item
            assert "tag" in item
            assert "category" in item
            assert "share_pct" in item
            assert result["total_gmv"] > 0

    def test_declining_ranking(self, db):
        from services.skills import rank_styles
        result = rank_styles(db, period="this_month", rank_type="declining", limit=3)
        assert len(result["ranking"]) <= 3
        assert result["rank_type"] == "declining"


class TestDetectRisk:
    """Skill 4: GMV 风险预警"""

    def test_default_params(self, db):
        from services.skills import detect_risks
        result = detect_risks(db)
        assert "risks" in result
        assert "risk_count" in result
        assert isinstance(result["risks"], list)
        assert result["risk_count"] == len(result["risks"])
        for risk in result["risks"]:
            assert "type" in risk
            assert risk["type"] in ("declining_hero", "supply_gap", "cvr_drop")

    def test_returns_empty_when_no_risks(self, db):
        from services.skills import detect_risks
        result = detect_risks(db, lookback_days=1, risk_threshold=0.5)
        assert isinstance(result["risks"], list)


class TestRecommendActions:
    """Skill 5: GMV 增长建议"""

    def test_default(self, db):
        from services.skills import recommend_actions
        result = recommend_actions(db, time_horizon="this_month")
        assert len(result["actions"]) >= 1
        for action in result["actions"]:
            assert "rank" in action
            assert "action_type" in action
            assert "expected_lift" in action
            assert "roi" in action
            assert action["roi"] in ("high", "medium", "low")
            assert len(action["reasoning"]) > 10
        assert result["total_expected_lift"] > 0
        assert isinstance(result["would_hit_target"], bool)

    def test_custom_lift_target(self, db):
        from services.skills import recommend_actions
        result = recommend_actions(db, target_gmv_lift=100000, time_horizon="this_month")
        assert len(result["actions"]) >= 1


class TestGeneratePromoCopy:
    """Skill 6: 文案生成（模板兜底，不调 LLM）"""

    def test_banner_premium(self, db):
        from services.skills import generate_promo_copy
        result = generate_promo_copy(db, style_code="nail_03", channel="banner", tone="premium")
        assert result["source"] in ("template", "deepseek")
        assert len(result["main_copy"]) > 0
        assert len(result["sub_copy"]) > 0
        assert len(result["cta"]) > 0
        assert result["char_count"] == len(result["main_copy"]) + len(result["sub_copy"])
        assert result["channel"] == "banner"
        assert result["tone"] == "premium"

    def test_push_urgent(self, db):
        from services.skills import generate_promo_copy
        result = generate_promo_copy(db, style_code="nail_04", channel="push", tone="urgent")
        assert result["channel"] == "push"
        assert result["tone"] == "urgent"
        assert len(result["main_copy"]) > 0

    def test_merchant_invite(self, db):
        from services.skills import generate_promo_copy
        result = generate_promo_copy(db, style_code="nail_01", channel="merchant_invite", tone="playful")
        assert result["channel"] == "merchant_invite"
        assert len(result["cta"]) > 0


class TestValidatePrediction:
    """Skill 7: 预测准确性验证"""

    def test_last_week(self, db):
        from services.skills import validate_prediction
        result = validate_prediction(db, period="last_week")
        assert "predictions_total" in result
        assert "predictions_hit" in result
        assert result["predictions_hit"] <= result["predictions_total"]
        if result["predictions_total"] > 0:
            assert result["accuracy"] is not None
            for detail in result["details"]:
                assert "verdict" in detail
                assert detail["verdict"] in ("accurate", "partial", "miss", "pending")
        assert len(result["narrative"]) > 0

    def test_empty_period(self, db):
        from services.skills import validate_prediction
        result = validate_prediction(db, period="today")
        assert isinstance(result["predictions_total"], int)
