"""
panel_sync.py — ثبت رویدادهای استعلام در پنل ادمین (Next.js API)

این ماژول وظیفه ارسال داده‌های استعلام، لایحه و سایر خدمات
به API پنل ادمین را بر عهده دارد تا در دیتابیس SQLite ذخیره شوند
و در پنل ادمین قابل مشاهده باشند.
"""
import logging
import json
import datetime

import aiohttp

from config import ADMIN_API_BASE

logger = logging.getLogger(__name__)


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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200 or resp.status == 201:
                    data = await resp.json()
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
                else:
                    text = await resp.text()
                    logger.warning(
                        f"[PANEL_SYNC] خطا در ثبت Case: HTTP {resp.status} — {text[:200]}"
                    )
                    return None
    except Exception as e:
        # ⭐ repr به‌جای str — برای TimeoutError که str خالی دارد و پیام لاگ
        # خالی می‌ماند («خطا در ارتباط با پنل ادمین:»)
        logger.warning(f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین: {e!r}")
        return None


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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"[PANEL_SYNC] Case آپدیت شد: id={case_id} fields={list(fields.keys())}")
                    return data
                else:
                    text = await resp.text()
                    logger.warning(
                        f"[PANEL_SYNC] خطا در آپدیت Case {case_id}: HTTP {resp.status} — {text[:200]}"
                    )
                    return None
    except Exception as e:
        logger.warning(f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین (آپدیت {case_id}): {e!r}")
        return None


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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                json={},
                timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"[PANEL_SYNC] Case وارد «آماده ارسال» شد: id={case_id}")
                    return data
                else:
                    text = await resp.text()
                    logger.warning(
                        f"[PANEL_SYNC] خطا در انتقال Case {case_id} به ready-to-send: "
                        f"HTTP {resp.status} — {text[:200]}"
                    )
                    return None
    except Exception as e:
        logger.warning(f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین (ready {case_id}): {e!r}")
        return None


async def find_case_in_panel(bale_user_id: int | str, service_type: str, tracking_code: str):
    """
    جستجوی یک Case موجود در پنل با baleUserId + serviceType + trackingCode.
    برای upsert_case_to_panel استفاده می‌شود. در صورت عدم وجود یا خطا None برمی‌گرداند.
    """
    if not tracking_code:
        return None
    url = f"{ADMIN_API_BASE}/admin/cases"
    params = {"search": str(tracking_code), "serviceType": service_type, "limit": "50"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
                for c in payload.get("cases", []):
                    if c.get("baleUserId") == str(bale_user_id) and c.get("trackingCode") == str(tracking_code):
                        return c
                return None
    except Exception as e:
        logger.warning(f"[PANEL_SYNC] خطا در جستجوی پرونده مووجود: {e!r}")
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
