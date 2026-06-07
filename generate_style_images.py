from __future__ import annotations

import argparse
import json
import os

from services.merchant_data_skill import generate_existing_style_images


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Jimeng/Ark nail images for existing merchant styles in jiaqu.db.")
    parser.add_argument("--hot-count", type=int, default=7, help="Number of hot styles to render per shop.")
    parser.add_argument("--cold-count", type=int, default=3, help="Number of cold styles to render per shop.")
    parser.add_argument("--shop-limit", type=int, default=0, help="Only process the first N shops. 0 means all shops.")
    parser.add_argument("--shop-id", action="append", default=[], help="Only process specific shop_id values. Can be passed multiple times.")
    parser.add_argument("--regenerate-all", action="store_true", help="Regenerate even if a style image already exists.")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    summary = generate_existing_style_images(
        base_dir=base_dir,
        hot_count=args.hot_count,
        cold_count=args.cold_count,
        shop_limit=args.shop_limit,
        only_missing=not bool(args.regenerate_all),
        shop_ids=args.shop_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
