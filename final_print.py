"""
final_print.py — ارسال خودکار «چاپ نهایی» در روز بعد از ثبت.

طبق دستور کارفرما:
  ۱. پس از پایان روند امضای هر مورد (به‌جز استعلامات)، در انتهای پیام‌های
     قبلی به کاربر گفته می‌شود: «چاپ نهایی نیز در روز آینده برای شما ارسال
     می‌گردد.» (FINAL_PRINT_NOTICE)
  ۲. هر موردی (به‌جز استعلامات) که در یک روز ثبت شده، روز بعد ساعت ۱۵:۴۵
     (وقت تهران) عیناً مانند بخش «استعلام کد رهگیری» استعلام می‌شود و فقط
     چاپ برای همان کاربر ارسال می‌گردد.
  ۳. فهرست موارد روی دیسک (final_print_queue.json) نگه‌داری می‌شود؛ اگر ربات
     قطع شده باشد، پس از راه‌اندازی مجدد همه را به خاطر دارد و اگر ساعت
     ۱۵:۴۵ امروز را از دست داده باشد، اجرای همان روز را جبران می‌کند.

ثبت مورد: record_registration(...) — از send_lavayeh_result /
send_bulk_item_result (لایحه، اظهارنامه، چک/اعسار، اعلام وکالت) و
send_tajdid_nazar_result (دعاوی اعتراضی) فراخوانی می‌شود.
اجرا: تسک استعلام معمولی با فلگ final_print=True در job_queue قرار می‌گیرد؛
scenarios.process_task در این حالت فقط چاپ را می‌فرستد و mark_sent را صدا
می‌زند (بدون ثبت استعلام در پنل، بدون پیام‌های «کد رهگیری اشتباه» و
«فرصت تکرار» مخصوص استعلام پولی).
"""

import asyncio
import datetime
import json
import logging
import os
import threading

from aiogram import Bot

import runtime_state
from config import ADMIN_ID

FINAL_PRINT_NOTICE = "📬 چاپ نهایی نیز در روز آینده برای شما ارسال می‌گردد."

# ایران از ۱۴۰۱ ساعت تابستانی ندارد — منطقهٔ زمانی ثابت UTC+03:30
# (بدون وابستگی به پایگاه دادهٔ tzdata که روی ویندوز ممکن است نصب نباشد)
TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30), "Asia/Tehran")
RUN_HOUR, RUN_MINUTE = 15, 45

# حداکثر دفعات تلاش برای یک مورد (هر روز یک تلاش) — پس از آن به مدیر اطلاع
MAX_ATTEMPTS = 3
# موارد ارسال‌شده پس از این تعداد روز از فایل پاک می‌شوند
KEEP_SENT_DAYS = 7

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "final_print_queue.json")
_lock = threading.Lock()

# دسته‌بندی‌های منوی استعلام (عیناً کلیدهای nav در بخش «کد رهگیری» scenarios)
_OBJECTION_SUB_MENUS = {
    "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
    "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
    "اعتراض ثالث", "اعتراض به قرار دادسرا",
}


def now_tehran() -> datetime.datetime:
    return datetime.datetime.now(TEHRAN_TZ)


def _today() -> str:
    return now_tehran().date().isoformat()


# ───────────────────────── ذخیره‌سازی روی دیسک ─────────────────────────

def _load() -> dict:
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("items", [])
                    data.setdefault("last_run_date", "")
                    return data
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در خواندن {STORE_FILE}: {e}")
    return {"items": [], "last_run_date": ""}


def _save(data: dict) -> None:
    tmp = STORE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE_FILE)  # نوشتن اتمیک — در قطعی ناگهانی فایل خراب نمی‌شود
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در ذخیرهٔ {STORE_FILE}: {e}")


# ───────────────────────── نگاشت نوع سرویس → منوی استعلام ─────────────────

def category_for(service_type: str | None, sign_menu_path: list | None = None,
                 is_ezhharnameh: bool = False, case_type: str = ""):
    """(doc_category, doc_subcategory) منوی استعلام برای یک مورد ثبت‌شده؛
    None اگر مورد استعلام/نامشخص باشد (در این صورت ثبت نمی‌شود)."""
    svc = (service_type or "").upper()
    path = [p for p in (sign_menu_path or []) if p]

    if svc in ("INQUIRY", "ADMIN_SEND"):
        return None
    if svc == "TAJDID_NAZAR" or case_type or (path and path[0] in _OBJECTION_SUB_MENUS):
        sub = case_type or (path[0] if path else "")
        return ("دعاوی اعتراضی", sub) if sub else None
    if svc == "EZHHARNAMEH" or is_ezhharnameh:
        return ("اظهارنامه", None)
    if svc == "CHECK":
        if any("دادخواست بدوی" in p for p in path):
            return ("دادخواست بدوی", None)
        if any(("دعاوی حقوقی" in p) or ("صلح" in p) for p in path):
            return ("دعاوی دادگاههای صلح", None)
        return None  # مسیر نامشخص — بدون حدس
    if svc in ("LAVAYEH", "EALAM_VAKALAHT", ""):
        return ("لایحه", None)
    return None


def record_registration(user_id: int, tracking_code: str, *, service_type: str | None = None,
                        sign_menu_path: list | None = None, is_ezhharnameh: bool = False,
                        case_type: str = "", title: str = "") -> bool:
    """ثبت یک مورد برای ارسال چاپ نهایی در روز بعد. هرگز خطا پرتاب نمی‌کند."""
    try:
        tracking_code = str(tracking_code or "").strip()
        if not user_id or not tracking_code:
            return False
        cat = category_for(service_type, sign_menu_path, is_ezhharnameh, case_type)
        if not cat:
            logging.info(
                f"[FINAL_PRINT] مورد {tracking_code} (سرویس {service_type}) ثبت نشد — "
                "دسته‌بندی منوی استعلام نامشخص یا از نوع استعلام است")
            return False
        with _lock:
            data = _load()
            for it in data["items"]:
                if it.get("user_id") == int(user_id) and it.get("tracking_code") == tracking_code:
                    return True  # تکراری
            data["items"].append({
                "user_id": int(user_id),
                "tracking_code": tracking_code,
                "doc_category": cat[0],
                "doc_subcategory": cat[1],
                "title": title or "",
                "service_type": service_type or "",
                "registered_date": _today(),
                "registered_at": now_tehran().isoformat(timespec="seconds"),
                "status": "pending",
                "attempts": 0,
                "last_attempt_date": "",
            })
            _save(data)
        logging.info(f"[FINAL_PRINT] مورد {tracking_code} ({cat[0]}) برای چاپ نهایی فردا ثبت شد")
        return True
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در ثبت مورد {tracking_code}: {e}")
        return False


def mark_sent(user_id: int, tracking_code: str) -> None:
    try:
        with _lock:
            data = _load()
            for it in data["items"]:
                if it.get("user_id") == int(user_id) and it.get("tracking_code") == str(tracking_code):
                    it["status"] = "sent"
                    it["sent_date"] = _today()
            _save(data)
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در mark_sent {tracking_code}: {e}")


def mark_failed(user_id: int, tracking_code: str, reason: str = "") -> None:
    """یک تلاش ناموفق — مورد pending می‌ماند تا فردا دوباره تلاش شود
    (تا MAX_ATTEMPTS)."""
    try:
        with _lock:
            data = _load()
            for it in data["items"]:
                if it.get("user_id") == int(user_id) and it.get("tracking_code") == str(tracking_code):
                    if it.get("status") != "sent":
                        it["status"] = "pending"
                        it["last_error"] = (reason or "")[:300]
            _save(data)
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در mark_failed {tracking_code}: {e}")


# ───────────────────────── اجرای روزانه ─────────────────────────

def _due_items(data: dict, today: str) -> list:
    return [
        it for it in data["items"]
        if it.get("status") in ("pending", "queued")
        and it.get("registered_date", today) < today          # فقط موارد روزهای قبل
        and it.get("last_attempt_date") != today              # هر روز یک تلاش
    ]


async def run_daily_batch(bot: Bot) -> int:
    """موارد روزهای قبل را در صف استعلام قرار می‌دهد. خروجی: تعداد تسک‌ها."""
    today = _today()
    exhausted = []
    queued = []
    with _lock:
        data = _load()
        for it in _due_items(data, today):
            if int(it.get("attempts", 0)) >= MAX_ATTEMPTS:
                it["status"] = "failed"
                exhausted.append(dict(it))
                continue
            it["attempts"] = int(it.get("attempts", 0)) + 1
            it["last_attempt_date"] = today
            it["status"] = "queued"
            queued.append(dict(it))
        # پاکسازی موارد ارسال‌شده/ناموفقِ قدیمی
        cutoff = (now_tehran().date() - datetime.timedelta(days=KEEP_SENT_DAYS)).isoformat()
        data["items"] = [
            it for it in data["items"]
            if not (it.get("status") in ("sent", "failed")
                    and (it.get("sent_date") or it.get("last_attempt_date") or it.get("registered_date", "")) < cutoff)
        ]
        data["last_run_date"] = today
        _save(data)

    for it in queued:
        doc_name = (f"{it['doc_category']} - {it['doc_subcategory']}"
                    if it.get("doc_subcategory") else it["doc_category"])
        await runtime_state.job_queue.put({
            "user_id": it["user_id"],
            "query_type": "کد رهگیری",
            "tracking_code": it["tracking_code"],
            "doc_category": it["doc_category"],
            "doc_subcategory": it.get("doc_subcategory"),
            "doc_type": doc_name,
            "need_attachments": False,
            "full_name": "",
            "payment_fee": 0,
            "final_print": True,   # ⭐ فقط چاپ؛ بدون پیام‌ها/ثبت‌های مخصوص استعلام پولی
        })

    try:
        if queued or exhausted:
            lines = [f"🗂 *چاپ نهایی روزانه ({today})*", f"📤 {len(queued)} مورد در صف استعلام و ارسال چاپ قرار گرفت."]
            if exhausted:
                lines.append(f"⚠️ {len(exhausted)} مورد پس از {MAX_ATTEMPTS} روز تلاش ارسال نشد:")
                for it in exhausted[:20]:
                    lines.append(f"• کاربر `{it['user_id']}` — کد `{it['tracking_code']}` ({it['doc_category']})"
                                 + (f" — {it.get('last_error','')[:80]}" if it.get("last_error") else ""))
            await bot.send_message(ADMIN_ID, "\n".join(lines), parse_mode="Markdown")
    except Exception:
        pass
    logging.info(f"[FINAL_PRINT] اجرای روزانه: {len(queued)} مورد در صف، {len(exhausted)} مورد ناموفق نهایی")
    return len(queued)


def _next_run_at(now: datetime.datetime) -> datetime.datetime:
    target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    return target


async def final_print_scheduler(bot: Bot):
    """حلقهٔ زمان‌بندی: هر روز ساعت ۱۵:۴۵ تهران. اگر ربات هنگام ۱۵:۴۵ امروز
    خاموش بوده، بلافاصله پس از راه‌اندازی اجرای همان روز جبران می‌شود."""
    await asyncio.sleep(30)  # فرصت برای بالا آمدن مرورگر/لاگین
    while True:
        try:
            now = now_tehran()
            today_target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
            with _lock:
                last_run = _load().get("last_run_date", "")
            if now >= today_target and last_run != now.date().isoformat():
                logging.info("[FINAL_PRINT] اجرای ساعت ۱۵:۴۵ امروز انجام نشده — اجرا (جبرانی/به‌موقع)")
                await run_daily_batch(bot)
                continue
            wait_s = (_next_run_at(now) - now).total_seconds()
            # حداکثر ۱۰ دقیقه‌ای بیدار می‌شویم تا تغییر ساعت سیستم/خواب رایانه جبران شود
            await asyncio.sleep(max(5.0, min(wait_s, 600.0)))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"[FINAL_PRINT] خطا در زمان‌بند: {e}", exc_info=True)
            await asyncio.sleep(60)
