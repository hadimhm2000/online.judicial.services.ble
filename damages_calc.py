# -*- coding: utf-8 -*-
"""
محاسبهٔ «خسارت تأخیر تأدیه» و «مهریه به نرخ روز» بر اساس شاخص بهای کالاها و
خدمات مصرفی (تورم) بانک مرکزی.

این ماژول هیچ وابستگی به aiogram ندارد (منطق خالص) — مثل ayani_calc.py.

داده: cpi_index.json (کنار همین فایل، در گیت نیست)
    {
      "base": "1400=100",
      "monthly": {"1403/01": 205.3, ...},     ← شاخص ماهانه
      "annual":  {"1365": 0.21, ...},          ← شاخص سالانه (اختیاری)
      "updated_at": "..."
    }
مدیر داده را با ارسال فایل اکسل (کپشن /cpi_import) یا دستور /cpi وارد می‌کند
(damages_handlers.py). هر ماه تا وقتی شاخص ماه قبل وارد نشده، به مدیر یادآوری
می‌شود. ⚠️ همهٔ اعداد باید از یک جدول بانک مرکزی با یک سال پایه وارد شوند.

قواعد محاسبه:
  خسارت تأخیر تأدیه (مادهٔ ۵۲۲ قانون آیین دادرسی مدنی):
      مبلغ به‌روز = مبلغ × (شاخص ماه مبنای پرداخت ÷ شاخص ماه سررسید)
      خسارت = مبلغ به‌روز − مبلغ
      ماه مبنای پرداخت = ماهِ قبل از تاریخ محاسبه (آخرین ماهی که شاخصش
      منتشر شده)؛ اگر شاخص آن ماه هنوز وارد نشده، آخرین ماه موجود استفاده و
      در نتیجه اعلام می‌شود.
  مهریه به نرخ روز (تبصرهٔ مادهٔ ۱۰۸۲ قانون مدنی):
      مهریهٔ به‌روز = مبلغ × (شاخص سال قبل از سال تأدیه ÷ شاخص سال وقوع عقد)
      شاخص سالانه = مقدار واردشدهٔ سالانه، یا میانگین ۱۲ ماه همان سال.
"""
import datetime
import json
import os
import threading

CPI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cpi_index.json")

_lock = threading.Lock()


# ── تاریخ شمسی ───────────────────────────────────────────────────────────

def today_jalali() -> tuple[int, int, int]:
    """تاریخ امروز (تهران) به شمسی."""
    tehran = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    now = datetime.datetime.now(tehran)
    try:
        import jdatetime
        j = jdatetime.date.fromgregorian(year=now.year, month=now.month, day=now.day)
        return j.year, j.month, j.day
    except ImportError:
        from regional_value_pdf import _gregorian_to_jalali
        return _gregorian_to_jalali(now.year, now.month, now.day)


def month_key(year: int, month: int) -> str:
    return f"{year:04d}/{month:02d}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def parse_jalali_date(text: str) -> tuple[int, int, int] | None:
    """«۱۴۰۳/۰۵/۱۲» یا «1403-5-12» → (1403, 5, 12)؛ ورودی نامعتبر → None"""
    from id_validation import normalize_digits
    raw = normalize_digits(text or "").replace("-", "/").replace(".", "/")
    parts = [p for p in raw.split("/") if p]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    y, m, d = (int(p) for p in parts)
    if y < 100:
        y += 1400 if y < 50 else 1300
    if not (1300 <= y <= 1500 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    if m > 6 and d > 30:
        return None
    return y, m, d


def parse_amount(text: str) -> int | None:
    from id_validation import normalize_digits
    raw = normalize_digits(text or "").replace(",", "").replace("،", "").replace("٬", "")
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if value > 0 else None


# ── دادهٔ شاخص ───────────────────────────────────────────────────────────

def load_cpi() -> dict:
    with _lock:
        if not os.path.exists(CPI_FILE):
            return {"base": "", "monthly": {}, "annual": {}, "updated_at": None}
        with open(CPI_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("monthly", {})
    data.setdefault("annual", {})
    data.setdefault("base", "")
    return data


def save_cpi(data: dict):
    data["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = CPI_FILE + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, CPI_FILE)


def set_monthly(year: int, month: int, value: float):
    data = load_cpi()
    data["monthly"][month_key(year, month)] = float(value)
    save_cpi(data)


def import_rows(rows: list[tuple], base: str | None = None, replace: bool = False) -> tuple[int, int]:
    """ورود دسته‌ای: هر سطر (سال، ماه یا None، شاخص). خروجی: (تعداد ماهانه، تعداد سالانه)."""
    data = {"base": "", "monthly": {}, "annual": {}} if replace else load_cpi()
    n_month = n_year = 0
    for year, month, value in rows:
        if month:
            data["monthly"][month_key(int(year), int(month))] = float(value)
            n_month += 1
        else:
            data["annual"][str(int(year))] = float(value)
            n_year += 1
    if base:
        data["base"] = base
    save_cpi(data)
    return n_month, n_year


def latest_month(data: dict | None = None) -> tuple[int, int] | None:
    data = data or load_cpi()
    if not data["monthly"]:
        return None
    key = max(data["monthly"])
    y, m = key.split("/")
    return int(y), int(m)


def missing_required_month(today: tuple[int, int, int] | None = None) -> tuple[int, int] | None:
    """ماه قبل از ماه جاری اگر شاخصش وارد نشده باشد (برای یادآوری ماهانه به مدیر)."""
    y, m, _ = today or today_jalali()
    py, pm = prev_month(y, m)
    if month_key(py, pm) in load_cpi()["monthly"]:
        return None
    return py, pm


def annual_index(year: int, data: dict | None = None) -> float | None:
    data = data or load_cpi()
    if str(year) in data["annual"]:
        return data["annual"][str(year)]
    values = [data["monthly"].get(month_key(year, m)) for m in range(1, 13)]
    if all(v is not None for v in values):
        return sum(values) / 12
    return None


# ── محاسبات ──────────────────────────────────────────────────────────────

class CpiMissing(Exception):
    """شاخص لازم برای محاسبه وارد نشده است."""


def calc_late_payment(amount: int, due: tuple[int, int, int],
                      calc_date: tuple[int, int, int] | None = None) -> dict:
    data = load_cpi()
    calc_date = calc_date or today_jalali()
    due_key = month_key(due[0], due[1])
    if due_key not in data["monthly"]:
        raise CpiMissing(f"شاخص ماه سررسید ({due_key}) وارد نشده است.")
    if (due[0], due[1], due[2]) >= calc_date:
        raise ValueError("تاریخ سررسید باید قبل از تاریخ محاسبه باشد.")

    target = prev_month(calc_date[0], calc_date[1])
    target_key = month_key(*target)
    used_latest = False
    if target_key not in data["monthly"]:
        latest = latest_month(data)
        if latest is None or month_key(*latest) < due_key:
            raise CpiMissing(f"شاخص ماه {target_key} وارد نشده است.")
        target, target_key, used_latest = latest, month_key(*latest), True
    if target_key < due_key:
        raise ValueError("تاریخ محاسبه باید حداقل یک ماه بعد از سررسید باشد.")

    base_idx = data["monthly"][due_key]
    target_idx = data["monthly"][target_key]
    updated = round(amount * target_idx / base_idx)
    return {
        "amount": amount,
        "due_key": due_key,
        "target_key": target_key,
        "base_index": base_idx,
        "target_index": target_idx,
        "updated_amount": updated,
        "damages": updated - amount,
        "used_latest_available": used_latest,
        "cpi_base": data.get("base", ""),
    }


def calc_mahrieh(amount: int, marriage_year: int, payment_year: int | None = None) -> dict:
    data = load_cpi()
    payment_year = payment_year or today_jalali()[0]
    target_year = payment_year - 1
    if marriage_year > target_year:
        raise ValueError("مهریهٔ عقدِ همین سال نیاز به محاسبهٔ نرخ روز ندارد.")
    base_idx = annual_index(marriage_year, data)
    if base_idx is None:
        raise CpiMissing(f"شاخص سالانهٔ سال {marriage_year} وارد نشده است.")
    target_idx = annual_index(target_year, data)
    if target_idx is None:
        raise CpiMissing(f"شاخص سالانهٔ سال {target_year} وارد نشده است.")
    updated = round(amount * target_idx / base_idx)
    return {
        "amount": amount,
        "marriage_year": marriage_year,
        "target_year": target_year,
        "base_index": base_idx,
        "target_index": target_idx,
        "updated_amount": updated,
        "cpi_base": data.get("base", ""),
    }
