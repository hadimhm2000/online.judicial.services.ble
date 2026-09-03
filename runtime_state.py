"""
حالت‌های مشترک و متغیرهای زنده‌ی برنامه که چند ماژول دیگر باید همزمان بهشون
دسترسی داشته باشن (صف کارها، وضعیت لاگین، صفحه/کانتکست مرورگر).

نکته‌ی مهم برای توسعه‌ی بعدی: هر ماژول دیگه که می‌خواد sana_page یا
browser_context رو *بخونه*، باید حتماً با `import runtime_state` و
`runtime_state.sana_page` بهش دسترسی پیدا کنه، نه با
`from runtime_state import sana_page`. چون این متغیرها بعداً (داخل
browser_worker در scenarios.py) مقداردهی می‌شن؛ اگر با from...import کپی
بگیری، همیشه مقدار None رو می‌بینی، نه مقدار واقعی و به‌روز.
"""
import asyncio
import os

job_queue: asyncio.Queue = asyncio.Queue()
login_event: asyncio.Event = asyncio.Event()

# نمونه‌ی زنده‌ی Dispatcher — در بدو اجرا داخل bot.py مقداردهی می‌شود.
# هرجای دیگر که به dp.fsm.resolve_context نیاز است، از اینجا (runtime_state.dp)
# استفاده کن، هرگز از «from bot import dp» — چون وقتی bot.py مستقیم اجرا می‌شود
# اسم ماژولش می‌شود "__main__"، و اگر جای دیگری بعداً "import bot" بزند، پایتون
# کل فایل bot.py را از نو، این‌بار با نام "bot"، اجرا می‌کند (چون در sys.modules
# نبوده). این یعنی dp دوباره ساخته می‌شود و router (که از قبل به dp اول متصل شده)
# دوباره به همان dp.include_router() می‌رسد و ارور
# "Router is already attached to <Dispatcher ...>" می‌دهد — دقیقاً همان خطایی که
# در لاگ دیدیم و باعث می‌شد شمارش منضمات و دکمه‌های تایید/رد ادمین کار نکنند.
dp = None

# این مقادیر در ابتدای اجرا None هستن و فقط داخل browser_worker
# (در scenarios.py) مقداردهی می‌شن. playwright_instance و browser جدید
# اضافه شدن تا بتوان بدون ری‌استارت کل ربات (پروسه‌ی پایتون)، فقط
# مرورگر/کانتکست/صفحه را وقتی کرش کرد یا بسته شد، از نو ساخت — چون
# async_playwright() خودش (نمونه‌ی p) باید زنده بماند تا بشود دوباره
# chromium.launch() صدا زد.
playwright_instance = None
browser = None
browser_context = None
sana_page = None

# قفل برای جلوگیری از تلاش‌های هم‌زمان چندگانه برای بازسازی مرورگر
# (مثلاً وقتی هم واچ‌داگ پس‌زمینه و هم حلقه‌ی اصلی هم‌زمان کرش را تشخیص می‌دهند)
browser_relaunch_lock: asyncio.Lock = asyncio.Lock()

# مجموعه‌ی کاربرانی که یک درخواست لایحه فعال دارند.
active_lavayeh_users: set = set()

# دیکشنری فاکتورهای لایحه در انتظار پرداخت.
# کلید: user_id (int)
# مقدار: {
#   "invoice_time": datetime,
#   "final_fee": int,
#   "court_total": int,
#   "tracking_code": str,
#   "national_ids": str,
#   "reminder_sent": bool,
#   "blocked": bool,
# }
pending_lavayeh_payments: dict = {}

# =========================================================
# اطلاعات فرآیند اخذ امضای الکترونیک لایحه
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "tracking_code": str,              — کد رهگیری لایحه
#   "province": str,                   — استان
#   "row_number": int,                 — ردیف فرعی
#   "lavayeh_title": str,              — عنوان لایحه
#   "persons": list,                   — لیست اشخاص ارائه‌دهنده
#   "sign_persons": list,              — لیست اشخاص قابل امضا از جدول [{idx, name, person_type, canSend, divVisible}]
#   "persons_awaiting_sign": list,     — لیست idx اشخاص در انتظار امضا
#   "current_person_idx": int,         — idx شخصی که فعلاً کدش ارسال شده
#   "sign_codes_received": dict,       — {idx: code} کدهای دریافت‌شده
#   "sign_sent_time": datetime,        — زمان ارسال آخرین کد
#   "wrong_code_time": datetime,       — زمان آخرین کد اشتباه (برای ۲۰ دقیقه)
#   "code_sent_announce_time": datetime, — زمان ارسال کد (برای ۶ دقیقه تایم‌اوت)
#   "resend_notified": bool,           — آیا نوتیف ارسال مجدد داده شده؟
#   "total_no_action_start": datetime, — شروع ۶۰ دقیقه بدون اقدام
# }
pending_lavayeh_sign: dict = {}

# =========================================================
# اطلاعات فرآیند اخذ امضای الکترونیک اظهارنامه
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "tracking_code": str,              — کد رهگیری اظهارنامه
#   "is_ezhharnameh": bool,            — always True for this dict
#   "sign_persons": list,              — لیست اشخاص قابل امضا از جدول [{idx, name, person_type}]
#   "persons_awaiting_sign": list,     — لیست idx اشخاص در انتظار کد
#   "current_person_idx": int,         — idx شخصی که فعلاً کدش ارسال شده
#   "sign_codes_received": dict,       — {idx: code} کدهای دریافت‌شده
#   "sign_sent_time": datetime,        — زمان ارسال آخرین کد
#   "wrong_code_time": datetime,       — زمان آخرین کد اشتباه (برای ۲۰ دقیقه)
#   "code_sent_announce_time": datetime, — زمان اعلام آمادگی به کاربر (برای ۶ دقیقه تایم‌اوت)
#   "resend_notified": bool,           — آیا نوتیف ارسال مجدد داده شده؟
#   "total_no_action_start": datetime, — شروع ۶۰ دقیقه بدون اقدام
# }
pending_ezhhar_sign: dict = {}

# =========================================================
# اطلاعات درخواست‌های اظهارنامه در انتظار ویرایش شناسه ملی
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "task_data": dict,          — اطلاعات کامل تسک اظهارنامه
#   "created_at": float,        — زمان ایجاد (loop time)
# }
pending_ezhhar_sana_fix: dict = {}

# =========================================================
# درخواست‌های دعاوی اعتراضی در انتظار اصلاح شناسه ملی ثنا
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "task_data": dict,          — اطلاعات کامل تسک دعاوی اعتراضی
#   "created_at": float,        — زمان ایجاد (loop time)
# }
pending_tn_sana_fix: dict = {}

# =========================================================
# فاکتورهای دعوی اعتراضی در انتظار پرداخت — مستقل از لایحه
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "invoice_time": datetime,
#   "final_fee": int,
#   "court_total": int,
#   "tracking_code": str,
#   "national_ids": str,
#   "case_type": str,
#   "tn_persons": list,
#   "reminder_sent": bool,
#   "blocked": bool,
# }
pending_tn_payments: dict = {}

# =========================================================
# اطلاعات فرآیند اخذ امضای الکترونیک دعاوی اعتراضی — مستقل از لایحه
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "tracking_code": str,
#   "case_type": str,              — نوع دعوی (برای menu_path ناوبری امضا)
#   "persons": list,
#   "sign_persons": list,
#   "persons_awaiting_sign": list,
#   "current_person_idx": int,
#   "sign_codes_received": dict,
#   "sign_sent_time": datetime,
#   "wrong_code_time": datetime,
#   "code_sent_announce_time": datetime,
#   "resend_notified": bool,
#   "total_no_action_start": datetime,
# }
pending_tn_sign: dict = {}

# =========================================================
# نتایج استعلام افراد پرونده (برای انتخاب تجدیدنظرخواه/خوانده)
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "all_names": [{"index": int, "name": str}, ...],
#   "section": "appellant" | "appellee",
#   "selected_indices": [int, ...],
#   "message_id": int,          — آیدی پیام لیست برای ویرایش
# }
tn_queried_persons: dict = {}

# =========================================================
# اطلاعات رسیدهای در انتظار تایید دستی مدیر
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "photo_path": str,          — مسیر فایل تصویر رسید
#   "service_type": str,        — "lavayeh" / "cart" / "stamp"
#   "expected_amount": int,     — مبلغ مورد انتظار
#   "message_id": int,          — آیدی پیام مدیر (برای ویرایش)
# }
pending_admin_payment_review: dict = {}

# =========================================================
# ⭐ فاکتورهای «هزینه دستی مدیر» (/fee) در انتظار پرداخت
# =========================================================
# مدیر با /fee <user_id> مبلغ و نوع سرویس را وارد می‌کند؛ فاکتور بله برای
# کاربر ارسال می‌شود. پس از پرداخت خودکار (successful_payment):
#   - به‌جز INQUIRY (استعلام) → ناوبری امضا برای کاربر آغاز می‌شود
#   - INQUIRY → فقط ثبت پرداخت (استعلام مرحله امضا ندارد)
# کلید: user_id (int)
# مقدار: {
#   "invoice_time": datetime,
#   "final_fee": int,            — مبلغ فاکتور (ریال)
#   "service_type": str,         — LAVAYEH / EZHHARNAMEH / TAJDID_NAZAR / CHECK / INQUIRY
#   "tracking_code": str,        — کد رهگیری/بایگانی (اختیاری)
#   "sign_menu_path": list|None, — مسیر منوی سامانه برای ناوبری امضا (چک/تجدیدنظر)
#   "admin_id": int,             — مدیر درخواست‌کننده
# }
pending_admin_fee_payments: dict = {}

# =========================================================
# ذخیره کدرهگیری و وضعیت تسک‌های incomplete برای مدیریت
# =========================================================
# کلید: "ezhhar:{bill_no}" یا "lavayeh:{bill_no}"
# مقدار: {
#   "bill_no": str,              — کد رهگیری ثنا
#   "user_id": int,              — آیدی کاربر
#   "type": str,                 — "ezhhar" یا "lavayeh"
#   "last_completed_step": str,  — آخرین مرحله تکمیل‌شده
#   "next_step": str,            — مرحله‌ای که باید از آن ادامه یابد
#   "task_data": dict,           — داده‌های کامل تسک
#   "created_at": float,         — زمان ایجاد
# }
incomplete_tasks: dict = {}

# =========================================================
# سیستم محدودیت تلاش‌های ناموفق استعلام (حداکثر ۲ تلاش)
# =========================================================
# کلید: user_id (int)
# مقدار: {"count": int, "last_attempt": str (ISO datetime)}
# پس از ۲ تلاش ناموفق متوالی، کاربر باید از اول شروع کند.
inquiry_attempts: dict = {}

# =========================================================
# کاربرانی که پرداخت کرده‌اند ولی سامانه در حین استعلام قطع شده
# (فرصت تکرار بدون پرداخت — ۴۵ دقیقه)
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "timestamp": datetime,      — زمان وقوع قطعی
#   "job_data": dict,          — داده‌ی کامل تسک (برای تکرار بدون پرداخت)
#   "notified": bool,          — آیا اطلاع‌رسانی انجام شده؟
# }
disrupted_users: dict = {}

# =========================================================
# فرصت رایگان اصلاح «کد رهگیری نامعتبر» (۳۰ دقیقه، بدون پرداخت مجدد)
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "expires_at": datetime,     — پایان مهلت ۳۰ دقیقه‌ای
#   "remaining": int,           — تعداد اصلاحات رایگان باقی‌مانده
#   "template_job": dict,       — نمونه‌ی job اصلی (برای کپی need_attachments/full_name و ...)
# }
invalid_tracking_retry: dict = {}
INVALID_TRACKING_RETRY_MINUTES = 30

# =========================================================
# پیگیری پیشرفت استعلام‌های دسته‌جمعی (برای گزارش نهایی کدهای نامعتبر)
# =========================================================
# کلید: user_id (int)
# مقدار: {"remaining": int, "invalid": [ {"tracking_code":.., "doc_name":..}, ... ], "template_job": dict}
bulk_inquiry_progress: dict = {}

# =========================================================
# سیستم اشتراک و محدودیت استفاده رایگان
# =========================================================
# حداکثر استفاده رایگان برای هر بخش (تمبر و ابزار)
MAX_FREE_USAGE = 2

# مبلغ اشتراک ماهیانه (ریال)
SUBSCRIPTION_FEE = 1_000_000

# مدت اشتراک (روز)
SUBSCRIPTION_DURATION_DAYS = 30

# دیکشنری شمارنده استفاده رایگان کاربران
# کلید: user_id (int)
# مقدار: {"stamp": int, "tools": int}
user_free_usage: dict = {}

# دیکشنری اشتراک فعال کاربران
# کلید: user_id (int)
# مقدار: {
#   "start_date": datetime,     — تاریخ شروع اشتراک
#   "end_date": datetime,       — تاریخ پایان اشتراک
#   "expiry_notified": bool,     — آیا اعلان انقضا ارسال شده؟
# }
user_subscriptions: dict = {}

# دیکشنری پرداخت‌های اشتراک در انتظار تایید مدیر
# کلید: user_id (int)
# مقدار: {
#   "photo_path": str,          — مسیر فایل تصویر رسید
#   "message_id": int,          — آیدی پیام مدیر (برای ویرایش)
#   "created_at": datetime,    — زمان ایجاد درخواست
# }
pending_subscription_payments: dict = {}


def get_user_usage(user_id: int) -> dict:
    """دریافت شمارنده استفاده کاربر. اگر وجود نداشت، صفر initializes."""
    if user_id not in user_free_usage:
        user_free_usage[user_id] = {"stamp": 0, "tools": 0}
    return user_free_usage[user_id]


def has_active_subscription(user_id: int) -> bool:
    """بررسی آیا کاربر اشتراک فعال دارد."""
    import datetime
    if user_id not in user_subscriptions:
        return False
    sub = user_subscriptions[user_id]
    return datetime.datetime.now() < sub["end_date"]


def can_use_service(user_id: int, service: str) -> bool:
    """بررسی آیا کاربر می‌تواند از خدمت استفاده کند (رایگان یا اشتراک)."""
    if has_active_subscription(user_id):
        return True
    usage = get_user_usage(user_id)
    return usage.get(service, 0) < MAX_FREE_USAGE


def increment_usage(user_id: int, service: str):
    """افزایش شمارنده استفاده رایگان."""
    usage = get_user_usage(user_id)
    usage[service] = usage.get(service, 0) + 1


def get_remaining_free(user_id: int, service: str) -> int:
    """دریافت تعداد دفعات باقی‌مانده رایگان."""
    if has_active_subscription(user_id):
        return -1  # اشتراک فعال — نامحدود
    usage = get_user_usage(user_id)
    return max(0, MAX_FREE_USAGE - usage.get(service, 0))


def activate_subscription(user_id: int):
    """فعال‌سازی اشتراک ماهیانه."""
    import datetime
    now = datetime.datetime.now()
    user_subscriptions[user_id] = {
        "start_date": now,
        "end_date": now + datetime.timedelta(days=SUBSCRIPTION_DURATION_DAYS),
        "expiry_notified": False,
    }
    _persist_subscriptions()


def get_expired_subscriptions() -> list:
    """دریافت لیست کاربرانی که اشتراکشان منقضی شده."""
    import datetime
    expired = []
    now = datetime.datetime.now()
    for uid, sub in user_subscriptions.items():
        if now >= sub["end_date"] and not sub["expiry_notified"]:
            expired.append(uid)
    return expired


def mark_expiry_notified(user_id: int):
    """علامت‌گذاری ارسال اعلان انقضای اشتراک."""
    if user_id in user_subscriptions:
        user_subscriptions[user_id]["expiry_notified"] = True
        _persist_subscriptions()


# =========================================================
# ذخیره‌ی دائمی اشتراک‌ها (بدون حذف پس از load)
# =========================================================
import json as _json
_SUB_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscriptions_store.json")

def _persist_subscriptions():
    """ذخیره‌ی دائمی اشتراک‌ها در فایل مستقل (بدون حذف)."""
    try:
        data = {}
        for uid, sub in user_subscriptions.items():
            data[str(uid)] = {
                "start_date": sub["start_date"].isoformat() if hasattr(sub["start_date"], "isoformat") else sub["start_date"],
                "end_date": sub["end_date"].isoformat() if hasattr(sub["end_date"], "isoformat") else sub["end_date"],
                "expiry_notified": sub.get("expiry_notified", False),
            }
        tmp = _SUB_STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SUB_STORE)
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[SUB-STORE] {e}")

def _load_persisted_subscriptions():
    """بارگذاری اشتراک‌های دائمی هنگام استارت."""
    import datetime as _dt
    if not os.path.exists(_SUB_STORE):
        return
    try:
        with open(_SUB_STORE, "r", encoding="utf-8") as f:
            data = _json.load(f)
        for uid_str, info in data.items():
            uid = int(uid_str)
            try:
                info["start_date"] = _dt.datetime.fromisoformat(info["start_date"])
                info["end_date"] = _dt.datetime.fromisoformat(info["end_date"])
            except Exception:
                pass
            user_subscriptions[uid] = info
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[SUB-STORE load] {e}")
