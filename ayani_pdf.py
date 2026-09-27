# -*- coding: utf-8 -*-
"""
PDF گزارش ارزش منطقه‌ای (عرصه + اعیانی) — دو صفحه، مینیمال.

  صفحهٔ ۱: مشخصات ملک و ورودی‌ها + سه مبلغ (عرصه، اعیانی، کل)
  صفحهٔ ۲: نحوهٔ محاسبه (گام‌به‌گام) + ضوابط اعمال‌شده

فونت: Vazirmatn (نسخهٔ ارقام فارسی، مجوز OFL) از پوشهٔ fonts/ پروژه؛
اگر نبود، به فونت‌های ویندوز (Tahoma) برمی‌گردد.
"""

import logging
import os
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

import ayani_calc as ac

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_HERE, "fonts")

# ═══ پالت ═══
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
SOFT = colors.HexColor("#F5F7F9")
ACCENT = colors.HexColor("#16324F")
ACCENT_SOFT = colors.HexColor("#E8EEF4")
NEG = colors.HexColor("#9B2C2C")

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

_FONTS = {"regular": "Helvetica", "bold": "Helvetica-Bold"}
_fonts_ready = False


def _ensure_fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    candidates = [
        ("AyaniRegular", os.path.join(_FONT_DIR, "Vazirmatn-FD-Regular.ttf"), "regular"),
        ("AyaniBold", os.path.join(_FONT_DIR, "Vazirmatn-FD-Bold.ttf"), "bold"),
        ("AyaniMedium", os.path.join(_FONT_DIR, "Vazirmatn-FD-Medium.ttf"), "medium"),
    ]
    fallbacks = {
        "regular": ["C:\\Windows\\Fonts\\tahoma.ttf"],
        "bold": ["C:\\Windows\\Fonts\\tahomabd.ttf", "C:\\Windows\\Fonts\\tahoma.ttf"],
        "medium": ["C:\\Windows\\Fonts\\tahoma.ttf"],
    }
    for name, path, role in candidates:
        paths = [path] + fallbacks[role]
        for p in paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont(name, p))
                    _FONTS[role] = name
                    break
                except Exception as e:
                    logger.warning(f"[AYANI-PDF] ثبت فونت {p} ناموفق: {e}")
    _FONTS.setdefault("medium", _FONTS["bold"])
    _fonts_ready = True


def _bidi(text: str) -> str:
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except ImportError:
        logger.warning("[AYANI-PDF] arabic_reshaper/python-bidi نصب نیست")
        return str(text)


_style_cache = {}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class RTLParagraph(Paragraph):
    """
    پاراگراف فارسی با شکست خط صحیح: متن منطقی ابتدا بر اساس عرض ستون به
    خطوط شکسته می‌شود و سپس الگوریتم BiDi روی هر خط جداگانه اعمال می‌شود
    (اگر BiDi روی کل متن اعمال شود، ترتیب خطوطِ متن چندخطی برعکس می‌شود).
    """

    def __init__(self, text, style):
        self._logical = str(text)
        super().__init__(_esc(_bidi(self._logical)), style)

    def wrap(self, availWidth, availHeight):
        st = self.style
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            words = arabic_reshaper.reshape(self._logical).split()
            space = pdfmetrics.stringWidth(" ", st.fontName, st.fontSize)
            lines, cur, cur_w = [], [], 0.0
            for w in words:
                ww = pdfmetrics.stringWidth(w, st.fontName, st.fontSize)
                if cur and cur_w + space + ww > availWidth - 1:
                    lines.append(" ".join(cur))
                    cur, cur_w = [w], ww
                else:
                    cur_w += (space if cur else 0) + ww
                    cur.append(w)
            if cur:
                lines.append(" ".join(cur))
            visual = "<br/>".join(_esc(get_display(ln, base_dir="R")) for ln in lines)
            self.__init_text(visual)
        except ImportError:
            pass
        return super().wrap(availWidth, availHeight)

    def __init_text(self, visual):
        Paragraph.__init__(self, visual, self.style)


def _p(text, size=9.5, color=INK, weight="regular", align="right", leading=None) -> Paragraph:
    key = (size, color.hexval(), weight, align, leading)
    st = _style_cache.get(key)
    if st is None:
        st = ParagraphStyle(
            name=f"ay{len(_style_cache)}",
            fontName=_FONTS.get(weight, _FONTS["regular"]),
            fontSize=size, leading=leading or size * 1.55, textColor=color,
            alignment={"right": 2, "center": 1, "left": 0}[align],
        )
        _style_cache[key] = st
    text = re.sub(r"(?<=\d),(?=\d)", "٬", str(text))
    text = re.sub(r"(?<=\d)\.(?=\d)", "٫", text)
    return RTLParagraph(text, st)


def _money(n: int) -> str:
    s = f"{abs(int(n)):,}".replace(",", "٬")
    return f"({s})" if n < 0 else s


def _floor_label(f) -> str:
    if f is None:
        return "—"
    f = int(f)
    if f == 0:
        return "همکف"
    return f"زیرزمین {_num(abs(f))}" if f < 0 else _num(f)


def _num(x) -> str:
    return ac.fmt(x).replace(",", "٬").replace(".", "٫")


# ═══ عدد به حروف ═══
_ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TENS = ["", "ده", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "هزار میلیارد", "میلیون میلیارد"]


def _three(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if 10 <= r < 20:
        parts.append(_TEENS[r - 10])
    else:
        t, o = divmod(r, 10)
        if t:
            parts.append(_TENS[t])
        if o:
            parts.append(_ONES[o])
    return " و ".join(parts)


def num_to_words(n: int) -> str:
    n = int(n)
    if n == 0:
        return "صفر"
    groups, i = [], 0
    while n > 0:
        n, g = divmod(n, 1000)
        if g:
            groups.append((_three(g) + (" " + _SCALES[i] if _SCALES[i] else "")).strip())
        i += 1
    return " و ".join(reversed(groups))


# ═══ اجزای صفحه ═══
def _rule(width=CONTENT_W, color=LINE, thickness=0.6, space=3 * mm):
    t = Table([[""]], colWidths=[width], rowHeights=[0.1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), thickness, color),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [Spacer(1, space), t, Spacer(1, space)]


def _header(title, subtitle, date_text):
    t = Table(
        [[_p(date_text, 8.5, MUTED, align="left"), _p(title, 16, ACCENT, "bold")],
         [_p("", 1), _p(subtitle, 9, MUTED)]],
        colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.65],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return [t] + _rule(color=ACCENT, thickness=1.4, space=2.5 * mm)


def _section_title(text):
    return [_p(text, 10.5, ACCENT, "bold"), Spacer(1, 1.5 * mm)]


def _kv_grid(pairs, cols=2):
    """جدول برچسب/مقدار راست‌به‌چپ؛ pairs: [(label, value, full_width?)]"""
    rows, style = [], [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6 * mm),
    ]
    label_w, val_w = CONTENT_W * 0.17, CONTENT_W * 0.33
    buf = []

    def flush():
        cells = []
        for lab, val in reversed(buf):
            cells += [_p(val, 9.5, INK, "medium"), _p(lab, 8.5, MUTED)]
        while len(cells) < 4:
            cells = [_p("", 1), _p("", 1)] + cells
        rows.append(cells)
        buf.clear()

    for item in pairs:
        lab, val = item[0], item[1]
        full = len(item) > 2 and item[2]
        if full:
            if buf:
                flush()
            rows.append([_p(val, 9.5, INK, "medium"), "", "", _p(lab, 8.5, MUTED)])
            style.append(("SPAN", (0, len(rows) - 1), (2, len(rows) - 1)))
            continue
        buf.append((lab, val))
        if len(buf) == cols:
            flush()
    if buf:
        flush()

    for i in range(len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    style.append(("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE))
    t = Table(rows, colWidths=[val_w, label_w, val_w, label_w])
    t.setStyle(TableStyle(style))
    return t


def _amount_tiles(land_value, building_value, total):
    def tile(label, value, dark=False):
        fg = colors.white if dark else INK
        sub = colors.HexColor("#C9D6E3") if dark else MUTED
        return [
            _p(label, 8.5, sub, align="center"),
            _p(_money(value), 15 if dark else 13, fg, "bold", align="center"),
            _p("ریال", 8, sub, align="center"),
        ]

    gap = 3 * mm
    w_small = (CONTENT_W - 2 * gap) * 0.3
    w_big = CONTENT_W - 2 * gap - 2 * w_small
    cells = [tile("ارزش منطقه‌ای کل", total, True), tile("ارزش اعیانی", building_value),
             tile("ارزش عرصه", land_value)]
    inner = []
    for c in cells:
        t = Table([[x] for x in c])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0.6 * mm),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6 * mm)]))
        inner.append(t)
    t = Table([[inner[0], "", inner[1], "", inner[2]]],
              colWidths=[w_big, gap, w_small, gap, w_small], rowHeights=[24 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, 0), ACCENT),
        ("BACKGROUND", (2, 0), (2, 0), ACCENT_SOFT),
        ("BACKGROUND", (4, 0), (4, 0), ACCENT_SOFT),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    words = _p(f"به حروف: {num_to_words(total)} ریال", 8.5, MUTED, align="right")
    return [t, Spacer(1, 2 * mm), words]


def _steps_table(steps):
    head = [_p("مبلغ (ریال)", 8.5, MUTED, "bold", "left"), _p("محاسبه", 8.5, MUTED, "bold"),
            _p("شرح", 8.5, MUTED, "bold"), _p("#", 8.5, MUTED, "bold", "center")]
    rows = [head]
    for i, (title, formula, amount) in enumerate(steps, 1):
        is_total = i == len(steps)
        amt = "" if amount is None else _money(amount)
        color = NEG if (amount is not None and amount < 0) else INK
        rows.append([
            _p(amt, 10 if is_total else 9.5, color, "bold" if is_total else "medium", "left"),
            _p(formula, 8.5, MUTED),
            _p(title, 9.5 if not is_total else 10, INK, "bold" if is_total else "regular"),
            _p(str(i), 8.5, MUTED, align="center"),
        ])
    t = Table(rows, colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.47, CONTENT_W * 0.25, CONTENT_W * 0.06],
              repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BACKGROUND", (0, -1), (-1, -1), ACCENT_SOFT),
    ]
    t.setStyle(TableStyle(style))
    return t


def _bullets(lines):
    out = []
    for ln in lines:
        out.append(_p(f"• {ln}", 8.5, INK, leading=13.5))
    return out


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
    canvas.setFont(_FONTS["regular"], 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, _bidi(
        "این گزارش بر اساس استعلام از سامانهٔ سازمان امور مالیاتی و جدول ارزش معاملاتی اعیانی تهیه شده و جنبهٔ اطلاع‌رسانی دارد."))
    canvas.drawString(MARGIN, 9 * mm, _bidi(f"صفحهٔ {doc.page} از ۲"))
    canvas.restoreState()


# ═══ ساخت PDF ═══
def build_ayani_pdf(output_path: str, *, province: str, county: str, address: str,
                    tax_result: dict, result: dict, date_text: str = None, time_text: str = None) -> bool:
    """
    result: خروجی ayani_calc.compute_all
    tax_result: خروجی سامانهٔ مالیاتی (برای شماره بلوک/ردیف و اداره)
    """
    _ensure_fonts()
    try:
        from regional_value_pdf import _get_persian_date, _get_persian_time
        date_text = date_text or _get_persian_date()
        time_text = time_text or _get_persian_time()
    except Exception:
        date_text = date_text or ""
        time_text = time_text or ""

    land, b = result["land"], result["building"]
    structured = (tax_result or {}).get("فیلدهای_ساختاریافته", {}) or {}
    year = (tax_result or {}).get("سال", "1405")

    def tax_field(k):
        v = structured.get(k)
        return str(v).strip() if v else "—"

    el = []
    # ─────────────── صفحهٔ ۱ ───────────────
    el += _header("گزارش ارزش منطقه‌ای ملک", f"عرصه و اعیانی — سال {year}",
                  f"{date_text}   ساعت {time_text}".strip())

    el += _section_title("مشخصات ملک")
    el.append(_kv_grid([
        ("استان", province), ("شهرستان", county),
        ("آدرس", address or "—", True),
        ("شماره بلوک", tax_field("شماره بلوک بر اساس دفترچه ارزش معاملاتی ملک")),
        ("شماره ردیف", tax_field("شماره ردیف بر اساس دفترچه ارزش معاملاتی ملک")),
        ("اداره کل امور مالیاتی", tax_field("اداره کل امور مالیاتی"), True),
    ]))
    el.append(Spacer(1, 5 * mm))

    el += _section_title("عرصه")
    land_pairs = [("متراژ عرصه", f"{_num(land['area'])} متر مربع"),
                  ("کاربری", land["land_use"] if land["land_use"] != "سایر" else "سایر")]
    if land["land_use"] == "سایر":
        land_pairs.append(("نوع کاربری", land["land_use_title"], True))
        land_pairs.append(("ضریب تعدیل", _num(land["coef"])))
    land_pairs.append(("ارزش هر متر", f"{_money(land['unit_value'])} ریال"))
    el.append(_kv_grid(land_pairs))
    el.append(Spacer(1, 5 * mm))

    el += _section_title("اعیانی")
    bp = [("کاربری", b["use_title"] if b["use_key"] in ac.BUILDING_MAIN_KEYS else "سایر"),
          ("نوع سازه", b["structure_title"])]
    if b["use_key"] not in ac.BUILDING_MAIN_KEYS:
        bp.append(("نوع کاربری", b["use_title"], True))
    bp += [("متراژ اعیانی", f"{_num(b['area'])} متر مربع"),
           ("نرخ هر متر", f"{_money(b['rate'])} ریال")]
    if not b["complete"]:
        bp.append(("وضعیت ساختمان", f"ناتمام — مرحلهٔ {b['stage_title']}"))
    else:
        bp += [("وضعیت ساختمان", "تکمیل‌شده"),
               ("پارکینگ و انباری", f"{_num(b['parking_area'])} متر مربع" if b["parking_area"] > 0 else "ندارد"),
               ("طبقه", _floor_label(b["floor"])),
               ("قدمت", f"{_num(b['age'])} سال")]
    el.append(_kv_grid(bp))
    el.append(Spacer(1, 7 * mm))

    el += _amount_tiles(land["value"], b["value"], result["total"])

    # ─────────────── صفحهٔ ۲ ───────────────
    el.append(PageBreak())
    el += _header("نحوهٔ محاسبه", f"{province} — {county}", f"{date_text}".strip())
    el.append(_steps_table(ac.explain_steps(result)))
    el.append(Spacer(1, 7 * mm))

    el += _section_title("ضوابط اعمال‌شده")
    rules = [
        "ارزش عرصه از سامانهٔ سازمان امور مالیاتی (ارزش معاملاتی هر متر مربع) × متراژ عرصه محاسبه شده است.",
    ]
    if land["land_use"] == "سایر":
        rules.append(f"برای کاربری‌های «سایر»، ارزش عرصه بر مبنای ارزش معاملاتی {land['base_use']} × ضریب تعدیل "
                     f"{_num(land['coef'])} محاسبه می‌شود (ضرایب: ۰٫۷، ۰٫۵، ۰٫۴، ۰٫۲، ۰٫۱).")
    rules.append("نرخ هر متر مربع اعیانی از جدول ارزش معاملاتی ساختمان به تفکیک شهرستان، کاربری و نوع سازه (به ریال) است.")
    if not b["complete"]:
        rules.append("برای ساختمان ناتمام، ارزش اعیانی به نسبت مرحلهٔ ساخت منظور می‌شود: "
                     "فونداسیون ۱۰٪، اسکلت ۳۰٪، سفت‌کاری ۵۰٪ و نازک‌کاری ۸۰٪.")
    else:
        rules += [
            "مسکونی و اداری بیش از پنج طبقه (بدون احتساب زیرزمین و پیلوت): از طبقهٔ ششم به بالا به ازای هر طبقه ۱٫۵٪ به نرخ هر متر افزوده می‌شود.",
            "تجاری: به ازای هر طبقه بالاتر یا پایین‌تر از همکف ۱۰٪ و حداکثر ۳۰٪ از نرخ هر متر کسر می‌شود.",
            "پارکینگ و انباری متعلق به واحد معادل ۵۰٪ نرخ هر متر مربع ساختمان محاسبه می‌شود.",
            "به ازای هر سال قدمت تا سقف ۲۰ سال، ۲٪ (حداکثر ۴۰٪) از کل ارزش اعیانی کسر می‌شود.",
        ]
    rules.append("ارزش منطقه‌ای کل = ارزش عرصه + ارزش اعیانی.")
    el += _bullets(rules)

    try:
        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=14 * mm, bottomMargin=18 * mm,
            title="گزارش ارزش منطقه‌ای ملک", author="",
        )
        doc.build(el, onFirstPage=_footer, onLaterPages=_footer)
        return True
    except Exception as e:
        logger.error(f"[AYANI-PDF] خطا در ساخت PDF: {e}", exc_info=True)
        return False
