"""
panel_sync.py — ثبت رویدادهای استعلام در پنل ادمین (Next.js API)

این ماژول وظیفه ارسال داده‌های استعلام، لایحه و سایر خدمات
به API پنل ادمین را بر عهده دارد تا در دیتابیس SQLite ذخیره شوند
و در پنل ادمین قابل مشاهده باشند.

⭐ نسخه اصلاح‌شده (رفع خطای «خطا در ارتباط با پنل ادمین: TimeoutError()»):
  ۱) Session مشترک aiohttp — قبلاً برای «هر» درخواست یک ClientSession جدید
     ساخته می‌شد (handshake TCP جدید + بدون connection reuse). حالا یک
     session سراسری lazy ساخته و مجدداً استفاده می‌شود.
  ۲) Timeout واقع‌بینانه — قبلاً total=10s بود که در حالت dev بودن پنل
     (کامپایل on-demand مسیرهای Next.js) یا شلوغی سرور، مرتباً Timeout
     می‌داد. حالا total=25s و connect=10s.
  ۳) Retry خودکار — هر درخواست حداکثر ۳ تلاش (با تاخیر ۱ و ۳ ثانیه).
     امن است، چون پنل خودش Case تکراری را تشخیص می‌دهد (_duplicate).
  ۴) Circuit Breaker — اگر پنل چند بار پشت‌سرهم پاسخ ندهد، به‌مدت ۵
     دقیقه تماس‌های جدید بلافاصله (بدون انتظار) رد می‌شوند تا فلوی اصلی
     ربات کند نشود. اولین موفقیت، بریکر را ریست می‌کند.
"""
import asyncio
import logging
import time

import aiohttp

from config import ADMIN_API_BASE

logger = logging.getLogger(__name__)

# ── تنظیمات اتصال ──────────────────────────────────────────────────────
_PANEL_TIMEOUT = aiohttp.ClientTimeout(total=25, connect=10)
_PANEL_RETRIES = 3          # تعداد کل تلاش‌ها برای هر درخواست
_RETRY_DELAYS = (1.0, 3.0)  # تاخیر قبل از تلاش ۲ و ۳ (ثانیه)

# ── Session مشترک ──────────────────────────────────────────────────────
_panel_session: aiohttp.ClientSession | None = None


def _get_panel_session() -> aiohttp.ClientSession:
    """دریافت session مشترک (lazy) — اتصال‌ها بین درخواست‌ها keep-alive می‌مانند."""
    global _panel_session
    if _panel_session is None or _panel_session.closed:
        connector = aiohttp.TCPConnector(
            ssl=False,
            limit=20,             # حداکثر اتصال همزمان
            ttl_dns_cache=300,    # کش DNS
            enable_cleanup_closed=True,
        )
        _panel_session = aiohttp.ClientSession(
            connector=connector,
            timeout=_PANEL_TIMEOUT,
        )
    return _panel_session


# ── Circuit Breaker ────────────────────────────────────────────────────
_BREAKER_THRESHOLD = 3       # بعد از ۳ شکست متوالی...
_BREAKER_COOLDOWN = 300.0    # ...۵ دقیقه تماس نگیر
_breaker = {"fail_streak": 0, "open_until": 0.0, "last_report": 0.0}


def _breaker_is_open() -> bool:
    return time.monotonic() < _breaker["open_until"]


def _breaker_record_success():
    _breaker["fail_streak"] = 0
    _breaker["open_until"] = 0.0


def _breaker_record_failure():
    _breaker["fail_streak"] += 1
    if _breaker["fail_streak"] >= _BREAKER_THRESHOLD:
        _breaker["open_until"] = time.monotonic() + _BREAKER_COOLDOWN
        logger.warning(
            f"[PANEL_SYNC] پنل پاسخگو نیست ({_breaker['fail_streak']} شکست متوالی) — "
            f"تماس‌های جدید تا {_BREAKER_COOLDOWN:.0f} ثانیه موقتاً متوقف می‌شوند "
            f"(داده‌ها از دست نمی‌روند؛ فقط ثبت پنل به تعویق می‌افتد)."
        )


def _breaker_log_throttled(msg: str):
    """لاگ با نرخ محدود — تا هر درخواست رد شده یک خط لاگ نریزد."""
    now = time.monotonic()
    if now - _breaker["last_report"] > 60:
        _breaker["last_report"] = now
        logger.info(f"[PANEL_SYNC] {msg}")


async def _panel_request(method: str, url: str, **kwargs):
    """اجرای یک درخواست HTTP به پنل با retry + breaker مشترک.

    Returns:
        (data, None) در موفقیت؛ (None, error_text) در شکست.
    """
    if _breaker_is_open():
        _breaker_log_throttled(
            "تماس با پنل به‌دلیل خطاهای اخیر موقتاً متوقف است (circuit breaker).")
        return None, "circuit_open"

    last_err = ""
    for attempt in range(1, _PANEL_RETRIES + 1):
        try:
            session = _get_panel_session()
            async with session.request(method, url, **kwargs) as resp:
                if resp.status in (200, 201):
                    _breaker_record_success()
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}
                    return data, None

                text = await resp.text()
                last_err = f"HTTP {resp.status} — {text[:200]}"
                # خطای ۴xx یعنی درخواست مشکل دارد؛ retry بی‌فایده است
                if 400 <= resp.status < 500:
                    logger.warning(f"[PANEL_SYNC] درخواست رد شد: {last_err}")
                    _breaker_record_failure()
                    return None, last_err
                logger.warning(
                    f"[PANEL_SYNC] پاسخ غیرموفق پنل (تلاش {attempt}/{_PANEL_RETRIES}): {last_err}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # repr به‌جای str — برای TimeoutError که str خالی دارد
            last_err = repr(e)
            logger.warning(
                f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین "
                f"(تلاش {attempt}/{_PANEL_RETRIES}): {last_err}")

        if attempt < _PANEL_RETRIES:
            await asyncio.sleep(_RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)])

    _breaker_record_failure()
    return None, last_err


async def warmup_panel():
    """بیدار کردن/گرم کردن پنل ادمین در شروع ربات (fire-and-forget).

    اگر پنل در حالت dev اجرا شود، اولین درخواست به هر مسیر باعث کامپایل
    می‌شود (۱۰ تا ۳۰ ثانیه). این تابع همان کامپایل را در استارت انجام
    می‌دهد تا درخواست‌های واقعی کاربران timeout نخورند.
    """
    try:
        url = f"{ADMIN_API_BASE}/admin/cases?limit=1"
        data, err = await _panel_request("GET", url)
        if err:
            logger.info(f"[PANEL_SYNC] warmup پنل ناموفق (غیرحیاتی): {err}")
        else:
            logger.info("[PANEL_SYNC] warmup پنل ادمین موفق بود.")
    except Exception as e:
        logger.info(f"[PANEL_SYNC] warmup پنل با خطا (غیرحیاتی): {e!r}")


async def register_case_to_panel(
    bale_user_id: int | str,
    full_name: str,
    service_type: str,
    status: str = "COMPLETED",
    tracking_code: str | None = None,
    document_category: str | None = None,
    sub_category: str | None = None,
    branch_name: str | None = None,
    branch_code: str | None = None,
    province: str | None = None,
    fee: int = 0,
    fee_status: str = "UNPAID",
    result_summary: str | None = None,
    error_details: str | None = None,
    error_step: str | None = None):
    """
    ثبت یک Case در پنل ادمین از طریق API.

    Parameters:
        bale_user_id: آیدی عددی تلگرام کاربر
        full_name: نام کامل کاربر
        service_type: نوع خدمات (INQUIRY, LAVAYEH, EZHHARNAMEH, ...)
        status: وضعیت (COMPLETED, PENDING_PAYMENT, FAILED, ...)
        tracking_code: کد رهگیری پرونده
        document_category: دسته‌بندی سند
        sub_category: زیردسته‌بندی
        branch_name: نام شعبه
        branch_code: کد شعبه
        province: استان
        fee: مبلغ کارمزد
        fee_status: وضعیت پرداخت (UNPAID, PAID, MANUAL_APPROVED)
        result_summary: خلاصه نتیجه
        error_details: جزئیات خطا
        error_step: مرحله‌ای که خطا رخ داده
    """
    url = f"{ADMIN_API_BASE}/admin/cases"

    payload = {
        "baleUserId": str(bale_user_id),
        "fullName": full_name,
        "serviceType": service_type,
        "status": status,
        "trackingCode": tracking_code,
        "documentCategory": document_category,
        "subCategory": sub_category,
        "branchName": branch_name,
        "branchCode": branch_code,
        "province": province,
        "fee": fee,
        "feeStatus": fee_status,
        "resultSummary": result_summary,
        "errorDetails": error_details,
        "errorStep": error_step,
    }

    # حذف فیلدهای None
    payload = {k: v for k, v in payload.items() if v is not None}

    data, err = await _panel_request("POST", url, json=payload)
    if data is None:
        if err != "circuit_open":
            logger.warning(f"[PANEL_SYNC] خطا در ثبت Case: {err}")
        return None

    if data.get("_duplicate"):
        logger.info(
            f"[PANEL_SYNC] Case تکراری شناسایی شد: type={service_type} "
            f"user={bale_user_id} tracking={tracking_code}"
        )
        return data
    logger.info(
        f"[PANEL_SYNC] Case ثبت شد: id={data.get('id', '?')} "
        f"type={service_type} user={bale_user_id} tracking={tracking_code}"
    )
    return data


async def register_inquiry_to_panel(
    user_id: int | str,
    full_name: str,
    tracking_code: str,
    doc_category: str,
    doc_subcategory: str | None = None,
    fee: int = 0,
    result_summary: str | None = None):
    """
    ثبت یک استعلام (INQUIRY) در پنل ادمین.

    این تابع wrapper ساده‌ای بر register_case_to_panel است
    با پارامترهای پیش‌فرض مناسب برای استعلام.
    """
    return await register_case_to_panel(
        bale_user_id=str(user_id),
        full_name=full_name,
        service_type="INQUIRY",
        status="COMPLETED",
        tracking_code=tracking_code,
        document_category=doc_category,
        sub_category=doc_subcategory,
        fee=fee,
        fee_status="UNPAID",
        result_summary=result_summary)


async def update_case_in_panel(case_id: str, **fields):
    """
    آپدیت یک Case موجود در پنل ادمین (با شناسه‌ای که هنگام ساخت برگردانده شده).

    از این تابع برای آپدیت وضعیت (status)، feeStatus، trackingCode،
    resultSummary، errorDetails و غیره در طول فلوی یک درخواست استفاده کن.
    فیلدهای camelCase پنل رو مستقیم پاس بده، مثلا:
        await update_case_in_panel(case_id, status="COMPLETED", trackingCode="123")
    """
    if not case_id:
        logger.warning("[PANEL_SYNC] update_case_in_panel بدون case_id صدا زده شد؛ نادیده گرفته شد.")
        return None

    url = f"{ADMIN_API_BASE}/admin/cases"
    payload = {"id": case_id, **{k: v for k, v in fields.items() if v is not None}}

    data, err = await _panel_request("PUT", url, json=payload)
    if data is None:
        if err != "circuit_open":
            logger.warning(f"[PANEL_SYNC] خطا در آپدیت Case {case_id}: {err}")
        return None

    logger.info(f"[PANEL_SYNC] Case آپدیت شد: id={case_id} fields={list(fields.keys())}")
    return data


async def mark_case_ready_to_send(case_id: str):
    """
    یک Case را وارد بخش «آماده ارسال» پنل ادمین می‌کند — یعنی امضا/تکمیل شده
    و ادمین باید متوجه شود که باید نتیجه را برای کاربر ارسال کند.

    نکته: طبق منطق پنل، فقط پرونده‌هایی که status=COMPLETED هستند قابل انتقال
    به ready-to-send هستند؛ پس این تابع اول Case را COMPLETED می‌کند سپس
    درخواست /ready را می‌زند.
    """
    if not case_id:
        logger.warning("[PANEL_SYNC] mark_case_ready_to_send بدون case_id صدا زده شد؛ نادیده گرفته شد.")
        return None

    await update_case_in_panel(case_id, status="COMPLETED")

    url = f"{ADMIN_API_BASE}/admin/cases/{case_id}/ready"
    data, err = await _panel_request("PUT", url, json={})
    if data is None:
        if err != "circuit_open":
            logger.warning(f"[PANEL_SYNC] خطا در انتقال Case {case_id} به ready-to-send: {err}")
        return None

    logger.info(f"[PANEL_SYNC] Case وارد «آماده ارسال» شد: id={case_id}")
    return data


async def find_case_in_panel(bale_user_id: int | str, service_type: str, tracking_code: str):
    """
    جستجوی یک Case موجود در پنل با baleUserId + serviceType + trackingCode.
    برای upsert_case_to_panel استفاده می‌شود. در صورت عدم وجود یا خطا None برمی‌گرداند.
    """
    if not tracking_code:
        return None
    url = f"{ADMIN_API_BASE}/admin/cases"
    params = {"search": str(tracking_code), "serviceType": service_type, "limit": "50"}

    data, err = await _panel_request("GET", url, params=params)
    if data is None:
        return None

    for c in data.get("cases", []):
        if c.get("baleUserId") == str(bale_user_id) and c.get("trackingCode") == str(tracking_code):
            return c
    return None


async def upsert_case_to_panel(
    bale_user_id: int | str,
    full_name: str,
    service_type: str,
    status: str,
    tracking_code: str | None = None,
    document_category: str | None = None,
    sub_category: str | None = None,
    branch_name: str | None = None,
    branch_code: str | None = None,
    province: str | None = None,
    fee: int = 0,
    fee_status: str | None = None,
    result_summary: str | None = None,
    error_details: str | None = None,
    error_step: str | None = None):
    """
    ثبت یا آپدیت یک Case در پنل ادمین بر اساس baleUserId+serviceType+trackingCode.

    مناسب فلوهایی مثل لایحه/اظهارنامه/چک/تجدیدنظر که در طول پردازش یک درخواست،
    چندین بار وضعیت گزارش می‌شود (مثلا «ثبت موقت» -> «خطا» یا «ثبت موقت» -> «ثبت
    نهایی»). اگر پرونده‌ای با همین شناسه‌ها از قبل باشد آپدیت می‌شود، در غیر این
    صورت پرونده جدید ساخته می‌شود — به‌جای اینکه هر مرحله یک رکورد جدا بسازد.
    """
    existing = await find_case_in_panel(bale_user_id, service_type, tracking_code) if tracking_code else None

    if existing:
        update_fields = {
            "fullName": full_name,
            "status": status,
            "documentCategory": document_category,
            "subCategory": sub_category,
            "branchName": branch_name,
            "branchCode": branch_code,
            "province": province,
            "resultSummary": result_summary,
            "errorDetails": error_details,
            "errorStep": error_step,
        }
        if fee_status is not None:
            update_fields["feeStatus"] = fee_status
        if fee:
            update_fields["fee"] = fee
        return await update_case_in_panel(existing["id"], **update_fields)

    return await register_case_to_panel(
        bale_user_id=bale_user_id,
        full_name=full_name,
        service_type=service_type,
        status=status,
        tracking_code=tracking_code,
        document_category=document_category,
        sub_category=sub_category,
        branch_name=branch_name,
        branch_code=branch_code,
        province=province,
        fee=fee,
        fee_status=fee_status or "UNPAID",
        result_summary=result_summary,
        error_details=error_details,
        error_step=error_step,
    )


async def mark_case_ready_to_send_by_tracking(bale_user_id: int | str, service_type: str, tracking_code: str):
    """
    مثل mark_case_ready_to_send ولی به‌جای شناسه‌ی پنل، پرونده را با
    baleUserId+serviceType+trackingCode پیدا می‌کند. برای نقاطی از کد
    (مثل پایان فلوی امضا) که فقط tracking_code در دسترس است مناسب‌تره.
    """
    case = await find_case_in_panel(bale_user_id, service_type, tracking_code)
    if not case:
        logger.warning(
            f"[PANEL_SYNC] پرونده‌ای برای ready-to-send پیدا نشد: "
            f"user={bale_user_id} type={service_type} tracking={tracking_code}"
        )
        return None
    return await mark_case_ready_to_send(case["id"])


async def register_failed_inquiry_to_panel(
    user_id: int | str,
    full_name: str,
    tracking_code: str,
    doc_category: str,
    doc_subcategory: str | None = None,
    error_details: str | None = None,
    error_step: str | None = None):
    """
    ثبت یک استعلام ناموفق در پنل ادمین با وضعیت FAILED.
    """
    return await register_case_to_panel(
        bale_user_id=str(user_id),
        full_name=full_name,
        service_type="INQUIRY",
        status="FAILED",
        tracking_code=tracking_code,
        document_category=doc_category,
        sub_category=doc_subcategory,
        fee=0,
        fee_status="UNPAID",
        error_details=error_details,
        error_step=error_step)
