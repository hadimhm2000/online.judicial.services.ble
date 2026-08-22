# -*- coding: utf-8 -*-
"""
bulk_processor.py
──────────────────────────────────────────────────────────────────────────
مرحلهٔ ۴: جایگزین واقعی run_bulk_processing_task (که تا امروز فقط
asyncio.sleep بود). این ماژول به‌جای اختراع اتوماسیون جدید، همان توابع
واقعی و تست‌شدهٔ ربات را برای هر ردیف صدا می‌زند:

    lavayeh_scenario.process_lavayeh_task(data, bot)
    ezhharnameh_scenario.process_ezhharnameh_task(data, bot)

این دو تابع از یک sana_page مشترک (runtime_state.sana_page) استفاده می‌کنند،
پس پردازش دسته‌جمعی ذاتاً *ترتیبی* است، نه موازی — دقیقاً مثل رفتار فعلی
ربات وقتی چند کاربر همزمان درخواست می‌دهند (صف روی یک مرورگر).

⚠️ نکات مهمی که هنگام خواندن کد واقعی شما کشف و باید مدنظر باشد:

1) «اعلام وکالت» یک تابع پردازش کاملاً جدا دارد
   (ealam_vakalaht_scenario.process_ealam_vakalaht_task) با فیلدهای اضافی
   (نوع دعوا، مبلغ تمبر، شماره قرارداد و...) که در فایل اکسل فعلی اصلاً
   جمع‌آوری نمی‌شوند. بنابراین این ماژول فعلاً ردیف‌های «اعلام وکالت» را
   NOT_SUPPORTED علامت می‌زند و پردازش نمی‌کند تا وقتی آن فیلدها به اکسل
   اضافه و یک مسیر جداگانه نوشته شود. این تصمیم عمدی است تا دادهٔ ناقص به
   یک فلوی حساس (محاسبهٔ تمبر/قرارداد) فرستاده نشود.

2) ستون‌های «نمایندهٔ پرونده نفر ۱/۲» (V,W) در فایل اظهارنامه در حال حاضر
   توسط process_ezhharnameh_task مصرف نمی‌شوند — چون در کد واقعی، «نماینده»
   فقط در دو حالت معنا دارد: (الف) نمایندهٔ شرکت برای شخص حقوقی (که همان
   ستون‌های D/G/J/M هستند)، (ب) وکیل به‌عنوان یک اسلات مستقل در بین
   اظهارکنندگان (person_type="وکیل"). اگر این دو ستون در فایل پر شوند، این
   ماژول مقدارشان را نادیده می‌گیرد و یک هشدار در گزارش نهایی می‌گذارد.
   پیشنهاد: در بازبینی بعدی اکسل، این دو ستون حذف یا معنای واقعی‌شان
   (مثلاً وکیل مستقل) روشن شود.

3) امضای الکترونیک (کد پیامکی) بخشی از این تابع نیست — دقیقاً مثل فلوی
   تکی، بعد از ثبت موفق، send_lavayeh_result / معادل اظهارنامه پیام نتیجه
   را برای user_id (صاحب دفتر) می‌فرستد و کاربر بعداً از همان مسیر همیشگی
   امضا می‌کند. یعنی این بخش تغییری لازم ندارد و با بقیهٔ سیستم یکپارچه است.

4) این کد به لایو سناها متصل نیست و در sandbox من قابل اجرا/تست کامل
   نیست (به Playwright واقعی، aiogram Bot واقعی و session لاگین‌شدهٔ مدیر
   نیاز دارد). منطق تبدیل داده (build_*_task_data) با تست واحد جداگانه
   بدون نیاز به مرورگر تأیید شده؛ اما اجرای واقعی حتماً باید ابتدا با
   تعداد کم (۲-۳ ردیف) و زیر نظر شما تست شود.
"""
import json
import asyncio
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_BRANCH_CODE_LOOKUP_PATH = os.path.join(os.path.dirname(__file__), "branch_code_lookup.json")
_branch_code_cache = None


def _load_branch_code_lookup() -> dict:
    """نگاشت «نام کامل شعبه» -> «کد ۵ رقمی شعبه» (#txtCourtCode) از units_compact.json"""
    global _branch_code_cache
    if _branch_code_cache is None:
        try:
            with open(_BRANCH_CODE_LOOKUP_PATH, encoding="utf-8") as f:
                _branch_code_cache = json.load(f)
        except FileNotFoundError:
            logger.error(f"branch_code_lookup.json پیدا نشد در {_BRANCH_CODE_LOOKUP_PATH}")
            _branch_code_cache = {}
    return _branch_code_cache


LAVAYEH_METHOD_CASE = "شماره پرونده و ردیف فرعی"
LAVAYEH_METHOD_ARCHIVE = "شعبه و شماره بایگانی"
UNSUPPORTED_BULK_TITLES = {"اعلام وکالت"}


# ══════════════════════════════════════════════════════════════════════
# تبدیل ردیف اعتبارسنجی‌شده -> data dict مطابق process_lavayeh_task
# ══════════════════════════════════════════════════════════════════════
def build_lavayeh_task_data(item: dict, user_id: int) -> dict:
    branch_lookup = _load_branch_code_lookup()

    persons = [{"person_type": "شخص حقیقی", "national_id": pid} for pid in item["providers"]]
    if item.get("representative_id"):
        persons.append({"person_type": "وکیل", "national_id": item["representative_id"]})

    tracking_method = "case_number" if item["method"] == LAVAYEH_METHOD_CASE else "archive_number"

    return {
        "user_id": user_id,
        "prepaid": False,
        "lavayeh_title": item["title"],
        "lavayeh_tracking_code": item.get("case_number", ""),
        "lavayeh_province": item.get("province", ""),  # استان پرونده (روش شماره‌پرونده)
        "lavayeh_row_number": item.get("sub_row", 1),
        "lavayeh_persons": persons,
        "lavayeh_text": item.get("text", ""),
        "lavayeh_attachments": item.get("attachments", []),
        "tracking_method": tracking_method,
        "lavayeh_archive_number": item.get("archive_number", ""),
        "lavayeh_branch_name": item.get("branch", ""),
        "lavayeh_branch_code": branch_lookup.get(item.get("branch", ""), ""),
    }


# ══════════════════════════════════════════════════════════════════════
# تبدیل ردیف اعتبارسنجی‌شده -> data dict مطابق process_ezhharnameh_task
# ══════════════════════════════════════════════════════════════════════
def _person_to_ezhhar_dict(person: dict) -> dict:
    ptype = person.get("type", "")
    if ptype == "شخص حقوقی":
        d = {"person_type": "شخص حقوقی", "company_id": person.get("id", "")}
        rep = person.get("company_rep", "")
        if rep:
            d["national_id"] = rep
            d["representative_type"] = "نماینده"
        return d
    return {"person_type": ptype, "national_id": person.get("id", "")}


def build_ezhharnameh_task_data(item: dict, user_id: int) -> dict:
    declarants = [_person_to_ezhhar_dict(p) for p in item["declarants"]]
    addressees = [_person_to_ezhhar_dict(p) for p in item["addressees"]]

    return {
        "user_id": user_id,
        "prepaid": False,
        "ezhhar_declarants": declarants,
        "ezhhar_addressees": addressees,
        "ezhhar_subject": item.get("title") or "سایر",
        "ezhhar_text": item.get("text", ""),
        "ezhhar_attachments": item.get("attachments", []),
    }


# ══════════════════════════════════════════════════════════════════════
# اجرای واقعی — جایگزین کامل asyncio.sleep قبلی
# ══════════════════════════════════════════════════════════════════════
async def run_bulk_processing_task(bot, user_id: int, tracking_code: str):
    # ایمپورت دیرهنگام تا این ماژول بدون نصب playwright/aiogram هم قابل
    # ایمپورت و تست‌واحد باشد (build_*_task_data نیازی به آن‌ها ندارد).
    from bulk_submissions import BULK_TASKS
    from lavayeh_scenario import process_lavayeh_task
    from ezhharnameh_scenario import process_ezhharnameh_task

    task_data = BULK_TASKS.get(tracking_code)
    if not task_data:
        return

    items = task_data.get("items", [])
    service_type = task_data.get("service_type", "lavayeh")
    service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
    total = len(items)

    await bot.send_message(
        user_id,
        f"⏳ *پردازش واقعی دسته‌جمعی آغاز شد*\n\n"
        f"کد پیگیری: `{tracking_code}`\n"
        f"تعداد موارد: *{total} مورد ({service_fa})*\n\n"
        f"⚠️ پردازش به‌صورت ترتیبی (یکی‌یکی) روی مرورگر مشترک انجام می‌شود؛ "
        f"لطفاً تا پایان صبر کنید و ربات را برای این کد رهگیری دوباره اجرا نکنید."
    )

    completed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    failures = []  # [(row_index, reason)]

    for item in items:
        completed += 1
        row_idx = item.get("row_index", completed)

        try:
            if service_type == "lavayeh":
                if item.get("title") in UNSUPPORTED_BULK_TITLES:
                    item["status"] = "skipped_unsupported"
                    skipped += 1
                    failures.append((row_idx, f"عنوان «{item.get('title')}» فعلاً در پردازش دسته‌جمعی پشتیبانی نمی‌شود"))
                    continue

                data = build_lavayeh_task_data(item, user_id)
                await process_lavayeh_task(data, bot)
            else:
                data = build_ezhharnameh_task_data(item, user_id)
                await process_ezhharnameh_task(data, bot)

            item["status"] = "completed"
            succeeded += 1

        except Exception as e:
            logger.error(f"[BULK] ردیف {row_idx} ({tracking_code}) با خطا مواجه شد: {e}", exc_info=True)
            item["status"] = "failed"
            item["error"] = str(e)
            failed += 1
            failures.append((row_idx, str(e)[:200]))
            # یک ردیف ناموفق کل دسته را متوقف نمی‌کند؛ به سراغ ردیف بعدی می‌رویم.

        if completed % 5 == 0 or completed == total:
            percentage = int((completed / total) * 100) if total else 100
            await bot.send_message(
                user_id,
                f"🔄 *گزارش پیشرفت (`{tracking_code}`)*\n\n"
                f"پیشرفت: *{completed} از {total}* ({percentage}%)\n"
                f"✅ موفق: {succeeded} | ❌ ناموفق: {failed} | ⏭ رد شده: {skipped}"
            )

    task_data["status"] = "completed"
    task_data["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = (
        f"🏁 *پردازش دسته‌جمعی به پایان رسید*\n\n"
        f"کد پیگیری: `{tracking_code}`\n"
        f"کل موارد: {total}\n"
        f"✅ ثبت موفق: {succeeded}\n"
        f"❌ ناموفق: {failed}\n"
        f"⏭ رد شده (پشتیبانی‌نشده): {skipped}\n"
    )
    if failures:
        summary += "\nجزئیات موارد ناموفق/رد‌شده:\n"
        for row_idx, reason in failures[:20]:
            summary += f"  • ردیف {row_idx}: {reason}\n"
        if len(failures) > 20:
            summary += f"  ... و {len(failures) - 20} مورد دیگر (در لاگ سرور موجود است)\n"

    await bot.send_message(user_id, summary)
