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

UPLOAD_PAGE_COUNT = "upload_page_count"
UPLOAD_FILE_SIZE = "upload_file_size"
UPLOAD_FILE_TYPE = "upload_file_type"
UPLOAD_DUPLICATE = "upload_duplicate"
UPLOAD_REGISTERED = "upload_registered"   # «پیوست مورد نظر با موفقیت ثبت گردید»
UPLOAD_CONFIRMED = "upload_confirmed"     # «پیوست مورد نظر با موفقیت تایید شد»

# خطای کدملی اشتباه یا عدم ثبت‌نام ثنا
NATIONAL_ID_INVALID_OR_NOT_REGISTERED = "national_id_invalid_or_not_registered"

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
        UPLOAD_PAGE_COUNT: "خطای تعداد صفحات",
        UPLOAD_FILE_SIZE: "خطای حجم فایل",
        UPLOAD_FILE_TYPE: "خطای نوع فایل",
        UPLOAD_DUPLICATE: "پیوست تکراری",
        UPLOAD_REGISTERED: "پیوست ثبت شد",
        UPLOAD_CONFIRMED: "پیوست تایید شد",
        NATIONAL_ID_INVALID_OR_NOT_REGISTERED: "کدملی اشتباه یا عدم ثبت‌نام ثنا",
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
