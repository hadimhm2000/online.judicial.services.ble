"""تنظیمات کلی ربات بله: توکن، شناسه ادمین، آدرس API، تعرفه‌ها.
تنها فایلی که برای تغییر قیمت/شماره کارت/توکن باید ویرایش کنی."""
import os

from dotenv import load_dotenv

# مقادیر رو از فایل .env (کنار همین فایل‌ها) می‌خونه، اگه .env نبود چیزی رو خراب نمی‌کنه
load_dotenv()


# ================= تنظیمات اصلی ربات =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ متغیر محیطی BOT_TOKEN تنظیم نشده است.\n"
        "قبل از اجرا این دستور را در ترمینال بزن (ویندوز):\n"
        "    set BOT_TOKEN=توکن_ربات_بله_شما\n"
        "یا در Linux/Mac:\n"
        "    export BOT_TOKEN=توکن_ربات_بله_شما"
    )

_admin_id_raw = os.environ.get("ADMIN_ID")
if not _admin_id_raw:
    raise RuntimeError(
        "❌ متغیر محیطی ADMIN_ID تنظیم نشده است.\n"
        "قبل از اجرا این دستور را در ترمینال بزن (ویندوز):\n"
        "    set ADMIN_ID=آیدی_عددی_بله_ادمین\n"
        "یا در Linux/Mac:\n"
        "    export ADMIN_ID=آیدی_عددی_بله_ادمین"
    )
ADMIN_ID = int(_admin_id_raw)

# آدرس API بله — مستقیم یا از طریق واسطه
# در حالت مستقیم: https://tapi.bale.ai
# در حالت واسطه (مثلاً Vercel Proxy): آدرس پروکسی
BALE_API_BASE = os.environ.get(
    "BALE_API_BASE",
    "https://tapi.bale.ai"
)

# اگر روزی به یک پروکسی واقعی (HTTP/SOCKS) نیاز شد، می‌توانی این متغیر را
# در .env ست کنی. در حالت فعلی خالی می‌ماند.
PROXY_URL = os.environ.get("PROXY_URL", "")

# آدرس پنل ادمین (Next.js) — exempt_users و working_hours از این آدرس
# تنظیمات را می‌خوانند. اگر روی همسرور است: http://localhost:3000
ADMIN_PANEL_URL = os.environ.get("ADMIN_PANEL_URL", "http://localhost:3000")

# آدرس API پنل ادمین — برای همگام‌سازی اشتراک‌ها و ...
ADMIN_API_BASE = os.environ.get("ADMIN_API_BASE", "http://localhost:3000/api")

# ================= تنظیمات مالی ربات =================
CARD_NUMBER = "6219861936929354"
ACCOUNT_NAME = "هادی منتظران"

# توکن کیف پول بله برای پرداخت آنلاین
BALE_WALLET_TOKEN = "WALLET-eg5yrAJGzAu1tDAn"

DEBUG_LOG_REQUESTS = False

FEES = {
    "شماره تماس": 65000,
    "کد ملی": 55000,
    "کد رهگیری ساده": 50000,
    "کد رهگیری با منضمات": 50000
}

# هزینه خدمات ثبت لایحه (تومان) — قبل از ارسال به سامانه
LAVAYEH_SERVICE_FEE = 50000

# هزینه خدمات ثبت اظهارنامه (تومان) — قبل از ارسال به سامانه
EZHHARNAMEH_SERVICE_FEE = 50000

def get_fee(query_type, need_attachments):
    if query_type == "شماره تماس":
        return FEES["شماره تماس"]
    elif query_type == "کد ملی":
        return FEES["کد ملی"]
    else:
        if need_attachments:
            return FEES["کد رهگیری با منضمات"]
        else:
            return FEES["کد رهگیری ساده"]


# ================= محاسبه هزینه لایحه =================
import math


def _round_up_to_thousand(amount: int) -> int:
    """رند کردن مبلغ به بالا به نزدیک‌ترین هزار (مثلاً ۱,۰۴۹,۴۴۹ → ۱,۰۵۰,۰۰۰)"""
    if amount <= 0:
        return 0
    return ((amount + 999) // 1000) * 1000


def calculate_lavayeh_fee(court_total: int) -> int:
    """
    محاسبه هزینه نهایی لایحه بر اساس مجموع هزینه درج شده در سامانه (ریال).

    مرحله ۱: مبلغ نمایش‌داده‌شده به بالا رند می‌شود (به نزدیک‌ترین هزار ریال).
    مرحله ۲: بر اساس مبلغ رندشده، کسر مشخصی اعمال می‌شود:
      تا ۲,۰۰۰,۰۰۰ ریال       → کسر ۱۰۰,۰۰۰ ریال
      ۲,۰۰۰,۰۰۱ تا ۳,۰۰۰,۰۰۰  → کسر ۲۸۰,۰۰۰ ریال
      بالای ۳,۰۰۰,۰۰۱ ریال     → کسر ۴۰۰,۰۰۰ ریال
    مرحله ۳: مبلغ نهایی = مبلغ_رند + (مبلغ_رند − کسر)

    مثال: مبلغ سامانه = ۱,۰۴۹,۴۴۹ ریال
      رند → ۱,۰۵۰,۰۰۰ ریال
      کسر (زیر ۲ میلیون) → ۱۰۰,۰۰۰ ریال
      خالص = ۱,۰۵۰,۰۰۰ − ۱۰۰,۰۰۰ = ۹۴۰,۰۰۰ ریال
      نهایی = ۱,۰۵۰,۰۰۰ + ۹۴۰,۰۰۰ = ۱,۹۹۰,۰۰۰ ریال
    """
    rounded = _round_up_to_thousand(court_total)

    if rounded <= 2_000_000:
        deduction = 100_000
    elif rounded <= 3_000_000:
        deduction = 280_000
    else:
        deduction = 400_000

    net = rounded - deduction
    final_fee = rounded + net  # = 2 * rounded - deduction
    return final_fee


def format_lavayeh_fee_explanation(court_total: int) -> str:
    """توضیح فرمول هزینه لایحه — فقط مبلغ نهایی نمایش داده می‌شود"""
    final_fee = calculate_lavayeh_fee(court_total)
    return f"💳 *مبلغ نهایی قابل پرداخت: {final_fee:,} ریال*"