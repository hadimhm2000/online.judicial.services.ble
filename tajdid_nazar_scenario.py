"""
سناریوی ثبت دعاوی اعتراضی در سامانه قضایی ثنا.

۷ نوع دعوی:
  تجدیدنظرخواهی، واخواهی، فرجام‌خواهی،
  اعاده دادرسی مدنی، اعاده دادرسی کیفری،
  اعتراض ثالث، اعتراض به قرار دادسرا

جریان کلی (مشابه اظهارنامه):
  ۱. کلیک «دعاوی اعتراضی» در منوی اصلی سامانه
  ۲. کلیک نوع دعوی (مثلاً تجدیدنظرخواهی)
  ۳. کلیک «ثبت و اصلاح دادخواست»
  ۴. مرحله «شروع» — انتخاب نوع ارائه (حقیقی/حقوقی/وکیل)
  ۵. مرحله «اطلاعات دادنامه» — شماره دادنامه، پرونده، تاریخ، استان
  ۶. بازیابی اطلاعات + پاپ‌آپ ثنا (خیر)
  ۷. حکم/قرار، مبلغ، اعسار
  ۸. مرحله «تجدیدنظرخواه» — افزودن اشخاص (شبیه اظهارکننده)
  ۹. مرحله «تجدیدنظرخوانده» — افزودن اشخاص (شبیه مخاطب)
  ۱۰. مرحله «مطلع/گواه» یا «سایر اشخاص» — شهود
  ۱۱. مرحله «متن» — شرح متن
  ۱۲. مرحله «منضمات» — پیوست‌ها
  ۱۳. مرحله «جهات» (فقط اعاده دادرسی)
  ۱۴. آماده‌سازی + محاسبه هزینه + چاپ
"""

import asyncio
import logging
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry,
    goto_url_with_retry, human_delay, safe_click_by_text,
    safe_type, wait_for_angular_idle,
    handle_session_expired, wait_for_horizontal_loading_bar)


class TajdidFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


class TajdidSanaQueryError(Exception):
    """خطای استعلام ثنا — شناسه ملی ثبت نشده."""
    def __init__(self, message: str, national_id: str = "", person_role: str = "", person_index: int = 0):
        super().__init__(message)
        self.national_id = national_id
        self.person_role = person_role
        self.person_index = person_index


# نگاشت نوع دعوی به نام منوی سامانه
CASE_TYPE_MENU_MAP = {
    "تجدیدنظرخواهی": "تجدیدنظرخواهی",
    "واخواهی": "واخواهی",
    "فرجام خواهی": "فرجام خواهی",
    "اعاده دادرسی مدنی": "اعاده دادرسی مدنی",
    "اعاده دادرسی کیفری": "اعاده دادرسی کیفری",
    "اعتراض ثالث": "اعتراض ثالث",
    "اعتراض به قرار دادسرا": "اعتراض به قرار دادسرا",
}

# نگاشت نوع دعوی به نام step اشخاص اول
APPELLANT_STEP_MAP = {
    "تجدیدنظرخواهی": "تجديدنظرخواه",
    "واخواهی": "واخواه",
    "فرجام خواهی": "فرجام‌خواه",
    "اعاده دادرسی مدنی": "درخواست‌کننده",
    "اعاده دادرسی کیفری": "درخواست‌کننده",
    "اعتراض ثالث": "اعتراض‌کننده ثالث",
    "اعتراض به قرار دادسرا": "اعتراض‌کننده",
}

# نگاشت نوع دعوی به نام step اشخاص دوم
APPELLEE_STEP_MAP = {
    "تجدیدنظرخواهی": "تجديدنظرخوانده",
    "واخواهی": "واخواه‌شده",
    "فرجام خواهی": "فرجام‌خواه‌شده",
    "اعاده دادرسی مدنی": "درخواست‌شونده",
    "اعاده دادرسی کیفری": "درخواست‌شونده",
    "اعتراض ثالث": "معترض‌عنه",
    "اعتراض به قرار دادسرا": "اعتراض‌شونده",
}

# نام step شهود/مطلع
WITNESS_STEP_MAP = {
    "اعاده دادرسی کیفری": "سايراشخاص",  # در کیفری نامش «سایر اشخاص» است
}
WITNESS_STEP_DEFAULT = "مطلع/ گواه"

# نگاشت جهات اعاده دادرسی به ایندکس checkbox
EADAH_MADANI_REASON_INDICES = {
    "موضوع حكم مورد، ادعاي خواهان نبوده است": 0,
    "وجود تضاد در مفاد يك حكم كه ناشي از استناد به اصول يا به مواد متضاد است": 1,
    "حكم صادره با حكم ديگري در خصوص همان دعوا و اصحاب آن متضاد است": 2,
    "طرف مقابل درخواست كننده اعاده دادرسي حيله و تقلبي به كار برده": 3,
    "پس از صدور حكم، اسناد و مداركي به دست آمده كه دليل حقانيت درخواست كننده باشد": 4,
    "حكم به ميزان بيشتر از خواسته صادر شده است": 5,
    "حكم دادگاه مستند به اسنادي بوده كه پس از صدور حكم جعلي بودنشان ثابت شده است": 6,
}

EADAH_KIFRI_REASON_INDICES = {
    "كسى به اتهام قتل شخصى محكوم شود و سپس زنده بودن وى محرز گردد": 0,
    "محكوميت چند نفر به اتهام ارتكاب جرمى كه نتوان بيش از يك مرتكب براى آن قائل شد": 1,
    "تعارض و تضاد مفاد دو حكم بى گناهى": 2,
    "درباره شخصى به اتهام واحد، احكام متفاوتى صادر شود": 3,
    "اثبات جعليت اسناد يا خلاف واقع بودن شهادت گواهان": 4,
    "حدوث واقعه جديد يا كشف ادله جديد بر بى گناهى": 5,
    "عمل ارتكابى جرم نباشد و يا مجازات مورد حكم بيش از مجازات مقرر قانونى باشد": 6,
}


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را به HTML امن برای ادیتور تبدیل می‌کند."""
    if not text:
        return "<p><br></p>"
    lines = text.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")
    return "".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════════════════

async def _click_menu_item(page, menu_text: str, bot: Bot, user_id: int):
    """کلیک روی آیتم منوی سامانه (li با ng-repeat=subMenu)."""
    clicked = await page.evaluate(f'''() => {{
        const items = Array.from(document.querySelectorAll('li.list-group-item'));
        const t = items.find(el => el.innerText && el.innerText.trim().includes("{menu_text}"));
        if (t) {{ t.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, menu_text, bot, user_id)


async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
    """کلیک روی box مرحله (شبیه ezhharnameh)."""
    clicked = await page.evaluate(f'''() => {{
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const t = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (t) {{
            const box = t.closest('.box');
            if (box) {{ box.click(); return true; }}
        }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)
        return
    await asyncio.sleep(1.5)
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        await asyncio.sleep(1.5)
        await page.evaluate(f'''() => {{
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const t = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
            if (t) {{
                const box = t.closest('.box');
                if (box) box.click();
            }}
        }}''')
        await asyncio.sleep(1.5)


async def _click_step_label(page, step_name: str, bot: Bot, user_id: int):
    """کلیک روی .step مرحله."""
    clicked = await page.evaluate(f'''() => {{
        const steps = Array.from(document.querySelectorAll('.step'));
        const t = steps.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (t) {{ t.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _click_add_btn(page, bot: Bot, user_id: int):
    """کلیک دکمه افزودن شخص."""
    clicked = await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const t = btns.find(el => el.innerText && (el.innerText.includes("افزودن") || el.innerText.includes("افراد جديد")));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)


async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int,
                            person_role: str = "", person_index: int = 0):
    """پر کردن کدملی شخص حقیقی و استعلام ثنا."""
    for sel in ["#txtRealIrNationalityCode1", "#txtRealIrNationalityCode"]:
        elem_count = await page.locator(sel).count()
        if elem_count > 0:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('{sel}');
                if (inp && inp.offsetParent !== null) {{
                    inp.value = "{national_id}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)
            break

    # استعلام ثنا
    await _query_sana(page, "actions.callNationalityCode", bot, user_id,
                      current_national_id=national_id, person_role=person_role, person_index=person_index)


async def _set_legal_record_no_zero(page):
    """شماره ثبت شخص حقوقی را روی «0» می‌گذارد."""
    for _ in range(10):
        done = await page.evaluate('''() => {
            const inp = document.querySelector('#txtLegalIrShSabt');
            if (!inp) return false;
            inp.value = "0";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }''')
        if done:
            break
        await asyncio.sleep(1)


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                            person_role: str = "", person_index: int = 0):
    """پر کردن شناسه ملی شرکت و نماینده."""
    company_id = person.get("company_id", "")
    rep_type = person.get("representative_type", "")
    nat_id = person.get("national_id", "")

    # پر کردن شناسه ملی حقوقی
    for sel in ["#txtLegalNationalityCode1", "#txtLegalNationalityCode"]:
        elem_count = await page.locator(sel).count()
        if elem_count > 0:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('{sel}');
                if (inp && inp.offsetParent !== null) {{
                    inp.value = "{company_id}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)
            break

    # استعلام شرکت
    await _query_sana(page, "actions.callLegalNationalityCode", bot, user_id,
                      is_legal=True, person_role=person_role, person_index=person_index)

    # تنظیم شماره ثبت روی 0
    await _set_legal_record_no_zero(page)

    # انتخاب نوع نماینده
    if rep_type == "مدیرعامل":
        agent_value = "0091000010000008"
    else:
        agent_value = "0091000010000010"

    dropdown_set = await page.evaluate(f'''() => {{
        const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
        if (sel && !sel.disabled) {{
            sel.focus();
            sel.value = "{agent_value}";
            sel.dispatchEvent(new Event("change", {{ bubbles: true }}));
            return true;
        }}
        return false;
    }}''')
    if dropdown_set:
        await asyncio.sleep(1)

    # پر کردن کدملی نماینده
    if nat_id:
        for sel in ["#txtRealIrNationalityCode1", "#txtRealIrNationalityCode"]:
            elem_count = await page.locator(sel).count()
            if elem_count > 0:
                await page.evaluate(f'''() => {{
                    const inp = document.querySelector('{sel}');
                    if (inp && inp.offsetParent !== null) {{
                        inp.value = "{nat_id}";
                        inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}
                }}''')
                await asyncio.sleep(1)
                break


async def _query_sana(page, ng_click: str, bot: Bot, user_id: int,
                      is_legal: bool = False,
                      current_national_id: str = "",
                      person_role: str = "",
                      person_index: int = 0,
                      max_retries: int = 5):
    """استعلام ثنا و بررسی نتیجه."""
    # کلیک دکمه استعلام
    clicked = await page.evaluate(f'''() => {{
        const btns = Array.from(document.querySelectorAll('button'));
        const t = btns.find(el =>
            el.getAttribute('ng-click') && el.getAttribute('ng-click').includes("{ng_click}")
        );
        if (t) {{ t.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        logging.warning(f"[TN] دکمه استعلام '{ng_click}' یافت نشد.")
        return

    await wait_for_horizontal_loading_bar(page, timeout=30)
    await asyncio.sleep(2)

    # بررسی خطای ثنا
    error_text = await _get_error_text(page)
    if error_text and ("ثبت" in error_text or "يافت نشد" in error_text or "اشتباه" in error_text):
        raise TajdidSanaQueryError(
            message=error_text,
            national_id=current_national_id,
            person_role=person_role,
            person_index=person_index)


async def _close_popup(page) -> bool:
    """بستن پاپ‌آپ (sweet-alert)."""
    closed = await page.evaluate('''() => {
        const confirmBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm');
        if (confirmBtn) { confirmBtn.click(); return true; }
        const cancelBtn = document.querySelector('.sweet-alert.showSweetAlert button.cancel');
        if (cancelBtn) { cancelBtn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _get_error_text(page) -> str:
    """دریافت متن خطای sweet-alert."""
    return await page.evaluate('''() => {
        const alert = document.querySelector('.sweet-alert.showSweetAlert p');
        return alert ? alert.innerText.trim() : "";
    }''')


async def _fill_text_editor(page, html_content: str, bot: Bot, user_id: int):
    """پر کردن ادیتور متن با HTML."""
    await page.evaluate(f'''() => {{
        const editor = document.querySelector('.note-editor.editable')
            || document.querySelector('[contenteditable="true"]');
        if (editor) {{
            editor.innerHTML = {html_content!r};
            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return true;
        }}
        return false;
    }}''')
    await asyncio.sleep(2)


async def _download_images(bot: Bot, file_ids: list, user_id: int) -> list:
    """دانلود تصاویر از بله و برگرداندن مسیر فایل‌ها."""
    from upload_helpers import download_and_save_file
    paths = []
    for fid in file_ids:
        try:
            path = await download_and_save_file(bot, user_id, fid)
            if path:
                paths.append(path)
        except Exception as e:
            logging.error(f"[TN] خطا در دانلود تصویر {fid}: {e}")
    return paths


async def _upload_attachment(page, title: str, image_paths: list, bot: Bot, user_id: int):
    """آپلود یک گروه پیوست (عنوان + تصاویر)."""
    if not image_paths:
        return

    # کلیک افزودن مدرک
    clicked = await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const t = btns.find(el => el.innerText && el.innerText.includes("افزودن"));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if clicked:
        await resilient_sleep(page, 3, bot, user_id)

    # پر کردن عنوان
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('input[ng-model*="Title"]');
        if (inp) {{
            inp.value = {title!r};
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # آپلود تصاویر
    for img_path in image_paths:
        try:
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(img_path)
            await resilient_sleep(page, 3, bot, user_id)
        except Exception as e:
            logging.error(f"[TN] خطا در آپلود {img_path}: {e}")


async def _click_preparation(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """کلیک مرحله آماده‌سازی."""
    for attempt in range(max_retries):
        try:
            await _click_step_label(page, "آماده‌سازی", bot, user_id)
            await resilient_sleep(page, 8, bot, user_id)
            # بررسی خطا
            error_text = await _get_error_text(page)
            if error_text and ("منقضی" in error_text or "ورود" in error_text):
                await handle_session_expired(page, bot, user_id)
                continue
            return True
        except Exception as e:
            logging.error(f"[TN] خطا در آماده‌سازی (تلاش {attempt+1}): {e}")
            await asyncio.sleep(3)
    return False


async def _calculate_cost(page, bot: Bot, user_id: int) -> dict:
    """محاسبه هزینه دادرسی."""
    # کلیک دکمه محاسبه هزینه
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnCalculateCash');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "محاسبه هزینه", bot, user_id)

    await resilient_sleep(page, 10, bot, user_id)

    # استخراج مبلغ
    cost_sum = await page.evaluate('''() => {
        const div = document.querySelector('[ng-model="viewModel.costSum"]');
        if (div) {
            const text = div.innerText || div.textContent || '';
            const num = text.replace(/,/g, '').trim();
            return parseInt(num) || 0;
        }
        // fallback: خواندن از جدول
        const tds = document.querySelectorAll('td.color-green.font-size-18');
        for (const td of tds) {
            const text = td.innerText || td.textContent || '';
            const num = text.replace(/,/g, '').trim();
            if (parseInt(num) > 0) return parseInt(num);
        }
        return 0;
    }''')

    # محاسبه مجموع با اضافه کردن هزینه‌های ثابت
    extra_items = await page.evaluate('''() => {
        const costs = [];
        const tds = document.querySelectorAll('td.color-red.font-size-17');
        for (const td of tds) {
            const text = td.innerText || td.textContent || '';
            const num = text.replace(/,/g, '').trim();
            if (parseInt(num) > 0) costs.push(parseInt(num));
        }
        return costs;
    }''')

    total = cost_sum
    if extra_items:
        total = cost_sum + sum(extra_items) + 50  # 50 ریال پیامک

    return {"cost_sum": cost_sum, "extra_items": extra_items, "total": total}


async def _click_goto_main(page, bot: Bot, user_id: int):
    """کلیک بازگشت به فهرست."""
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnGotoMainPage');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if clicked:
        await resilient_sleep(page, 3, bot, user_id)


async def _print_tajdid_nazar(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    """چاپ PDF دادخواست تجدیدنظر/دعاوی اعتراضی.

    ⚠️ نکته برای حاجی: این تابع بر اساس الگوی مشابه در check_scenario.py
    (_print_check) نوشته شده چون تجدیدنظر تا امروز اصلاً به مرحله چاپ نمی‌رسید
    و منطق چاپش وجود نداشت. سلکتورها («چاپ»، لینک تب جدید) از همون الگوی
    مشترک سامانه سنا گرفته شده‌اند اما روی صفحه واقعی تجدیدنظر تست نشده‌اند.
    اگر روی سرور واقعی کار نکرد، لاگ/اسکرین‌شات صفحه‌ی «آماده‌سازی» تجدیدنظر
    رو برام بفرست تا سلکتور دقیق رو اصلاح کنم.
    """
    import os
    import time
    pdf_path = ""
    try:
        clicked = await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const t = btns.find(b => b.innerText.includes("چاپ"));
            if (t && !t.disabled) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "چاپ", bot, user_id)

        await asyncio.sleep(3)

        new_page = await browser_context.new_page()
        try:
            print_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a'));
                const t = links.find(a => a.innerText && a.innerText.includes("چاپ"));
                return t ? t.href : null;
            }''')
            if not print_url:
                await new_page.close()
                return ""

            await new_page.goto(print_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            pdf_path = f"tn_{bill_no}_{int(time.time())}.pdf"
            await new_page.pdf(path=pdf_path, format="A4", print_background=True)
        finally:
            await new_page.close()

    except Exception as e:
        logging.error(f"[TN] خطا در چاپ PDF: {e}", exc_info=True)
        return ""

    return pdf_path


# ══════════════════════════════════════════════════════════════════════════════
# تابع اصلی پردازش تسک
# ══════════════════════════════════════════════════════════════════════════════

async def process_tajdid_nazar_task(data: dict, bot: Bot):
    """پردازش تسک ثبت دعوی اعتراضی"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]

    case_type = data.get("case_type", "")
    judge_no = data.get("tn_judge_no", "")
    file_no = data.get("tn_file_no", "")
    # ردیف فرعی حذف شد — مقدار پیش‌فرض ۱
    judge_date = data.get("tn_judge_date", "")
    province = data.get("tn_province", "")
    doc_type = data.get("tn_doc_type", "حکم")
    amount = data.get("tn_amount", 0)
    insolvency = data.get("tn_insolvency", False)
    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    witnesses = data.get("tn_witnesses", [])
    tn_text = data.get("tn_text", "")
    extra_text = data.get("tn_extra_text", "")
    attachments = data.get("tn_attachments", [])
    reasons = data.get("tn_reasons", [])

    has_lawyer = any(p.get("person_type") == "وکیل" for p in appellants)
    has_legal = any(p.get("person_type") == "شخص حقوقی" for p in appellants)
    has_real = any(p.get("person_type") == "شخص حقیقی" for p in appellants)
    only_real = has_real and not has_legal and not has_lawyer

    needs_reasons = case_type in ("اعاده دادرسی مدنی", "اعاده دادرسی کیفری")
    is_prosecutor = case_type == "اعتراض به قرار دادسرا"

    # نام‌های step
    appellant_step = APPELLANT_STEP_MAP.get(case_type, "تجديدنظرخواه")
    appellee_step = APPELLEE_STEP_MAP.get(case_type, "تجديدنظرخوانده")
    witness_step = WITNESS_STEP_MAP.get(case_type, WITNESS_STEP_DEFAULT)
    menu_item = CASE_TYPE_MENU_MAP.get(case_type, case_type)

    logging.info(
        f"[TN] user={user_id} case={case_type} judge={judge_no} file={file_no} "
        f"appellants={len(appellants)} appellees={len(appellees)} witnesses={len(witnesses)}"
    )

    await bot.send_message(
        user_id,
        f"⏳ *در حال ثبت {case_type}...*")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [TN] شروع ثبت {case_type} برای کاربر {user_id}\n"
        f"دادنامه: {judge_no} | تجدیدنظرخواه: {len(appellants)} | تجدیدنظرخوانده: {len(appellees)}"
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not ok:
                return
            await human_delay(3.0, 5.0)

            # ── ۱. کلیک «دعاوی اعتراضی» ────────────────────────
            await _click_menu_item(sana_page, "دعاوی اعتراضی", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. کلیک نوع دعوی ──────────────────────────────────
            await _click_menu_item(sana_page, menu_item, bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. کلیک «ثبت و اصلاح دادخواست» ──────────────────────
            await _click_step_box(sana_page, "ثبت و اصلاح دادخواست", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۴. مرحله «شروع» ────────────────────────────────────
            await _click_step_label(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # FIX: برای اعتراض ثالث، حتماً رادیوی «شخص حقیقی» (value=1) را
            # صریحاً کلیک و دیجست آنگولار را اجبار کنیم. مشکل این بود که
            # در ناوبری بازگشت، گزینه «شخص حقیقی» پنهان می‌شد.
            if only_real or case_type == "اعتراض ثالث":
                radio_clicked = await sana_page.evaluate('''() => {
                    // ابتدا رادیوی شخص حقیقی (value=1)
                    const rdb = document.querySelector('input[value="1"]');
                    if (rdb) {
                        rdb.click();
                        try {
                            const scope = angular.element(rdb).scope();
                            if (scope) scope.$apply();
                        } catch(e) {}
                    }
                    // اطمینان از اینکه رادیوی وکیل انتخاب نشده
                    const rdbLawyer = document.querySelector('#rdbLawyerOffer');
                    if (rdbLawyer && rdbLawyer.checked) {
                        rdbLawyer.checked = false;
                    }
                    // اطمینان از اینکه رادیوی نماینده انتخاب نشده
                    const rdbAgent = document.querySelector('#rdbAgentOffer');
                    if (rdbAgent && rdbAgent.checked) {
                        rdbAgent.checked = false;
                    }
                    return rdb ? true : false;
                }''')
                logging.info(f"[TN] radio clicked for start step (only_real={only_real}, case={case_type}): {radio_clicked}")
                await asyncio.sleep(2)
            elif has_lawyer:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbLawyerOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)
            else:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbAgentOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)

            # ── ۵. مرحله «اطلاعات دادنامه» ────────────────────────
            await _click_step_label(sana_page, "اطلاعات دادنامه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # شماره دادنامه
            await sana_page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtJudgeNo');
                if (inp) {{
                    inp.value = "{judge_no}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

            # شماره پرونده
            await sana_page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtReferingCaseNo');
                if (inp) {{
                    inp.value = "{file_no}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

            # تاریخ دادنامه
            await sana_page.evaluate(f'''() => {{
                const inps = document.querySelectorAll('input[persian-datepicker-popup]');
                if (inps.length > 0) {{
                    inps[0].value = "{judge_date}";
                    inps[0].dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inps[0].dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

            # استان
            await safe_click_by_text(sana_page, province[:10], bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # کلیک بازیابی
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnGetHst');
                if (btn) btn.click();
            }''')
            await resilient_sleep(sana_page, 8, bot, user_id)

            # پاپ‌آپ ثنا — کلیک خیر
            await _close_popup_sana(sana_page, bot, user_id)

            # تاریخ دادنامه (مجدداً در فرم جدید)
            await asyncio.sleep(2)
            await sana_page.evaluate(f'''() => {{
                const inps = document.querySelectorAll('input[persian-datepicker-popup]');
                if (inps.length > 0) {{
                    inps[0].value = "{judge_date}";
                    inps[0].dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inps[0].dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

            # حکم یا قرار + مبلغ + اعسار (فقط برای غیر اعتراض به قرار دادسرا)
            if not is_prosecutor:
                # حکم یا قرار
                if doc_type == "قرار":
                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[value="1"]');
                        if (rdb) rdb.click();
                    }''')
                    await asyncio.sleep(1)

                # مبلغ
                amount_str = str(amount) if amount > 0 else "1"
                await sana_page.evaluate(f'''() => {{{{
                    const inp = document.querySelector('input[ng-model*="Amount"]');
                    if (inp) {{{{
                        inp.value = "{amount_str}";
                        inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}}}
                }}''')
                await asyncio.sleep(1)

                # اعسار
                if insolvency:
                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[ng-model*="IsInsolvency"]');
                        if (rdb) rdb.click();
                    }''')
                    await asyncio.sleep(1)
                
            # ── ۶. مرحله «تجدیدنظرخواه» ──────────────────────────
            await _click_step_label(sana_page, appellant_step, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(appellants):
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype == "وکیل":
                    continue  # وکیل در step جداگانه اضافه می‌شود

                await _click_add_btn(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 3, bot, user_id)

                # Fix 4: اطمینان از ریست فرم — انتخاب رادیوی صحیح
                # FIX: برای اعتراض ثالث، حتماً دیجست آنگولار اجبار شود
                if ptype == "شخص حقیقی":
                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[value="1"]');
                        if (rdb) {
                            rdb.click();
                            try {
                                const scope = angular.element(rdb).scope();
                                if (scope) scope.$apply();
                            } catch(e) {}
                        }
                    }''')
                    await asyncio.sleep(1)

                if ptype == "شخص حقوقی":
                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[value="0"]');
                        if (rdb) {
                            rdb.click();
                            try {
                                const scope = angular.element(rdb).scope();
                                if (scope) scope.$apply();
                            } catch(e) {}
                        }
                    }''')
                    await asyncio.sleep(1)

                if ptype == "شخص حقوقی":
                    await _fill_legal_person(sana_page, person, bot, user_id,
                                              person_role="appellant", person_index=idx)
                else:
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                            person_role="appellant", person_index=idx)
                await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷. مرحله تجدیدنظرخوانده (فقط برای غیر اعتراض به قرار دادسرا)
            if not is_prosecutor:
                await _click_step_label(sana_page, appellee_step, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, person in enumerate(appellees):
                    ptype = person.get("person_type", "شخص حقیقی")

                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    if ptype == "شخص حقوقی":
                        await _fill_legal_person(sana_page, person, bot, user_id,
                                                  person_role="appellee", person_index=idx)
                    else:
                        await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                                person_role="appellee", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۸. مرحله شهود/مطلع ────────────────────────────────
            if witnesses:
                await _click_step_label(sana_page, witness_step, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, w in enumerate(witnesses):
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, w["national_id"], bot, user_id,
                                        person_role="witness", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۹. مرحله «متن» ─────────────────────────────────────
            await _click_step_label(sana_page, "متن", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # استفاده از HTML ورد در صورت وجود، در غیر اینصورت تبدیل متنی
            stored_html = data.get("tn_text_html", "")
            html_content = stored_html if stored_html else _text_to_editor_html(tn_text)
            await _fill_text_editor(sana_page, html_content, bot, user_id)
            await asyncio.sleep(2)

            # ── ۱۰. مرحله «منضمات» ────────────────────────────────
            await _click_step_label(sana_page, "منضمات", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for att in attachments:
                title = att.get("title", "مستندات")
                image_ids = att.get("images", [])
                if not image_ids:
                    continue

                image_paths = await _download_images(bot, image_ids, user_id)
                if image_paths:
                    await _upload_attachment(sana_page, title, image_paths, bot, user_id)
                    await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۱۱. مرحله «جهات» (فقط اعاده دادرسی) ──────────────
            if needs_reasons and reasons:
                await _click_step_label(sana_page, "جهات", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                if case_type == "اعاده دادرسی مدنی":
                    reason_map = EADAH_MADANI_REASON_INDICES
                else:
                    reason_map = EADAH_KIFRI_REASON_INDICES

                for reason_text in reasons:
                    idx = reason_map.get(reason_text)
                    if idx is not None:
                        chk_id = f"chk{idx}"
                        await sana_page.evaluate(f'''() => {{
                            const chk = document.querySelector('#{chk_id}');
                            if (chk && !chk.checked) {{
                                chk.click();
                            }}
                        }}''')
                        await asyncio.sleep(1)

            # ── ۱۲. آماده‌سازی ──────────────────────────────────────
            ok = await _click_preparation(sana_page, bot, user_id)
            if not ok:
                await bot.send_message(user_id, "❌ خطا در آماده‌سازی. لطفاً مجدداً تلاش فرمایید.")
                return

            # استخراج شماره بایگانی/رهگیری (همون الگوی مشترک سامانه سنا)
            bill_no = await sana_page.evaluate('''() => {
                const inp = document.querySelector('#txtBillNo');
                if (inp) return inp.value;
                const sp = document.querySelector('[ng-model*="BillNo"]');
                if (sp) return sp.innerText || sp.textContent;
                return "";
            }''')
            if not bill_no:
                bill_no = f"{file_no}-{judge_no}" if file_no or judge_no else ""
            logging.info(f"[TN] bill_no={bill_no}")

            # ── ۱۳. محاسبه هزینه ────────────────────────────────────
            cost_info = await _calculate_cost(sana_page, bot, user_id)
            total_cost = cost_info.get("total", 0)

            # ── ۱۴. چاپ PDF ─────────────────────────────────────────
            pdf_path = await _print_tajdid_nazar(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۵. ارسال فاکتور و شروع فلوی پرداخت (مثل لایحه) ──────
            from lavayeh_handlers import send_lavayeh_result
            appellant_nat_ids = ", ".join([
                p.get("national_id", "") for p in appellants if p.get("national_id")
            ])

            if pdf_path:
                await send_lavayeh_result(
                    bot, user_id, pdf_path, total_cost,
                    tracking_code=bill_no,
                    national_ids=appellant_nat_ids,
                    lavayeh_title=f"{case_type} — پرونده {file_no}",
                    lavayeh_province=province,
                    lavayeh_row_number=1,
                    lavayeh_persons=appellants,
                    skip_fee_calc=True,
                    is_ezhharnameh=False,
                    service_type="TAJDID_NAZAR")
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [TN] ثبت {case_type} کاربر {user_id} موفق."
                    f" کد: {bill_no} — هزینه: {total_cost:,} ریال"
                )
            else:
                # اگر چاپ ناموفق بود، دست‌کم فاکتور رو با اطلاعات موجود بفرست
                await bot.send_message(
                    user_id,
                    f"💰 *هزینه دادرسی: {total_cost:,} ریال*\n\n"
                    f"⚠️ چاپ نسخه پرونده با خطا مواجه شد؛ لطفاً با پشتیبانی تماس بگیرید."
                )
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="TAJDID_NAZAR", status="FAILED",
                        tracking_code=bill_no or None,
                        document_category=case_type,
                        fee=total_cost,
                        error_details="ثبت در سامانه انجام شد اما چاپ PDF ناموفق بود",
                        error_step="print_pdf",
                    )
                except Exception as panel_err:
                    logging.warning(f"[TN] خطا در ثبت شکست پرونده در پنل: {panel_err}")

            # ── بازگشت به فهرست ────────────────────────────────────
            await _click_goto_main(sana_page, bot, user_id)

            # ذخیره لاگ
            await log_event(
                user_id=user_id,
                event_type=f"tn_{data.get('task_type', '')}",
                details=f"{case_type} - هزینه: {total_cost:,} ریال"
            )

            return  # موفقیت

        except TajdidSanaQueryError as e:
            logging.error(f"[TN] خطای ثنا: {e}")
            # ذخیره در pending برای اصلاح توسط کاربر
            runtime_state.pending_tn_sana_fix[user_id] = {
                "task_data": {
                    **data,
                    "_sana_error_national_id": e.national_id,
                    "_sana_error_person_role": e.person_role,
                    "_sana_error_person_index": e.person_index,
                },
                "created_at": asyncio.get_event_loop().time(),
            }

            role_label = "تجدیدنظرخواه" if e.person_role == "appellant" else "تجدیدنظرخوانده"
            if e.person_role == "witness":
                role_label = "مطلع/گواه"

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ ویرایش شناسه ملی", callback_data=f"tn_fix_nid:{user_id}")],
                [InlineKeyboardButton(text="🗑 حذف درخواست", callback_data=f"tn_del_req:{user_id}")],
            ])
            await bot.send_message(
                user_id,
                f"⚠️ شناسه ملی `{e.national_id}` ({role_label}) ثبت‌نام ثنا ندارد یا اشتباه است.\n\n"
                f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=kb)
            return  # متوقف شد — منتظر اصلاح کاربر

        except TajdidFatalError as e:
            logging.error(f"[TN] خطای قطعی (تلاش {attempt+1}): {e}")
            await bot.send_message(user_id, f"❌ خطا در ثبت: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(10)
                continue
            return

        except Exception as e:
            logging.error(f"[TN] خطای عمومی (تلاش {attempt+1}): {e}", exc_info=True)
            if attempt < max_attempts - 1:
                await bot.send_message(user_id, "⚠️ خطایی رخ داد. در حال تلاش مجدد...")
                await asyncio.sleep(10)
                continue
            await bot.send_message(user_id, f"❌ خطا در ثبت {case_type}. لطفاً مجدداً تلاش فرمایید.")
            await bot.send_message(ADMIN_ID, f"❌ [TN] خطا در ثبت {case_type} برای {user_id}: {e}")
            return


async def _close_popup_sana(page, bot: Bot, user_id: int):
    """بستن پاپ‌آپ ثنا (بله/خیر) — کلیک خیر."""
    for _ in range(5):
        closed = await page.evaluate('''() => {
            // پاپ‌آپ sweet-alert با دکمه بلی/خیر
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;

            // بررسی آیا پاپ‌آپ ثنا است
            const h2 = popup.querySelector('h2');
            if (!h2) return false;
            const title = h2.innerText || '';
            if (!title.includes('ثنا') && !title.includes('اشخاص')) return false;

            // کلیک خیر
            const cancelBtn = popup.querySelector('button.cancel');
            if (cancelBtn) { cancelBtn.click(); return true; }

            // fallback: کلیک بلی
            const confirmBtn = popup.querySelector('button.confirm');
            if (confirmBtn) { confirmBtn.click(); return true; }

            return false;
        }''')
        if closed:
            await asyncio.sleep(2)
            return
        await asyncio.sleep(2)
