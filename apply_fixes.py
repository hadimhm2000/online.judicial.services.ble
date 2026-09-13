#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اصلاح «ارسال مکرر پیام عذرخواهی بازیابی کرش» — ارسال فقط یک‌بار برای هر پرونده.

ریشهٔ باگ: entry کاربر برای همیشه در pending_lavayeh_sign / pending_ezhhar_sign /
pending_ezhhar_sana_fix می‌ماند و state_persister هر ۶۰ ثانیه آن را دوباره
ذخیره می‌کند؛ با هر کرش/ری‌استارت، notify_crash_recovery دوباره همان پیام
«بابت اختلال پیش‌آمده...» را می‌فرستاد — حتی ماه‌ها بعد.

این بسته دو لایهٔ دفاع نصب می‌کند:
  ۱) dedupe با اثر انگشت پرونده (recovery_notified — persist می‌شود):
     هر کاربر فقط یک‌بار برای هر پرونده/رویداد اطلاع‌رسانی می‌شود؛
     پرونده یا رویداد جدید → اثر انگشت جدید → اطلاع‌رسانی دوباره.
  ۲) پیشنهاد تکمیلی — TTL صف‌ها (cleanup_expired_pending_entries):
     entryهای بیش از ۲۴ ساعت عدم فعالیت از صف‌های امضا/پرداخت پاک می‌شوند
     (قابل تنظیم با _PENDING_TTL_HOURS)؛ ریشهٔ ماندگاری ابدی را هم قطع می‌کند.

روش استفاده:
  ۱. این اسکریپت و fixes.json را در ریشهٔ پروژه کپی کنید.
  ۲. اجرا:  python apply_fixes.py
  ۳. python -m py_compile runtime_state.py persistence.py bot.py
  ۴. ری‌استارت ربات.

نکته: کاربر گیرافتادهٔ فعلی ممکن است یک بار دیگر (فقط یک بار) پیام بگیرد،
چون هنوز برای پروندهٔ فعلی‌اش اثر انگشت ثبت نشده؛ از کرش بعدی به بعد
تکرار متوقف می‌شود.
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
