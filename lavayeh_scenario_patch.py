"""
تغییرات لازم در lavayeh_scenario.py برای ارسال bill_no به داشبورد

در هر جایی که log_event فراخوانی می‌شود، پارامتر bill_no را اضافه کنید.
همچنین در بلاک‌های except، اگر lavayeh_bill_no قبلاً استخراج شده، آن را ارسال کنید.

نمونه تغییرات:
"""

# ══════════════════════════════════════════════════════════════════════════════
# تغییر ۱: در جایی که صحت‌سنجی پرونده ناموفق است (حدود خط ۲۰۰)
# ══════════════════════════════════════════════════════════════════════════════

# قبل (کد فعلی):
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note="صحت‌سنجی پرونده ناموفق"
)
"""

# بعد (کد جدید — اضافه کردن bill_no):
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note="صحت‌سنجی پرونده ناموفق",
    bill_no=lavayeh_bill_no  # ← اضافه شده
)
"""


# ══════════════════════════════════════════════════════════════════════════════
# تغییر ۲: در بلاک except نهایی (حدود خط ۴۷۰)
# ══════════════════════════════════════════════════════════════════════════════

# قبل:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
)
"""

# بعد:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}",
    bill_no=lavayeh_bill_no  # ← اضافه شده
)
"""


# ══════════════════════════════════════════════════════════════════════════════
# تغییر ۳: در جایی که آپلود پیوست‌ها ناموفق است (حدود خط ۳۷۰)
# ══════════════════════════════════════════════════════════════════════════════

# قبل:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"آپلود پیوست‌ها ناموفق (کد لایحه: {lavayeh_bill_no})"
)
"""

# بعد:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"آپلود پیوست‌ها ناموفق",
    bill_no=lavayeh_bill_no  # ← اضافه شده
)
"""


# ══════════════════════════════════════════════════════════════════════════════
# تغییر ۴: در بلاک خطای قطعی LavayehFatalError
# ══════════════════════════════════════════════════════════════════════════════

# قبل:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"خطای قطعی: {str(e)[:200]}"
)
"""

# بعد:
"""
await log_event(
    "خطای سامانه", "لایحه", str(user_id), user_id,
    tracking_code=tracking_code, doc_name=title,
    note=f"خطای قطعی: {str(e)[:200]}",
    bill_no=lavayeh_bill_no  # ← اضافه شده
)
"""


# ══════════════════════════════════════════════════════════════════════════════
# تغییر ۵: همین تغییرات در ezhharnameh_scenario.py هم اعمال شود
# ══════════════════════════════════════════════════════════════════════════════

# در ezhharnameh_scenario.py هم دقیقاً همین تغییرات:
# هر جا log_event فراخوانی می‌شود، bill_no=bill_no اضافه شود

# ══════════════════════════════════════════════════════════════════════════════
# نکته مهم: استخراج txtBillNo حتی در صورت خطا
# ══════════════════════════════════════════════════════════════════════════════

# در بلاک except اصلی process_lavayeh_task، قبل از log_event
# سعی کنید bill_no را استخراج کنید:

"""
except Exception as e:
    # تلاش برای استخراج bill_no حتی در صورت خطا
    try:
        lavayeh_bill_no = await _extract_bill_no(sana_page)
    except Exception:
        pass  # اگر صفحه از دسترس خارج شده، bill_no قبلی استفاده می‌شود
    
    logging.error(f"[LAVAYEH] تلاش {attempt + 1} ناموفق: {e}")
    ...
    await log_event(
        "خطای سامانه", "لایحه", str(user_id), user_id,
        tracking_code=tracking_code, doc_name=title,
        note=f"...",
        bill_no=lavayeh_bill_no  # ← حالا حتی در خطا هم ارسال می‌شود
    )
"""
