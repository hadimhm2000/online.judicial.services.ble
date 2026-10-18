"""
تبدیل فایل Word (.docx) به HTML با حفظ فرمت (بولد، ایتالیک، آندرلاین، ترازبندی و ...).

کاربرد: کاربر می‌تواند به‌جای تایپ متن، فایل ورد را ارسال کند.
متن استخراج‌شده عیناً با فرمت اصلی در ادیتور سامانه قضایی وارد می‌شود.

⚠️ اصلاحیهٔ مهم:
قبلاً `from docx import Document` در سطح ماژول بود؛ اگر بستهٔ python-docx
نصب نبود، کل ماژول (و همهٔ هندلرهایی که آن را import می‌کردند) با خطای:
    ModuleNotFoundError: No module named 'docx'
کرش می‌کرد — نتیجه: ربات به فایل ورد «هیچ واکنشی نشان نمی‌داد» و وارد
مرحلهٔ بعد نمی‌شد (گزارش کارفرما).

حالا سند کاملاً با stdlib (zipfile + xml.etree) پارس می‌شود و به
python-docx وابسته نیست؛ یعنی docx_to_html / docx_to_plain_text همیشه
کار می‌کنند.
"""

import os
import logging
from config import temp_path

logger = logging.getLogger(__name__)

# حداکثر حجم مجاز فایل ورد (بایت)
MAX_DOCX_SIZE = 10 * 1024 * 1024  # 10 MB

# ═════════════════════════════════════════════════════════════════════════════
# پارسر XML (stdlib) — همیشه استفاده می‌شود
#
# ⚠️ اصلاحیه (حفظ عینِ قالب ورد):
# python-docx فقط فرمت «مستقیم» هر run را می‌خواند (run.bold فقط w:b)؛ در
# نتیجه این موارد در سامانه بی‌قالب درج می‌شدند:
#   • بولد/ایتالیک متن فارسی که ورد آن را با w:bCs / w:iCs ذخیره می‌کند
#   • قالبی که از استایل (Character/Paragraph style) به ارث رسیده
#   • خط‌خوردهٔ دوتایی (w:dstrike)، و w:b w:val="0" که اشتباهاً بولد می‌شد
#   • متن داخل لینک (w:hyperlink)، تغییرات ردیابی‌شده (w:ins)، کنترل‌های
#     محتوا (w:sdt) و جدول‌ها که کلاً حذف می‌شدند
#   • شکست خط (Shift+Enter) که به فاصله تبدیل می‌شد
# حالا سند مستقیم از XML با در نظر گرفتن استایل‌ها خوانده می‌شود.
# ═════════════════════════════════════════════════════════════════════════════
import html as html_lib
import zipfile
import xml.etree.ElementTree as ET

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_NS

# ویژگی‌های toggle که بررسی می‌شوند → نام داخلی
_TOGGLE_TAGS = {
    "b": "bold", "bCs": "bold_cs",
    "i": "italic", "iCs": "italic_cs",
    "strike": "strike", "dstrike": "dstrike",
}


def _on_off(el) -> bool:
    """مقدار یک عنصر on/off ورد (w:b, w:i, ...)؛ بدون w:val یعنی روشن."""
    val = el.get(_W + "val")
    if val is None:
        return True
    return val.strip().lower() not in ("0", "false", "off", "none")


def _read_rpr(rPr) -> dict:
    """ویژگی‌های قالب یک w:rPr را (فقط آن‌هایی که صریحاً تعیین شده‌اند)
    برمی‌گرداند."""
    props = {}
    if rPr is None:
        return props
    for tag, name in _TOGGLE_TAGS.items():
        el = rPr.find(_W + tag)
        if el is not None:
            props[name] = _on_off(el)
    u = rPr.find(_W + "u")
    if u is not None:
        props["underline"] = (u.get(_W + "val") or "single").lower() != "none"
    sz = rPr.find(_W + "sz")
    if sz is None:
        sz = rPr.find(_W + "szCs")
    if sz is not None:
        v = sz.get(_W + "val") or ""
        if v.isdigit():
            props["size_half_pt"] = int(v)
    color = rPr.find(_W + "color")
    if color is not None:
        v = (color.get(_W + "val") or "").strip()
        if len(v) == 6 and v.lower() not in ("auto", "000000"):
            props["color"] = v
    vert = rPr.find(_W + "vertAlign")
    if vert is not None:
        v = (vert.get(_W + "val") or "").lower()
        if v in ("superscript", "subscript"):
            props["vert"] = v
    return props


class _Styles:
    """استایل‌های سند (word/styles.xml) با زنجیرهٔ basedOn."""

    def __init__(self, xml_bytes):
        self._styles = {}
        self.defaults = {}
        self.default_para_style = None
        if not xml_bytes:
            return
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return
        dd = root.find(_W + "docDefaults")
        if dd is not None:
            rpr_default = dd.find(_W + "rPrDefault")
            if rpr_default is not None:
                self.defaults = _read_rpr(rpr_default.find(_W + "rPr"))
        for st in root.findall(_W + "style"):
            sid = st.get(_W + "styleId")
            if not sid:
                continue
            based = st.find(_W + "basedOn")
            pPr = st.find(_W + "pPr")
            jc = pPr.find(_W + "jc") if pPr is not None else None
            self._styles[sid] = {
                "based_on": based.get(_W + "val") if based is not None else None,
                "rpr": _read_rpr(st.find(_W + "rPr")),
                "jc": jc.get(_W + "val") if jc is not None else None,
            }
            if (st.get(_W + "type") == "paragraph"
                    and _on_off_attr(st.get(_W + "default"))):
                self.default_para_style = sid

    def rpr_chain(self, style_id) -> dict:
        """ویژگی‌های run یک استایل با احتساب basedOn (فرزند بر والد مقدم است)."""
        chain, seen = [], set()
        while style_id and style_id in self._styles and style_id not in seen:
            seen.add(style_id)
            chain.append(self._styles[style_id])
            style_id = self._styles[style_id]["based_on"]
        merged = {}
        for st in reversed(chain):
            merged.update(st["rpr"])
        return merged

    def jc_chain(self, style_id):
        seen = set()
        while style_id and style_id in self._styles and style_id not in seen:
            seen.add(style_id)
            if self._styles[style_id]["jc"]:
                return self._styles[style_id]["jc"]
            style_id = self._styles[style_id]["based_on"]
        return None


def _on_off_attr(val) -> bool:
    return bool(val) and val.strip().lower() in ("1", "true", "on")


class _Run:
    def __init__(self, text: str, props: dict):
        self.text = text
        self.bold = bool(props.get("bold") or props.get("bold_cs"))
        self.italic = bool(props.get("italic") or props.get("italic_cs"))
        self.underline = bool(props.get("underline"))
        self.strike = bool(props.get("strike") or props.get("dstrike"))
        self.size_half_pt = props.get("direct_size_half_pt")
        self.color = props.get("color")
        self.vert = props.get("vert")


class _Paragraph:
    def __init__(self, runs, alignment):
        self.runs = runs
        self.alignment = alignment

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


def _run_text(r) -> str:
    """متن یک w:r — w:t، تب و شکست خط حفظ می‌شوند."""
    parts = []
    for child in r:
        tag = child.tag
        if tag == _W + "t":
            parts.append(child.text or "")
        elif tag == _W + "tab":
            parts.append("\t")
        elif tag in (_W + "br", _W + "cr"):
            parts.append("\n")
        elif tag == _W + "noBreakHyphen":
            parts.append("-")
    return "".join(parts)


# عناصری که run‌های داخلشان جزء متن پاراگراف است
_RUN_CONTAINERS = {
    _W + "hyperlink", _W + "ins", _W + "smartTag", _W + "customXml",
    _W + "fldSimple", _W + "bdo", _W + "dir", _W + "moveTo",
}


def _iter_runs(container):
    """همهٔ w:r های یک پاراگراف به ترتیب سند (شامل لینک/ins/sdt)."""
    for child in container:
        tag = child.tag
        if tag == _W + "r":
            yield child
        elif tag in _RUN_CONTAINERS:
            yield from _iter_runs(child)
        elif tag == _W + "sdt":
            content = child.find(_W + "sdtContent")
            if content is not None:
                yield from _iter_runs(content)
        # w:del / w:moveFrom (متن حذف‌شده) عمداً نادیده گرفته می‌شود


def _parse_paragraph(p, styles: _Styles) -> _Paragraph:
    pPr = p.find(_W + "pPr")
    p_style = None
    alignment = None
    if pPr is not None:
        ps = pPr.find(_W + "pStyle")
        if ps is not None:
            p_style = ps.get(_W + "val")
        jc = pPr.find(_W + "jc")
        if jc is not None:
            alignment = jc.get(_W + "val")
    if p_style is None:
        p_style = styles.default_para_style
    if alignment is None:
        alignment = styles.jc_chain(p_style)

    base = dict(styles.defaults)
    base.pop("size_half_pt", None)
    base.update(styles.rpr_chain(p_style))
    base.pop("size_half_pt", None)

    runs = []
    for r in _iter_runs(p):
        text = _run_text(r)
        if not text:
            continue
        rPr = r.find(_W + "rPr")
        props = dict(base)
        if rPr is not None:
            rs = rPr.find(_W + "rStyle")
            if rs is not None:
                char_props = styles.rpr_chain(rs.get(_W + "val"))
                char_props.pop("size_half_pt", None)
                props.update(char_props)
        direct = _read_rpr(rPr)
        # اندازهٔ فونت فقط وقتی صریحاً روی run تعیین شده (مثل قبل)
        if "size_half_pt" in direct:
            props["direct_size_half_pt"] = direct.pop("size_half_pt")
        props.update(direct)
        runs.append(_Run(text, props))
    return _Paragraph(runs, alignment)


def _iter_block_paragraphs(container):
    """پاراگراف‌های بدنه به ترتیب سند — شامل پاراگراف‌های داخل جدول و sdt."""
    for child in container:
        tag = child.tag
        if tag == _W + "p":
            yield child
        elif tag == _W + "tbl":
            for tr in child.findall(_W + "tr"):
                for tc in tr.findall(_W + "tc"):
                    yield from _iter_block_paragraphs(tc)
        elif tag == _W + "sdt":
            content = child.find(_W + "sdtContent")
            if content is not None:
                yield from _iter_block_paragraphs(content)
        elif tag in (_W + "customXml", _W + "ins"):
            yield from _iter_block_paragraphs(child)


def _open_docx_document(filepath: str):
    """باز کردن .docx و برگرداندن لیست پاراگراف‌ها (با قالب نهایی هر run)."""
    with zipfile.ZipFile(filepath) as z:
        xml_bytes = z.read("word/document.xml")
        try:
            styles_bytes = z.read("word/styles.xml")
        except KeyError:
            styles_bytes = None
    styles = _Styles(styles_bytes)
    root = ET.fromstring(xml_bytes)
    body = root.find(_W + "body")
    if body is None:
        body = root
    return [_parse_paragraph(p, styles) for p in _iter_block_paragraphs(body)]


# ═════════════════════════════════════════════════════════════════════════════
# تبدیل به HTML
# ═════════════════════════════════════════════════════════════════════════════
def _align_to_css(alignment) -> str:
    """تبدیل ترازبندی ورد (right/center/left/both/start/end) به استایل CSS."""
    if alignment is None:
        return "text-align: right;"  # پیش‌فرض: راست‌چین
    val = str(alignment).strip().upper()
    if "RIGHT" in val or val == "END":
        return "text-align: right;"
    if "CENTER" in val:
        return "text-align: center;"
    if "LEFT" in val or val == "START":
        return "text-align: left;"
    if "JUSTIFY" in val or val in ("BOTH", "DISTRIBUTE"):
        return "text-align: justify;"
    return "text-align: right;"  # پیش‌فرض: راست‌چین


def _run_to_html(run) -> str:
    """
    یک Run ورد را به HTML تبدیل می‌کند.
    بولد، ایتالیک، آندرلاین، خط‌خورده، رنگ، بالانویس/زیرنویس و اندازه فونت حفظ می‌شوند.
    """
    text = run.text or ""
    if not text:
        return ""

    text = html_lib.escape(text, quote=False)

    # حفظ فاصله‌های ابتدای خط
    if text.startswith(" "):
        leading = len(text) - len(text.lstrip(" "))
        text = (" " * leading) + text[leading:]
    text = text.replace("  ", "  ")
    text = text.replace("\t", " " * 4)
    text = text.replace("\n", "<br>")

    tags = []
    if run.bold:
        tags.append("b")
    if run.italic:
        tags.append("i")
    if run.underline:
        tags.append("u")
    if run.strike:
        tags.append("s")
    if run.vert == "superscript":
        tags.append("sup")
    elif run.vert == "subscript":
        tags.append("sub")

    for tag in tags:
        text = f"<{tag}>{text}</{tag}>"

    styles = []
    if run.color:
        styles.append(f"color: #{run.color};")
    if run.size_half_pt:
        # ورد اندازه را در half-points ذخیره می‌کند (1 pt = 2 half-pts)
        size_pt = run.size_half_pt / 2.0
        if size_pt != 12:  # 12pt پیش‌فرض است
            styles.append(f"font-size: {size_pt:g}pt;")
    if styles:
        text = f'<span style="{" ".join(styles)}">{text}</span>'

    return text


def _paragraph_to_html(paragraph) -> str:
    """
    یک پاراگراف ورد را به تگ <p> HTML تبدیل می‌کند.
    """
    inner_html = "".join(_run_to_html(run) for run in paragraph.runs)

    if not inner_html.strip():
        return "<p><br></p>"

    align_style = _align_to_css(paragraph.alignment)
    return f'<p style="{align_style}">{inner_html}</p>'


def docx_to_html(filepath: str) -> str:
    """
    فایل .docx را می‌خواند و HTML مناسب برای ادیتور سامانه برمی‌گرداند.

    پارامترها:
        filepath: مسیر فایل .docx

    بازگشت:
        رشته HTML (مثلاً <p>متن <b>بولد</b></p><p>خط دوم</p>)
    """
    try:
        paragraphs = _open_docx_document(filepath)
    except Exception as e:
        logger.error(f"خطا در باز کردن فایل ورد: {e}")
        raise ValueError(f"خطا در باز کردن فایل ورد: {e}")

    result = "".join(_paragraph_to_html(para) for para in paragraphs)

    if not result.strip() or result == "<p><br></p>":
        return "<p><br></p>"

    return result


def docx_to_plain_text(filepath: str) -> str:
    """
    فایل .docx را می‌خواند و متن خام (بدون HTML) برمی‌گرداند.
    برای نمایش در پیش‌نمایش پیام‌رسان استفاده می‌شود.
    """
    try:
        paragraphs = _open_docx_document(filepath)
    except Exception as e:
        logger.error(f"خطا در باز کردن فایل ورد: {e}")
        return ""

    return "\n".join(para.text for para in paragraphs)


def validate_docx(filepath: str) -> tuple:
    """
    اعتبارسنجی فایل ورد.
    بازگشت: (is_valid: bool, error_message: str)
    """
    if not os.path.exists(filepath):
        return False, "فایل یافت نشد."

    if not filepath.lower().endswith(".docx"):
        return False, "فقط فایل‌های .docx پشتیبانی می‌شوند."

    size = os.path.getsize(filepath)
    if size > MAX_DOCX_SIZE:
        mb = size / (1024 * 1024)
        return False, f"حجم فایل ({mb:.1f} MB) بیش از حد مجاز (10 MB) است."

    if size < 100:
        return False, "فایل خالی یا ناقص به نظر می‌رسد."

    return True, ""


async def download_docx_from_bale(bot, file_id: str, user_id: int) -> str:
    """
    دانلود فایل ورد از بله و ذخیره محلی.
    بازگشت: مسیر فایل دانلودشده یا None در صورت خطا.
    """
    import time
    try:
        file_info = await bot.get_file(file_id)
        if not file_info.file_path:
            logger.error(f"[DOCX] مسیر فایل تلگرام خالی است برای {file_id}")
            return None

        filename = temp_path(f"docx_{user_id}_{int(time.time()*1000)}.docx")
        await bot.download_file(file_info.file_path, filename)
        return filename
    except Exception as e:
        logger.error(f"[DOCX] خطا در دانلود فایل ورد: {e}")
        return None
