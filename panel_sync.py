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
        logger.error(f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین: {e}")
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
