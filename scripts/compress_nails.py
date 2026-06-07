"""
nail 图压缩脚本 —— 显示用缩略图 600×600 + AI 用原图高清

架构（用户反馈：后台保存高清，显示加载小一点的图）：
  /static/nails/          → 600×600 JPG q80 (40-60KB/张) ← 前端 grid / chip
  /static/nails_orig/     → 原图 PNG (1.4MB/张)           ← AI 试戴用

效果：
- 单张缩略图：1.4MB → ~50KB (节省 96%)
- 总量：34MB → ~1.5MB
- 加载时间：91s → 4s

幂等：再跑一次不会重复压（跳过已经 < 200KB 的）。
"""
import os
import shutil
import sys

from PIL import Image

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAILS_DIR = f"{BASE_DIR}/static/nails"
BACKUP_DIR = f"{BASE_DIR}/static/nails_orig"
MAX_DIM = 600
JPEG_QUALITY = 80


def main():
    if not os.path.isdir(NAILS_DIR):
        sys.exit(f"❌ 找不到 {NAILS_DIR}")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    total_before = total_after = 0
    converted = skipped = 0

    for fname in sorted(os.listdir(NAILS_DIR)):
        src = os.path.join(NAILS_DIR, fname)
        if not fname.lower().endswith((".png", ".jpg", ".jpeg")) or not os.path.isfile(src):
            continue

        sid = os.path.splitext(fname)[0]
        out_path = os.path.join(NAILS_DIR, f"{sid}.jpg")

        before = os.path.getsize(src)
        total_before += before

        # 已经压过的不再重压
        if fname.lower().endswith(".jpg") and before < 200_000:
            print(f"⏭  {fname}  已经 {before//1024}KB，跳过")
            skipped += 1
            total_after += before
            continue

        # 备份原图（首次才备份；已存在表示之前压过）
        backup_path = os.path.join(BACKUP_DIR, fname)
        if not os.path.exists(backup_path):
            shutil.copy2(src, backup_path)

        # 打开 → 等比缩 → 保存 JPG
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
            im.save(out_path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)

        # 原文件是 PNG → 现在生成的 JPG 路径不同 → 删原 PNG（已备份到 nails_orig）
        if src != out_path and os.path.exists(src):
            os.remove(src)

        after = os.path.getsize(out_path)
        total_after += after
        saving = (1 - after / before) * 100
        print(f"✅ {fname} → {sid}.jpg   {before//1024}KB → {after//1024}KB  (-{saving:.0f}%)")
        converted += 1

    print()
    print("━━━ 完成 ━━━")
    print(f"压缩: {converted}  跳过: {skipped}")
    print(f"总体积: {total_before/1024/1024:.1f}MB → {total_after/1024/1024:.1f}MB  "
          f"(节省 {(1-total_after/max(total_before,1))*100:.0f}%)")
    print(f"高清原图备份: {BACKUP_DIR}  (AI 试戴会优先用这个)")


if __name__ == "__main__":
    main()

