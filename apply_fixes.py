#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اعمال خودکار اصلاحات راند ۲ سامانه ثنا:
  الف) تشخیص/مدیریت پاپ‌آپ «ورود همزمان/انقضای نشست» در آماده‌سازی لایحه و اظهارنامه
     (اطلاع به مدیر برای لاگین مجدد + ادامهٔ همان تلاش — به‌جای ۳ بار retry بی‌فایده)
  ب) فلوی /send: سؤال «آیا ناوبری امضا پس از پرداخت انجام شود؟» ← نوع درخواست ←
     (مسیر امضای چک/نوع دعوی) — فعال‌سازی خودکار ناوبری امضا پس از پرداخت کاربر

روش استفاده:
  ۱. این اسکریپت و fixes.json را در «ریشهٔ پروژه» کنار فایل‌های سورس کپی کنید.
  ۲. اجرا:  python apply_fixes.py

هر اصلاح فقط وقتی اعمال می‌شود که متنِ هدف «دقیقاً یک‌بار» پیدا شود؛
در غیر این صورت رد می‌شود و کد خروجی غیرصفر می‌گیرید. برای هر فایل
فقط یک‌بار نسخهٔ پشتیبان .bak گرفته می‌شود.
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
    print("\n✅ همهٔ اصلاحات با موفقیت اعمال شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
