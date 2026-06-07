import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.merchant_data_skill import authenticate_merchant, generate_merchant_dataset_skill
from services.merchant_skills import (
    _call_openclaw,
    _normalize_openclaw_result,
    build_merchant_skills,
    create_custom_skill,
    dispatch_openclaw_agent,
    get_openclaw_status,
    list_custom_skills,
    list_merchant_history,
    list_skill_registry,
    run_openclaw_skill,
    save_merchant_history,
)


BJT = timezone(timedelta(hours=8))


class MerchantSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = self.tmp.name
        data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self._write_logs(os.path.join(data_dir, "tryon.jsonl"))
        self._write_db(os.path.join(data_dir, "jiaqu.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_exposes_schedulable_skills(self):
        registry = list_skill_registry()

        self.assertIn("merchant_style_profile", registry["skill_ids"])
        self.assertIn("periodic_ops_report", registry["skill_ids"])
        self.assertIn("same_style_competitor_analysis", registry["skill_ids"])
        self.assertIn("hot_style_launch", registry["skill_ids"])
        self.assertIn("cold_style_retire", registry["skill_ids"])
        self.assertIn("automation_queue", registry["skill_ids"])
        self.assertIn("trigger_examples", registry["skills"]["hot_style_launch"])
        self.assertIn("output_schema", registry["skills"]["cold_style_retire"])

    def test_builds_local_fallback_for_all_skills(self):
        payload = build_merchant_skills(self.base_dir, shop_id="shop_002", period_days=7)
        skills = payload["skills"]

        self.assertEqual(payload["mode"], "local_fallback")
        self.assertEqual(payload["shop"]["id"], "shop_002")
        self.assertEqual(skills["merchant_style_profile"]["primary_category"], "B")
        self.assertIn("periodic_ops_report", skills)
        self.assertIn("same_style_competitor_analysis", skills)
        self.assertIn("hot_style_launch", skills)
        self.assertIn("cold_style_retire", skills)
        self.assertIn("automation_queue", skills)

    def test_openclaw_skill_prompt_can_be_built_without_openclaw(self):
        payload = run_openclaw_skill(
            self.base_dir,
            skill_id="hot_style_launch",
            shop_id="shop_002",
            period_days=7,
            user_message="Find launch candidates",
            use_openclaw=False,
        )

        self.assertEqual(payload["mode"], "openclaw_skill")
        self.assertEqual(payload["skill_id"], "hot_style_launch")
        self.assertFalse(payload["openclaw"]["used"])
        self.assertIn("SKILL_ID: hot_style_launch", payload["prompt"])
        self.assertIn("MERCHANT_CONTEXT", payload["prompt"])
        self.assertIn("local_fallback", payload)

    def test_agent_dispatch_prompt_can_be_built_without_openclaw(self):
        payload = dispatch_openclaw_agent(
            self.base_dir,
            message="Help me find hot styles and cold styles",
            shop_id="shop_002",
            period_days=7,
            use_openclaw=False,
        )

        self.assertEqual(payload["mode"], "openclaw_agent_dispatch")
        self.assertFalse(payload["openclaw"]["used"])
        self.assertIn("SKILL_REGISTRY", payload["prompt"])
        self.assertIn("MERCHANT_MESSAGE", payload["prompt"])
        self.assertIn("hot_style_launch", payload["prompt"])
        self.assertIn("cold_style_retire", payload["prompt"])

    def test_hot_and_cold_fallback_return_candidates(self):
        skills = build_merchant_skills(self.base_dir, shop_id="shop_002", period_days=7)["skills"]

        hot = skills["hot_style_launch"]["hot_candidates"]
        cold = skills["cold_style_retire"]["cold_candidates"]

        self.assertGreater(len(hot), 0)
        self.assertEqual(hot[0]["style_id"], "nail_05")
        self.assertGreater(len(cold), 0)
        self.assertTrue(any(item["suggested_action"] in {"observe", "revise", "deprioritize", "retire"} for item in cold))

    def test_unknown_shop_is_rejected(self):
        with self.assertRaises(ValueError):
            build_merchant_skills(self.base_dir, shop_id="shop_999", period_days=7)

    def test_generated_merchant_dataset_can_power_analysis_and_login(self):
        summary = generate_merchant_dataset_skill(
            self.base_dir,
            merchant_count=4,
            min_styles_per_shop=8,
            max_styles_per_shop=8,
            days=21,
            seed=42,
            enable_portal_accounts=True,
        )

        self.assertEqual(summary["merchant_count"], 4)
        merchant = authenticate_merchant(self.base_dir, username="merchant_0001", password="demo123456")
        self.assertIsNotNone(merchant)

        payload = build_merchant_skills(self.base_dir, shop_id=merchant["shop_id"], period_days=14)

        self.assertEqual(payload["shop"]["id"], merchant["shop_id"])
        self.assertIn("city", payload["shop"])
        self.assertGreater(len(payload["skills"]["hot_style_launch"]["hot_candidates"]), 0)
        self.assertIn("group_buy_orders", payload["skills"]["periodic_ops_report"]["metrics"])

    def test_custom_skill_can_be_created_and_listed_without_openclaw(self):
        payload = create_custom_skill(
            self.base_dir,
            message="帮我创建一个每周分析爆款和冷门款并整理动作队列的新 skill",
            shop_id="shop_002",
            period_days=7,
            use_openclaw=False,
        )

        self.assertEqual(payload["mode"], "custom_skill_created")
        self.assertIn("created_skill", payload)
        skills = list_custom_skills(self.base_dir)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["id"], payload["created_skill"]["id"])

    def test_custom_skill_can_be_run_after_creation(self):
        created = create_custom_skill(
            self.base_dir,
            message="创建一个关注竞品和动作队列的新 skill",
            shop_id="shop_002",
            period_days=7,
            use_openclaw=False,
        )["created_skill"]

        payload = run_openclaw_skill(
            self.base_dir,
            skill_id=created["id"],
            shop_id="shop_002",
            period_days=7,
            user_message=created["message"],
            use_openclaw=False,
        )

        self.assertEqual(payload["skill_id"], created["id"])
        self.assertEqual(payload["skill_definition"]["name"], created["name"])
        self.assertEqual(payload["local_fallback"]["kind"], "custom_skill")

    def test_history_record_can_be_saved_and_listed(self):
        payload = run_openclaw_skill(
            self.base_dir,
            skill_id="merchant_style_profile",
            shop_id="shop_002",
            period_days=7,
            user_message="请分析我的店",
            use_openclaw=False,
        )
        payload["__actualDurationMs"] = 4200
        saved = save_merchant_history(self.base_dir, {
            "type": "run_skill",
            "title": "商家风格画像",
            "summary": "这是一条测试记录",
            "user_message": "运行 SKILL：商家风格画像",
            "skill_id": "merchant_style_profile",
            "shop_id": "shop_002",
            "period_days": 7,
            "payload": payload,
        })

        records = list_merchant_history(self.base_dir)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], saved["id"])
        self.assertEqual(records[0]["title"], "商家风格画像")
        self.assertEqual(records[0]["payload"]["skill_id"], "merchant_style_profile")
        self.assertNotIn("prompt", records[0]["payload"])

    def test_history_record_normalizes_legacy_openclaw_payloads(self):
        legacy_envelope = {
            "runId": "run_legacy_history",
            "status": "ok",
            "result": {
                "payloads": [
                    {"text": "正在生成商家风格画像"},
                    {"text": "```json\n{\"skill_id\":\"merchant_style_profile\",\"ui_summary\":\"已为门店生成新版画像\",\"analysis\":{\"style_summary\":\"门店适合继续做法式清透路线\"},\"actions\":[\"refresh_primary_styles\"]}\n```"},
                ]
            },
            "meta": {"durationMs": 12800},
        }
        saved = save_merchant_history(self.base_dir, {
            "type": "run_skill",
            "title": "商家风格画像",
            "summary": json.dumps(legacy_envelope, ensure_ascii=False),
            "user_message": "运行 SKILL：商家风格画像",
            "skill_id": "merchant_style_profile",
            "shop_id": "shop_002",
            "period_days": 7,
            "payload": {
                "mode": "openclaw_skill",
                "skill_id": "merchant_style_profile",
                "openclaw": {
                    "used": True,
                    "transport": "remote_http",
                    "reply": json.dumps(legacy_envelope, ensure_ascii=False),
                    "progress": [],
                    "meta": None,
                    "debug": {},
                },
            },
        })

        records = list_merchant_history(self.base_dir)

        self.assertEqual(records[0]["id"], saved["id"])
        self.assertEqual(records[0]["summary"], "已为门店生成新版画像")
        self.assertEqual(records[0]["payload"]["openclaw"]["reply"]["ui_summary"], "已为门店生成新版画像")
        self.assertEqual(records[0]["payload"]["openclaw"]["progress"], ["正在生成商家风格画像"])
        self.assertEqual(records[0]["payload"]["openclaw"]["meta"]["durationMs"], 12800)

    @patch.dict(os.environ, {"OPENCLAW_TRANSPORT": "remote_http", "OPENCLAW_REMOTE_BASE_URL": "http://example.com"}, clear=False)
    def test_status_prefers_remote_http_transport(self):
        status = get_openclaw_status()

        self.assertTrue(status["available"])
        self.assertEqual(status["transport"], "remote_http")
        self.assertEqual(status["remote_url"], "http://example.com/api/admin/chat")

    @patch.dict(os.environ, {"OPENCLAW_TRANSPORT": "remote_http", "OPENCLAW_REMOTE_BASE_URL": "http://example.com"}, clear=False)
    @patch("services.merchant_skills.urllib.request.urlopen")
    def test_remote_http_transport_calls_server_proxy(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"reply": {"ui_summary": "ok"}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        payload = _call_openclaw("hello", "session_1", timeout=7)

        self.assertTrue(payload["used"])
        self.assertEqual(payload["transport"], "remote_http")
        self.assertEqual(payload["reply"]["ui_summary"], "ok")
        request_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(request_obj.full_url, "http://example.com/api/admin/chat")

    @patch.dict(os.environ, {"OPENCLAW_TRANSPORT": "remote_http", "OPENCLAW_REMOTE_BASE_URL": "http://example.com"}, clear=False)
    @patch("services.merchant_skills.urllib.request.urlopen")
    def test_remote_http_transport_unwraps_openclaw_envelope(self, mock_urlopen):
        response = MagicMock()
        envelope = {
            "runId": "run_123",
            "status": "completed",
            "result": {
                "payloads": [
                    {"text": "正在运行「商家风格画像」，读取当前门店、周期和本地数据上下文..."},
                    {"text": "```json\n{\"skill_id\":\"merchant_style_profile\",\"ui_summary\":\"门店偏法式极简，适合扩大奶白与微闪系列。\",\"analysis\":{\"strengths\":[\"风格辨识度高\"]},\"actions\":[\"refresh_primary_styles\"]}\n```"},
                ]
            },
            "meta": {"durationMs": 60614},
        }
        response.read.return_value = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        payload = _call_openclaw("hello", "session_2", timeout=7)

        self.assertEqual(payload["reply"]["ui_summary"], "门店偏法式极简，适合扩大奶白与微闪系列。")
        self.assertEqual(payload["progress"], ["正在运行「商家风格画像」，读取当前门店、周期和本地数据上下文..."])
        self.assertEqual(payload["meta"]["durationMs"], 60614)
        self.assertEqual(payload["debug"]["run_id"], "run_123")

    def test_normalize_openclaw_result_uses_last_payload_json(self):
        raw = "\n".join([
            "some log line",
            json.dumps({
                "runId": "run_456",
                "status": "completed",
                "result": {
                    "payloads": [
                        {"text": "正在调度 skills"},
                        {"text": "{\"intent\":\"生成商家周报\",\"selected_skills\":[\"periodic_ops_report\"],\"ui_summary\":\"已生成周报\"}"},
                    ]
                },
                "meta": {"durationMs": 3210},
            }, ensure_ascii=False),
        ])

        normalized = _normalize_openclaw_result(raw)

        self.assertEqual(normalized["reply"]["ui_summary"], "已生成周报")
        self.assertEqual(normalized["progress"], ["正在调度 skills"])
        self.assertEqual(normalized["meta"]["durationMs"], 3210)

    def test_normalize_openclaw_result_unwraps_legacy_reply_string(self):
        envelope = {
            "runId": "run_789",
            "status": "completed",
            "result": {
                "payloads": [
                    {"text": "正在读取历史数据"},
                    {"text": "```json\n{\"skill_id\":\"merchant_style_profile\",\"ui_summary\":\"已解包旧版远端结果\",\"analysis\":{\"style_summary\":\"门店定位清晰\"},\"actions\":[]}\n```"},
                ]
            },
            "meta": {"durationMs": 5432},
        }

        normalized = _normalize_openclaw_result({
            "reply": json.dumps(envelope, ensure_ascii=False),
            "progress": [],
            "meta": None,
            "debug": {},
        })

        self.assertEqual(normalized["reply"]["ui_summary"], "已解包旧版远端结果")
        self.assertEqual(normalized["progress"], ["正在读取历史数据"])
        self.assertEqual(normalized["meta"]["durationMs"], 5432)

    def _write_logs(self, path):
        now = datetime(2026, 6, 5, 12, 0, tzinfo=BJT)
        records = []

        def add(minutes, event, request_id, style_id, action=None, shop_id=None):
            row = {
                "ts": (now - timedelta(minutes=minutes)).isoformat(),
                "event": event,
                "request_id": request_id,
                "user_id": f"u_{request_id}",
                "nickname": f"user_{request_id}",
                "style_id": style_id,
                "style_kind": "preset",
            }
            if action:
                row["action"] = action
            if shop_id:
                row["shop_id"] = shop_id
            records.append(row)

        for i in range(8):
            req = f"hot_b_{i}"
            add(i * 6, "tryon_start", req, "nail_05")
            add(i * 6 - 1, "tryon_success", req, "nail_05")
            add(i * 6 - 2, "feedback", req, "nail_05", action="like")
            if i < 4:
                add(i * 6 - 3, "feedback", req, "nail_05", action="book", shop_id="shop_002")

        for i in range(3):
            req = f"cold_d_{i}"
            add(200 + i * 10, "tryon_start", req, "nail_12")
            add(199 + i * 10, "feedback", req, "nail_12", action="dislike")

        for i in range(3):
            req = f"peer_a_{i}"
            add(300 + i * 10, "tryon_start", req, "nail_01")
            add(299 + i * 10, "feedback", req, "nail_01", action="like")
            add(298 + i * 10, "feedback", req, "nail_01", action="book", shop_id="shop_001")

        with open(path, "w", encoding="utf-8") as fp:
            for row in records:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_db(self, path):
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE plaza (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                request_id TEXT,
                style_id TEXT,
                result_image_url TEXT,
                caption TEXT DEFAULT '',
                likes INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE community_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                platform TEXT,
                style_tag TEXT,
                mention_count INTEGER,
                growth_rate REAL,
                sample_posts TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO plaza(user_id, request_id, style_id, result_image_url, likes, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            [
                ("u1", "hot_b_1", "nail_05", "/static/results/hot_b_1.png", 12, "2026-06-05T11:00:00+08:00"),
                ("u2", "hot_b_2", "nail_05", "/static/results/hot_b_2.png", 9, "2026-06-05T11:20:00+08:00"),
            ],
        )
        conn.executemany(
            "INSERT INTO community_trends(date, platform, style_tag, mention_count, growth_rate, sample_posts) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            [
                ("2026-06-05", "xhs", "milk_coffee", 240, 0.08, "[]"),
                ("2026-06-05", "douyin", "strawberry_heart", 380, 0.11, "[]"),
                ("2026-06-05", "xhs", "dark_metal", 60, -0.08, "[]"),
            ],
        )
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main()
