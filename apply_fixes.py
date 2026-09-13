#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فعال‌سازی بخش‌های «ثبت دادخواست چک» و «دعاوی اعتراضی» برای همهٔ کاربران.

این دو بخش قبلاً فقط برای مدیر (ADMIN_ID) فعال بود:
  ۱) در keyboards.py دکمه‌ها برای غیرمدیرها با پسوند «(به زودی)» نمایش
     داده می‌شد (و هندلرها فقط روی متن دقیق فعال‌اند)؛
  ۲) در handlers.py شاخه‌های process_flow_type برای غیرمدیر پیام
     «در حال توسعه است» می‌دادند و return می‌کردند.

این اسکریپت هر ۴ اصلاح را با anchor دقیق اعمال می‌کند و برای هر فایل
یک نسخهٔ پشتیبان .bak می‌گیرد.

روش استفاده:
  ۱. این اسکریپت و fixes.json را در ریشهٔ پروژه کنار keyboards.py و
     handlers.py کپی کنید.
  ۲. اجرا:  python apply_fixes.py
"""
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    fixes_file = root / "fixes.json"
    if not fixes_file.exists():
        print("[خطا] fixes.json کنار این اسکریپت یافت نشد.")
        return 1

    fixes = json.loads(fixes_file.read_text(encoding="utf-8"))
    failed = False

    for fx in fixes:
        path = root / fx["file"]
        title = fx["title"]
        if not path.exists():
            print(f"[خطا] {fx['file']} ← {title}: فایل یافت نشد.")
            failed = True
            continue

        src = path.read_text(encoding="utf-8")
        count = src.count(fx["old"])
        if count != 1:
            print(f"[خطا] {fx['file']} ← {title}: تعداد تطبیق = {count} (باید دقیقاً ۱ باشد) — اعمال نشد.")
            failed = True
            continue

        bak = path.parent / (path.name + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)

        path.write_text(src.replace(fx["old"], fx["new"], 1), encoding="utf-8")
        print(f"[OK] {fx['file']} ← {title}")

    if failed:
        print("\n⚠ تعدادی اصلاح اعمال نشد — فایل‌های .bak بدون تغییر مانده‌اند. خروجی: شکست")
        return 1
    print("\n✅ همهٔ اصلاحات با موفقیت اعمال شد. ربات را ری‌استارت کنید.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
