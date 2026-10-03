# -*- coding: utf-8 -*-
"""
PDF «راهنمای جامع ربات» — معرفی همهٔ امکانات ربات خدمات قضایی آنلاین.

طرح رسمی (قاب دوخطی + نوار سرمه‌ای و خط طلایی) هم‌خانوادهٔ گزارش ارزش منطقه‌ای
و خسارت تأخیر تأدیه؛ اجزای مشترک (فونت Vazirmatn، پاراگراف راست‌به‌چپ، کارت)
از ayani_pdf گرفته می‌شود.

این فایل فقط PDF را می‌سازد؛ ارسال به کاربران در guide_handlers.py است.
اعداد اشتراک (مبلغ/مدت/دفعات رایگان) هنگام ساخت از runtime_state خوانده
می‌شوند تا با تغییر تعرفه، راهنما هم به‌روز بماند.
"""
import io
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ayani_pdf import (
    CONTENT_W, MARGIN, PAGE_H, PAGE_W, PAL_CLASSIC, _FONTS, _box, _draw_ltr, _draw_rtl,
    _ensure_fonts, _footer_line, _p, _row,
)

logger = logging.getLogger(__name__)

GUIDE_FILENAME = "راهنمای ربات خدمات قضایی آنلاین.pdf"
SUPPORT_PHONE = "09306186888"
RULES_URL = "https://forms.gle/UeevWfg5YiDkC5F37"


def _subscription_numbers() -> tuple[int, int, int]:
    """(مبلغ اشتراک به تومان، مدت به روز، دفعات استفادهٔ رایگان)"""
    try:
        import runtime_state
        return (int(runtime_state.SUBSCRIPTION_FEE) // 10,
                int(runtime_state.SUBSCRIPTION_DURATION_DAYS),
                int(runtime_state.MAX_FREE_USAGE))
    except Exception:
        return 250_000, 30, 2


def _fa(n) -> str:
    return f"{n:,}"


# ══════════════════════════════════════════════════════════════════
# محتوا — هر بخش: (عنوان، توضیح کوتاه، [کارت‌ها])
# هر کارت: (عنوان، شرح، [نکات])
# ══════════════════════════════════════════════════════════════════
def _sections() -> list:
    sub_fee, sub_days, free_uses = _subscription_numbers()
    return [
        ("استعلام از سامانهٔ قضایی",
         "از منوی اصلی «استعلام» را بزنید. برای چند استعلام در یک پرداخت، «استعلام (چند مورد همزمان)» را انتخاب کنید.",
         [
             ("استعلام با کد رهگیری",
              "دریافت نسخهٔ چاپی سند ثبت‌شده در سامانه با کد رهگیری ۱۶ رقمی.",
              ["لایحه، اظهارنامه، شکواییه، دادخواست بدوی، دعاوی صلح، دعاوی اعتراضی، دعاوی طاری، "
               "شورای حل اختلاف و دیوان عدالت اداری",
               "امکان دریافت پیوست‌ها (منضمات) همراه با سند اصلی"]),
             ("استعلام با شماره همراه",
              "یافتن اشخاص ثبت‌شده در سامانهٔ ثنا که با یک شماره همراه ثبت‌نام کرده‌اند.",
              ["شماره را با ۰۹ وارد کنید"]),
             ("استعلام با کد ملی",
              "دریافت برگهٔ مشخصات ثبت‌نام شخص در سامانهٔ ثنا با کد ملی ده‌رقمی.",
              []),
             ("استعلام دسته‌جمعی با اکسل",
              "برای بیش از ۵ استعلام: فایل اکسل نمونه را دریافت، تکمیل و ارسال کنید تا همه در "
              "پس‌زمینه انجام شود.",
              ["از مسیر «استعلام (چند مورد همزمان)»"]),
         ]),
        ("ثبت لایحه، اظهارنامه و دادخواست",
         "ثبت در سامانه به نام شما انجام می‌شود و نسخهٔ نهایی برایتان ارسال می‌گردد.",
         [
             ("ثبت لایحه",
              "ثبت لایحه با انتخاب عنوان، وارد کردن اشخاص، متن و پیوست‌ها.",
              ["ثبت تکی یا ثبت دسته‌جمعی سریع با فایل اکسل (بیش از ۵ مورد)",
               "امضای الکترونیک طرفین با کد پیامکی"]),
             ("ثبت اظهارنامه",
              "ثبت اظهارنامه با مشخصات اظهارکننده، مخاطب، موضوع و متن.",
              ["ثبت تکی یا دسته‌جمعی با اکسل",
               "ثبت به وکالت با کد ملی وکیل"]),
             ("دعاوی اعتراضی",
              "تجدیدنظرخواهی، واخواهی، فرجام‌خواهی، اعادهٔ دادرسی مدنی و کیفری، اعتراض ثالث "
              "و اعتراض به قرار دادسرا.",
              []),
             ("ثبت دادخواست",
              "صدور اجرائیهٔ چک، مطالبهٔ وجه چک و سایر مطالبات، طلاق (توافقی، به درخواست زوجه "
              "یا زوج)، نفقه، الزام به تمکین، مهریه و انواع اعسار.",
              ["ثبت دسته‌جمعی چک‌ها با فایل اکسل",
               "انتخاب دادگاه حقوقی یا صلح برای دعاوی اعسار"]),
         ]),
        ("محاسبات و ابزارها",
         "نتیجهٔ محاسبات به‌صورت گزارش رسمی PDF ارسال می‌شود.",
         [
             ("محاسبهٔ تمبر",
              "محاسبهٔ تمبر مالیاتی وکیل برای دعاوی مالی (بر اساس مبلغ خواسته) و غیرمالی.",
              []),
             ("ارزش منطقه‌ای ملک",
              "استعلام ارزش معاملاتی ملک با انتخاب استان، شهرستان و نشانی، همراه با گزارش PDF.",
              []),
             ("خسارت تأخیر تأدیه و مهریه",
              "محاسبهٔ خسارت تأخیر تأدیه و مهریه به نرخ روز بر اساس شاخص رسمی بانک مرکزی.",
              []),
             ("ابزار فایل",
              "کاهش حجم عکس و تبدیل PDF چندصفحه‌ای به عکس (هر صفحه یک عکس) برای بارگذاری "
              "آسان در سامانه.",
              []),
         ]),
        ("حساب کاربری و پرداخت",
         "هزینهٔ هر خدمت پیش از پرداخت در فاکتور به شما نمایش داده می‌شود.",
         [
             ("کیف پول",
              "کیف پول خود را یک‌بار شارژ کنید و فاکتورهای بعدی را با یک دکمه از موجودی آن بپردازید.",
              ["مشاهدهٔ موجودی و تراکنش‌های اخیر"]),
             ("سوابق و فاکتورهای من",
              "مشاهدهٔ درخواست‌های اخیر و دریافت دوبارهٔ فایل‌هایی که قبلاً برایتان ارسال شده است.",
              []),
             ("اشتراک ماهانه",
              f"ابزار فایل، محاسبهٔ تمبر، خسارت تأخیر تأدیه و مهریه هرکدام {_fa(free_uses)} بار رایگان "
              f"است؛ پس از آن با اشتراک {_fa(sub_days)} روزه به مبلغ {_fa(sub_fee)} تومان، استفاده از "
              "همهٔ آن‌ها نامحدود می‌شود.",
              []),
             ("روش‌های پرداخت",
              "پرداخت آنلاین با فاکتور کیف پول بله، پرداخت از کیف پول ربات، یا کارت‌به‌کارت با "
              "ارسال رسید.",
              []),
         ]),
    ]


# چیدمان دکمه‌های منوی اصلی (keyboards.get_flow_type_kb) — راست، چپ
_MENU = [
    ("استعلام", "استعلام (چند مورد همزمان)"),
    ("ثبت لایحه", "ثبت اظهارنامه"),
    ("دعاوی اعتراضی", "ثبت دادخواست"),
    ("محاسبه تمبر", "ارزش منطقه‌ای"),
    ("ابزار فایل", "خسارت تأخیر و مهریه"),
    ("سوابق و فاکتورهای من", "کیف پول"),
]


def _tips() -> list:
    return [
        "پیش از هر چیز آیین‌نامهٔ استفاده را مطالعه و در ربات تأیید کنید.",
        "کد ملی و تاریخ تولد را دقیق وارد کنید؛ در صورت خطا، فرصت محدودی برای اصلاح داده می‌شود.",
        "اگر پس از پرداخت، سامانهٔ قضایی دچار اختلال شود، تا ۴۵ دقیقه می‌توانید بدون پرداخت "
        "دوباره تلاش کنید.",
        "در هر مرحله با دکمهٔ «شروع مجدد» به منوی اصلی برمی‌گردید.",
        "اگر بیش از یک ساعت کاری انجام ندهید، ربات به‌طور خودکار به منوی اصلی بازمی‌گردد.",
    ]


# ══════════════════════════════════════════════════════════════════
# چیدمان
# ══════════════════════════════════════════════════════════════════
def _elements(P) -> list:
    W = CONTENT_W - 4 * mm
    gap = 4 * mm
    card_w = (W - gap) / 2

    def section(num, title, lead):
        badge = Table([[_p(str(num), 11, colors.white, "bold", "center")]], colWidths=[8 * mm], rowHeights=[8 * mm])
        badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), P["accent"]),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        head = _row([badge, "", _p(title, 12.5, P["accent"], "bold")], [8 * mm, 3 * mm, W - 11 * mm], valign="MIDDLE")
        line = Table([[""]], colWidths=[W], rowHeights=[1.2 * mm])
        line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, P["gold"])]))
        out = [head, line, Spacer(1, 1.6 * mm)]
        if lead:
            out += [_p(lead, 8.6, P["muted"], leading=8.6 * 1.7), Spacer(1, 2.2 * mm)]
        return out

    def card(title, desc, notes):
        fl = [_p(title, 10.2, P["accent"], "bold"),
              _p(desc, 8.5, P["ink"], leading=8.5 * 1.75)]
        for n in notes:
            fl.append(_p(f"◂ {n}", 7.9, P["muted"], leading=7.9 * 1.7))
        return _box(fl, card_w, bg=P["soft"], border=P["line"], radius=5, pad=3.4 * mm)

    el = [Spacer(1, 1 * mm)]
    intro = _box([
        _p("کاربر گرامی، خوش آمدید", 11.5, P["accent"], "bold"),
        _p("ربات خدمات قضایی آنلاین، کارهای پرتکرار شما در سامانه‌های قضایی را بدون مراجعه "
           "حضوری انجام می‌دهد: استعلام، ثبت لایحه و اظهارنامه و دادخواست، امضای الکترونیک، "
           "محاسبات حقوقی و گزارش‌های رسمی PDF. در این راهنما همهٔ امکانات ربات و نحوهٔ "
           "استفاده از آن‌ها را می‌بینید.", 9, P["ink"], leading=9 * 1.85),
    ], W, bg=P["accent_soft"], border=P["accent"], radius=6, pad=4.5 * mm, border_w=0.8)
    el += [intro, Spacer(1, 6 * mm)]

    for i, (title, lead, cards) in enumerate(_sections(), 1):
        el.append(CondPageBreak(60 * mm))
        el += section(i, title, lead)
        for j in range(0, len(cards), 2):
            pair = [card(*c) for c in cards[j:j + 2]]
            if len(pair) == 1:
                pair.append(_p("", 1))
            el.append(_pair_row(pair, card_w, gap))
            el.append(Spacer(1, gap))
        el.append(Spacer(1, 3 * mm))

    n_sec = len(_sections())
    rows = []
    for a, b in _MENU:
        rows.append([_p(b, 9, P["accent"], "medium", "center"), "", _p(a, 9, P["accent"], "medium", "center")])
    mt = Table(rows, colWidths=[card_w, gap, card_w])
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm)]
    for r in range(len(rows)):
        for c in (0, 2):
            cmds += [("BACKGROUND", (c, r), (c, r), P["accent_soft"]), ("BOX", (c, r), (c, r), 0.6, P["line"])]
    mt.setStyle(TableStyle(cmds))
    el.append(CondPageBreak(70 * mm))
    el += section(n_sec + 1, "منوی اصلی ربات در یک نگاه",
                  "پس از تأیید آیین‌نامه، این دکمه‌ها را در منوی اصلی می‌بینید:")
    el += [mt, Spacer(1, 7 * mm)]

    tips = [_p(f"• {t}", 8.6, P["ink"], leading=8.6 * 1.75) for t in _tips()]
    el.append(KeepTogether(section(n_sec + 2, "نکات مهم", "") + [
        _box(tips, W, border=P["gold"], radius=5, pad=4 * mm, border_w=0.8)]))
    el.append(Spacer(1, 6 * mm))

    support = _box([
        _p("پشتیبانی", 10.5, colors.white, "bold"),
        _p(f"در صورت هرگونه پرسش یا مشکل، به شمارهٔ {SUPPORT_PHONE} در بله یا واتس‌اپ پیام دهید.",
           9, colors.white, leading=9 * 1.8),
        _row([_p("آیین‌نامهٔ استفاده:", 8.2, colors.HexColor("#E3C77E")),
              Paragraph(RULES_URL, ParagraphStyle("guide_url", fontName="Helvetica", fontSize=8.2,
                                                  leading=8.2 * 1.8, textColor=colors.HexColor("#E3C77E")))],
             [24 * mm, W - 24 * mm - 9 * mm]),
    ], W, bg=P["accent"], radius=6, pad=4.5 * mm)
    el.append(KeepTogether([support]))
    return el


def _pair_row(cells, card_w, gap):
    """دو کارت کنار هم (راست‌به‌چپ) با فاصلهٔ میانی."""
    t = Table([[cells[1], "", cells[0]]], colWidths=[card_w, gap, card_w])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _render(target, total_pages: int) -> int:
    _ensure_fonts()
    P = PAL_CLASSIC
    band1, band2 = 34 * mm, 16 * mm
    pages = {"n": 0}

    def frame(c, top_band):
        c.setStrokeColor(P["accent"]); c.setLineWidth(1.3)
        c.rect(8 * mm, 8 * mm, PAGE_W - 16 * mm, PAGE_H - 16 * mm)
        c.setStrokeColor(P["gold"]); c.setLineWidth(0.5)
        c.rect(9.6 * mm, 9.6 * mm, PAGE_W - 19.2 * mm, PAGE_H - 19.2 * mm)
        top = PAGE_H - 9.6 * mm
        c.setFillColor(P["accent"])
        c.rect(9.6 * mm, top - top_band, PAGE_W - 19.2 * mm, top_band, stroke=0, fill=1)
        c.setFillColor(P["gold"])
        c.rect(9.6 * mm, top - top_band - 1.1 * mm, PAGE_W - 19.2 * mm, 1.1 * mm, stroke=0, fill=1)
        return top

    def first(c, doc):
        pages["n"] = doc.page
        c.saveState()
        top = frame(c, band1)
        rx, lx = PAGE_W - MARGIN - 2 * mm, MARGIN + 2 * mm
        _draw_rtl(c, rx, top - 15 * mm, "راهنمای جامع ربات خدمات قضایی آنلاین", _FONTS["bold"], 19, colors.white)
        _draw_rtl(c, rx, top - 24 * mm, "معرفی امکانات و نحوهٔ استفاده", _FONTS["regular"], 10.5,
                  colors.HexColor("#C8D3E6"))
        _draw_ltr(c, lx, top - 15 * mm, "پیام‌رسان بله", _FONTS["regular"], 9, colors.HexColor("#E3C77E"))
        _footer_line(c, doc, P, y=13 * mm, total_pages=total_pages, text="ربات خدمات قضایی آنلاین")
        c.restoreState()

    def later(c, doc):
        pages["n"] = doc.page
        c.saveState()
        top = frame(c, band2)
        _draw_rtl(c, PAGE_W - MARGIN - 2 * mm, top - 10.5 * mm, "راهنمای جامع ربات خدمات قضایی آنلاین",
                  _FONTS["bold"], 11.5, colors.white)
        _footer_line(c, doc, P, y=13 * mm, total_pages=total_pages, text="ربات خدمات قضایی آنلاین")
        c.restoreState()

    doc = SimpleDocTemplate(target, pagesize=A4, title="راهنمای ربات خدمات قضایی آنلاین", author="",
                            leftMargin=MARGIN + 2 * mm, rightMargin=MARGIN + 2 * mm,
                            topMargin=9.6 * mm + band2 + 6 * mm, bottomMargin=22 * mm)
    el = [Spacer(1, band1 - band2)] + _elements(P)
    doc.build(el, onFirstPage=first, onLaterPages=later)
    return pages["n"]


def build_guide_pdf(output_path: str) -> bool:
    """ساخت PDF راهنما؛ True در صورت موفقیت."""
    try:
        total = _render(io.BytesIO(), 1)          # دور اول: شمارش صفحات
        _render(output_path, total)
        return True
    except Exception as e:
        logger.error(f"[GUIDE-PDF] خطا در ساخت PDF راهنما: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "guide_sample.pdf"
    print("OK" if build_guide_pdf(out) else "FAILED", out)
