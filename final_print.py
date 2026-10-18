"""
final_print.py — ارسال خودکار «چاپ نهایی» در روز بعد از ثبت.

طبق دستور کارفرما:
  ۱. پس از پایان روند امضای هر مورد (به‌جز استعلامات)، در انتهای پیام‌های
     قبلی به کاربر گفته می‌شود: «چاپ نهایی نیز در روز آینده برای شما ارسال
     می‌گردد.» (FINAL_PRINT_NOTICE)
  ۲. هر موردی (به‌جز استعلامات) که در یک روز ثبت شده، روز بعد ساعت ۱۷:۰۰
     (وقت تهران) عیناً مانند بخش «استعلام کد رهگیری» استعلام می‌شود و فقط
     چاپ برای همان کاربر ارسال می‌گردد.
  ۲.۱ هر ارسال ناموفق همان روز (بلافاصله) به مدیر اطلاع داده می‌شود
     (report_failure) و روز بعد دوباره تلاش می‌شود.
  ۳. فهرست موارد روی دیسک (final_print_queue.json) نگه‌داری می‌شود؛ اگر ربات
     قطع شده باشد، پس از راه‌اندازی مجدد همه را به خاطر دارد و اگر ساعت
     ۱۷:۰۰ امروز را از دست داده باشد، اجرای همان روز را جبران می‌کند.

ثبت مورد: record_registration(...) — از send_lavayeh_result /
send_bulk_item_result (لایحه، اظهارنامه، چک/اعسار، اعلام وکالت) و
send_tajdid_nazar_result (دعاوی اعتراضی) فراخوانی می‌شود.
اجرا: تسک استعلام معمولی با فلگ final_print=True در job_queue قرار می‌گیرد؛
scenarios.process_task در این حالت فقط چاپ را می‌فرستد و mark_sent را صدا
می‌زند (بدون ثبت استعلام در پنل، بدون پیام‌های «کد رهگیری اشتباه» و
«فرصت تکرار» مخصوص استعلام پولی).

⭐ ۱۴۰۵/۰۷ — طبق دستور کارفرما چاپ نهایی فقط وقتی ارسال می‌شود که درج امضای
همهٔ اشخاص کامل شده باشد: مورد هنگام ثبت با signed=False ذخیره می‌شود و
mark_signed(...) (از on_*_sign_submit_success پس از امضای آخرین نفر) آن را
آمادهٔ ارسال می‌کند. چاپ روز بعد از تکمیل امضا ساعت ۱۷:۰۰ ارسال می‌گردد.
موارد قدیمیِ فایل که فیلد sign_required ندارند مثل قبل ارسال می‌شوند.
اگر مدیر در پنل امضای پرونده را «درج شده» علامت بزند (Case.hasSignature)،
پیش از اجرای روزانه همان هم امضای کامل حساب می‌شود (_sync_signatures_from_panel).

⭐ ۱۴۰۵/۰۷ — چاپ درخواستی کاربر (request_print): از «پرونده‌های در انتظار
امضا و پرداخت» و «سوابق» کاربر می‌تواند همان لحظه چاپ PDF را بگیرد. همان تسک
final_print=True در صف می‌رود؛ کلید (کاربر، کد) در بخش on_demand فایل ذخیره
می‌شود تا mark_sent / report_failure مورد صف چاپ نهایی روز بعد را دست نزنند و
در خطا به خود کاربر پیام برود (نه «فردا دوباره تلاش می‌شود» به مدیر).
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
RUN_HOUR, RUN_MINUTE = 17, 0

# حداکثر دفعات تلاش برای یک مورد (هر روز یک تلاش) — پس از آن به مدیر اطلاع
MAX_ATTEMPTS = 3
# موارد ارسال‌شده پس از این تعداد روز از فایل پاک می‌شوند
KEEP_SENT_DAYS = 7
# موارد بدون امضا پس از این تعداد روز (بدون تکمیل امضا) از فایل پاک می‌شوند
KEEP_UNSIGNED_DAYS = 30

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
                    data.setdefault("on_demand", [])
                    return data
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در خواندن {STORE_FILE}: {e}")
    return {"items": [], "last_run_date": "", "on_demand": []}


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
                # ⭐ فقط پس از تکمیل درج امضا ارسال می‌شود (mark_signed)
                "sign_required": True,
                "signed": False,
                "attempts": 0,
                "last_attempt_date": "",
            })
            _save(data)
        logging.info(f"[FINAL_PRINT] مورد {tracking_code} ({cat[0]}) ثبت شد — "
                     "چاپ نهایی پس از تکمیل امضا ارسال می‌شود")
        return True
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در ثبت مورد {tracking_code}: {e}")
        return False


def mark_signed(user_id: int, *tracking_codes: str) -> bool:
    """درج امضای همهٔ اشخاص کامل شد — مورد برای چاپ نهایی روز بعد آماده می‌شود.
    چند کد قابل ارسال است (مثلاً کد رهگیری و کد ردیف دسته‌جمعی)؛ اگر هیچ کدی
    مطابقت نکند و کاربر فقط یک مورد بدون امضا داشته باشد، همان علامت می‌خورد.
    هرگز خطا پرتاب نمی‌کند."""
    try:
        codes = {str(c).strip() for c in tracking_codes if c and str(c).strip()}
        with _lock:
            data = _load()
            unsigned = [
                it for it in data["items"]
                if it.get("user_id") == int(user_id) and it.get("sign_required")
                and not it.get("signed")
            ]
            targets = [it for it in unsigned if it.get("tracking_code") in codes]
            if not targets and len(unsigned) == 1:
                # کد خالی/متفاوت ولی کاربر فقط یک مورد بدون امضا دارد — همان است
                targets = unsigned
            for it in targets:
                it["signed"] = True
                it["signed_date"] = _today()
            if targets:
                _save(data)
        # ⭐ «پرونده‌های در انتظار امضا و پرداخت»: پروندهٔ امضاشده از منو خارج شود
        try:
            import pending_cases
            pending_cases.mark_signed(user_id, *codes)
        except Exception as _pc_err:
            logging.warning(f"[FINAL_PRINT] به‌روزرسانی پرونده‌های در انتظار ناموفق: {_pc_err}")
        if targets:
            logging.info(f"[FINAL_PRINT] امضای مورد {targets[0].get('tracking_code')} کاربر "
                         f"{user_id} کامل شد — چاپ نهایی فردا ارسال می‌شود")
        else:
            logging.info(f"[FINAL_PRINT] مورد بدون امضایی برای کاربر {user_id} "
                         f"با کد {codes or '—'} پیدا نشد")
        return bool(targets)
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در mark_signed {tracking_codes}: {e}")
        return False


def mark_sent(user_id: int, tracking_code: str) -> None:
    if _pop_on_demand(user_id, tracking_code):
        logging.info(f"[FINAL_PRINT] چاپ درخواستی کد {tracking_code} برای کاربر {user_id} ارسال شد")
        return
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


async def report_failure(bot: Bot, user_id: int, tracking_code: str,
                         doc_name: str, reason: str) -> None:
    """⭐ طبق دستور کارفرما: هر ارسال ناموفق چاپ نهایی همان روز (بلافاصله)
    به مدیر اطلاع داده می‌شود. به کاربر پیامی نمی‌رود؛ مورد در صف می‌ماند
    و روز بعد ساعت ۱۷:۰۰ دوباره تلاش می‌شود (تا MAX_ATTEMPTS روز).
    ⭐ چاپ درخواستی کاربر: فقط به خود کاربر گفته می‌شود که بعداً دوباره بگیرد."""
    if _pop_on_demand(user_id, tracking_code):
        logging.warning(f"[FINAL_PRINT] چاپ درخواستی کد {tracking_code} کاربر {user_id} ناموفق: {reason}")
        try:
            await bot.send_message(user_id, ON_DEMAND_FAILED_TEXT.format(tc=tracking_code))
        except Exception:
            pass
        return
    mark_failed(user_id, tracking_code, reason)
    attempts = 0
    try:
        with _lock:
            for it in _load()["items"]:
                if it.get("user_id") == int(user_id) and it.get("tracking_code") == str(tracking_code):
                    attempts = int(it.get("attempts", 0))
    except Exception:
        pass
    retry_note = (
        "فردا ساعت ۱۷:۰۰ دوباره تلاش می‌شود."
        if attempts < MAX_ATTEMPTS else
        "این آخرین تلاش خودکار بود — لطفاً به‌صورت دستی پیگیری و چاپ را برای کاربر ارسال کنید.")
    try:
        await bot.send_message(
            ADMIN_ID,
            "⚠️ *ارسال چاپ نهایی ناموفق بود*\n\n"
            f"👤 کاربر: `{user_id}`\n"
            f"🔢 کد رهگیری: `{tracking_code}`\n"
            f"📂 نوع: {doc_name}\n"
            f"❌ علت: {(reason or 'نامشخص')[:250]}\n"
            f"🔁 تلاش {attempts} از {MAX_ATTEMPTS} — {retry_note}",
            parse_mode="Markdown")
    except Exception:
        # اگر Markdown متن خطا را نپذیرفت، بدون قالب ارسال شود
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ ارسال چاپ نهایی ناموفق — کاربر {user_id} — کد {tracking_code} — "
                f"{doc_name} — علت: {(reason or 'نامشخص')[:250]} — تلاش {attempts}/{MAX_ATTEMPTS}")
        except Exception:
            pass


# ───────────────────────── چاپ درخواستی کاربر ─────────────────────────

ON_DEMAND_FAILED_TEXT = (
    "⚠️ دریافت چاپ PDF کد رهگیری `{tc}` در حال حاضر ممکن نشد.\n"
    "لطفاً کمی بعد دوباره از همین بخش درخواست دهید.")
# هر کد حداکثر یک درخواست در جریان؛ درخواستِ گیرکرده پس از این مدت آزاد می‌شود
ON_DEMAND_STALE_HOURS = 24


def _pop_on_demand(user_id: int, tracking_code: str) -> bool:
    try:
        with _lock:
            data = _load()
            key = (int(user_id), str(tracking_code))
            before = len(data["on_demand"])
            data["on_demand"] = [r for r in data["on_demand"]
                                 if (r.get("user_id"), r.get("tracking_code")) != key]
            if len(data["on_demand"]) == before:
                return False
            _save(data)
            return True
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در on_demand {tracking_code}: {e}")
        return False


def print_in_progress(user_id: int, tracking_code: str) -> bool:
    cutoff = (now_tehran() - datetime.timedelta(hours=ON_DEMAND_STALE_HOURS)).isoformat()
    with _lock:
        return any(r.get("user_id") == int(user_id) and r.get("tracking_code") == str(tracking_code)
                   and (r.get("at") or "") >= cutoff
                   for r in _load()["on_demand"])


def queued_category(user_id: int, tracking_code: str):
    """(doc_category, doc_subcategory) موردی که در صف چاپ نهایی ثبت شده؛ None اگر نبود."""
    with _lock:
        for it in _load()["items"]:
            if it.get("user_id") == int(user_id) and it.get("tracking_code") == str(tracking_code):
                return it.get("doc_category"), it.get("doc_subcategory")
    return None


async def request_print(user_id: int, tracking_code: str, doc_category: str,
                        doc_subcategory: str | None = None) -> bool:
    """چاپ PDF همین حالا (به درخواست کاربر) در صف استعلام قرار می‌گیرد.
    False اگر درخواست قبلی همین کد هنوز در جریان باشد."""
    tracking_code = str(tracking_code).strip()
    if print_in_progress(user_id, tracking_code):
        return False
    with _lock:
        data = _load()
        key = (int(user_id), tracking_code)
        data["on_demand"] = [r for r in data["on_demand"]
                             if (r.get("user_id"), r.get("tracking_code")) != key]
        data["on_demand"].append({"user_id": int(user_id), "tracking_code": tracking_code,
                                  "at": now_tehran().isoformat(timespec="seconds")})
        _save(data)
    doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
    await runtime_state.job_queue.put({
        "user_id": int(user_id),
        "query_type": "کد رهگیری",
        "tracking_code": tracking_code,
        "doc_category": doc_category,
        "doc_subcategory": doc_subcategory,
        "doc_type": doc_name,
        "need_attachments": False,
        "full_name": "",
        "payment_fee": 0,
        "final_print": True,   # همان مسیر چاپ نهایی — فقط ارسال چاپ
        "print_caption": f"📄 *چاپ PDF* — کد رهگیری: `{tracking_code}`\n{doc_name}",
    })
    logging.info(f"[FINAL_PRINT] چاپ درخواستی کد {tracking_code} کاربر {user_id} در صف قرار گرفت")
    return True


# ───────────────────────── اجرای روزانه ─────────────────────────

def _is_signed(it: dict) -> bool:
    # موارد قدیمی (پیش از این قاعده) فیلد sign_required ندارند → مثل قبل
    return bool(it.get("signed")) or not it.get("sign_required")


def _due_items(data: dict, today: str) -> list:
    return [
        it for it in data["items"]
        if it.get("status") in ("pending", "queued")
        and _is_signed(it)                                    # ⭐ فقط با امضای کامل
        and (it.get("signed_date") or it.get("registered_date", today)) < today  # روز بعد
        and it.get("last_attempt_date") != today              # هر روز یک تلاش
    ]


def _panel_signed_date(case: dict) -> str:
    """تاریخ (تهران) signedAt پنل؛ اگر نبود/نامعتبر بود: امروز."""
    raw = str(case.get("signedAt") or "")
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(TEHRAN_TZ).date().isoformat()
    except ValueError:
        return _today()


async def _sync_signatures_from_panel() -> int:
    """موارد بدون امضا که مدیر در پنل «امضا درج شد» زده (Case.hasSignature)
    امضاشده حساب می‌شوند. خطای پنل هیچ موردی را تغییر نمی‌دهد."""
    with _lock:
        unsigned = [dict(it) for it in _load()["items"]
                    if it.get("status") in ("pending", "queued") and not _is_signed(it)]
    if not unsigned:
        return 0
    try:
        from panel_sync import find_case_in_panel
    except Exception:
        return 0
    found = {}
    for it in unsigned:
        try:
            case = await find_case_in_panel(it["user_id"], it.get("service_type") or "LAVAYEH",
                                            it["tracking_code"])
        except Exception as e:
            logging.warning(f"[FINAL_PRINT] بررسی امضای پنل برای {it['tracking_code']} ناموفق: {e}")
            continue
        if case and case.get("hasSignature"):
            found[(it["user_id"], it["tracking_code"])] = _panel_signed_date(case)
    if found:
        with _lock:
            data = _load()
            for it in data["items"]:
                key = (it.get("user_id"), it.get("tracking_code"))
                if key in found and not _is_signed(it):
                    it["signed"] = True
                    it["signed_date"] = found[key]
                    it["signed_by"] = "panel"
            _save(data)
        logging.info(f"[FINAL_PRINT] {len(found)} مورد با علامت امضای پنل آمادهٔ چاپ نهایی شد")
    return len(found)


async def run_daily_batch(bot: Bot) -> int:
    """موارد روزهای قبل را در صف استعلام قرار می‌دهد. خروجی: تعداد تسک‌ها."""
    try:
        await _sync_signatures_from_panel()
    except Exception as e:
        logging.error(f"[FINAL_PRINT] خطا در همگام‌سازی امضا از پنل: {e}")
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
        unsigned_cutoff = (now_tehran().date() - datetime.timedelta(days=KEEP_UNSIGNED_DAYS)).isoformat()
        data["items"] = [
            it for it in data["items"]
            if not (it.get("status") in ("sent", "failed")
                    and (it.get("sent_date") or it.get("last_attempt_date") or it.get("registered_date", "")) < cutoff)
            and not (not _is_signed(it) and it.get("registered_date", "") < unsigned_cutoff)
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
    """حلقهٔ زمان‌بندی: هر روز ساعت ۱۷:۰۰ تهران. اگر ربات هنگام ۱۷:۰۰ امروز
    خاموش بوده، بلافاصله پس از راه‌اندازی اجرای همان روز جبران می‌شود."""
    await asyncio.sleep(30)  # فرصت برای بالا آمدن مرورگر/لاگین
    while True:
        try:
            now = now_tehran()
            today_target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
            with _lock:
                last_run = _load().get("last_run_date", "")
            if now >= today_target and last_run != now.date().isoformat():
                logging.info("[FINAL_PRINT] اجرای ساعت ۱۷:۰۰ امروز انجام نشده — اجرا (جبرانی/به‌موقع)")
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
