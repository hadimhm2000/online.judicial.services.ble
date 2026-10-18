"""
pending_cases.py — «🖊 پرونده‌های در انتظار امضا و پرداخت» (۱۴۰۵/۰۷).

دستور کارفرما:
  ۱. گزینه‌ای در منوی اصلی برای پرونده‌هایی که امضا درج نشده و/یا هزینه
     پرداخت نشده است؛ کاربر با زدن هر پرونده مراحل باقی‌مانده را انجام می‌دهد.
     درج امضا فقط برای پرونده‌هایی فعال است که هزینه‌شان از قبل پرداخت شده.
  ۲. لایحه فقط ۴ روز در این بخش می‌ماند و بعد حذف می‌شود؛ سایر موارد همیشه.
  ۳. اگر کاربر بخواهد، چاپ PDF هم برایش ارسال می‌شود (final_print.request_print).

ثبت پرونده‌ها (بدون تغییر روند فعلی — فقط ثبت در کنار آن):
  - record_unpaid: هنگام ارسال فاکتور در send_lavayeh_result /
    send_tajdid_nazar_result (همان dict فاکتور pending_*_payments ذخیره می‌شود)
  - record_paid: هنگام شروع فلوی امضا پس از پرداخت/معافیت/پیش‌پرداخت
    (_go_to_sign_flow_after_prepaid و _tn_start_sign_flow)
  - mark_paid: پرداخت موفق فاکتور در lavayeh_successful_payment
  - mark_signed: پایان امضای همهٔ اشخاص (از final_print.mark_signed)
  - mark_cancelled: کاربر در یادآور «آیا مورد ثبتی شما کنسل است؟» بله زده

ادامهٔ روند از این منو دقیقاً از همان توابع موجود استفاده می‌کند:
  - پرداخت: فاکتور با payload {"type": "pending_case", "tc": ...}؛ پس از پرداخت
    همان dict فاکتور در pending_lavayeh_payments / pending_tn_payments گذاشته و
    lavayeh_successful_payment / tn_successful_payment صدا زده می‌شود.
  - امضا: _go_to_sign_flow_after_prepaid / _tn_start_sign_flow

ثبت‌های دسته‌جمعی منوی امضای اختصاصی خودشان را دارند و اینجا ثبت نمی‌شوند.
داده روی دیسک (pending_cases.json) نگه‌داری می‌شود تا ری‌استارت چیزی را گم نکند.
"""

import datetime
import json
import logging
import os
import threading

from final_print import TEHRAN_TZ, category_for

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_cases.json")
_lock = threading.Lock()

KIND_LAVAYEH = "lavayeh"   # لایحه، اظهارنامه، چک، اعلام وکالت، اصلاح قرارداد (send_lavayeh_result)
KIND_TN = "tn"             # دعاوی اعتراضی (send_tajdid_nazar_result)

# لایحه فقط ۴ روز در منو می‌ماند؛ سایر موارد تا درج امضا همیشه
LAVAYEH_VISIBLE_DAYS = 4
# رکوردها (برای دریافت دوبارهٔ چاپ از «سوابق») پس از این مدت پاک می‌شوند
KEEP_RECORD_DAYS = 365

# فیلدهای datetime در dict فاکتور — برای ذخیرهٔ JSON حذف/بازسازی می‌شوند
_DT_FIELDS = ("invoice_time",)


def _now() -> datetime.datetime:
    return datetime.datetime.now(TEHRAN_TZ)


def _load() -> dict:
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("items", [])
                    return data
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در خواندن {STORE_FILE}: {e}")
    return {"items": []}


def _save(data: dict) -> None:
    tmp = STORE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در ذخیرهٔ {STORE_FILE}: {e}")


def _clean_ctx(ctx: dict) -> dict:
    out = {}
    for k, v in (ctx or {}).items():
        if k in _DT_FIELDS or isinstance(v, (datetime.datetime, datetime.date)):
            continue
        out[k] = v
    # JSON-پذیر بودن (persons ممکن است شیء غیرمعمول داشته باشد)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


def _find(data: dict, user_id: int, tracking_code: str):
    for it in data["items"]:
        if it.get("user_id") == int(user_id) and it.get("tracking_code") == str(tracking_code):
            return it
    return None


def _upsert(user_id: int, kind: str, ctx: dict, paid: bool, service_type: str = "",
            title: str = "") -> bool:
    try:
        tracking_code = str((ctx or {}).get("tracking_code") or "").strip()
        if not user_id or not tracking_code:
            return False
        ctx = _clean_ctx(ctx)
        if kind == KIND_TN:
            service_type = "TAJDID_NAZAR"
            cat = category_for("TAJDID_NAZAR", case_type=ctx.get("case_type", ""))
        else:
            service_type = service_type or ctx.get("service_type") or (
                "EZHHARNAMEH" if ctx.get("is_ezhharnameh") else "LAVAYEH")
            cat = category_for(service_type, ctx.get("sign_menu_path"),
                               bool(ctx.get("is_ezhharnameh")))
        now_iso = _now().isoformat(timespec="seconds")
        with _lock:
            data = _load()
            it = _find(data, user_id, tracking_code)
            if it is None:
                it = {
                    "user_id": int(user_id),
                    "tracking_code": tracking_code,
                    "registered_at": now_iso,
                    "paid": False,
                    "signed": False,
                    "cancelled": False,
                }
                data["items"].append(it)
            # ctx قبلی با ctx جدید ادغام می‌شود (مثلاً tn_persons در شاخهٔ معافیت نیست)
            merged = dict(it.get("ctx") or {})
            merged.update({k: v for k, v in ctx.items() if v not in (None, "", [])})
            it.update({
                "kind": kind,
                "service_type": service_type,
                "title": title or ctx.get("lavayeh_title") or ctx.get("case_type") or it.get("title", ""),
                "ctx": merged,
                "doc_category": cat[0] if cat else it.get("doc_category"),
                "doc_subcategory": cat[1] if cat else it.get("doc_subcategory"),
            })
            if "final_fee" in ctx and not it.get("paid"):
                it["final_fee"] = int(ctx.get("final_fee") or 0)
            if paid and not it.get("paid"):
                it["paid"] = True
                it["paid_at"] = now_iso
            _purge(data)
            _save(data)
        return True
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در ثبت پرونده: {e}", exc_info=True)
        return False


def record_unpaid(user_id: int, kind: str, ctx: dict) -> bool:
    """فاکتور ارسال شد و هنوز پرداخت نشده. هرگز خطا پرتاب نمی‌کند."""
    return _upsert(user_id, kind, ctx, paid=False)


def record_paid(user_id: int, kind: str, ctx: dict, service_type: str = "", title: str = "") -> bool:
    """هزینه پرداخت/تسویه شده (یا کاربر معاف است) و پرونده آمادهٔ درج امضاست."""
    return _upsert(user_id, kind, ctx, paid=True, service_type=service_type, title=title)


def _set(user_id: int, tracking_codes, **fields) -> bool:
    try:
        codes = {str(c).strip() for c in tracking_codes if c and str(c).strip()}
        if not codes:
            return False
        changed = False
        with _lock:
            data = _load()
            for it in data["items"]:
                if it.get("user_id") == int(user_id) and it.get("tracking_code") in codes:
                    it.update(fields)
                    changed = True
            if changed:
                _save(data)
        return changed
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در به‌روزرسانی {tracking_codes}: {e}")
        return False


def mark_paid(user_id: int, tracking_code: str) -> bool:
    return _set(user_id, [tracking_code], paid=True, paid_at=_now().isoformat(timespec="seconds"))


def mark_signed(user_id: int, *tracking_codes: str) -> bool:
    return _set(user_id, tracking_codes, signed=True, signed_at=_now().isoformat(timespec="seconds"))


def mark_cancelled(user_id: int, tracking_code: str) -> bool:
    return _set(user_id, [tracking_code], cancelled=True)


def _registered(it: dict) -> datetime.datetime:
    try:
        dt = datetime.datetime.fromisoformat(it.get("registered_at") or "")
        return dt if dt.tzinfo else dt.replace(tzinfo=TEHRAN_TZ)
    except ValueError:
        return _now()


def _is_visible(it: dict, now: datetime.datetime) -> bool:
    if it.get("signed") or it.get("cancelled"):
        return False
    if it.get("service_type") == "LAVAYEH":
        return now - _registered(it) < datetime.timedelta(days=LAVAYEH_VISIBLE_DAYS)
    return True


def _purge(data: dict) -> None:
    cutoff = _now() - datetime.timedelta(days=KEEP_RECORD_DAYS)
    data["items"] = [it for it in data["items"] if _registered(it) >= cutoff]


def open_cases(user_id: int, now: datetime.datetime | None = None) -> list:
    """پرونده‌های بدون امضای کاربر که باید در منو نمایش داده شوند (جدیدترین اول)."""
    now = now or _now()
    with _lock:
        items = [dict(it) for it in _load()["items"]
                 if it.get("user_id") == int(user_id) and _is_visible(it, now)]
    items.sort(key=lambda it: it.get("registered_at") or "", reverse=True)
    return items


def get(user_id: int, tracking_code: str) -> dict | None:
    with _lock:
        it = _find(_load(), user_id, tracking_code)
        return dict(it) if it else None


def is_open(user_id: int, tracking_code: str) -> dict | None:
    """همان get، فقط اگر پرونده هنوز در منو قابل نمایش باشد."""
    it = get(user_id, tracking_code)
    return it if it and _is_visible(it, _now()) else None


def print_category(user_id: int, tracking_code: str):
    """(doc_category, doc_subcategory) منوی استعلام برای دریافت چاپ؛ None اگر نامشخص."""
    it = get(user_id, tracking_code)
    if it and it.get("doc_category"):
        return it["doc_category"], it.get("doc_subcategory")
    return None


def payment_context(it: dict) -> dict:
    """dict فاکتور برای pending_lavayeh_payments / pending_tn_payments."""
    ctx = dict(it.get("ctx") or {})
    ctx["tracking_code"] = it["tracking_code"]
    ctx["final_fee"] = int(it.get("final_fee") or ctx.get("final_fee") or 0)
    ctx["invoice_time"] = datetime.datetime.now()
    ctx["reminder_sent"] = True   # یادآور «کنسل است؟» برای فاکتور ادامهٔ روند تکرار نشود
    ctx["blocked"] = False
    ctx.setdefault("court_total", 0)
    ctx.setdefault("national_ids", "")
    return ctx


async def sync_with_panel(user_id: int) -> None:
    """امضای ثبت‌شده توسط مدیر (hasSignature) و پرداخت تأییدشده در پنل
    (feeStatus) روی دفتر اعمال می‌شود. خطای پنل چیزی را تغییر نمی‌دهد.

    ⚠️ وضعیت CANCELLED پنل عمداً نادیده گرفته می‌شود: stale_requests پرونده‌های
    بی‌اقدام را پس از ۲۴ ساعت لغو می‌کند، ولی طبق دستور کارفرما این پرونده‌ها
    (به‌جز لایحه پس از ۴ روز) باید همیشه قابل ادامه باشند.
    """
    if not open_cases(user_id):
        return
    try:
        from panel_sync import get_user_cases
        cases = await get_user_cases(user_id, limit=30)
    except Exception as e:
        logger.warning(f"[PENDING_CASES] دریافت پرونده‌های پنل ناموفق: {e}")
        return
    if not cases:
        return
    signed, paid = [], []
    for c in cases:
        tc = str(c.get("trackingCode") or "")
        if not tc:
            continue
        if c.get("hasSignature"):
            signed.append(tc)
        if c.get("feeStatus") in ("PAID", "MANUAL_APPROVED"):
            paid.append(tc)
    if signed:
        mark_signed(user_id, *signed)
    for tc in paid:
        it = get(user_id, tc)
        if it and not it.get("paid"):
            mark_paid(user_id, tc)
