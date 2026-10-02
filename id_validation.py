"""
id_validation.py — اعتبارسنجی کدملی (۱۰ رقمی) و شناسه ملی اشخاص حقوقی (۱۱ رقمی)
══════════════════════════════════════════════════════════════════════════════

با رقم کنترل استاندارد، کدملی/شناسهٔ اشتباه همان لحظهٔ ورود رد می‌شود؛ پیش
از آن‌که درخواست به سامانه برسد و خطای «کدملی اشتباه» و پنجرهٔ ۳۰ دقیقه‌ای
ویرایش (nid_fix_window.py) را ایجاد کند.

پیاده‌سازی به‌صورت یک middleware بیرونی روی همهٔ پیام‌هاست (در bot.py ثبت
می‌شود) و فقط در stateهایی که نامشان نشان می‌دهد منتظر کدملی/شناسهٔ ملی
هستند دخالت می‌کند؛ آن هم فقط وقتی متن ورودی دقیقاً ۱۰ (یا ۱۱) رقم است و رقم
کنترلش غلط است. بقیهٔ ورودی‌ها (دکمه‌ها، «بازگشت»، طول اشتباه و ...) دست‌نخورده
به هندلر همان سرویس می‌رسند تا اعتبارسنجی‌های فعلی هر سرویس همان‌طور بماند.
"""
from aiogram import BaseMiddleware, types

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# پسوند نام stateهایی که منتظر کدملی شخص حقیقی‌اند (۱۰ رقم)
_PERSON_SUFFIXES = ("national_id", "_nid")
# پسوند نام stateهایی که منتظر شناسه ملی شخص حقوقی‌اند (۱۱ رقم)
_COMPANY_SUFFIXES = ("company_id", "company_id_no_rep")

_LEGAL_WEIGHTS = (29, 27, 23, 19, 17, 29, 27, 23, 19, 17)


def normalize_digits(text: str) -> str:
    """تبدیل ارقام فارسی/عربی به انگلیسی و حذف فاصله و خط تیره."""
    return (text or "").translate(_DIGITS).replace(" ", "").replace("-", "").replace("‌", "")


def is_valid_national_id(code: str) -> bool:
    """کدملی ۱۰ رقمی اشخاص حقیقی (الگوریتم رقم کنترل سازمان ثبت احوال)."""
    code = normalize_digits(code)
    if len(code) != 10 or not code.isdigit():
        return False
    if len(set(code)) == 1 or int(code[3:9]) == 0:
        return False
    digits = [int(c) for c in code]
    total = sum(digits[i] * (10 - i) for i in range(9))
    remainder = total % 11
    check = digits[9]
    return check == remainder if remainder < 2 else check == 11 - remainder


def is_valid_legal_id(code: str) -> bool:
    """شناسه ملی ۱۱ رقمی اشخاص حقوقی."""
    code = normalize_digits(code)
    if len(code) != 11 or not code.isdigit():
        return False
    if int(code[3:9]) == 0:
        return False
    digits = [int(c) for c in code]
    decimal = digits[9] + 2
    total = sum((decimal + digits[i]) * _LEGAL_WEIGHTS[i] for i in range(10))
    remainder = total % 11
    if remainder == 10:
        remainder = 0
    return remainder == digits[10]


def _state_name(raw_state: str | None) -> str:
    if not raw_state:
        return ""
    return raw_state.split(":", 1)[-1]


def _expects_person_id(state_name: str) -> bool:
    return state_name.endswith(_PERSON_SUFFIXES)


def _expects_company_id(state_name: str) -> bool:
    return state_name.endswith(_COMPANY_SUFFIXES)


INVALID_NID_TEXT = (
    "⚠️ *کدملی وارد‌شده معتبر نیست.*\n\n"
    "رقم کنترل این کدملی با الگوی رسمی همخوانی ندارد؛ احتمالاً یک رقم اشتباه "
    "تایپ شده است. لطفاً کدملی را دوباره و با دقت وارد کنید:"
)
INVALID_LEGAL_ID_TEXT = (
    "⚠️ *شناسه ملی وارد‌شده معتبر نیست.*\n\n"
    "رقم کنترل این شناسه ملی با الگوی رسمی همخوانی ندارد؛ احتمالاً یک رقم "
    "اشتباه تایپ شده است. لطفاً شناسه ملی شرکت را دوباره وارد کنید:"
)


class IdValidationMiddleware(BaseMiddleware):
    """ورودی ۱۰/۱۱ رقمی با رقم کنترل غلط را قبل از رسیدن به هندلر رد می‌کند."""

    async def __call__(self, handler, event: types.Message, data: dict):
        if not isinstance(event, types.Message) or not event.text:
            return await handler(event, data)
        state_name = _state_name(data.get("raw_state"))
        if not state_name:
            return await handler(event, data)
        value = normalize_digits(event.text.strip())
        if not value.isdigit():
            return await handler(event, data)
        if _expects_person_id(state_name) and len(value) == 10 and not is_valid_national_id(value):
            await event.answer(INVALID_NID_TEXT)
            return None
        if _expects_company_id(state_name) and len(value) == 11 and not is_valid_legal_id(value):
            await event.answer(INVALID_LEGAL_ID_TEXT)
            return None
        return await handler(event, data)
