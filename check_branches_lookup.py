# -*- coding: utf-8 -*-
"""
check_branches_lookup.py
──────────────────────────────────────────────────────────────────────────
Resolver صحیح برای «نام شعبه (صلاحیت دادگاه)» در ثبت دسته‌جمعی چک.

⚠️ اصلاحیه: در نسخهٔ قبلی check_bulk_validation.py به‌اشتباه از
bulk_submissions._resolve_branch_code (که روی branch_code_lookup.json کار
می‌کند و برای روش «بایگانی» در ثبت دسته‌جمعی لوایح ساخته شده) استفاده شده بود.
آن دیتاست برای سنا > چک درست نیست. طبق فایل ارسالی هادی (units_output.csv,
دقیقاً همان لیستی که check_handlers.py::check_branch_callback از طریق
branches.py/ROOT_NODES برای انتخاب تعاملی صلاحیت دادگاه نشان می‌دهد)، این
فایل جدید و منبع صحیح resolve است.

فرمت units_output.csv:  Code, Name, Path, Level
  - Code: کد ۵ رقمی واحد (دقیقاً همان چیزی که check_scenario.py به‌عنوان
    check_branch_code به سنا می‌فرستد)
  - Name: نام واحد (منحصربه‌فرد در کل فایل — بررسی شد: صفر نام تکراری از
    ۳۱۰۶ ردیف)
  - Path: مسیر کامل سلسله‌مراتبی با جداکنندهٔ " > " (استان > حوزه قضایی > ...)
  - Level: عمق در درخت (۱ تا ۵)

محل فایل روی سرور: کنار branch_code_lookup.json / units_compact.json در
ریشهٔ پروژه، با همین نام (units_output.csv) — یا مسیر را در
CHECK_UNITS_CSV_PATH پایین عوض کنید.
"""
import csv
import re
import logging
from pathlib import Path
from difflib import get_close_matches

logger = logging.getLogger(__name__)

CHECK_UNITS_CSV_PATH = Path("units_output.csv")

_LOOKUP_BY_NAME = {}      # normalize(Name) -> row dict
_LOOKUP_BY_PATH = {}      # normalize(Path) -> row dict
_ALL_ROWS = []
_LOADED = False


def _normalize(text) -> str:
    """یکسان‌سازی املا: ی/ک عربی، حذف نیم‌فاصله/اعراب، فشرده‌سازی فاصله‌ها.
    عیناً همان normalize موجود در error_catalog.py — اینجا کپی شده تا این
    ماژول به‌تنهایی (بدون وابستگی به error_catalog) هم کار کند. اگر
    می‌خواهید فقط یک نسخه در پروژه باشد، این تابع را حذف و به‌جایش
    `from error_catalog import normalize as _normalize` بگذارید."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه")
    t = t.replace("‌", "").replace("‏", "").replace("‎", "").replace("‍", "")
    t = re.sub(r"[ً-ٰٟ]", "", t)  # اعراب
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _load():
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    if not CHECK_UNITS_CSV_PATH.exists():
        logger.warning(
            f"⚠️ فایل {CHECK_UNITS_CSV_PATH} پیدا نشد — resolve نام شعبهٔ چک غیرفعال است."
        )
        return
    with CHECK_UNITS_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("Code") or "").strip()
            name = (row.get("Name") or "").strip()
            path = (row.get("Path") or "").strip()
            level = (row.get("Level") or "").strip()
            if not code or not name:
                continue
            item = {"code": code, "name": name, "path": path, "level": level}
            _ALL_ROWS.append(item)
            _LOOKUP_BY_NAME[_normalize(name)] = item
            if path:
                _LOOKUP_BY_PATH[_normalize(path)] = item
    logger.info(f"✅ {len(_ALL_ROWS)} واحد قضائی از {CHECK_UNITS_CSV_PATH} برای resolve چک بارگذاری شد")


def resolve_check_branch(branch_name: str):
    """
    ورودی: نام شعبه همان‌طور که کاربر در اکسل نوشته (می‌تواند فقط نام واحد
    باشد، یا کل مسیر کپی‌شده با " > ").
    خروجی: (code, matched_item, suggestions)
      - اگر پیدا شود: code پر است، matched_item دیکشنری کامل ردیف، suggestions=[]
      - اگر پیدا نشود: code="", matched_item=None، suggestions تا ۳ نزدیک‌ترین نام
    """
    _load()
    if not branch_name:
        return "", None, []

    norm = _normalize(branch_name)

    # ۱) تطبیق دقیق روی نام
    item = _LOOKUP_BY_NAME.get(norm)
    if item:
        return item["code"], item, []

    # ۲) تطبیق دقیق روی کل مسیر (اگر کاربر مسیر کامل را کپی کرده)
    item = _LOOKUP_BY_PATH.get(norm)
    if item:
        return item["code"], item, []

    # ۳) اگر مسیر کامل داده شده ولی جزئی فرق دارد، آخرین بخش مسیر را هم امتحان کن
    if ">" in branch_name:
        last_segment = _normalize(branch_name.split(">")[-1])
        item = _LOOKUP_BY_NAME.get(last_segment)
        if item:
            return item["code"], item, []

    # ۴) پیدا نشد → نزدیک‌ترین نام‌ها برای پیام خطای کاربرپسند
    suggestions = get_close_matches(norm, _LOOKUP_BY_NAME.keys(), n=3, cutoff=0.6)
    suggested_names = [_LOOKUP_BY_NAME[s]["name"] for s in suggestions]
    return "", None, suggested_names


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("استفاده: python check_branches_lookup.py '<نام شعبه>'")
        sys.exit(1)
    code, item, suggestions = resolve_check_branch(sys.argv[1])
    if item:
        print(f"✅ پیدا شد: {item['name']}  →  کد: {code}\nمسیر: {item['path']}")
    else:
        print("❌ پیدا نشد.")
        if suggestions:
            print("نزدیک‌ترین موارد:")
            for s in suggestions:
                print("  •", s)
