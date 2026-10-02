"""
user_files.py — فهرست فایل‌هایی که ربات برای هر کاربر فرستاده (برای «سوابق و فاکتورهای من»)
═══════════════════════════════════════════════════════════════════════════════

bale_file_sender.send_document_direct پس از هر ارسال موفق، file_id بلهٔ فایل را
اینجا ثبت می‌کند تا کاربر بتواند بعداً فایل‌های قبلی‌اش (چاپ لایحه، اظهارنامه،
نتیجهٔ استعلام و ...) را بدون آپلود دوباره، فقط با file_id دوباره دریافت کند.

ذخیره در user_files.json — برای هر کاربر حداکثر MAX_PER_USER فایل آخر و فقط
فایل‌های MAX_AGE_DAYS روز اخیر.
"""
import datetime
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files.json")
MAX_PER_USER = 30
MAX_AGE_DAYS = 90

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(STORE_FILE):
        return {}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[USER_FILES] خطا در خواندن: {e}")
        return {}


def _save(data: dict):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, STORE_FILE)


def record(chat_id, file_id: str, filename: str, caption: str | None = None):
    """ثبت یک فایل ارسال‌شده. هرگز استثنا بیرون نمی‌دهد."""
    if not chat_id or not file_id:
        return
    try:
        with _lock:
            data = _load()
            items = data.get(str(chat_id), [])
            items.append({
                "file_id": file_id,
                "filename": filename or "",
                "caption": (caption or "")[:120],
                "sent_at": datetime.datetime.now().isoformat(timespec="seconds"),
            })
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()
            data[str(chat_id)] = [i for i in items if i["sent_at"] >= cutoff][-MAX_PER_USER:]
            _save(data)
    except Exception as e:
        logger.error(f"[USER_FILES] خطا در ثبت: {e}")


def recent(chat_id, limit: int = 10) -> list[dict]:
    """فایل‌های اخیر کاربر — جدیدترین اول."""
    with _lock:
        items = _load().get(str(chat_id), [])
    return list(reversed(items))[:limit]
