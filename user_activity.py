"""
گیت فعالیت کاربر — بازگشت خودکار و بی‌صدا به منوی اصلی پس از ۱ ساعت بی‌کاری

قاعدهٔ کارفرما (۱۴۰۵/۰۶):
۱) اگر کاربر بیش از یک ساعت هیچ اقدامی در ربات انجام ندهد، با اولین
   اقدام بعدی‌اش، state او بی‌صدا پاک می‌شود تا مستقیماً در منوی اصلی
   قرار بگیرد — بدون هیچ پیام «به منوی اصلی بازگشتید».
۲) پس از هر خاموشی/وصل‌مجدد ربات، حافظهٔ FSM (MemoryStorage) از نو شروع
   می‌شود؛ یعنی همهٔ کاربران به‌طور خودکار در منوی اصلی‌اند و هیچ پیامی
   نیز به آن‌ها اعلام نمی‌شود.
۳) سوئیپر پس‌زمینه (sweep_inactive_users) هم هر ۶۰ ثانیه state کاربران
   غایب (>۱ ساعت) را proactive پاک می‌کند تا وضعیت FSM همیشه با واقعیت
   هم‌خوان باشد.
۴) دکمهٔ «🔄 شروع مجدد» (هندلر سراسری در handlers.py) صرفاً کاربر را به
   منوی اصلی برمی‌گرداند.

ایمنی‌ها (این موارد هرگز ریست نمی‌شوند):
- کاربران دارای فرآیند فعال (پرداخت، امضا، اصلاح، صف ثبت، سبد دسته‌جمعی
  و ...) — از طریق is_busy()
- پیام‌های successful_payment — فاکتور ممکن است با تأخیر بیش از یک ساعت
  پرداخت شود؛ ریست کردن state در این لحظه پرداخت را یتیم می‌کند.
- stateهای «انتظار پرداخت/رسید/تسویه» — تشخیص با کلیدواژه در نام state
  (prepay / payment / settlement / receipt).
"""
import logging
import time

from aiogram import BaseMiddleware
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message as AiogramMessage

import runtime_state

# ⭐ آستانهٔ بی‌کاری: ۱ ساعت (طبق دستور کارفرما)
INACTIVITY_LIMIT_SECONDS = 60 * 60

# آخرین فعالیت هر کاربر (monotonic seconds) — فقط برای جلسهٔ جاری لازم است؛
# بعد از ری‌استارت هم FSM خالی است و نیازی به ماندگاری نیست.
_last_activity: dict = {}

# کلیدواژه‌های نام state که «انتظار پرداخت» را نشان می‌دهند — این stateها
# نباید با گیت بی‌کاری پاک شوند (فاکتور باز کاربر از بین نمی‌رود).
_PAYMENT_STATE_KEYWORDS = ("prepay", "payment", "settlement", "receipt")

# مخازن runtime_state که حضور کاربر در آن‌ها یعنی «فرآیند فعال دارد» —
# برای این کاربران هرگز state پاک نمی‌شود حتی بعد از ۱ ساعت بی‌کاری.
_BUSY_STORE_NAMES = (
    "disrupted_users",            # پرداخت‌شده ولی سامانه قطع (تلاش مجدد ۴۵ دقیقه‌ای)
    "active_lavayeh_users",       # درخواست لایحه در حال پردازش
    "pending_lavayeh_sign",       # امضای الکترونیک لایحه
    "pending_ezhhar_sign",        # امضای الکترونیک اظهارنامه
    "pending_tn_sign",            # امضای الکترونیک دعاوی اعتراضی
    "pending_ezhhar_sana_fix",    # اصلاح sana اظهارنامه
    "pending_tn_sana_fix",        # اصلاح sana دعاوی اعتراضی
    "pending_lavayeh_sana_fix",   # اصلاح sana لایحه
    "pending_tn_retrieve_fix",    # اصلاح بازیابی اعتراض
    "pending_lavayeh_payments",   # فاکتور لایحه در انتظار پرداخت
    "pending_tn_payments",        # فاکتور دعاوی اعتراضی در انتظار پرداخت
    "pending_contract_fix",       # پنجرهٔ ۴۵ دقیقه‌ای کد قرارداد وکالت
    "pending_nid_fix_windows",    # پنجره‌های ویرایش کدملی/دادنامه
    "invalid_tracking_retry",     # تلاش مجدد کدرهگیری نامعتبر
    "pending_subscription_payments",  # پرداخت اشتراک
    "incomplete_tasks",           # تسک‌های ناقص قابل ادامه
    "bulk_inquiry_progress",      # استعلام دسته‌جمعی در حال پردازش
)


def touch(user_id) -> None:
    """ثبت/نوسازی زمان آخرین اقدام کاربر."""
    try:
        _last_activity[int(user_id)] = time.monotonic()
    except (TypeError, ValueError):
        pass


def seconds_idle(user_id):
    """ثانیه‌های سپری‌شده از آخرین اقدام کاربر — None اگر رکوردی نباشد."""
    ts = _last_activity.get(user_id)
    if ts is None:
        return None
    return time.monotonic() - ts


def is_busy(user_id) -> bool:
    """آیا کاربر فرآیند فعال دارد؟ (پرداخت/امضا/اصلاح/صف/...)"""
    for name in _BUSY_STORE_NAMES:
        store = getattr(runtime_state, name, None)
        if not store:
            continue
        try:
            if user_id in store:
                return True
        except TypeError:
            # مخازنی که کلیدشان از نوع دیگری است — نادیده گرفته می‌شود
            continue
    return False


def _is_payment_wait_state(raw_state) -> bool:
    """آیا state جاری از نوع «انتظار پرداخت/رسید/تسویه» است؟"""
    if not raw_state:
        return False
    low = str(raw_state).lower()
    return any(k in low for k in _PAYMENT_STATE_KEYWORDS)


class InactivityGate(BaseMiddleware):
    """میان‌افزار فعالیت — برای message و callback_query ثبت می‌شود.

    - برای همهٔ رویدادها: زمان آخرین اقدام به‌روز می‌شود.
    - فقط برای «پیام»های عادی (نه پرداخت موفق): اگر کاربر بیش از ۱ ساعت
      بی‌کار بوده، state دارد و فرآیند فعالی هم ندارد → state بی‌صدا پاک
      می‌شود تا پیام جاری مثل یک کاربر تازه در منوی اصلی پردازش شود.
      (کال‌بک‌ها ریست نمی‌شوند — ممکن است هندلرشان به دادهٔ FSM وابسته باشد.)
    """

    async def __call__(self, handler, event, data: dict):
        user = getattr(event, "from_user", None)
        uid = getattr(user, "id", None) if user else None

        if uid is not None:
            idle = seconds_idle(uid)
            touch(uid)

            # فقط پیام (نه کال‌بک) — این middleware فقط روی message و
            # callback_query ثبت می‌شود؛ تشخیص با isinstance نوع واقعی
            is_message = isinstance(event, AiogramMessage)
            # پرداخت موفق هرگز ریست نمی‌شود (فاکتور با تأخیر هم پرداخت‌پذیر است)
            has_successful_payment = getattr(event, "successful_payment", None) is not None

            if (
                is_message
                and not has_successful_payment
                and idle is not None
                and idle > INACTIVITY_LIMIT_SECONDS
                and not is_busy(uid)
            ):
                state = data.get("state")
                raw_state = data.get("raw_state")
                # stateهای «انتظار پرداخت/رسید/تسویه» معاف‌اند — فاکتور باز
                # کاربر نباید با ریست بی‌کاری از بین برود (پرداخت دیرهنگام
                # از طریق global_successful_payment_handler پردازش می‌شود)
                if state is not None and raw_state and not _is_payment_wait_state(raw_state):
                    try:
                        await state.clear()
                        logging.info(
                            f"[INACTIVITY] کاربر {uid} پس از {int(idle // 60)} دقیقه "
                            f"بی‌کاری بی‌صدا به منوی اصلی بازگردانده شد "
                            f"(state قبلی: {raw_state})")
                    except Exception as e:
                        logging.warning(f"[INACTIVITY] خطا در پاک‌کردن state کاربر {uid}: {e}")

        return await handler(event, data)


async def sweep_inactive_users(bot):
    """سوئیپر پس‌زمینه — پاک‌سازی proactive state کاربران غایب (>۱ ساعت).

    در حلقهٔ state_persister (هر ۶۰ ثانیه) فراخوانی می‌شود. کاربرانی که
    فرآیند فعال دارند (is_busy) دست‌نخورده می‌مانند.
    """
    dp = getattr(runtime_state, "dp", None)
    if dp is None or bot is None:
        return

    bot_id = getattr(bot, "id", None)
    if bot_id is None:
        return

    for uid in list(_last_activity.keys()):
        idle = seconds_idle(uid)
        if idle is None or idle <= INACTIVITY_LIMIT_SECONDS:
            continue
        if is_busy(uid):
            continue
        try:
            key = StorageKey(bot_id=bot_id, chat_id=uid, user_id=uid)
            current_state = await dp.storage.get_state(key)
            if current_state:
                # ⭐ stateهای «انتظار پرداخت/رسید/تسویه» معاف‌اند — فاکتور
                # باز کاربر نباید با سوئیپر بی‌کاری از بین برود
                if _is_payment_wait_state(current_state):
                    continue
                await dp.storage.set_state(key, state=None)
                await dp.storage.set_data(key, {})
                logging.info(
                    f"[INACTIVITY] (سوئیپر) state کاربر {uid} پس از "
                    f"{int(idle // 60)} دقیقه بی‌کاری پاک شد — در منوی اصلی "
                    f"قرار می‌گیرد (بدون پیام).")
        except Exception as e:
            logging.warning(f"[INACTIVITY] خطای سوئیپر برای کاربر {uid}: {e}")
