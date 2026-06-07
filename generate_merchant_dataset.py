from __future__ import annotations

import argparse
import json
import os

from services.merchant_data_skill import generate_merchant_dataset_skill


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a mock merchant BI dataset for the merchant-side workbench.")
    parser.add_argument("--count", type=int, default=1000, help="Number of merchants to generate.")
    parser.add_argument("--min-styles", type=int, default=18, help="Minimum listed styles per merchant.")
    parser.add_argument("--max-styles", type=int, default=36, help="Maximum listed styles per merchant.")
    parser.add_argument("--days", type=int, default=30, help="Number of daily rows to generate per merchant/style sample.")
    parser.add_argument("--seed", type=int, default=20260606, help="Random seed for reproducible data.")
    parser.add_argument("--disable-portal-accounts", action="store_true", help="Do not enable generated merchants as login accounts for the merchant portal.")
    parser.add_argument("--keep-existing", action="store_true", help="Append over existing generated tables instead of replacing them.")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    summary = generate_merchant_dataset_skill(
        base_dir=base_dir,
        merchant_count=args.count,
        min_styles_per_shop=args.min_styles,
        max_styles_per_shop=args.max_styles,
        days=args.days,
        seed=args.seed,
        replace_existing=not args.keep_existing,
        enable_portal_accounts=not bool(args.disable_portal_accounts),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
