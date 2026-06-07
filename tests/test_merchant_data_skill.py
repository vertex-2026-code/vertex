import os
import tempfile
import unittest

from services.merchant_data_skill import (
    generate_merchant_dataset_skill,
    get_generated_merchant_detail,
    get_merchant_dataset_overview,
    list_generated_merchants,
)


class MerchantDataSkillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = self.tmp.name
        generate_merchant_dataset_skill(
            self.base_dir,
            merchant_count=6,
            min_styles_per_shop=8,
            max_styles_per_shop=8,
            days=14,
            seed=123,
            enable_portal_accounts=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_overview_reports_totals(self):
        overview = get_merchant_dataset_overview(self.base_dir)

        self.assertEqual(overview["totals"]["merchants"], 6)
        self.assertEqual(overview["totals"]["portal_accounts"], 6)
        self.assertGreaterEqual(overview["totals"]["styles"], 48)
        self.assertTrue(overview["cities"])
        self.assertTrue(overview["styles"])

    def test_list_generated_merchants_returns_paginated_items(self):
        result = list_generated_merchants(self.base_dir, page=1, page_size=3)

        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 3)
        self.assertEqual(result["total"], 6)
        self.assertEqual(len(result["items"]), 3)
        self.assertIn("username", result["items"][0])
        self.assertIn("style_count", result["items"][0])

    def test_merchant_detail_contains_styles_and_daily_metrics(self):
        shop_id = list_generated_merchants(self.base_dir, page=1, page_size=1)["items"][0]["shop_id"]

        detail = get_generated_merchant_detail(self.base_dir, shop_id, style_limit=5, daily_limit=7)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["profile"]["shop_id"], shop_id)
        self.assertEqual(len(detail["top_styles"]), 5)
        self.assertEqual(len(detail["recent_daily_metrics"]), 7)
        self.assertIn("group_buy_orders_30d", detail["top_styles"][0])


if __name__ == "__main__":
    unittest.main()
