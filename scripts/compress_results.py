"""
results 图压缩脚本 —— plaza 缩略图 800×800 JPG q80

架构（沿用 nails 双版本思路）：
  /static/results/{rid}.png  → AI 输出原图（保留，用户下载/分享用）
  /static/results/{rid}.jpg  → 800×800 JPG q80（plaza grid 缩略图用）

幂等：再跑一次不会重复压（已存在 jpg 则跳过）。
"""
import os
import sys

from PIL import Image

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = f"{BASE_DIR}/static/results"
MAX_DIM = 800
JPEG_QUALITY = 80


def compress_one(png_path: str) -> tuple[int, int]:
    """压一张 png → 同名 jpg，返回 (before, after) 字节数。已存在 jpg 跳过。"""
    sid = os.path.splitext(os.path.basename(png_path))[0]
    jpg_path = os.path.join(os.path.dirname(png_path), f"{sid}.jpg")
    if os.path.exists(jpg_path):
        return os.path.getsize(png_path), os.path.getsize(jpg_path)
    before = os.path.getsize(png_path)
    with Image.open(png_path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
        im.save(jpg_path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return before, os.path.getsize(jpg_path)


def main():
    if not os.path.isdir(RESULTS_DIR):
        sys.exit(f"❌ 找不到 {RESULTS_DIR}")

    total_before = total_after = 0
    done = skipped = 0
    for fname in sorted(os.listdir(RESULTS_DIR)):
        if not fname.lower().endswith(".png"):
            continue
        src = os.path.join(RESULTS_DIR, fname)
        sid = os.path.splitext(fname)[0]
        jpg_path = os.path.join(RESULTS_DIR, f"{sid}.jpg")
        already = os.path.exists(jpg_path)
        before, after = compress_one(src)
        total_before += before
        total_after += after
        if already:
            skipped += 1
            print(f"⏭  {fname}  已有 jpg，跳过")
        else:
            done += 1
            saving = (1 - after / before) * 100 if before else 0
            print(f"✅ {fname} → {sid}.jpg   {before//1024}KB → {after//1024}KB  (-{saving:.0f}%)")

    print()
    print("━━━ 完成 ━━━")
    print(f"压缩: {done}  跳过: {skipped}")
    if total_before:
        print(f"总体积: {total_before/1024/1024:.1f}MB → {total_after/1024/1024:.1f}MB  "
              f"(节省 {(1-total_after/total_before)*100:.0f}%)")


if __name__ == "__main__":
    main()
