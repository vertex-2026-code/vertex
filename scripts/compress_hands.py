"""
hands 图压缩脚本 —— 显示用缩略图 600×600 + 原图保留作 AI 复用源

架构（同 nails 双版本）：
  /static/uploads/hands/{uid}.png  → 原图（每用户 1 张，复用源 / AI fallback）
  /static/uploads/hands/{uid}.jpg  → 600×600 JPG q80 (~40-60KB)，前端"我的手部" 用

为什么要压：单张 hand 原图常 1-3 MB，375 KB/s 带宽下 4-8s 才出图；
压成 jpg 后 ~50 KB ≈ 0.1s 出图，体验从「卡」→「即时」。

DB 字段不动：hand_originals.image_path 保留 .png（"原图必保存"约定），
                                       /api/user/hand 在响应层把 .png 换成 .jpg。

幂等：再跑一次会跳过已经压过的（jpg 已存在）。
"""
import os
import sys

from PIL import Image

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS_DIR = f"{BASE_DIR}/static/uploads/hands"
MAX_DIM = 600
JPEG_QUALITY = 80


def main():
    if not os.path.isdir(HANDS_DIR):
        sys.exit(f"❌ 找不到 {HANDS_DIR}")

    total_before = total_after = 0
    converted = skipped = 0

    for fname in sorted(os.listdir(HANDS_DIR)):
        if not fname.lower().endswith(".png"):
            continue
        src = os.path.join(HANDS_DIR, fname)
        if not os.path.isfile(src):
            continue

        uid = os.path.splitext(fname)[0]
        out_path = os.path.join(HANDS_DIR, f"{uid}.jpg")

        before = os.path.getsize(src)
        total_before += before

        if os.path.exists(out_path):
            after = os.path.getsize(out_path)
            total_after += after
            print(f"⏭  {uid}.jpg 已存在 ({after//1024}KB)，跳过")
            skipped += 1
            continue

        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
                im.save(out_path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        except Exception as e:
            print(f"❌ {fname} 压缩失败: {e}")
            continue

        after = os.path.getsize(out_path)
        total_after += after
        saving = (1 - after / before) * 100
        print(f"✅ {fname} → {uid}.jpg   {before//1024}KB → {after//1024}KB  (-{saving:.0f}%)")
        converted += 1

    print()
    print("━━━ 完成 ━━━")
    print(f"压缩: {converted}  跳过: {skipped}")
    if total_before:
        print(f"总体积: {total_before/1024/1024:.1f}MB → {total_after/1024/1024:.1f}MB  "
              f"(节省 {(1-total_after/total_before)*100:.0f}%)")
    print("PNG 原图保留不动；前端通过 /api/user/hand 会拿到 jpg URL。")


if __name__ == "__main__":
    main()
