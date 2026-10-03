"""
کاتالوگ متمرکز خطاها/هشدارها/پیام‌های سامانه (سامانه ثنا).

چرا؟
  تا این لحظه، ده‌ها متنِ پاپ‌آپ (خطا/هشدار/موفقیت) به‌صورت پراکنده در فایل‌های
  مختلف با `.includes(...)` / `in` بررسی می‌شدند. این ماژول همه‌ی آن‌ها را در یک
  منبع واحد جمع می‌کند تا:
    ۱. هر خطایی در هر جای سامانه برای ربات «شناخته‌شده» و قابل دسته‌بندی باشد.
    ۲. اگر خطای جدید/ناشناخته‌ای دیده شد، ربات آن را تشخیص دهد (category="unknown")،
       کرش نکند و بتواند مسیر خود را ادامه دهد و خطا را گزارش/آپلود کند
       (از طریق bug_reporter).

نکته‌ی املا:
  متن سامانه گاهی با «ی/ي» یا «ک/ك» عربی، نیم‌فاصله (ZWNJ) یا اعراب متفاوت نوشته
  می‌شود. تابع normalize این تفاوت‌ها را یکسان می‌کند تا نیازی به فهرست‌کردن همه‌ی
  حالت‌ها نباشد و تطبیق مقاوم باشد.
"""

import re
import logging

# ── دسته‌بندی‌ها ─────────────────────────────────────────────
SESSION_EXPIRY = "session_expiry"
LOAD_ERROR = "load_error"
VALIDATION = "validation"
NOT_FOUND = "not_found"

SIGN_WRONG_CODE = "sign_wrong_code"
SIGN_SANA_NOT_REGISTERED = "sign_sana_not_registered"
SIGN_CODE_SENT = "sign_code_sent"
SIGN_ALREADY_SENT = "sign_already_sent"
SIGN_SUCCESS = "sign_success"
RECOVERY_SUCCESS = "recovery_success"

# کدرهگیری معتبر است اما متعلق به نوع سند دیگری است (مثلاً اظهارنامه) و در
# این فرم/بخش قابل بازیابی نیست
WRONG_FORM_TRACKING_CODE = "wrong_form_tracking_code"

UPLOAD_PAGE_COUNT = "upload_page_count"
UPLOAD_FILE_SIZE = "upload_file_size"
UPLOAD_FILE_TYPE = "upload_file_type"
UPLOAD_DUPLICATE = "upload_duplicate"
UPLOAD_REGISTERED = "upload_registered"   # «پیوست مورد نظر با موفقیت ثبت گردید»
UPLOAD_CONFIRMED = "upload_confirmed"     # «پیوست مورد نظر با موفقیت تایید شد»

# خطای کدملی اشتباه یا عدم ثبت‌نام ثنا
NATIONAL_ID_INVALID_OR_NOT_REGISTERED = "national_id_invalid_or_not_registered"

# ⭐ اصلاحیهٔ کارفرما: خطای «شماره تصمیم نهایی یا شماره پرونده اشتباه می باشد»
# در استعلام/بازیابی دادنامهٔ دعاوی اعتراضی
RETRIEVE_MISMATCH = "retrieve_mismatch"

# ⭐ اصلاحیهٔ کارفرما: «شخص ارائه‌کننده لایحه به‌نام ... در فهرست اشخاص
# پرونده نیست و امکان ثبت لایحه دفاعیه وجود ندارد»
PERSON_NOT_IN_CASE = "person_not_in_case"

GENERAL_ERROR = "general_error"
SUCCESS = "success"
UNKNOWN = "unknown"


def normalize(text) -> str:
    """یکسان‌سازی املا: ی/ک عربی، حذف نیم‌فاصله/اعراب، فشرده‌سازی فاصله‌ها."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه")
    t = t.replace("‌", "").replace("‏", "").replace("‎", "").replace("‍", "")
    t = re.sub(r"[ً-ٰٟ]", "", t)  # اعراب
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ── کاتالوگ اصلی: (دسته، [الگوهای زیررشته‌ای])، به ترتیب اولویتِ تطبیق ─────────
# ترتیب مهم است: دسته‌های خاص‌تر (مثل «امضا در ثنا ثبت نشده») باید قبل از
# دسته‌های عمومی‌تر (مثل general_error) بررسی شوند.
CATALOG = [
    # ── ⭐ خطاهای خاص کارفرما (باید قبل از دسته‌های عمومی بررسی شوند) ──
    (RETRIEVE_MISMATCH, [
        "تصمیم نهایی یا شماره پرونده اشتباه",
        "تصمیم نهایی",
        "شماره پرونده اشتباه",
    ]),
    (PERSON_NOT_IN_CASE, [
        "در فهرست اشخاص پرونده نیست",
    ]),

    # ── امضا (خاص‌ترین‌ها اول) ──
    (SIGN_SANA_NOT_REGISTERED, [
        "در سامانه ثنا درج نشده",
        "در سامانه ثنا ثبت نشده",
    ]),
    (SIGN_WRONG_CODE, [
        "رمز موقت نادرست", "رمز موقت اشتباه", "خطای سرویس ثنا : رمز موقت",
    ]),
    (SIGN_SUCCESS, [
        "امضاء با موفقیت در صفحه چاپ درج گردید",
        "با موفقیت در صفحه چاپ",
        "در صفحه ی چاپ درج شده",
        "در صفحه چاپ درج شده",
    ]),
    (SIGN_CODE_SENT, [
        "رمز موقت به شماره همراه ارسال شد",
    ]),
    (SIGN_ALREADY_SENT, [
        "10 دقیقه", "۱۰ دقیقه",
    ]),
    # ⚠️ باید پیش از RECOVERY_SUCCESS بررسی شود چون این پیام هم شامل واژه‌ی
    # عمومی «بازیابی» است («... قابل بازیابی در این فرم نیست»)
    (WRONG_FORM_TRACKING_CODE, [
        "قابل بازیابی در این فرم نیست",
        "قابل بازیابی در این فرم نمی باشد",
    ]),
    (RECOVERY_SUCCESS, [
        "بازیابی اظهارنامه با موفقیت", "بازیابی",
    ]),

    # ── آپلود منضمات ──
    (UPLOAD_CONFIRMED, ["پیوست مورد نظر با موفقیت تایید شد", "با موفقیت تایید"]),
    (UPLOAD_REGISTERED, ["پیوست مورد نظر با موفقیت ثبت گردید"]),
    (UPLOAD_PAGE_COUNT, ["تعداد صفحات", "صفحات اشتباه", "صفحه اشتباه", "تعداد صفحه"]),
    (UPLOAD_FILE_SIZE, ["حجم فایل", "حجم بیش", "حجم مجاز", "سایز فایل", "اندازه فایل", "حجم فایل بیش از"]),
    (UPLOAD_FILE_TYPE, ["نوع فایل", "فرمت فایل", "پسوند فایل"]),
    (UPLOAD_DUPLICATE, ["تکراری", "قبلا", "قبلاً"]),

    # ── نشست / احراز هویت ──
    (SESSION_EXPIRY, [
        "از ساعت ورود شما میگذرد",
        "اصل اولویت", "احراز هویت", "تمدید کنید", "تمدید نمایید",
        "منقضی", "رایانه ای دیگر", "ورود قبلی", "اعتبار ورود",
        "خطای دسترسی کاربر", "نشست شما", "نشست منقضی", "session",
    ]),

    # ── خطای بارگذاری/سرویس ──
    (LOAD_ERROR, [
        "تاخیر در اجرای سرویس", "سرویس با خطا", "خطا در فراخوانی", "خطای سرور",
    ]),

    # ── اعتبارسنجی ورودی / جستجو ──
    (VALIDATION, [
        "لطفا اطلاعات خواسته شده را به درستی وارد نمایید",
        "معتبر نیست", "کد رهگیری معتبر نیست",
        # ⭐ پاپ‌آپ «کد رهگیری نامعتبر است» (h2) — قبلاً هیچ الگویی آن را
        # نمی‌گرفت و استعلام به‌اشتباه با «۰ پیوست» ادامه می‌یافت
        "نامعتبر است", "کد رهگیری نامعتبر",
        "تاریخ تولد ارسالی مربوط به شماره ملی",
    ]),
    # ── کدملی اشتباه یا عدم ثبت‌نام ثنا (باعث خطای «تاریخچه اولویت بندی شده ... در سیستم موجود نمی باشد») ──
    (NATIONAL_ID_INVALID_OR_NOT_REGISTERED, [
        "تاریخچه اولویت بندی شده", "تاريخچه اولويت بندي شده",
        "در سیستم موجود نمی باشد", "در سيستم موجود نيست",
    ]),
    (NOT_FOUND, [
        "یافت نشد", "اطلاعاتی یافت نشد",
        "ثبت نشده است",
        "اطلاعاتی با این شماره ملی ثبت نشده است",
        "اطلاعاتی با این شناسه ملی ثبت نشده است",
    ]),

    # ── عمومی (آخرین‌ها) ──
    (SUCCESS, ["با موفقیت", "موفقیت انجام"]),
    (GENERAL_ERROR, ["خطا", "مشکل", "امکان پذیر نیست", "امکان‌پذیر نیست"]),
]

# الگوهای نرمال‌شده (کش)
_NORMALIZED_CATALOG = [(cat, [normalize(p) for p in pats]) for cat, pats in CATALOG]


def classify(text) -> str:
    """
    دسته‌ی یک متن پاپ‌آپ/خطا را برمی‌گرداند (به ترتیب اولویت کاتالوگ).
    اگر هیچ الگویی مطابقت نداشت → "unknown".
    """
    norm = normalize(text)
    if not norm:
        return UNKNOWN
    for cat, patterns in _NORMALIZED_CATALOG:
        for p in patterns:
            if p and p in norm:
                return cat
    return UNKNOWN


def matches(text, category) -> bool:
    """آیا متن در دسته‌ی مشخصی قرار می‌گیرد؟"""
    return classify(text) == category


# ── توابع کمکیِ سازگار با کدِ موجود ─────────────────────────────

_SESSION_KEYWORDS = [normalize(p) for p in [
    "انقض", "نشست", "session", "ورود", "لاگین",
    "از ساعت ورود شما میگذرد", "اصل اولویت", "احراز هویت", "تمدید",
]]


def is_session_expiry(text) -> bool:
    norm = normalize(text)
    if not norm:
        return False
    return any(k in norm for k in _SESSION_KEYWORDS)


# ── ⭐ توابع کمکی اصلاحیهٔ کارفرما (نرمال‌سازی‌شده — مقاوم به ي/ک عربی و
#    نیم‌فاصله) ────────────────────────────────────────────────────

def is_retrieve_mismatch(text) -> bool:
    """آیا متن، خطای «شماره تصمیم نهایی یا شماره پرونده اشتباه می باشد» است؟"""
    norm = normalize(text)
    if not norm:
        return False
    return ("تصمیم نهایی" in norm) or ("شماره پرونده اشتباه" in norm)


def is_person_not_in_case(text) -> bool:
    """آیا متن، خطای «... در فهرست اشخاص پرونده نیست ...» است؟"""
    norm = normalize(text)
    if not norm:
        return False
    return "در فهرست اشخاص پرونده نیست" in norm


def is_birthdate_error(text) -> bool:
    """آیا متن، خطای «تاریخ تولد ارسالی مربوط به شماره ملی ... اشتباه است» است؟

    نرمال‌سازی‌شده — نسخه‌های قبلی در فایل‌های مختلف با substring خام
    بررسی می‌شدند و به ي/ک عربی حساس بودند.
    """
    norm = normalize(text)
    if not norm:
        return False
    return "تاریخ تولد" in norm and "اشتباه" in norm


def extract_national_id(text) -> str:
    """استخراج شماره ملی از متن خطای سامانه (مثل «... مربوط به شماره ملی
    4420910144 اشتباه است») — ۱۰ رقمی؛ خالی اگر یافت نشد."""
    if not text:
        return ""
    m = re.search(r"\d{10,}", str(text))
    return m.group(0)[:10] if m else ""


def classify_sana_popup(text) -> str:
    """⭐ اصلاحیهٔ کارفرما (۱۴۰۵/۰۶/۲۸) — دسته‌بندی پاپ‌آپ پس از کلیک
    دکمهٔ «استعلام ثنا» در کلیهٔ فلوها (لایحه/اظهارنامه/دادخواست/اعتراضی):
      "person_not_in_case" | "birthdate" | "not_registered" | "other"

    انقضای نشست قبل از این تابع و جداگانه مدیریت می‌شود.
    نرمال‌سازی‌شده — مقاوم به ي/ک عربی و نیم‌فاصله.
    """
    if not text or not isinstance(text, str):
        return "other"
    if is_person_not_in_case(text):
        return "person_not_in_case"
    if is_birthdate_error(text):
        return "birthdate"
    norm = normalize(text)
    if "اطلاعاتی با این شناسه ملی ثبت نشده است" in norm or (
            "شناسه ملی" in norm and "ثبت نشده" in norm):
        return "not_registered"
    return "other"


def is_load_error(text) -> bool:
    return classify(text) == LOAD_ERROR


def classify_upload_error(text) -> str:
    """
    نگاشت به دسته‌های سازگار با upload_helpers.detect_error_type:
    "page_count" | "file_size" | "file_type" | "session" | "duplicate" | "general" | "unknown"
    """
    if not text:
        return "unknown"
    cat = classify(text)
    mapping = {
        UPLOAD_PAGE_COUNT: "page_count",
        UPLOAD_FILE_SIZE: "file_size",
        UPLOAD_FILE_TYPE: "file_type",
        SESSION_EXPIRY: "session",
        UPLOAD_DUPLICATE: "duplicate",
        GENERAL_ERROR: "general",
    }
    if cat in mapping:
        return mapping[cat]
    # اگر جزو دسته‌های آپلود نبود ولی متن انقضای نشست داشت
    if is_session_expiry(text):
        return "session"
    # اگر واژه‌ی خطا داشت
    if any(k in normalize(text) for k in ("خطا", "مشکل", "امکان", "سرور")):
        return "general"
    return "unknown"


def classify_sign_popup(text, has_success_icon=False, has_warning_icon=False, has_error_icon=False) -> str:
    """
    طبقه‌بندی پاپ‌آپ نتیجه‌ی امضا با ترکیب متن و آیکون:
      "success" | "wrong_code" | "sana_not_registered" | "code_sent" |
      "already_sent" | "recovery" | "error" | None
    """
    cat = classify(text)
    if cat == SIGN_SANA_NOT_REGISTERED:
        return "sana_not_registered"
    if cat == SIGN_WRONG_CODE:
        return "wrong_code"
    if cat == SIGN_CODE_SENT:
        return "code_sent"
    if cat == SIGN_ALREADY_SENT:
        return "already_sent"
    if cat == RECOVERY_SUCCESS:
        return "recovery"
    if cat == SIGN_SUCCESS:
        return "success"
    # بر اساس آیکون
    if has_success_icon:
        return "success"
    if has_warning_icon and ("درج شده" in normalize(text)):
        return "success"
    if has_error_icon:
        return "error"
    return None


def describe(text) -> str:
    """توضیح کوتاه انسانی از دسته‌ی خطا — برای لاگ/گزارش."""
    cat = classify(text)
    labels = {
        SESSION_EXPIRY: "انقضای نشست",
        LOAD_ERROR: "خطای بارگذاری/سرویس",
        VALIDATION: "خطای اعتبارسنجی ورودی",
        NOT_FOUND: "یافت نشد",
        SIGN_WRONG_CODE: "رمز موقت نادرست",
        SIGN_SANA_NOT_REGISTERED: "امضا در ثنا ثبت نشده",
        SIGN_CODE_SENT: "رمز موقت ارسال شد",
        SIGN_ALREADY_SENT: "کد قبلاً ارسال شده",
        SIGN_SUCCESS: "امضای موفق",
        RECOVERY_SUCCESS: "بازیابی موفق",
        WRONG_FORM_TRACKING_CODE: "کدرهگیری متعلق به فرم/نوع سند دیگر",
        UPLOAD_PAGE_COUNT: "خطای تعداد صفحات",
        UPLOAD_FILE_SIZE: "خطای حجم فایل",
        UPLOAD_FILE_TYPE: "خطای نوع فایل",
        UPLOAD_DUPLICATE: "پیوست تکراری",
        UPLOAD_REGISTERED: "پیوست ثبت شد",
        UPLOAD_CONFIRMED: "پیوست تایید شد",
        NATIONAL_ID_INVALID_OR_NOT_REGISTERED: "کدملی اشتباه یا عدم ثبت‌نام ثنا",
        RETRIEVE_MISMATCH: "شماره تصمیم نهایی/پرونده اشتباه",
        PERSON_NOT_IN_CASE: "شخص در فهرست اشخاص پرونده نیست",
        GENERAL_ERROR: "خطای عمومی",
        SUCCESS: "عملیات موفق",
        UNKNOWN: "خطای ناشناخته",
    }
    return labels.get(cat, cat)


def log_unknown(prefix, text):
    """ثبت خطای ناشناخته برای بررسی بعدی (تا کاتالوگ به‌مرور کامل شود)."""
    norm = normalize(text)
    if norm:
        logging.warning(f"[{prefix}][ERROR_CATALOG] خطای ناشناخته (به کاتالوگ اضافه شود): {norm[:200]}")


# =====================================================================
# ⭐ جدول تصمیم مرکزی (Error Policy)
# ---------------------------------------------------------------------
# هر بخش ربات که به خطا/پاپ‌آپ سامانه می‌خورد، ابتدا با classify() دستهٔ
# خطا را از همین فایل پیدا می‌کند و سپس با decide() از همین جدول می‌خواند
# که چه اقدامی باید انجام شود. این جدول فقط «تصمیم» را مشخص می‌کند؛ اجرای
# آن در همان بخشی است که خطا رخ داده (تا روندهای فعلیِ درست تغییری نکنند).
#
# برای افزودن خطای جدید: الگوی متن را به CATALOG بالا اضافه کنید و اگر
# اقدام خاصی لازم دارد، یک ردیف به ERROR_POLICY اضافه کنید.
# =====================================================================

# ── اقدام‌ها ──
ACTION_CONTINUE = "continue"                  # خطا نیست / ادامهٔ روند
ACTION_RETRY_SAME = "retry_same"              # خطای موقت سامانه — تلاش مجدد همان مرحله
ACTION_RELOGIN = "relogin"                    # انقضای نشست — ورود مجدد و ادامه
ACTION_FREE_CORRECTION = "free_correction"    # ورودی کاربر اشتباه — یک‌بار اصلاح رایگان
ACTION_SWITCH_CATEGORY = "switch_category"    # دستهٔ اشتباه — ورود خودکار به دستهٔ صحیح
ACTION_ASK_USER = "ask_user"                  # اطلاع به کاربر برای اصلاح همان فیلد
ACTION_STOP_NOTIFY_ADMIN = "stop_notify_admin"  # توقف روند + اطلاع به مدیر برای رسیدگی دستی

# ── دسته → (اقدام، اطلاع به مدیر؟) ──
ERROR_POLICY = {
    SESSION_EXPIRY: (ACTION_RELOGIN, True),
    LOAD_ERROR: (ACTION_RETRY_SAME, False),
    VALIDATION: (ACTION_FREE_CORRECTION, True),
    WRONG_FORM_TRACKING_CODE: (ACTION_SWITCH_CATEGORY, True),
    NOT_FOUND: (ACTION_STOP_NOTIFY_ADMIN, True),
    NATIONAL_ID_INVALID_OR_NOT_REGISTERED: (ACTION_ASK_USER, True),
    RETRIEVE_MISMATCH: (ACTION_ASK_USER, True),
    PERSON_NOT_IN_CASE: (ACTION_ASK_USER, True),
    SIGN_WRONG_CODE: (ACTION_ASK_USER, False),
    SIGN_SANA_NOT_REGISTERED: (ACTION_ASK_USER, True),
    UPLOAD_PAGE_COUNT: (ACTION_RETRY_SAME, False),
    UPLOAD_FILE_SIZE: (ACTION_ASK_USER, True),
    UPLOAD_FILE_TYPE: (ACTION_ASK_USER, True),
    UPLOAD_DUPLICATE: (ACTION_CONTINUE, False),
    UPLOAD_REGISTERED: (ACTION_CONTINUE, False),
    UPLOAD_CONFIRMED: (ACTION_CONTINUE, False),
    SIGN_CODE_SENT: (ACTION_CONTINUE, False),
    SIGN_ALREADY_SENT: (ACTION_CONTINUE, False),
    SIGN_SUCCESS: (ACTION_CONTINUE, False),
    RECOVERY_SUCCESS: (ACTION_CONTINUE, False),
    SUCCESS: (ACTION_CONTINUE, False),
    GENERAL_ERROR: (ACTION_STOP_NOTIFY_ADMIN, True),
    UNKNOWN: (ACTION_STOP_NOTIFY_ADMIN, True),
}


def decide(text) -> dict:
    """تصمیم مرکزی برای یک متن خطا/پاپ‌آپ سامانه.

    خروجی: {"category", "action", "notify_admin", "label"}
    """
    cat = classify(text)
    action, notify = ERROR_POLICY.get(cat, (ACTION_STOP_NOTIFY_ADMIN, True))
    return {"category": cat, "action": action, "notify_admin": notify, "label": describe(text)}


# =====================================================================
# ⭐ استعلام کدرهگیری: پیام‌های فرصت اصلاح رایگان (یک‌بار) و «موردی استعلام نشد»
# =====================================================================

INQUIRY_FREE_CORRECTION_MSG = (
    "❌ کدرهگیری اشتباه است یا دستهٔ مربوطه را به‌اشتباه انتخاب کرده‌اید.\n\n"
    "✅ *یک‌بار دیگر* امکان اصلاح بدون پرداخت هزینه را دارید "
    "(تا {minutes} دقیقه).\n\n"
    "لطفاً کدرهگیری صحیح را ارسال نمایید (در مرحلهٔ بعد می‌توانید دسته را هم اصلاح کنید):"
)

INQUIRY_NOTHING_FOUND_MSG = (
    "❌ با اطلاعات اصلاح‌شده هم موردی استعلام نشد.\n\n"
    "🔖 کدرهگیری: `{tracking_code}`\n"
    "📂 دسته: {doc_name}\n\n"
    "فرصت اصلاح رایگان استفاده شده است. در صورت نیاز، پشتیبانی موضوع را بررسی و "
    "نتیجه را برایتان ارسال خواهد کرد."
)

INQUIRY_CATEGORY_SWITCHED_NOTE = (
    "⚠️ دسته‌ای که انتخاب کرده بودید («{old}») اشتباه بود؛ "
    "استعلام در دستهٔ صحیح «{new}» انجام شد."
)


# =====================================================================
# ⭐ نگاشت پیام «این کد رهگیری مربوط به «…» می باشد» به دستهٔ منوی ربات
# ---------------------------------------------------------------------
# ترتیب مهم است: موارد خاص‌تر (شورا/دیوان/کیفری) پیش از موارد عمومی.
# هر ردیف: (کلیدواژه‌های لازم — همه باید باشند، دستهٔ اصلی، زیردسته)
# نام زیردسته‌ها دقیقاً مطابق keyboards.SUB_MENUS است.
# =====================================================================
WRONG_FORM_TARGETS = [
    (("دیوان", "تجدیدنظر"), "دیوان عدالت اداری", "تجدیدنظرخواهی دیوان عدالت اداری"),
    (("دیوان", "دادخواست"), "دیوان عدالت اداری", "دادخواست بدوی دیوان عدالت اداری"),
    (("شورا", "تجدیدنظر"), "شورای حل اختلاف", "تجدیدنظرخواهی شورا"),
    (("شورا", "واخواهی"), "شورای حل اختلاف", "واخواهی شورا"),
    (("شورا", "اعتراض ثالث"), "شورای حل اختلاف", "اعتراض ثالث شورا"),
    (("تجدیدنظر",), "دعاوی اعتراضی", "تجدیدنظرخواهی"),
    (("واخواهی",), "دعاوی اعتراضی", "واخواهی"),
    (("فرجام",), "دعاوی اعتراضی", "فرجام خواهی"),
    (("اعاده دادرسی", "کیفری"), "دعاوی اعتراضی", "اعاده دادرسی کیفری"),
    (("اعاده دادرسی",), "دعاوی اعتراضی", "اعاده دادرسی مدنی"),
    (("اعتراض ثالث",), "دعاوی اعتراضی", "اعتراض ثالث"),
    (("اعتراض به قرار",), "دعاوی اعتراضی", "اعتراض به قرار دادسرا"),
    (("تقابل",), "دعاوی طاری", "دعوای تقابل"),
    (("ورود ثالث",), "دعاوی طاری", "دعوای ورود ثالث"),
    (("جلب ثالث",), "دعاوی طاری", "دعوای جلب ثالث"),
    (("اظهارنامه",), "اظهارنامه", None),
    (("لایحه",), "لایحه", None),
    (("شکواییه",), "شکواییه", None),
    (("شکوائیه",), "شکواییه", None),
    (("صلح",), "دعاوی دادگاههای صلح", None),
    (("دادخواست",), "دادخواست بدوی", None),
]
_NORMALIZED_WRONG_FORM_TARGETS = [
    (tuple(normalize(k).replace(" ", "") for k in keys), cat, sub)
    for keys, cat, sub in WRONG_FORM_TARGETS
]


def extract_wrong_form_name(text) -> str:
    """نام فرم داخل «…» در پیام «این کد رهگیری مربوط به «X» می باشد» — خالی اگر نبود."""
    if not text:
        return ""
    m = re.search(r"«([^»]+)»", str(text))
    if m:
        return m.group(1).strip()
    m = re.search(r"مربوط\s*به\s+(.+?)\s+می\s*باشد", normalize(text))
    return m.group(1).strip() if m else ""


def resolve_wrong_form_target(text):
    """دستهٔ صحیح منوی ربات برای پیام «کد رهگیری مربوط به فرم دیگر».

    خروجی: (دستهٔ اصلی، زیردسته یا None) — یا None اگر نام فرم شناخته نشد.
    فقط نام داخل «…» بررسی می‌شود تا واژه‌های عمومی پیام (مثل «فرم») اشتباه
    تطبیق نخورند.
    """
    name = extract_wrong_form_name(text)
    if not name:
        return None
    key = normalize(name).replace(" ", "")
    for keys, cat, sub in _NORMALIZED_WRONG_FORM_TARGETS:
        if all(k in key for k in keys):
            return (cat, sub)
    return None
