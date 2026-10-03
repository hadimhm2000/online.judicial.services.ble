"""
funnel.py — ثبت مراحل فرم‌ها برای «قیف تبدیل» پنل
══════════════════════════════════════════════════════════════════════════════

یک middleware بیرونی روی پیام‌ها، state فعلی هر کاربر را (یعنی مرحله‌ای که کاربر
در حال پاسخ دادن به آن است) ثبت می‌کند. پرداخت موفق هم به‌عنوان مرحلهٔ «PAID»
همان سرویس ثبت می‌شود. رویدادها در حافظه جمع و هر FLUSH_SECONDS ثانیه یک‌جا
به پنل (POST /api/admin/funnel) فرستاده می‌شوند؛ هر (کاربر، سرویس، مرحله) در
هر روز فقط یک‌بار شمرده می‌شود.

پنل از روی این داده نشان می‌دهد چند نفر وارد هر سرویس شدند، چند نفر به هر
مرحله رسیدند و بیشترین ریزش در کدام مرحله است.

این ماژول هیچ‌وقت جریان کاربر را کند یا متوقف نمی‌کند (همهٔ مسیرها try/except).
"""
import asyncio
import datetime
import logging

from aiogram import BaseMiddleware, types

logger = logging.getLogger(__name__)

FLUSH_SECONDS = 60
MAX_BUFFER = 5000

_INQUIRY_STATES = {
    "main_menu", "waiting_for_tracking_code", "waiting_for_corrected_tracking_code",
    "waiting_for_corrected_doc_category", "waiting_for_corrected_doc_subcategory",
    "waiting_for_phone_number", "waiting_for_national_id", "waiting_for_doc_category",
    "waiting_for_doc_subcategory", "waiting_for_attachments_opt", "confirm_opt",
    "waiting_for_payment_receipt",
}

_PREFIXES = (
    (("lavayeh_", "waiting_for_lavayeh_"), "LAVAYEH"),
    (("ezhhar_", "waiting_for_ezhhar_"), "EZHHARNAMEH"),
    (("tn_", "waiting_for_tn_"), "TAJDID_NAZAR"),
    (("check_", "waiting_for_check_"), "CHECK"),
    (("ealam_", "waiting_for_ealam_"), "EALAM_VAKALAHT"),
    (("rv_",), "REGIONAL_VALUE"),
    (("dmg_", "mahr_"), "DAMAGES"),
    (("bulk_inquiry_",), "INQUIRY"),
    (("bulk_",), "BULK"),
    (("contract_fix",), "CONTRACT_FIX"),
)

_buffer: list[dict] = []
_seen: set = set()
_seen_day: str = ""


def flow_of(state_name: str) -> str | None:
    if state_name in _INQUIRY_STATES:
        return "INQUIRY"
    for prefixes, flow in _PREFIXES:
        if state_name.startswith(prefixes):
            return flow
    return None


def _record(uid: int, flow: str, step: str):
    global _seen_day
    today = datetime.date.today().isoformat()
    if today != _seen_day:
        _seen.clear()
        _seen_day = today
    key = (uid, flow, step)
    if key in _seen or len(_buffer) >= MAX_BUFFER:
        return
    _seen.add(key)
    _buffer.append({
        "baleUserId": str(uid), "flow": flow, "step": step,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })


class FunnelMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: dict):
        try:
            raw = data.get("raw_state")
            if raw and event.from_user:
                step = raw.split(":", 1)[-1]
                flow = flow_of(step)
                if flow:
                    _record(event.from_user.id, flow, "PAID" if event.successful_payment else step)
        except Exception as e:
            logger.debug(f"[FUNNEL] ثبت مرحله ناموفق: {e}")
        return await handler(event, data)


async def flush_loop():
    from panel_sync import post_funnel_events
    while True:
        try:
            await asyncio.sleep(FLUSH_SECONDS)
            if not _buffer:
                continue
            batch = _buffer[:1000]
            if await post_funnel_events(batch):
                del _buffer[:len(batch)]
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[FUNNEL] خطا در ارسال رویدادها: {e}")
