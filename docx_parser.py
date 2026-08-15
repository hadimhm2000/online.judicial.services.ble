"""
تبدیل فایل Word (.docx) به HTML با حفظ فرمت (بولد، ایتالیک، آندرلاین، ترازبندی و ...).

کاربرد: کاربر می‌تواند به‌جای تایپ متن، فایل ورد را ارسال کند.
متن استخراج‌شده عیناً با فرمت اصلی در ادیتور سامانه قضایی وارد می‌شود.
"""

import os
import logging
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger(__name__)

# حداکثر حجم مجاز فایل ورد (بایت)
MAX_DOCX_SIZE = 10 * 1024 * 1024  # 10 MB


def _align_to_css(alignment) -> str:
    """تبدیل ترازبندی ورد به استایل CSS."""
    if alignment == WD_ALIGN_PARAGRAPH.RIGHT:
        return "text-align: right;"
    elif alignment == WD_ALIGN_PARAGRAPH.CENTER:
        return "text-align: center;"
    elif alignment == WD_ALIGN_PARAGRAPH.LEFT:
        return "text-align: left;"
    elif alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
        return "text-align: justify;"
    return "text-align: right;"  # پیش‌فرض: راست‌چین


def _run_to_html(run) -> str:
    """
    یک Run ورد را به HTML تبدیل می‌کند.
    بولد، ایتالیک، آندرلاین، خط‌خورده و اندازه فونت حفظ می‌شوند.
    """
    text = run.text or ""
    if not text:
        return ""

    # escape کاراکترهای HTML
    import html as html_lib
    text = html_lib.escape(text, quote=False)

    # حفظ فاصله‌های ابتدای خط
    if text.startswith(" "):
        leading = len(text) - len(text.lstrip(" "))
        text = ("\u00a0" * leading) + text[leading:]
    text = text.replace("  ", "\u00a0 ")

    # بررسی فرمت‌ها
    tags = []
    if run.bold:
        tags.append("b")
    if run.italic:
        tags.append("i")
    if run.underline:
        tags.append("u")
    if run.font.strike:
        tags.append("s")

    #包裹 متن با تگ‌ها
    for tag in tags:
        text = f"<{tag}>{text}</{tag}>"

    # اندازه فونت
    font_size = run.font.size
    if font_size:
        # ورد اندازه را در half-points ذخیره می‌کند (1 pt = 2 half-pts)
        size_pt = font_size.pt
        if size_pt and size_pt != 12:  # 12pt پیش‌فرض است
            text = f'<span style="font-size: {size_pt}pt;">{text}</span>'

    return text


def _paragraph_to_html(paragraph) -> str:
    """
    یک پاراگراف ورد را به تگ <p> HTML تبدیل می‌کند.
    """
    # جمع‌آوری HTML تمام run‌های پاراگراف
    inner_html = ""
    for run in paragraph.runs:
        inner_html += _run_to_html(run)

    # اگر پاراگراف خالی است
    if not inner_html.strip():
        return "<p><br></p>"

    # ترازبندی
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
        doc = Document(filepath)
    except Exception as e:
        logger.error(f"خطا در باز کردن فایل ورد: {e}")
        raise ValueError(f"خطا در باز کردن فایل ورد: {e}")

    html_parts = []
    for para in doc.paragraphs:
        html_parts.append(_paragraph_to_html(para))

    result = "".join(html_parts)

    if not result.strip() or result == "<p><br></p>":
        return "<p><br></p>"

    return result


def docx_to_plain_text(filepath: str) -> str:
    """
    فایل .docx را می‌خواند و متن خام (بدون HTML) برمی‌گرداند.
    برای نمایش در پیش‌نمایش پیام‌رسان استفاده می‌شود.
    """
    try:
        doc = Document(filepath)
    except Exception as e:
        logger.error(f"خطا در باز کردن فایل ورد: {e}")
        return ""

    lines = []
    for para in doc.paragraphs:
        lines.append(para.text)

    return "\n".join(lines)


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

        filename = f"docx_{user_id}_{int(time.time()*1000)}.docx"
        await bot.download_file(file_info.file_path, filename)
        return filename
    except Exception as e:
        logger.error(f"[DOCX] خطا در دانلود فایل ورد: {e}")
        return None
