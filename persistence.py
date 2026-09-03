"""
ماژول ذخیره‌سازی و بازیابی حالت ربات (Persistence Layer).

این ماژول تمام داده‌های حساس ربات را به‌صورت دوره‌ای در یک فایل JSON
ذخیره می‌کند تا در صورت کرش یا ری‌استارت، اطلاعات از بین نرود.

قابلیت‌ها:
- ذخیره‌سازی دوره‌ی کاربران disrupted (پرداخت شده ولی سامانه قطع شده)
- ذخیره‌سازی شمارنده‌ی تلاش‌های ناموفق استعلام
- ذخیره‌سازی وضعیت پرداخت‌های لایحه‌ی در انتظار
- ذخیره‌سازی وضعیت امضای لایحه و اظهارنامه
- ذخیره‌سازی اطلاعات کاربران فعال (FSM states)
- بازیابی خودکار هنگام شروع ربات — با تفکیک ثبت‌شده / ثبت‌نشده
- ذخیره‌سازی وضعیت پرداخت‌های اشتراک
- ذخیره‌سازی وضعیت درخواست‌های ناقص (incomplete_tasks)
- نوتیفیکیشن پیش از کرش به مدیر و کاربر
"""
import json
import os
import logging
import datetime
import asyncio

logger = logging.getLogger(__name__)

# مسیر فایل ذخیره‌سازی — در کنار سایر فایل‌های پروژه
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_persisted_state.json")

# فایل پشتیبان — در صورت خرابی فایل اصلی
STATE_FILE_BACKUP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_persisted_state.bak.json")


def _serialize_datetime(obj):
    """تبدیل آبجکت‌های non-JSON (مثل datetime) به رشته‌ی قابل ذخیره."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return {"_type_": "datetime", "value": obj.isoformat()}
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, asyncio.Event):
        return "<asyncio.Event>"
    raise TypeError(f"Type {type(obj)} not serializable")


def _deserialize_datetime(value):
    """تبدیل رشته‌ی ISO به datetime در صورت امکان.

    از فرمت جدید (dict با _type_) و قدیم (str) پشتیبانی می‌کند.
    """
    if isinstance(value, dict) and value.get("_type_") == "datetime":
        try:
            return datetime.datetime.fromisoformat(value["value"])
        except (ValueError, TypeError, KeyError):
            return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return value
    return value


def _deserialize_all_datetimes(info: dict, keys: list):
    """تبدیل تمام فیلدهای datetime در یک دیکشنری."""
    for key in keys:
        if key in info:
            info[key] = _deserialize_datetime(info[key])
    return info


def save_state(data: dict, filepath: str = STATE_FILE):
    """ذخیره‌سازی حالت در فایل JSON — با پشتیبان‌گیری خودکار."""
    try:
        # پشتیبان‌گیری از فایل قبلی (اگر وجود دارد)
        if os.path.exists(filepath) and filepath == STATE_FILE:
            try:
                import shutil
                shutil.copy2(filepath, STATE_FILE_BACKUP)
            except Exception:
                pass

        # نوشتن فایل جدید
        tmp_path = filepath + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=_serialize_datetime, indent=2)
        # اتمیک رینیم — جلوگیری از خراب شدن فایل در صورت کرش حین نوشتن
        os.replace(tmp_path, filepath)
        logger.debug(f"[PERSIST] حالت با موفقیت ذخیره شد ({len(data)} کلید)")
    except Exception as e:
        logger.error(f"[PERSIST] خطا در ذخیره‌سازی حالت: {e}")
        # تلاش با پشتیبان
        if os.path.exists(STATE_FILE_BACKUP):
            try:
                with open(STATE_FILE_BACKUP, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, ensure_ascii=False, default=_serialize_datetime, indent=2)
                logger.info("[PERSIST] بازیابی از فایل پشتیبان موفق بود.")
            except Exception as be:
                logger.error(f"[PERSIST] خطا در بازیابی از پشتیبان: {be}")


def load_state(filepath: str = STATE_FILE) -> dict:
    """بارگذاری حالت از فایل JSON — با فال‌بک به پشتیبان."""
    if not os.path.exists(filepath):
        # تلاش از فایل پشتیبان
        if os.path.exists(STATE_FILE_BACKUP):
            logger.warning("[PERSIST] فایل اصلی یافت نشد — تلاش از پشتیبان.")
            try:
                with open(STATE_FILE_BACKUP, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"[PERSIST] حالت از پشتیبان بارگذاری شد ({len(data)} کلید)")
                return data
            except Exception as e:
                logger.error(f"[PERSIST] خطا در بارگذاری پشتیبان: {e}")
        logger.info("[PERSIST] فایل حالت یافت نشد — شروع تازه.")
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"[PERSIST] حالت با موفقیت بارگذاری شد ({len(data)} کلید)")
        return data
    except Exception as e:
        logger.error(f"[PERSIST] خطا در بارگذاری حالت: {e}")
        # تلاش از پشتیبان
        if os.path.exists(STATE_FILE_BACKUP):
            try:
                with open(STATE_FILE_BACKUP, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"[PERSIST] حالت از پشتیبان بارگذاری شد ({len(data)} کلید)")
                return data
            except Exception:
                pass
        return {}


def save_runtime_state():
    """ذخیره‌سازی تمام متغیرهای حساس runtime_state در فایل.

    این تابع باید دوره‌ای فراخوانی شود (مثلاً هر ۶۰ ثانیه).
    """
    import runtime_state

    data = {}

    # 1. کاربرانی که پرداخت کرده‌اند ولی سامانه قطع شده (disrupted)
    disrupted = {}
    for uid, info in runtime_state.disrupted_users.items():
        disrupted[str(uid)] = {
            k: v for k, v in info.items()
        }
    data["disrupted_users"] = disrupted

    # 2. شمارنده‌ی تلاش‌های ناموفق استعلام
    attempts = {}
    for uid, info in runtime_state.inquiry_attempts.items():
        attempts[str(uid)] = info
    data["inquiry_attempts"] = attempts

    # 3. فاکتورهای لایحه در انتظار پرداخت
    lavayeh_payments = {}
    for uid, info in runtime_state.pending_lavayeh_payments.items():
        lavayeh_payments[str(uid)] = info
    data["pending_lavayeh_payments"] = lavayeh_payments

    # 4. وضعیت امضای لایحه
    lavayeh_sign = {}
    for uid, info in runtime_state.pending_lavayeh_sign.items():
        lavayeh_sign[str(uid)] = info
    data["pending_lavayeh_sign"] = lavayeh_sign

    # 5. وضعیت امضای اظهارنامه
    ezhhar_sign = {}
    for uid, info in runtime_state.pending_ezhhar_sign.items():
        ezhhar_sign[str(uid)] = info
    data["pending_ezhhar_sign"] = ezhhar_sign

    # 6. وضعیت اصلاح شناسه ملی اظهارنامه
    ezhhar_fix = {}
    for uid, info in runtime_state.pending_ezhhar_sana_fix.items():
        ezhhar_fix[str(uid)] = info
    data["pending_ezhhar_sana_fix"] = ezhhar_fix

    # 7. استفاده رایگان کاربران
    free_usage = {}
    for uid, info in runtime_state.user_free_usage.items():
        free_usage[str(uid)] = info
    data["user_free_usage"] = free_usage

    # 8. اشتراک فعال
    subscriptions = {}
    for uid, info in runtime_state.user_subscriptions.items():
        subscriptions[str(uid)] = info
    data["user_subscriptions"] = subscriptions

    # 9. پرداخت اشتراک در انتظار تایید
    sub_payments = {}
    for uid, info in runtime_state.pending_subscription_payments.items():
        sub_payments[str(uid)] = info
    data["pending_subscription_payments"] = sub_payments

    # 9-ب. ⭐ فاکتورهای «هزینه دستی مدیر» (/fee) در انتظار پرداخت
    admin_fee_payments = {}
    for uid, info in runtime_state.pending_admin_fee_payments.items():
        admin_fee_payments[str(uid)] = info
    data["pending_admin_fee_payments"] = admin_fee_payments

    # 10. اطلاعات FSM کاربران فعال (برای بازیابی پس از کرش)
    # ── بهبود: تفکیک کاربرانی که ثبت شده‌اند از کسانی که هنوز ثبت نشده‌اند ──
    user_sessions = {}
    for uid in runtime_state.active_lavayeh_users:
        user_sessions[str(uid)] = {"in_lavayeh_flow": True, "submitted": True}
    # کاربرانی که در disrupted هستند = پرداخت کرده ولی ثبت قطع شده
    for uid in runtime_state.disrupted_users:
        if str(uid) not in user_sessions:
            user_sessions[str(uid)] = {"in_lavayeh_flow": False, "submitted": False, "disrupted": True}
    # کاربرانی در انتظار امضا
    for uid in runtime_state.pending_lavayeh_sign:
        if str(uid) not in user_sessions:
            user_sessions[str(uid)] = {"in_lavayeh_flow": False, "submitted": True, "in_sign_flow": True}
    for uid in runtime_state.pending_ezhhar_sign:
        if str(uid) not in user_sessions:
            user_sessions[str(uid)] = {"in_lavayeh_flow": False, "submitted": True, "in_ezhhar_sign_flow": True}
    # کاربران در انتظار پرداخت لایحه
    for uid in runtime_state.pending_lavayeh_payments:
        if str(uid) not in user_sessions:
            user_sessions[str(uid)] = {"in_lavayeh_flow": True, "submitted": False, "awaiting_payment": True}
    data["user_sessions"] = user_sessions

    # 11. تسک‌های ناقص
    incomplete = {}
    for key, info in runtime_state.incomplete_tasks.items():
        incomplete[key] = info
    data["incomplete_tasks"] = incomplete

    # 12. علامت کرش — برای تشخیص ری‌استارت غیرعادی
    data["crash_flag"] = False
    data["last_save_time"] = datetime.datetime.now().isoformat()

    save_state(data)


def load_into_runtime_state():
    """بارگذاری داده‌های ذخیره‌شده به داخل runtime_state.

    خروجی: تاپل (active_submitted, active_unsubmitted)
      - active_submitted: لیست user_id‌هایی که درخواستشان ثبت شده (در روند پردازش)
      - active_unsubmitted: لیست user_id‌هایی که هنوز ثبت نکرده‌اند
    """
    import runtime_state

    data = load_state()
    if not data:
        return [], []

    active_submitted = []
    active_unsubmitted = []

    # 1. disrupted_users — پرداخت کرده ولی ثبت قطع شده (ثبت‌نشده)
    for uid_str, info in data.get("disrupted_users", {}).items():
        uid = int(uid_str)
        if "timestamp" in info:
            info["timestamp"] = _deserialize_datetime(info["timestamp"])
        runtime_state.disrupted_users[uid] = info
        active_unsubmitted.append(uid)

    # 2. inquiry_attempts
    for uid_str, info in data.get("inquiry_attempts", {}).items():
        runtime_state.inquiry_attempts[int(uid_str)] = info

    # 3. pending_lavayeh_payments — در انتظار پرداخت (ثبت‌نشده)
    for uid_str, info in data.get("pending_lavayeh_payments", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, ["invoice_time"])
        runtime_state.pending_lavayeh_payments[uid] = info
        active_unsubmitted.append(uid)

    # 4. pending_lavayeh_sign — در روند امضا (ثبت‌شده)
    for uid_str, info in data.get("pending_lavayeh_sign", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, [
            "sign_sent_time", "wrong_code_time",
            "code_sent_announce_time", "total_no_action_start"
        ])
        runtime_state.pending_lavayeh_sign[uid] = info
        active_submitted.append(uid)

    # 5. pending_ezhhar_sign — در روند امضا اظهارنامه (ثبت‌شده)
    for uid_str, info in data.get("pending_ezhhar_sign", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, [
            "sign_sent_time", "wrong_code_time",
            "code_sent_announce_time", "total_no_action_start"
        ])
        runtime_state.pending_ezhhar_sign[uid] = info
        active_submitted.append(uid)

    # 6. pending_ezhhar_sana_fix — در انتظار اصلاح (ثبت‌شده)
    for uid_str, info in data.get("pending_ezhhar_sana_fix", {}).items():
        runtime_state.pending_ezhhar_sana_fix[int(uid_str)] = info
        active_submitted.append(int(uid_str))

    # 7. user_free_usage
    for uid_str, info in data.get("user_free_usage", {}).items():
        runtime_state.user_free_usage[int(uid_str)] = info

    # 8. user_subscriptions
    for uid_str, info in data.get("user_subscriptions", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, ["start_date", "end_date"])
        runtime_state.user_subscriptions[uid] = info

    # 9. pending_subscription_payments
    for uid_str, info in data.get("pending_subscription_payments", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, ["created_at"])
        runtime_state.pending_subscription_payments[uid] = info

    # 9-ب. ⭐ pending_admin_fee_payments — فاکتورهای هزینه دستی مدیر (/fee)
    for uid_str, info in data.get("pending_admin_fee_payments", {}).items():
        uid = int(uid_str)
        info = _deserialize_all_datetimes(info, ["invoice_time"])
        runtime_state.pending_admin_fee_payments[uid] = info
        # کاربر در انتظار پرداخت فاکتور مدیر است → ثبت‌نشده (نیاز به اقدام مجدد)
        active_unsubmitted.append(uid)

    # 10. user_sessions — بازسازی active_lavayeh_users
    for uid_str, info in data.get("user_sessions", {}).items():
        uid = int(uid_str)
        if info.get("in_lavayeh_flow"):
            runtime_state.active_lavayeh_users.add(uid)

    # 11. incomplete_tasks
    for key, info in data.get("incomplete_tasks", {}).items():
        runtime_state.incomplete_tasks[key] = info

    # حذف فایل‌های حالت پس از بارگذاری موفق
    for fp in [STATE_FILE, STATE_FILE_BACKUP]:
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
    logger.info("[PERSIST] فایل‌های حالت پس از بارگذاری حذف شدند.")

    # حذف موارد تکراری
    active_submitted = list(set(active_submitted))
    active_unsubmitted = list(set(active_unsubmitted))
    # حذف از unsubmitted اگر در submitted هست
    active_unsubmitted = [u for u in active_unsubmitted if u not in active_submitted]

    return active_submitted, active_unsubmitted


def mark_crash_and_save():
    """علامت‌گذاری کرش و ذخیره‌سازی فوری — قبل از خاموش شدن فراخوانی شود."""
    import runtime_state
    save_runtime_state()
    # حالا crash_flag را True کن — خواندن و به‌روزرسانی
    data = load_state()
    if data:
        data["crash_flag"] = True
        save_state(data)
    logger.warning("[PERSIST] crash_flag فعال شد و حالت ذخیره گردید.")


def was_crash() -> tuple:
    """بررسی آیا ری‌استارت قبلی ناشی از کرش بوده است.

    خروجی: (bool, dict)
      - bool: آیا کرش رخ داده
      - dict: داده‌های ذخیره‌شده (برای استفاده در بازیابی)

    نکته: فایل حالت را حذف نمی‌کند — load_into_runtime_state این کار را می‌کند.
    """
    data = load_state()
    return data.get("crash_flag", False), data


def cleanup_expired_disrupted():
    """حذف رکوردهای منقضی‌شده‌ی disrupted (بیشتر از ۴۵ دقیقه).

    خروجی: لیست user_id‌های پاک‌شده.
    """
    import runtime_state
    now = datetime.datetime.now()
    expired = []
    for uid, info in list(runtime_state.disrupted_users.items()):
        ts = info.get("timestamp")
        if ts:
            ts = _deserialize_datetime(ts)
            if (now - ts) > datetime.timedelta(minutes=45):
                expired.append(uid)
                del runtime_state.disrupted_users[uid]
    if expired:
        logger.info(f"[PERSIST] {len(expired)} رکورد منقضی‌شده‌ی disrupted حذف شد.")
    return expired


def cleanup_expired_inquiry_attempts():
    """پاکسازی شمارنده‌ی تلاش‌های قدیمی (بیشتر از ۲ ساعت).

    این تابع جلوگیری می‌کند دیکشنری inquiry_attempts بی‌رویه بزرگ شود.
    """
    import runtime_state
    now = datetime.datetime.now()
    expired = []
    for uid, info in list(runtime_state.inquiry_attempts.items()):
        last = info.get("last_attempt")
        if last:
            last = _deserialize_datetime(last)
            if (now - last) > datetime.timedelta(hours=2):
                expired.append(uid)
                del runtime_state.inquiry_attempts[uid]
    if expired:
        logger.info(f"[PERSIST] {len(expired)} رکورد منقضی inquiry_attempts حذف شد.")
    return expired
