"""
محاسبه تمبر مالیاتی و حق‌الوکاله برای دعاوی مالی
بر اساس آیین‌نامه تعرفه حق‌الوکاله (ماده ۹) و ماده ۱۰۳ ق.م.م.
"""
from decimal import Decimal, ROUND_HALF_UP


def calculate_stamp_duty(claim_amount: int) -> dict:
    """
    محاسبه تمبر دادگستری و حق‌الوکاله برای دعاوی مالی معمولی

    Args:
        claim_amount: بهای خواسته به ریال (عدد صحیح)

    Returns:
        dict شامل ۶ مقدار: تمبر کلی، تمبر بدوی، تمبر تجدیدنظر،
        حق‌الوکاله کلی، حق‌الوکاله بدوی، حق‌الوکاله تجدیدنظر
        (همه به ریال، به عدد صحیح گرد شده)
    """
    if claim_amount is None or claim_amount <= 0:
        raise ValueError("بهای خواسته باید عددی مثبت باشد")

    amount = Decimal(str(claim_amount))

    # پله‌های تعرفه حق‌الوکاله (ماده ۹ آیین‌نامه تعرفه حق‌الوکاله)
    TIERS = [
        (Decimal("500000000"), Decimal("0.08")),    # تا ۵۰۰ میلیون ریال: ۸٪
        (Decimal("2000000000"), Decimal("0.07")),   # مازاد تا ۲ میلیارد ریال: ۷٪
        (Decimal("10000000000"), Decimal("0.05")),  # مازاد تا ۱۰ میلیارد ریال: ۵٪
        (Decimal("30000000000"), Decimal("0.04")),  # مازاد تا ۳۰ میلیارد ریال: ۴٪
    ]

    haghalvekaleh_kolli = Decimal("0")
    remaining = amount
    lower_bound = Decimal("0")

    for upper_bound, rate in TIERS:
        if remaining <= 0:
            break
        tier_span = upper_bound - lower_bound
        tier_amount = min(remaining, tier_span)
        haghalvekaleh_kolli += tier_amount * rate
        remaining -= tier_amount
        lower_bound = upper_bound

    if remaining > 0:
        raise ValueError(
            "بهای خواسته بیش از سقف تعرفه (۳۰ میلیارد ریال) است؛ "
            "نیاز به بررسی جداگانه دارد"
        )

    # تقسیم بین مرحله بدوی (۶۰٪) و تجدیدنظر (۴۰٪)
    haghalvekaleh_bedvi = haghalvekaleh_kolli * Decimal("0.6")
    haghalvekaleh_tajdidnazar = haghalvekaleh_kolli * Decimal("0.4")

    # تمبر مالیاتی = ۵٪ حق‌الوکاله هر مرحله — ماده ۱۰۳ ق.م.م
    tamber_bedvi = haghalvekaleh_bedvi * Decimal("0.05")
    tamber_tajdidnazar = haghalvekaleh_tajdidnazar * Decimal("0.05")
    tamber_kolli = tamber_bedvi + tamber_tajdidnazar

    def r(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return {
        "tamber_kolli": r(tamber_kolli),
        "tamber_bedvi": r(tamber_bedvi),
        "tamber_tajdidnazar": r(tamber_tajdidnazar),
        "haghalvekaleh_kolli": r(haghalvekaleh_kolli),
        "haghalvekaleh_bedvi": r(haghalvekaleh_bedvi),
        "haghalvekaleh_tajdidnazar": r(haghalvekaleh_tajdidnazar),
    }


def format_result_fa(claim_amount: int, result: dict) -> str:
    """قالب‌بندی خروجی به فارسی برای ارسال در ربات بله"""

    def fmt(n: int) -> str:
        return f"{n:,}"

    return (
        f"📄 محاسبه برای بهای خواسته: *{fmt(claim_amount)} ریال*\n\n"
        f"🔹 تمبر کلی: *{fmt(result['tamber_kolli'])} ریال*\n"
        f"🔹 تمبر بدوی: *{fmt(result['tamber_bedvi'])} ریال*\n"
        f"🔹 تمبر تجدیدنظر: *{fmt(result['tamber_tajdidnazar'])} ریال*\n\n"
        f"🔸 حق‌الوکاله کلی: *{fmt(result['haghalvekaleh_kolli'])} ریال*\n"
        f"🔸 حق‌الوکاله بدوی: *{fmt(result['haghalvekaleh_bedvi'])} ریال*\n"
        f"🔸 حق‌الوکاله تجدیدنظر: *{fmt(result['haghalvekaleh_tajdidnazar'])} ریال*"
    )
