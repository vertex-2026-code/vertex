"""
nail 图压缩脚本 —— 把 /static/nails/ 下每张 PNG 缩成 1024×1024 quality 85 的 JPG。

为什么：原图平均 1.4MB（PNG，2000×2000+），25 张共 34MB。
在 3M 带宽下加载 91s，是 C 端"卡死"的真正凶手。

效果：
- 单张：1.4MB → ~100KB (节省 93%)
- 总量：34MB → ~2.5MB
- 加载时间：91s → 6-8s

会做：
1. 把 nail_*.png 备份到 nails_orig/（首次跑才备份，幂等）
2. 用 PIL 读 PNG → 等比缩到最长边 1024 → 保存为 JPG quality 85
3. 删掉原 PNG（已备份在 nails_orig/）

用法：
    cd /opt/jiaqu && source venv/bin/activate
    pip install Pillow      # 如果没装
    python3 scripts/compress_nails.py
    ./deploy.sh             # 重启让 Flask 重新扫目录
"""
import os
import shutil
import sys

from PIL import Image

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAILS_DIR = f"{BASE_DIR}/static/nails"
BACKUP_DIR = f"{BASE_DIR}/static/nails_orig"
MAX_DIM = 1024
JPEG_QUALITY = 85


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
        if fname.lower().endswith(".jpg") and before < 300_000:
            print(f"⏭  {fname}  已经 {before//1024}KB，跳过")
            skipped += 1
            total_after += before
            continue

        # 备份原图（首次）
        backup_path = os.path.join(BACKUP_DIR, fname)
        if not os.path.exists(backup_path):
            shutil.copy2(src, backup_path)

        # 打开 + 等比缩 + 保存 JPG
        with Image.open(src) as im:
            im = im.convert("RGB")  # PNG 有 alpha 通道，转 RGB
            im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
            im.save(out_path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)

        # 如果原文件是 .png，新生成的 .jpg 路径不同 → 删原 PNG
        if src != out_path and os.path.exists(src):
            os.remove(src)

        after = os.path.getsize(out_path)
        total_after += after
        saving = (1 - after / before) * 100
        print(f"✅ {fname} → {sid}.jpg   {before//1024}KB → {after//1024}KB  (-{saving:.0f}%)")
        converted += 1

    print()
    print(f"━━━ 完成 ━━━")
    print(f"压缩: {converted}  跳过: {skipped}")
    print(f"总体积: {total_before/1024/1024:.1f}MB → {total_after/1024/1024:.1f}MB  "
          f"(节省 {(1-total_after/max(total_before,1))*100:.0f}%)")
    print(f"备份位于: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
