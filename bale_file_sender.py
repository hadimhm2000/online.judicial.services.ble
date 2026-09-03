"""
bale_file_sender.py — ارسال مستقیم فایل به API بله با aiohttp.

FSInputFile در aiogram گاهی با API بله ناسازگار است (خطای
'failed to get HTTP URL content'). این ماژول از multipart/form-data
مستقیم استفاده می‌کند.
"""
import json
import logging
import os

import aiohttp

from config import BOT_TOKEN, BALE_API_BASE

logger = logging.getLogger(__name__)


def _api_url(method: str) -> str:
    """آدرس کامل متد API بله."""
    base = BALE_API_BASE.rstrip('/')
    return f"{base}/bot{BOT_TOKEN}/{method}"


def _serialize_reply_markup(reply_markup) -> str | None:
    """تبدیل InlineKeyboardMarkup aiogram به JSON برای API بله."""
    if reply_markup is None:
        return None
    try:
        if hasattr(reply_markup, 'model_dump'):
            return json.dumps(reply_markup.model_dump(exclude_none=True), ensure_ascii=False)
        return json.dumps(reply_markup, ensure_ascii=False, default=str)
    except Exception:
        return None


async def send_document_direct(
    chat_id: int,
    file_path: str,
    filename: str = None,
    caption: str = None,
    reply_markup=None,
) -> bool:
    """ارسال فایل (سند) به کاربر با multipart/form-data مستقیم.

    ⭐ نسخه اصلاح‌شده: در صورت خطای شبکه/سرویس، یک بار تلاش مجدد انجام
    می‌شود (ارسال PDF لایحه گاهی در تلاش اول شکست می‌خورد و فایل حذف
    می‌شد بدون اینکه به کاربر برسد).

    Args:
        chat_id: شناسه گفتگو
        file_path: مسیر فایل روی دیسک
        filename: نام فایل برای کاربر (اختیاری)
        caption: زیرنویس (اختیاری)
        reply_markup: کیبورد اینلاین (اختیاری)

    Returns:
        True در صورت موفقیت
    """
    # دو تلاش (اصلی + یک retry) با فاصله کوتاه
    for attempt in range(1, 3):
        result = await _send_document_once(chat_id, file_path, filename, caption, reply_markup)
        if result:
            return result
        if attempt == 1:
            import asyncio as _asyncio
            await _asyncio.sleep(2)
            logging.info(f"[BALE-FILE] تلاش مجدد ارسال فایل: {filename or file_path} -> chat {chat_id}")
    return False


async def _send_document_once(
    chat_id: int,
    file_path: str,
    filename: str = None,
    caption: str = None,
    reply_markup=None,
) -> bool:
    """یک تلاش ارسال فایل (سند) به کاربر با multipart/form-data مستقیم."""
    if not os.path.exists(file_path):
        logger.error(f"[BALE-FILE] فایل وجود ندارد: {file_path}")
        return False

    if filename is None:
        filename = os.path.basename(file_path)

    url = _api_url('sendDocument')
    try:
        # خواندن فایل در حافظه قبل از ساخت FormData —
        # جلوگیری از خطای «I/O operation on closed file»
        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('chat_id', str(chat_id))
            if caption:
                data.add_field('caption', caption)
            rm_json = _serialize_reply_markup(reply_markup)
            if rm_json:
                data.add_field('reply_markup', rm_json)
            data.add_field(
                'document',
                file_bytes,
                filename=filename,
                content_type='application/octet-stream'
            )
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=60), ssl=False) as resp:
                result = await resp.json()
                if result.get('ok'):
                    logger.info(f"[BALE-FILE] فایل ارسال شد: {filename} -> chat {chat_id}")
                    return result.get('result')  # dict شامل message_id
                else:
                    logger.error(f"[BALE-FILE] خطای API: {result.get('description', 'unknown')}")
                    return False
    except Exception as e:
        logger.error(f"[BALE-FILE] خطا در ارسال فایل {filename}: {e}")
        return False


async def send_photo_direct(
    chat_id: int,
    file_path: str,
    caption: str = None,
    reply_markup=None,
) -> bool:
    """ارسال تصویر به کاربر با multipart/form-data مستقیم.

    Args:
        chat_id: شناسه گفتگو
        file_path: مسیر فایل روی دیسک
        caption: زیرنویس (اختیاری)
        reply_markup: کیبورد اینلاین (اختیاری)

    Returns:
        True در صورت موفقیت
    """
    if not os.path.exists(file_path):
        logger.error(f"[BALE-FILE] فایل وجود ندارد: {file_path}")
        return False

    url = _api_url('sendPhoto')
    try:
        # خواندن فایل در حافظه قبل از ساخت FormData
        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('chat_id', str(chat_id))
            if caption:
                data.add_field('caption', caption)
            rm_json = _serialize_reply_markup(reply_markup)
            if rm_json:
                data.add_field('reply_markup', rm_json)
            data.add_field(
                'photo',
                file_bytes,
                filename=os.path.basename(file_path),
                content_type='image/jpeg'
            )
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=60), ssl=False) as resp:
                result = await resp.json()
                if result.get('ok'):
                    return result.get('result')  # dict شامل message_id
                else:
                    logger.error(f"[BALE-FILE] خطای API عکس: {result.get('description', 'unknown')}")
                    return None
    except Exception as e:
        logger.error(f"[BALE-FILE] خطا در ارسال عکس: {e}")
        return None


async def create_invoice_link(
    title: str,
    description: str,
    payload: str,
    provider_token: str,
    prices: list,
    photo_url: str = None,
) -> str | None:
    """ایجاد لینک پرداخت کیف‌پولی بله.

    Returns:
        URL لینک پرداخت در صورت موفقیت، None در صورت خطا
    """
    url = _api_url('createInvoiceLink')
    body = {
        'title': title,
        'description': description,
        'payload': payload,
        'provider_token': provider_token,
        'prices': prices,
    }
    if photo_url:
        body['photo_url'] = photo_url

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False
            ) as resp:
                result = await resp.json()
                if result.get('ok'):
                    link = result.get('result')
                    logger.info(f"[BALE-FILE] لینک پرداخت ایجاد شد: {link}")
                    return link
                else:
                    logger.error(f"[BALE-FILE] خطای ایجاد لینک پرداخت: {result.get('description')}")
                    return None
    except Exception as e:
        logger.error(f"[BALE-FILE] خطا در ایجاد لینک پرداخت: {e}")
        return None


async def send_invoice(
    chat_id: int,
    title: str,
    description: str,
    payload: str,
    provider_token: str,
    prices: list,
    photo_url: str = None,
    reply_markup=None,
) -> bool:
    """ارسال فاکتور پرداخت کیف‌پولی به کاربر.

    Returns:
        True در صورت موفقیت
    """
    url = _api_url('sendInvoice')
    body = {
        'chat_id': chat_id,
        'title': title,
        'description': description,
        'payload': payload,
        'provider_token': provider_token,
        'prices': prices,
    }
    if photo_url:
        body['photo_url'] = photo_url

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False
            ) as resp:
                result = await resp.json()
                if result.get('ok'):
                    logger.info(f"[BALE-FILE] فاکتور پرداخت ارسال شد برای chat {chat_id}")
                    return True
                else:
                    logger.error(f"[BALE-FILE] خطای ارسال فاکتور: {result.get('description')}")
                    return False
    except Exception as e:
        logger.error(f"[BALE-FILE] خطا در ارسال فاکتور: {e}")
        return False
