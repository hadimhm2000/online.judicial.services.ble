"""
سناریوی ثبت اظهارنامه در سامانه قضایی ثنا.

جریان کلی:
  ۱. کلیک «ارایه و پیگیری اظهارنامه»
  ۲. کلیک «ثبت و اصلاح اظهارنامه»
  ۳. مرحله «شروع» — انتخاب نوع ارائه‌دهنده (حقیقی / حقوقی / وکیل)
  ۴. مرحله «اظهارکننده» — افزودن اشخاص اظهارکننده
  ۵. مرحله «وکیل» (در صورت وجود وکیل) — افزودن وکیل
  ۶. مرحله «موضوع اظهارنامه» (در صورت وجود حقوقی) — ثبت نماینده
  ۷. مرحله «متن» — وارد کردن شرح متن
  ۸. ثبت موقت
  ۹. مرحله «منضمات»:
     - اگر حقوقی: ثبت مدرک نمایندگی (اجباری) + سایر پیوست‌ها
     - اگر وکیل داشت: مانند اعلام وکالت (تصویر الکترونیک وکالت‌نامه)
     - در غیر این صورت: سایر ضمائم
  ۱۰. آماده‌سازی جهت محاسبه هزینه
  ۱۱. محاسبه و دریافت هزینه
  ۱۲. چاپ PDF
  ۱۳. ارسال نتیجه به کاربر
"""

import asyncio
import logging
import os
import time
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, soft_click_if_exists,
    goto_url_with_retry, human_delay, force_click_by_text,
    safe_click_by_text, safe_type, wait_for_angular_idle,
    handle_session_expired, wait_for_horizontal_loading_bar)


class EzhharFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


class EzhharSanaQueryError(Exception):
    """خطای استعلام ثنا — شناسه ملی ثبت نشده یا تاریخ تولد اشتباه."""
    def __init__(self, message: str, national_id: str = "", person_role: str = "", person_index: int = 0):
        super().__init__(message)
        self.national_id = national_id
        self.person_role = person_role      # "declarant" یا "addressee"
        self.person_index = person_index    # ایندکس شخص در لیست


# مقدار value برای نوع نماینده در سامانه
AGENT_TYPE_VALUES = {
    "مدیرعامل": "0091000010000008",
    "نماینده":  "0091000010000007",
}

# مقدار value برای نوع نماینده در بخش نماينده (addressee agent step)
ADDRESSEE_AGENT_TYPE_VALUES = {
    "سایر نمایندگان قانونی": "0091000010000010",
    "مدیر شرکت": "0091000010000008",
}


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را با حفظ فاصله‌ها/اینترها به HTML امن برای ادیتور تبدیل می‌کند."""
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


async def process_ezhharnameh_task(data: dict, bot: Bot):
    """پردازش تسک ثبت اظهارنامه"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]
    is_prepaid = data.get("prepaid", False)

    declarants = data.get("ezhhar_declarants", [])
    addressees = data.get("ezhhar_addressees", [])
    subject = data.get("ezhhar_subject", "سایر")
    ezhhar_text = data.get("ezhhar_text", "")
    attachment_groups = data.get("ezhhar_attachments", [])

    # تشخیص وجود وکیل و حقوقی در اظهارکنندگان
    has_lawyer = any(p.get("person_type") == "وکیل" for p in declarants)
    has_legal_declarant = any(p.get("person_type") == "شخص حقوقی" for p in declarants)
    has_real_declarant = any(p.get("person_type") == "شخص حقیقی" for p in declarants)
    # تنها حقیقی (بدون حقوقی و وکیل)
    only_real_declarant = has_real_declarant and not has_legal_declarant and not has_lawyer

    logging.info(
        f"[EZHHAR] user={user_id} declarants={declarants} addressees={addressees} "
        f"subject={subject} has_lawyer={has_lawyer} has_legal={has_legal_declarant}"
    )

    await bot.send_message(
        user_id,
        f"⏳ *در حال ثبت اظهارنامه...*\n"
        f"موضوع: *{subject}*")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [EZHHAR] شروع ثبت اظهارنامه برای کاربر {user_id}\n"
        f"موضوع: {subject} | اظهارکنندگان: {len(declarants)} | مخاطبین: {len(addressees)}"
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

            # ── ۱. کلیک «ارایه و پیگیری اظهارنامه» ─────────────────────
            clicked = await sana_page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a.list-group-item'));
                const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری اظهارنامه"));
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. کلیک «ثبت و اصلاح اظهارنامه» ────────────────────────
            await _click_step_box(sana_page, "ثبت و اصلاح اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. مرحله «شروع» — انتخاب نوع ارائه ─────────────────────
            await _click_step_label(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            if only_real_declarant:
                # فقط حقیقی — مستقیم وارد بخش اظهارکننده می‌شویم
                logging.info("[EZHHAR] only real declarant — skipping start step selection")
            elif has_lawyer:
                # دارد وکیل + (احتمالاً حقیقی/حقوقی)
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbLawyerOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)
            else:
                # حقوقی بدون وکیل
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbAgentOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)

            # ── ۴. مرحله «اظهارکننده» ────────────────────────────────────
            await _click_step_label(sana_page, "اظهاركننده", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(declarants):
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype in ("شخص حقیقی", "وکیل"):
                    # وکیل در بخش اظهارکننده با کدملی حقیقی اضافه می‌شود
                    # (وکیل بعداً در step وکیل اضافه می‌شود)
                    if ptype == "وکیل":
                        continue  # وکیل را در step وکیل اضافه می‌کنیم
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                            person_role="declarant", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_legal_person(sana_page, person, bot, user_id,
                                              person_role="declarant", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۴.۵. مرحله «مخاطب» ────────────────────────────────────
            await _click_step_label(sana_page, "مخاطب", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(addressees):
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype == "شخص حقیقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                            person_role="addressee", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_legal_person(sana_page, person, bot, user_id,
                                              person_role="addressee", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۴.۶. مرحله «نماينده» ──────────────────────────────────
            # بعد از تکمیل مخاطب باید وارد بخش نماينده شویم
            # این مرحله همیشه باید طی شود — اطلاعات نماینده از اظهارکننده حقوقی گرفته می‌شود
            await _click_step_label(sana_page, "نماينده", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            if has_legal_declarant:
                # یافتن اولین اظهارکننده حقوقی و استفاده از اطلاعات نماینده او
                legal_decl = next(
                    (p for p in declarants if p.get("person_type") == "شخص حقوقی"), {}
                )
                rep_type = legal_decl.get("representative_type", "")
                nat_id = legal_decl.get("national_id", "")

                # نگاشت نوع نماینده اظهارکننده به dropdown نماينده
                if rep_type == "مدیرعامل":
                    agent_label = "مدير شركت"
                    agent_value = "0091000010000008"
                else:
                    agent_label = "ساير نمايندگان قانوني"
                    agent_value = "0091000010000010"

                logging.info(f"[EZHHAR][نماينده] انتخاب نوع نماینده: {agent_label} ({rep_type}) -> {agent_value}")

                # اول کلیک «افزودن» تا فرم نماینده باز شود
                await _click_add_btn(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                # صبر تا dropdown و فیلدها رندر شوند
                await wait_for_angular_idle(sana_page)
                await asyncio.sleep(3)

                # انتخاب نوع نماینده از dropdown — با AngularJS trigger صحیح
                dropdown_set = await sana_page.evaluate(f'''() => {{
                    const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
                    if (sel && !sel.disabled) {{
                        sel.focus();
                        sel.value = "{agent_value}";
                        sel.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        sel.dispatchEvent(new Event("change", {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }}''')

                if not dropdown_set:
                    # fallback: جستجو در همه select ها
                    await sana_page.evaluate(f'''() => {{
                        const sels = Array.from(document.querySelectorAll('select'));
                        for (const s of sels) {{
                            const opts = Array.from(s.options);
                            const opt = opts.find(o => o.value === "{agent_value}");
                            if (opt && !s.disabled) {{
                                s.focus();
                                s.value = "{agent_value}";
                                s.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                s.dispatchEvent(new Event("change", {{ bubbles: true }}));
                                return;
                            }}
                        }}
                    }}''')

                logging.info(f"[EZHHAR][نماينده] dropdown={'set' if dropdown_set else 'fallback'}")
                await asyncio.sleep(3)

                # وارد کردن کدملی نماینده
                if nat_id:
                    await wait_for_angular_idle(sana_page)
                    await asyncio.sleep(2)

                    # چند تلاش برای پیدا کردن فیلد کدملی (ممکن است هنوز رندر نشده باشد)
                    nat_id_set = False
                    for _nat_try in range(5):
                        nat_id_set = await sana_page.evaluate(f'''() => {{
                            const inp = document.querySelector('#txtRealIrNationalityCode');
                            if (inp && !inp.disabled) {{
                                inp.focus();
                                inp.value = "";
                                inp.value = "{nat_id}";
                                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}''')
                        if nat_id_set:
                            break
                        logging.warning(f"[EZHHAR][نماينده] فیلد کدملی پیدا نشد — تلاش {_nat_try+1}")
                        await asyncio.sleep(3)

                    logging.info(f"[EZHHAR][نماينده] nat_id_set={nat_id_set}")
                    await asyncio.sleep(2)

                    if nat_id_set:
                        # استعلام شخص — استفاده مستقیم از #btnCallNationalityCode
                        await _query_sana(sana_page, "actions.callNationalityCode", bot, user_id,
                                          current_national_id=nat_id, person_role="addressee_agent")
                        await resilient_sleep(sana_page, 5, bot, user_id)
                    else:
                        logging.error(f"[EZHHAR][نماينده] فیلد کدملی after 5 attempts not found")
            else:
                logging.info("[EZHHAR][نماينده] اظهارکننده حقوقی ندارد — مرحله نماينده بدون عملیات عبور می‌شود")

            # ── ۵. مرحله «وکیل» (اگر وکیل داشتیم) ─────────────────────
            if has_lawyer:
                await _click_step_label(sana_page, "وكيل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, person in enumerate(declarants):
                    if person.get("person_type") != "وکیل":
                        continue
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_lawyer_person(sana_page, person["national_id"], bot, user_id,
                                               person_role="declarant", person_index=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۶. مرحله «موضوع اظهارنامه» ──────────────────────────────
            # این مرحله همیشه باید طی شود (چه اظهارکننده حقیقی باشد چه حقوقی)
            await _click_step_label(sana_page, "موضوع اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # کلیک «افزودن»
            await _click_add_btn(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # باز کردن dropdown «موضوع» و جستجوی «سایر»
            search_input = sana_page.locator('.ui-select-search').first
            opened = False
            for open_attempt in range(4):
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('.ui-select-toggle');
                    if (btn) btn.click();
                }''')
                try:
                    await search_input.wait_for(state="visible", timeout=4000)
                    opened = True
                    break
                except PlaywrightTimeoutError:
                    logging.warning(f"[EZHHAR] dropdown موضوع باز نشد (تلاش {open_attempt + 1})")
                    await asyncio.sleep(1.5)

            if opened:
                await search_input.fill("")
                await search_input.type("سایر", delay=150)
                await asyncio.sleep(3)

                subject_clicked = await sana_page.evaluate('''() => {
                    // اولویت با آیتم دقیق typeahead که شامل «سایر موضوعات اظهارنامه» است
                    const highlighted = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'));
                    const visibleHighlighted = highlighted.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visibleHighlighted.length > 0) {
                        let target = visibleHighlighted[0];
                        // کلیک روی والد قابل‌کلیک (ردیف) در صورت وجود، وگرنه خود المان
                        const row = target.closest('a, .ui-select-choices-row, li') || target;
                        row.click();
                        target.click();
                        return true;
                    }
                    const choices = Array.from(document.querySelectorAll('.ui-select-choices-row, .ui-select-choices div[ng-repeat]'));
                    const visible = choices.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visible.length > 0) { visible[0].click(); return true; }
                    const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
                    const visLis = lis.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visLis.length > 0) { visLis[0].click(); return true; }
                    return false;
                }''')
                await asyncio.sleep(3)

                if not subject_clicked:
                    logging.warning("[EZHHAR] گزینه اول dropdown موضوع پیدا/کلیک نشد — تلاش مجدد")
                    # تلاش دوم: کلیک با locator روی آیتم typeahead
                    try:
                        option_locator = sana_page.locator('[ng-bind-html*="typeaheadHighlight"]').first
                        await option_locator.wait_for(state="visible", timeout=3000)
                        await option_locator.click()
                        await asyncio.sleep(3)
                    except PlaywrightTimeoutError:
                        logging.warning("[EZHHAR] تلاش دوم انتخاب موضوع نیز ناموفق بود")
            else:
                logging.warning("[EZHHAR] dropdown موضوع باز نشد — ادامه بدون انتخاب موضوع")

            # اگر کاربر عنوانی متفاوت از پیش‌فرض انتخاب کرده باشد، در فیلد توضیحات درج می‌شود
            if subject and subject != "سایر":
                await sana_page.evaluate('''(desc) => {
                    const inp = document.querySelector('input[name="txtDescription"]');
                    if (inp) {
                        inp.value = desc;
                        inp.dispatchEvent(new Event("input", { bubbles: true }));
                        inp.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', subject)
                await asyncio.sleep(1)

            # ── ۷. مرحله «شرح» ───────────────────────────────────────────
            await _click_step_label(sana_page, "شرح", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # استفاده از HTML ورد در صورت وجود، در غیر اینصورت تبدیل متنی
            stored_html = data.get("ezhhar_text_html", "")
            ezhhar_text_html = stored_html if stored_html else _text_to_editor_html(ezhhar_text)
            await sana_page.evaluate('''(html) => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    editor.focus();
                    editor.innerHTML = html;
                    editor.dispatchEvent(new Event("input", { bubbles: true }));
                    editor.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', ezhhar_text_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

            # اعمال H3
            await sana_page.evaluate('''() => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    const range = document.createRange();
                    range.selectNodeContents(editor);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
                    editor.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(0.5)
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('button[name="h3"]') ||
                    Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(0.5)

            # ── ۸. ثبت موقت ──────────────────────────────────────────────
            await _click_save_temp(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[EZHHAR] bill_no={bill_no}")

            # ذخیره کدرهگیری در گوگل شیت + اطلاع به مدیر
            if bill_no:
                await log_event("ثبت موقت", "اظهارنامه", str(user_id), user_id,
                                tracking_code=bill_no, note=f"اظهارنامه ثبت موقت شد | موضوع: {subject}")
                await bot.send_message(
                    ADMIN_ID,
                    f"📋 *ثبت موقت اظهارنامه موفق*\n"
                    f"👤 کاربر: {user_id}\n"
                    f"🔢 کد رهگیری: `{bill_no}`\n"
                    f"📝 موضوع: {subject}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۹. مرحله «منضمات» ────────────────────────────────────────
            # دانلود تصاویر از بله
            groups_with_paths = []
            for group in attachment_groups:
                paths = await _download_images(bot, group.get("images", []), user_id)
                groups_with_paths.append({"title": group.get("title", "مستندات"), "paths": paths})

            if has_legal_declarant or attachment_groups:
                # تلاش برای ورود به منضمات (با retry در صورت خطای سامانه)
                attachments_ok = False
                for _attach_retry in range(3):
                    await _click_step_box(sana_page, "منضمات", bot, user_id)
                    await resilient_sleep(sana_page, 5, bot, user_id)

                    # بررسی خطای سامانه (پاپ‌آپ خطا مثل "خطای دسترسی به اطلاعات")
                    has_error = await sana_page.evaluate('''() => {
                        const popup = document.querySelector('.sweet-alert.showSweetAlert');
                        if (!popup) return false;
                        const icon = popup.querySelector('.sa-icon.sa-error');
                        return icon && window.getComputedStyle(icon).display !== 'none';
                    }''')

                    if not has_error:
                        attachments_ok = True
                        break

                    # بستن پاپ‌آپ خطا
                    await _close_popup(sana_page)
                    logging.warning(f"[EZHHAR][منضمات] خطای سامانه در ورود به منضمات (تلاش {_attach_retry+1})")

                    if _attach_retry < 2:
                        # بازگشت به فهرست و تلاش مجدد
                        await _click_goto_main(sana_page, bot, user_id)
                        await resilient_sleep(sana_page, 4, bot, user_id)

                if not attachments_ok:
                    error_msg = f"⚠️ *خطا در بخش منضمات*\nکد رهگیری: `{bill_no}`\nبا شماره *09306186888* در واتساپ پیام دهید."
                    await bot.send_message(user_id, error_msg)
                    await bot.send_message(ADMIN_ID, f"❌ [EZHHAR] خطای منضمات (3 تلاش ناموفق) کاربر {user_id} | کد: {bill_no}")
                    await log_event("خطای سامانه", "اظهارنامه", str(user_id), user_id,
                                    tracking_code=bill_no, note="خطا در ورود به منضمات (3 تلاش)")
                    # ذخیره تسک incomplete برای مدیریت
                    runtime_state.incomplete_tasks[f"ezhhar:{bill_no}"] = {
                        "bill_no": bill_no, "user_id": user_id, "type": "ezhhar",
                        "last_completed_step": "ثبت موقت", "next_step": "منضمات",
                        "task_data": data, "created_at": time.time(),
                    }
                    return

                # اگر حقوقی داشتیم، مدرک نمایندگی اجباری است
                if has_legal_declarant:
                    # اولین گروه پیوست‌ها را به عنوان مدرک نمایندگی ثبت می‌کنیم
                    proxy_group = groups_with_paths[0] if groups_with_paths else {"title": "مدرک نمایندگی", "paths": []}
                    await _upload_proxy_document(sana_page, proxy_group["paths"], bot, user_id)
                    remaining_groups = groups_with_paths[1:]
                else:
                    remaining_groups = groups_with_paths

                # اگر وکیل داشتیم، وکالت‌نامه الکترونیک
                if has_lawyer:
                    # یافتن اولین وکیل برای شماره قرارداد
                    first_lawyer = next((p for p in declarants if p.get("person_type") == "وکیل"), {})
                    contract_no = first_lawyer.get("contract_number", "")
                    stamp_val = first_lawyer.get("stamp_amount_value", 0)
                    await _upload_electronic_vakalaht(sana_page, contract_no, stamp_val, bot, user_id)

                # سایر پیوست‌ها
                for idx, group in enumerate(remaining_groups):
                    if group["paths"]:
                        # اگر اولین گروه نیست، دکمه «پیوست جدید» را بزن
                        if idx > 0:
                            await asyncio.sleep(2)
                            clicked = await sana_page.evaluate('''() => {
                                const btn = document.querySelector('#newAttachmentType');
                                if (btn && !btn.disabled) { btn.click(); return true; }
                                return false;
                            }''')
                            if clicked:
                                logging.info(f"[EZHHAR] کلیک «پیوست جدید» قبل از گروه {idx+1}")
                                await asyncio.sleep(3)
                                await wait_for_angular_idle(sana_page)
                                await asyncio.sleep(1)
                            else:
                                logging.warning(f"[EZHHAR] دکمه «پیوست جدید» پیدا نشد")

                        # ⭐ استفاده از _upload_attachment_with_retry به‌جای _upload_other_attachment
                        # این تابع retry محلی انجام می‌دهد و اگر نشد، کل ثبت را ری‌استارت نمی‌کند
                        upload_result = await _upload_attachment_with_retry(
                            sana_page,
                            group["title"],
                            group["paths"],
                            bot,
                            user_id,
                            bill_no=bill_no,
                            max_retries=3)

                        # اگر خطای کدنویسی بود (مثل module_missing) — توقف کامل
                        if not upload_result["success"]:
                            error_type = upload_result.get("error_type")
                            if error_type in ("module_missing", "code_error"):
                                logging.error(
                                    f"[EZHHAR] خطای کدنویسی در آپلود — توقف کل فرآیند. "
                                    f"خطا: {upload_result.get('error')}"
                                )
                                # ذخیره در incomplete_tasks برای پیگیری بعدی
                                if bill_no:
                                    runtime_state.incomplete_tasks[f"ezhhar:{bill_no}"] = {
                                        "bill_no": bill_no, "user_id": user_id, "type": "ezhhar",
                                        "last_completed_step": "ثبت موقت", "next_step": "منضمات",
                                        "task_data": data, "created_at": time.time(),
                                        "attachment_groups": remaining_groups[idx:],
                                    }
                                return  # توقف کل process_ezhharnameh_task بدون retry

                            # خطای غیر کدنویسی — ادامه با گروه بعدی
                            logging.warning(
                                f"[EZHHAR] آپلود گروه [{group['title']}] ناموفق، ادامه با گروه بعدی"
                            )

                # پاکسازی فایل‌های موقت
                for group in groups_with_paths:
                    for p in group["paths"]:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                await _click_goto_main(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۰. آماده‌سازی ───────────────────────────────────────────
            # نام صحیح: «آماده سازي جهت دريافت وجه» (نه محاسبه هزينه و ارسال)
            await _click_step_box(sana_page, "آماده سازي جهت دريافت وجه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            prep_ok = await _click_preparation(sana_page, bot, user_id)
            if not prep_ok:
                await bot.send_message(
                    user_id,
                    f"⚠️ مرحله آماده‌سازی با مشکل مواجه شد.\n"
                    f"کد رهگیری: `{bill_no}`\n"
                    f"با شماره *09306186888* در واتساپ پیام دهید.")
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR] آماده‌سازی ناموفق کاربر {user_id} | کد: {bill_no}")
                await log_event("خطای سامانه", "اظهارنامه", str(user_id), user_id,
                                tracking_code=bill_no, note="آماده‌سازی ناموفق")
                if bill_no:
                    runtime_state.incomplete_tasks[f"ezhhar:{bill_no}"] = {
                        "bill_no": bill_no, "user_id": user_id, "type": "ezhhar",
                        "last_completed_step": "منضمات", "next_step": "آماده‌سازی",
                        "task_data": data, "created_at": time.time(),
                    }
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۱. محاسبه هزینه ─────────────────────────────────────────
            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            cost_info = await _calculate_cost(sana_page, bot, user_id)
            final_total = cost_info.get("final_total", 0)
            cost_sum_rounded = cost_info.get("cost_sum_rounded", 0)
            cost_error = cost_info.get("cost_error", False)
            logging.info(f"[EZHHAR] cost_info={cost_info}, final_total={final_total}, cost_error={cost_error}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. چاپ PDF ──────────────────────────────────────────────
            pdf_path = await _print_ezhharnameh(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۳. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result, send_bulk_item_result
            nat_ids = ", ".join([
                p.get("national_id", "") for p in declarants if p.get("national_id")
            ])

            if cost_error:
                # جدول هزینه نمایش داده نشد — ارسال PDF + پیام خطا
                await bot.send_message(
                    user_id,
                    f"⚠️ *بخش هزینه سامانه دادگاه اختلال دارد.*\n\n"
                    f"📄 اظهارنامه شما با کد رهگیری `{bill_no}` ثبت و چاپ شد.\n"
                    f"لطفاً برای محاسبه هزینه به مدیریت به شماره *09306186888* در واتساپ پیام دهید.")
                # ارسال PDF بدون مبلغ هزینه
                if pdf_path and os.path.exists(pdf_path):
                    from bale_file_sender import send_document_direct
                    await send_document_direct(user_id, pdf_path)
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [EZHHAR] جدول هزینه نمایش داده نشد. کاربر {user_id} | کد: {bill_no}"
                )
            else:
                is_bulk = data.get("_is_bulk", False)
                batch_tc = data.get("batch_tracking_code", "")
                row_idx = data.get("_bulk_row_index", 0)
                if is_bulk:
                    await send_bulk_item_result(
                        bot, user_id, pdf_path, final_total,
                        tracking_code=bill_no,
                        national_ids=nat_ids,
                        lavayeh_title=f"اظهارنامه — {subject}",
                        lavayeh_persons=declarants,
                        is_ezhharnameh=True,
                        batch_tracking_code=batch_tc,
                        row_index=row_idx,
                        lavayeh_bill_no="",
                    )
                else:
                    await send_lavayeh_result(
                        bot, user_id, pdf_path, final_total,
                        tracking_code=bill_no,
                        national_ids=nat_ids,
                        lavayeh_title=f"اظهارنامه — {subject}",
                        lavayeh_province="",
                        lavayeh_row_number=1,
                        lavayeh_persons=declarants,
                        skip_fee_calc=True,  # هزینه اظهارنامه قبلاً با فرمول جدید محاسبه شده
                    is_ezhharnameh=True,  # برای تمایز لایحه/اظهارنامه در جریان امضا
                    prepaid=is_prepaid,
                )

                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [EZHHAR] ثبت اظهارنامه کاربر {user_id} موفق. هزینه: {final_total:,} ریال"
                )
            return

        except EzhharSanaQueryError as e:
            logging.error(f"[EZHHAR] خطای استعلام ثنا user={user_id}: {e}")
            # ذخیره اطلاعات تسک برای ادامه بعدی در صورت ویرایش شناسه ملی
            pending_task_data = dict(data)
            pending_task_data["_sana_error_national_id"] = e.national_id
            pending_task_data["_sana_error_person_role"] = e.person_role
            pending_task_data["_sana_error_person_index"] = e.person_index
            runtime_state.pending_ezhhar_sana_fix[user_id] = {
                "task_data": pending_task_data,
                "created_at": asyncio.get_event_loop().time(),
            }

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            role_label = "اظهارکننده" if e.person_role == "declarant" else "مخاطب"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ ویرایش شناسه ملی",
                        callback_data=f"ezhhar_fix_nid:{user_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 حذف درخواست",
                        callback_data=f"ezhhar_del_req:{user_id}"
                    ),
                ],
            ])
            await bot.send_message(
                user_id,
                f"⚠️ *خطای استعلام ثنا*\n\n"
                f"شناسه ملی `{e.national_id}` ({role_label}) ثبت‌نام ثنا ندارد یا اشتباه است.\n\n"
                f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:\n"
                f"• *ویرایش شناسه ملی:* شناسه صحیح را ارسال کنید تا اظهارنامه با همان اطلاعات قبلی ثبت شود.\n"
                f"• *حذف درخواست:* درخواست اظهارنامه حذف می‌شود.\n\n"
                f"⏰ _توجه: اگر ظرف ۱ ساعت اقدامی نکنید، درخواست به‌صورت خودکار حذف خواهد شد._",
                reply_markup=kb)

            # زمان‌بندی حذف خودکار پس از ۱ ساعت
            asyncio.create_task(_auto_delete_pending_ezhhar(bot, user_id, 3600))
            return

        except EzhharFatalError as e:
            logging.error(f"[EZHHAR] خطای قطعی user={user_id}: {e}")
            await bot.send_message(user_id, f"⚠️ *خطای قطعی:* {str(e)[:200]}")
            await log_event(
                "خطای سامانه", "اظهارنامه", str(user_id), user_id,
                doc_name=subject, note=f"خطای قطعی: {str(e)[:200]}"
            )
            return

        except Exception as e:
            logging.error(f"[EZHHAR] تلاش {attempt+1} ناموفق user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [EZHHAR] تلاش {attempt+1} ناموفق. ریلود...\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت اظهارنامه با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR] کاربر {user_id} پس از {max_attempts} تلاش ناموفق.")
                await log_event(
                    "خطای سامانه", "اظهارنامه", str(user_id), user_id,
                    doc_name=subject,
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
                )
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="process_ezhharnameh_task", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
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

    # مسیر کلیک مستقیم از safe_click_by_text عبور نمی‌کند؛ اینجا هم صریحاً
    # چک انقضا انجام می‌شود (نقطه‌ای که کلیک روی «منضمات» قبلاً بدون این چک بود).
    await asyncio.sleep(1.5)
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        logging.info(f"_click_step_box: session renewed after clicking box '{step_name}', retrying click.")
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
    clicked = await page.evaluate(f'''() => {{
        const steps = Array.from(document.querySelectorAll('.step'));
        const t = steps.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (t) {{ t.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _click_add_btn(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)
    await asyncio.sleep(2)


async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int,
                            person_role: str = "", person_index: int = 0):
    """پر کردن کدملی شخص حقیقی و استعلام"""
    # پر کردن فیلد کدملی
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


async def _set_legal_record_no_zero(page, prefix: str = "EZHHAR"):
    """شماره ثبت شخص حقوقی (#txtLegalIrShSabt / RecordNo) را روی «0» می‌گذارد.

    سامانه وقتی شخص حقوقی خصوصی است (LegalPersonType==4 و identityInfo==1)،
    این فیلد را اجباری می‌کند. این فیلد فقط پس از استعلام موفق شرکت رندر می‌شود،
    پس این تابع باید بعد از callLegalNationalityCode صدا زده شود.
    """
    for _ in range(10):
        done = await page.evaluate('''() => {
            const inp = document.querySelector('#txtLegalIrShSabt');
            if (!inp) return false;
            inp.value = "0";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            try {
                if (typeof angular !== 'undefined') {
                    const ctrl = angular.element(inp).controller('ngModel');
                    if (ctrl) { ctrl.$setViewValue("0"); ctrl.$render(); }
                }
            } catch(e) {}
            return true;
        }''')
        if done:
            logging.info(f"[{prefix}] شماره ثبت شخص حقوقی روی «0» تنظیم شد")
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    logging.warning(f"[{prefix}] فیلد شماره ثبت (#txtLegalIrShSabt) یافت نشد — رد شد")
    return False


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                              person_role: str = "", person_index: int = 0):
    """پر کردن اطلاعات شخص حقوقی و استعلام"""
    company_id = person.get("company_id", "")
    national_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "نماینده")

    # اگر کدملی نماینده وجود ندارد، فقط شناسه ملی شرکت را ثبت می‌کنیم
    if not national_id:
        logging.info(f"[EZHHAR] شخص حقوقی بدون کدملی نماینده — فقط ثبت شناسه ملی شرکت")
        # انتخاب رادیوباتن «شخص حقوقی» (value=3)
        await page.evaluate('''() => {
            const rdb = document.querySelector('#rdb3, input[value="3"][name="personType"]');
            if (rdb) rdb.click();
        }''')
        await asyncio.sleep(2)

        # انتخاب «غیردولتی / خصوصی» (value=4)
        await page.evaluate('''() => {
            const rdb = document.querySelector('#rdbPrivate, input[value="4"][name="LegalPersonType"]');
            if (rdb) rdb.click();
        }''')
        await asyncio.sleep(2)

        # وارد کردن شناسه ملی شرکت
        await page.evaluate(f'''() => {{
            const inp = document.querySelector('#txtLegalIrNationalityCode');
            if (inp) {{
                inp.value = "{company_id}";
                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
            }}
        }}''')
        await asyncio.sleep(1)

        # استعلام شرکت
        await _query_sana(page, "actions.callLegalNationalityCode", bot, user_id, is_legal=True,
                          current_national_id=company_id, person_role=person_role, person_index=person_index)
        # شماره ثبت شخص حقوقی — همیشه صفر
        await _set_legal_record_no_zero(page)
        return

    # ── ادامه فرآیند عادی با کدملی نماینده ──

    # انتخاب رادیوباتن «شخص حقوقی» (value=3)
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdb3, input[value="3"][name="personType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # انتخاب «غیردولتی / خصوصی» (value=4)
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdbPrivate, input[value="4"][name="LegalPersonType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # وارد کردن شناسه ملی شرکت
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtLegalIrNationalityCode');
        if (inp) {{
            inp.value = "{company_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام شرکت
    await _query_sana(page, "actions.callLegalNationalityCode", bot, user_id, is_legal=True,
                      current_national_id=company_id, person_role=person_role, person_index=person_index)
    # شماره ثبت شخص حقوقی — همیشه صفر
    await _set_legal_record_no_zero(page)
    await asyncio.sleep(5)

    # انتخاب نوع نماینده (مدیرعامل یا نماینده)
    agent_value = AGENT_TYPE_VALUES.get(rep_type, AGENT_TYPE_VALUES["نماینده"])
    logging.info(f"[EZHHAR] انتخاب نوع نماینده: {rep_type} -> {agent_value}")
    
    # انتخاب نوع نماینده از dropdown
    selected = await page.evaluate(f'''() => {{
        // روش ۱: dropdown معمولی
        const sel = document.querySelector('#agentType, select[name="agentType"]');
        if (sel) {{
            sel.value = "{agent_value}";
            sel.dispatchEvent(new Event("change", {{ bubbles: true }}));
            return true;
        }}
        // روش ۲: ui-select یا ng-select
        const uiSelect = document.querySelector('.ui-select-toggle, [ng-model*="agentType"]');
        if (uiSelect) {{
            uiSelect.click();
            return false; // نیاز به جستجو در dropdown دارد
        }}
        return false;
    }}''')
    
    if not selected:
        # تلاش برای انتخاب از dropdown با جستجو
        await asyncio.sleep(1)
        await page.evaluate(f'''() => {{
            const choices = Array.from(document.querySelectorAll('.ui-select-choices-row, li[ng-repeat*="agentType"]'));
            const target = choices.find(el => el.innerText && el.innerText.includes("{rep_type}"));
            if (target) target.click();
        }}''')
    
    await asyncio.sleep(2)

    # وارد کردن کدملی نماینده
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtRealIrNationalityCode, #txtRealIrNationalityCode1');
        if (inp && inp.offsetParent !== null) {{
            inp.value = "{national_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام نماینده
    await _query_sana(page, "actions.callNationalityCode", bot, user_id,
                      current_national_id=national_id, person_role=person_role, person_index=person_index)


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int,
                               person_role: str = "", person_index: int = 0):
    """پر کردن کدملی وکیل در step وکیل"""
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtNationalityCode');
        if (inp) {{
            inp.value = "{national_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام وکیل از ثنا
    await _query_sana(page, "actions.getLawyerDataWithSana", bot, user_id,
                      current_national_id=national_id, person_role=person_role, person_index=person_index)


async def _query_sana(page, ng_click: str, bot: Bot, user_id: int, is_legal: bool = False, max_retries: int = 5,
                      current_national_id: str = "", person_role: str = "", person_index: int = 0):
    """
    استعلام از ثنا — کلیک دکمه استعلام و بررسی نتیجه.
    وقتی استعلام موفق باشد، فیلدهای صفحه پر و غیرقابل ویرایش می‌شوند.
    اگر خطای «اطلاعاتی با این شناسه ملی ثبت نشده است» یا «تاریخ تولد ارسالی
    مربوط به شماره ملی ... اشتباه است» ظاهر شود، EzhharSanaQueryError پرتاب می‌شود.
    اگر session منقضی شود، handle_session_expired صدا زده می‌شود.
    """
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EZHHAR] session renewed before query attempt {attempt+1}")
            continue

        clicked = await page.evaluate(f'''() => {{
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click}"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            // fallback: دکمه warning با tooltip استعلام
            const warns = Array.from(document.querySelectorAll('button.btn-warning'));
            const w = warns.find(b => !b.disabled && (
                (b.getAttribute("tooltip") || "").includes("استعلام") ||
                (b.getAttribute("title") || "").includes("استعلام")
            ));
            if (w) {{ w.click(); return true; }}
            return false;
        }}''')

        if not clicked:
            logging.warning(f"[EZHHAR] دکمه استعلام ({ng_click}) پیدا نشد — تلاش {attempt+1}")

        # صبر اولیه قبل از بررسی
        await asyncio.sleep(5)

        # منتظر ناپدید شدن لودینگ افقی بالای صفحه
        had_loading_error = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if had_loading_error:
            logging.warning(f"[EZHHAR] خطا بعد از لودینگ استعلام — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از استعلام
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EZHHAR] session renewed after query attempt {attempt+1}")
            continue

        # بررسی پاپ‌آپ خطای ثنا (شناسه ملی ثبت نشده یا تاریخ تولد اشتباه)
        popup_error = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' ').trim();
            return msg || null;
        }''')

        if popup_error:
            # بررسی session expiry در پاپ‌آپ
            is_session_expired = ("منقضی" in popup_error or "منقضي" in popup_error or
                                  "رایانه ای دیگر" in popup_error or "رایانه اي ديگر" in popup_error or
                                  "اعتبار ورود" in popup_error or "ورود قبلی" in popup_error)

            if is_session_expired:
                logging.warning(f"[EZHHAR] session expiry detected in popup after query")
                await _close_popup(page)
                await handle_session_expired(bot, user_id, page=page)
                continue

            is_not_registered = ("اطلاعاتی با این شناسه ملی ثبت نشده است" in popup_error or
                                  "اطلاعاتي با اين شناسه ملي ثبت نشده است" in popup_error)
            is_birthdate_error = ("تاریخ تولد ارسالی مربوط به شماره ملی" in popup_error and "اشتباه است" in popup_error) or \
                                 ("تاريخ تولد ارسالي مربوط به شماره ملي" in popup_error and "اشتباه است" in popup_error)

            if is_not_registered or is_birthdate_error:
                # بستن پاپ‌آپ
                await _close_popup(page)
                logging.warning(f"[EZHHAR] خطای ثنا برای شناسه {current_national_id}: {popup_error}")
                raise EzhharSanaQueryError(
                    popup_error,
                    national_id=current_national_id,
                    person_role=person_role,
                    person_index=person_index)

        # بستن هر پاپ‌آپ خطای دیگر
        await _close_popup(page)
        await asyncio.sleep(2)

        # بررسی موفقیت استعلام: فیلد ExtractedFromSana=1 یا disabled
        success = await page.evaluate('''() => {
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"]'
            );
            return disabled !== null;
        }''')
        if success:
            logging.info(f"[EZHHAR] استعلام موفق ({ng_click})")
            return

        # retry
        await asyncio.sleep(5)

    logging.warning(f"[EZHHAR] استعلام ({ng_click}) پس از {max_retries} تلاش نتیجه نداد")


async def _close_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _click_save_temp(page, bot: Bot, user_id: int, max_retries: int = 5):
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EZHHAR] session renewed before save attempt {attempt+1}")
            continue

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnSave');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "ثبت موقت", bot, user_id)

        # صبر اولیه
        await asyncio.sleep(5)

        # منتظر ناپدید شدن لودینگ
        had_loading_error = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if had_loading_error:
            logging.warning(f"[EZHHAR] خطا بعد از لودینگ ثبت موقت — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از ثبت
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EZHHAR] session renewed after save attempt {attempt+1}")
            continue

        await asyncio.sleep(5)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            // بررسی session expiry در popup
            const h2 = popup.querySelector('h2');
            if (h2) {
                const text = h2.innerText;
                if (text.includes("منقضی") || text.includes("منقضي") ||
                    text.includes("رایانه ای دیگر") || text.includes("اعتبار ورود")) {
                    return "session_expired";
                }
            }
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')

        if success == "session_expired":
            logging.warning(f"[EZHHAR] session expiry detected in popup after save")
            await _close_popup(page)
            await handle_session_expired(bot, user_id, page=page)
            continue

        if success:
            await _close_success_popup(page)
            return

        error_text = await _get_error_text(page)
        if error_text:
            # بررسی آیا error متن session expiry دارد
            if ("منقضی" in error_text or "منقضي" in error_text or
                "رایانه ای دیگر" in error_text or "اعتبار ورود" in error_text):
                logging.warning(f"[EZHHAR] session expiry in error text after save")
                await handle_session_expired(bot, user_id, page=page)
                continue
            raise EzhharFatalError(error_text)
        await asyncio.sleep(5)


async def _click_goto_main(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await soft_click_if_exists(page, "بازگشت به فهرست")


async def _upload_proxy_document(page, image_paths: list, bot: Bot, user_id: int):
    """آپلود مدرک نمایندگی (مقاوم) — بازنویسی‌شده بر اساس مسیر دقیق سامانه.

    مسیر دقیق:
      ۱. انتخاب «تصویر مدرک نمایندگی» از #attachmentType
      ۲. #txtNo = 0
      ۳. تقویم = امروز
      ۴. اگر >۱ فایل: #txt001 + #incAttach0  |  اگر ۱ فایل: اسکیپ
      ۵. #btnSaveDoc + انتظار لودینگ
      ۶. بستن پاپ‌آپ موفقیت
      ۷. editDocument روی ردیف
      ۸. آپلود با #files_multipleFileUploader
      ۹. #btnUploadAll
      ۱۰. تشخیص ورود همزمان → حذف + شروع از اول
      ۱۱. انتظار alertها + #btnApplyAll
    """
    from upload_helpers import (
        prepare_files_for_upload,
        click_save_doc_with_retry, close_success_popup, close_error_popup,
        wait_for_angular_idle, get_and_close_error_popup_text, detect_error_type,
        full_delete_attachment_row,
        wait_for_upload_confirmation, wait_for_alerts_to_disappear,
        click_apply_all_with_retry,
        wait_for_loading_bar, detect_concurrent_login_popup,
        click_edit_document_for_title)

    if not image_paths:
        logging.info("[EZHHAR] مدرک نمایندگی فایلی ندارد، رد شدن")
        return

    # آماده‌سازی فایل‌ها
    prepared, errors = await prepare_files_for_upload(image_paths, bot, user_id, "EZHHAR")
    if not prepared:
        logging.error(f"[EZHHAR] هیچ فایل معتبری برای مدرک نمایندگی وجود ندارد")
        return

    image_count = len(prepared)

    for attempt in range(1, 4):  # ۳ تلاش
        try:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info("[EZHHAR][منضمات] نشست قبل از مدرک نمایندگی تمدید شد")
                await asyncio.sleep(2)

            # مرحله ۱: انتخاب تصوير مدرک نمايندگي
            selected = await page.evaluate('''() => {
                const sel = document.querySelector('#attachmentType');
                if (!sel) return false;
                const opts = Array.from(sel.options);
                const opt = opts.find(o =>
                    o.text.includes("تصوير مدرک نمايندگي") ||
                    o.text.includes("تصویر مدرک نمایندگی")
                );
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change")); return true; }
                return false;
            }''')
            if not selected:
                logging.warning("[EZHHAR] گزینه تصویر مدرک نمایندگی پیدا نشد")
                return
            await asyncio.sleep(3)

            # مرحله ۲: #txtNo = 0
            await page.evaluate('''() => {
                const inp = document.querySelector('#txtNo');
                if (inp) { inp.value = "0"; inp.dispatchEvent(new Event("input", { bubbles: true })); }
            }''')
            await asyncio.sleep(1)

            # مرحله ۲.۵: #txtName = «مدرک نمایندگی» (الزامی)
            await page.evaluate('''() => {
                const inp = document.querySelector('#txtName');
                if (inp) {
                    inp.value = "مدرک نمایندگی";
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(1)

            # مرحله ۳: تقویم = امروز
            await page.evaluate('''() => {
                const calBtn = document.querySelector('button.btn-primary i.glyphicon-calendar');
                if (calBtn) calBtn.closest('button').click();
            }''')
            await asyncio.sleep(2)
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const todayBtn = btns.find(b => b.innerText && b.innerText.trim() === "امروز");
                if (todayBtn) todayBtn.click();
            }''')
            await asyncio.sleep(1)

            # مرحله ۴: تعداد صفحات — اگر ۱ فایل باشد اسکیپ
            if image_count > 1:
                await page.evaluate(f'''() => {{
                    const inp = document.querySelector('#txt001');
                    if (inp && !(inp.disabled)) {{
                        inp.value = "{image_count}";
                        inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    }}
                }}''')
                await asyncio.sleep(1)

                # افزودن پیوست
                await page.evaluate('''() => {
                    const btn = document.querySelector('#incAttach0');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await asyncio.sleep(3)
            else:
                logging.info(f"[EZHHAR] مدرک نمایندگی تک‌برگ ({image_count} فایل) — #txt001 و #incAttach0 اسکیپ شدند")

            # مرحله ۵: ذخیره سند + انتظار لودینگ
            save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="EZHHAR")
            if not save_ok:
                error_text = await get_and_close_error_popup_text(page)
                error_type = detect_error_type(error_text) if error_text else "save_failed"
                logging.warning(f"[EZHHAR] ذخیره مدرک نمایندگی ناموفق (نوع: {error_type}): {error_text}")
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(3)

            # مرحله ۶: بستن پاپ‌آپ موفقیت
            # (click_save_doc_with_retry معمولاً پاپ‌آپ را می‌بندد، ولی اطمینان می‌کنیم)
            await close_success_popup(page)
            await asyncio.sleep(1)

            # مرحله ۷+۸: کلیک editDocument روی ردیف + انتظار آپلودر
            # ⭐ از تابع جدید استفاده می‌کند: Playwright native click + انتظار #files_multipleFileUploader
            edit_ok = await click_edit_document_for_title(
                page, "مدرک نمایندگی", bot, user_id, prefix="EZHHAR")
            if not edit_ok:
                logging.warning("[EZHHAR] editDocument یا آپلودر برای مدرک نمایندگی ناموفق")
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                await asyncio.sleep(2)
                continue

            # مرحله ۹: آپلود فایل‌ها با #files_multipleFileUploader
            # (آپلودر توسط click_edit_document_for_title تضمین شده)
            try:
                file_input = page.locator('#files_multipleFileUploader')
                await file_input.set_input_files(prepared)
                logging.info(f"[EZHHAR] {len(prepared)} فایل با #files_multipleFileUploader انتخاب شدند")
            except Exception as e:
                logging.error(f"[EZHHAR] خطا در انتخاب فایل مدرک نمایندگی: {e}")
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(3)

            # مرحله ۱۰: کلیک آپلود همه (#btnUploadAll)
            # ⭐ از چند روش فال‌بک AngularJS استفاده می‌کند
            clicked_method = await page.evaluate('''() => {
                const btn = document.querySelector('#btnUploadAll');
                if (!btn || btn.disabled) return 'disabled_or_missing';

                // روش ۱: angular.element().scope().$apply
                try {
                    if (typeof angular !== 'undefined') {
                        const ngEl = angular.element(btn);
                        if (ngEl && ngEl.scope) {
                            const scope = ngEl.scope();
                            if (scope && scope.actions && typeof scope.actions.addMultipleDocumentFile === 'function') {
                                scope.$apply(() => { scope.actions.addMultipleDocumentFile(scope.directivesApiSingleUpload); });
                                return 'angular_apply_direct_call';
                            }
                            ngEl.scope().$apply(() => { btn.click(); });
                            return 'angular_apply_click';
                        }
                    }
                } catch(e) {}

                // روش ۲: mouse events + $apply
                try {
                    btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    if (typeof angular !== 'undefined') {
                        const rootScope = angular.element(document).scope();
                        if (rootScope) rootScope.$apply();
                    }
                    return 'mouse_events';
                } catch(e) {}

                btn.click();
                btn.dispatchEvent(new Event('click', { bubbles: true }));
                return 'fallback';
            }''')
            logging.info(f"[EZHHAR] آپلود همه (مدرک نمایندگی): روش {clicked_method}")

            # ⭐ انتظار واقعی برای شروع آپلود
            from upload_helpers import wait_for_loading_bar
            upload_started = False
            for _wait_i in range(15):
                await asyncio.sleep(1)
                ui_state = await page.evaluate('''() => {
                    const blockUI = document.querySelector('.blockUI');
                    if (blockUI && window.getComputedStyle(blockUI).display !== 'none') return 'blockui';
                    const bars = document.querySelectorAll('.progress-bar.progress-bar-striped.progress-bar-animated');
                    for (const bar of bars) {
                        const rect = bar.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return 'progress_bar';
                    }
                    const btn = document.querySelector('#btnUploadAll');
                    if (btn && btn.disabled) return 'btn_disabled';
                    const alerts = Array.from(document.querySelectorAll('.alert-success [ng-bind-html]'));
                    const upload_ok = alerts.some(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت ثبت گردید"));
                    if (upload_ok) return 'upload_confirmed';
                    return null;
                }''')
                if ui_state:
                    upload_started = True
                    logging.info(f"[EZHHAR] آپلود مدرک نمایندگی: وضعیت = {ui_state}")
                    if ui_state == 'upload_confirmed':
                        break
                    break

            if not upload_started:
                logging.warning("[EZHHAR] آپلود مدرک نمایندگی: هیچ علامتی از شروع آپلود دریافت نشد")

            # مرحله ۱۰.۱: تشخیص فوری ورود همزمان
            is_concurrent = await detect_concurrent_login_popup(page)
            if is_concurrent:
                logging.error("[EZHHAR] خطای ورود همزمان بعد از آپلود مدرک نمایندگی!")
                await check_and_handle_expiry(page, bot, user_id)
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                await asyncio.sleep(2)
                continue

            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info("[EZHHAR] نشست حین آپلود مدرک نمایندگی تمدید شد")
                await asyncio.sleep(3)
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                continue

            # مرحله ۱۱: انتظار تایید آپلود
            all_ok = await wait_for_upload_confirmation(page, image_count, bot, user_id, prefix="EZHHAR")
            if not all_ok:
                error_text = await get_and_close_error_popup_text(page)
                logging.warning(f"[EZHHAR] آپلود مدرک نمایندگی تایید نشد: {error_text}")
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
                await asyncio.sleep(2)
                continue

            # انتظار ناپدید شدن کامل alertها قبل از تایید
            alerts_gone = await wait_for_alerts_to_disappear(page, bot, user_id, prefix="EZHHAR")
            if not alerts_gone:
                logging.warning("[EZHHAR] alertهای مدرک نمایندگی ناپدید نشدند — ادامه با احتیاط")

            await wait_for_angular_idle(page)
            await asyncio.sleep(1)

            # اعمال همه (#btnApplyAll)
            confirmed = await click_apply_all_with_retry(page, image_count, bot, user_id, prefix="EZHHAR")
            if confirmed:
                await close_success_popup(page)
                await close_error_popup(page)
                await wait_for_angular_idle(page)
                logging.info("[EZHHAR] مدرک نمایندگی با موفقیت آپلود شد")
                return

            error_text = await get_and_close_error_popup_text(page)
            error_type = detect_error_type(error_text) if error_text else "unknown"
            if error_type == "session":
                # خطای ورود همزمان — فقط تلاش مجدد بدون حذف
                logging.warning("[EZHHAR] ورود همزمان در اعمال همه — تلاش مجدد")
                continue

            logging.warning(f"[EZHHAR] اعمال همه مدرک نمایندگی ناموفق: {error_text}")
            await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
            await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"[EZHHAR] خطا در آپلود مدرک نمایندگی (تلاش {attempt}): {e}")
            try:
                await full_delete_attachment_row(page, "مدرک نمایندگی", bot, user_id, "EZHHAR")
            except Exception:
                pass
            await asyncio.sleep(5)

    logging.error("[EZHHAR] مدرک نمایندگی پس از ۳ تلاش ناموفق")
    await bot.send_message(ADMIN_ID, f"❌ [EZHHAR] آپلود مدرک نمایندگی ناموفق | کاربر: {user_id}")

    try:
        from bug_reporter import report_bug
        await report_bug(bot, where="_upload_proxy_document", error=e,
                         user_id=user_id,
                         page=getattr(runtime_state, "sana_page", None))
    except Exception:
        pass


async def _upload_electronic_vakalaht(page, contract_number: str, lawyer_amount_value: int, bot: Bot, user_id: int):
    """آپلود وکالت‌نامه الکترونیک (مقاوم — با retry ذخیره و تشخیص خطا)"""
    from upload_helpers import click_save_doc_with_retry, close_success_popup, get_and_close_error_popup_text

    try:
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info("[EZHHAR][منضمات] نشست قبل از وکالت‌نامه الکترونیک تمدید شد")
            await asyncio.sleep(2)

        selected = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel) return false;
            const opts = Array.from(sel.options);
            const opt = opts.find(o =>
                o.text.includes("تصوير الكترونيك وكالت نامه") ||
                o.text.includes("تصویر الکترونیک وکالت نامه")
            );
            if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change")); return true; }
            return false;
        }''')
        if not selected:
            logging.warning("[EZHHAR] گزینه تصویر الکترونیک وکالت‌نامه پیدا نشد")
            return
        await asyncio.sleep(3)

        if contract_number:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtNo');
                if (inp) {{
                    inp.value = "{contract_number}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
        else:
            await page.evaluate('''() => {
                const inp = document.querySelector('#txtNo');
                if (inp) {
                    inp.value = "0";
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''')
        await asyncio.sleep(1)

        if lawyer_amount_value > 0:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtLawyerAmount');
                if (inp) {{
                    inp.removeAttribute('disabled');
                    inp.value = "{lawyer_amount_value}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

        # ذخیره سند با retry
        save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="EZHHAR")
        if not save_ok:
            error_text = await get_and_close_error_popup_text(page)
            logging.error(f"[EZHHAR] ذخیره وکالت‌نامه الکترونیک ناموفق: {error_text}")
            return
        logging.info("[EZHHAR] وکالت‌نامه الکترونیک با موفقیت ثبت شد")

    except Exception as e:
        logging.error(f"[EZHHAR] خطا در آپلود وکالت‌نامه الکترونیک: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_upload_electronic_vakalaht", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass


async def _upload_other_attachment(page, title: str, image_paths: list, bot: Bot, user_id: int) -> dict:
    """
    آپلود سایر ضمائم (مقاوم — از upload_helpers).

    ⭐ تغییر مهم: این تابع هیچ‌وقت Exception نمی‌اندازد.
    - اگر upload_helpers موجود نباشد (ModuleNotFoundError) → error_type='module_missing'
    - اگر خطای کدنویسی رخ دهد → error_type='code_error'
    - اگر آپلود شکست خورد → error_type از upload_helpers

    بازگشت:
        {
            "success": bool,
            "error": str|None,
            "error_type": str|None,  # 'module_missing', 'code_error', 'session', 'timeout', 'general'
        }
    """
    result = {"success": False, "error": None, "error_type": None}

    if not image_paths:
        result["success"] = True  # هیچ فایلی نیست — موفق فرض کن
        return result

    try:
        from upload_helpers import resilient_upload_attachment
    except ImportError as e:
        # ⭐ خطای کدنویسی — نباید retry شود
        result["error"] = f"ModuleNotFoundError: upload_helpers پیدا نشد — {e}"
        result["error_type"] = "module_missing"
        logging.error(f"[EZHHAR] {result['error']}")
        await bot.send_message(
            ADMIN_ID,
            f"🚨 [EZHHAR] خطای کدنویسی: فایل upload_helpers.py روی سرور موجود نیست!\n"
            f"کاربر: {user_id} | عنوان پیوست: {title}\n"
            f"خطا: {e}"
        )
        return result
    except Exception as e:
        result["error"] = f"خطا در import upload_helpers: {e}"
        result["error_type"] = "code_error"
        logging.error(f"[EZHHAR] {result['error']}")
        return result

    try:
        upload_result = await resilient_upload_attachment(
            page, title, image_paths, bot, user_id,
            prefix="EZHHAR")

        if upload_result["success"]:
            logging.info(f"[EZHHAR] آپلود سایر ضمائم [{title}] موفق")
            result["success"] = True
            return result

        # آپلود ناموفق — بدون raise، فقط گزارش
        result["error"] = upload_result.get("error", "نامشخص")
        result["error_type"] = upload_result.get("error_type", "unknown")
        logging.error(
            f"[EZHHAR] آپلود سایر ضمائم [{title}] ناموفق: {result['error']} (نوع: {result['error_type']})"
        )
        await bot.send_message(
            ADMIN_ID,
            f"❌ [EZHHAR] آپلود پیوست [{title}] ناموفق\n"
            f"کاربر: {user_id} | خطا: {result['error'][:200]}\n"
            f"نوع خطا: {result['error_type']}"
        )
        return result

    except Exception as e:
        # هر استثنای غیرمنتظره — بدون raise
        result["error"] = f"استثنا در آپلود: {e}"
        result["error_type"] = "code_error"
        logging.error(f"[EZHHAR] {result['error']}", exc_info=True)
        return result


async def _upload_attachment_with_retry(
    page,
    title: str,
    image_paths: list,
    bot: Bot,
    user_id: int,
    bill_no: str = None,
    max_retries: int = 3) -> dict:
    """
    آپلود یک ضمیمه با retry محلی — بدون این‌که کل ثبت از اول شروع شود.

    ⭐ تفاوت کلیدی با نسخه‌ی قبل:
    - قبلاً اگر _upload_other_attachment Exception می‌انداخت، کل process_ezhharnameh_task
      از اول شروع می‌شد (goto Offices/Index → کلیک «ارایه و پیگیری» → ...)
    - حالا: فقط این ضمیمه retry می‌شود، و اگر واقعاً نشد، به کاربر/مدیر گزارش می‌دهد
      و ادامه می‌دهد (نه این‌که کل ثبت را ری‌استارت کند)

    retry فقط در این موارد انجام می‌شود:
    - error_type == 'session' (خطای ورود همزمان — لاگین مجدد + retry)
    - error_type == 'timeout' (تایم‌اوت — retry با تأخیر بیشتر)

    retry انجام نمی‌شود در:
    - error_type == 'module_missing' (خطای کدنویسی — باید فایل کپی شود)
    - error_type == 'code_error' (خطای کدنویسی)
    - error_type در ('validation', 'file_size', 'file_type', 'page_count') (خطای فایل)
    """
    last_result = {"success": False, "error": None, "error_type": None}

    for attempt in range(1, max_retries + 1):
        logging.info(f"[EZHHAR] ─── آپلود ضمیمه [{title}] — تلاش {attempt}/{max_retries} ───")

        last_result = await _upload_other_attachment(page, title, image_paths, bot, user_id)

        if last_result["success"]:
            return last_result

        error_type = last_result.get("error_type", "unknown")
        error_msg = last_result.get("error", "نامشخص")

        # تصمیم‌گیری برای retry
        should_retry = error_type in ("session", "timeout", "general", "unknown")
        is_code_error = error_type in ("module_missing", "code_error")

        if is_code_error:
            # خطای کدنویسی — هیچ فایده‌ای ندارد retry کنیم
            logging.error(
                f"[EZHHAR] خطای کدنویسی در آپلود [{title}] — بدون retry: {error_msg}"
            )
            # اطلاع به کاربر
            await bot.send_message(
                user_id,
                f"⚠️ *خطای فنی در آپلود پیوست*\n\n"
                f"عنوان: {title}\n"
                f"کد رهگیری: `{bill_no or 'نامشخص'}`\n\n"
                f"لطفاً به پشتیبانی اطلاع دهید.\n"
                f"📞 واتساپ: 09306186888")
            return last_result

        if not should_retry:
            # خطای فایل/اعتبارسنجی — retry فایده‌ای ندارد
            logging.error(
                f"[EZHHAR] خطای غیرقابل-retry در آپلود [{title}] (نوع: {error_type}): {error_msg}"
            )
            return last_result

        if attempt < max_retries:
            logging.warning(
                f"[EZHHAR] آپلود [{title}] ناموفق (تلاش {attempt}/{max_retries}) — retry بعد از تأخیر..."
            )
            # تأخیر تصاعدی: ۱۰، ۲۰، ۳۰ ثانیه
            await asyncio.sleep(10 * attempt)
            # اطمینان از بازگشت به فهرست قبل از retry
            try:
                from browser_helpers import soft_click_if_exists
                await soft_click_if_exists(page, "بازگشت به فهرست")
                await asyncio.sleep(3)
            except Exception:
                pass
        else:
            logging.error(
                f"[EZHHAR] آپلود [{title}] بعد از {max_retries} تلاش ناموفق — توقف"
            )
            # اطلاع به کاربر + مدیر
            await bot.send_message(
                user_id,
                f"⚠️ *آپلود پیوست ناموفق*\n\n"
                f"عنوان: {title}\n"
                f"کد رهگیری: `{bill_no or 'نامشخص'}`\n"
                f"خطا: {error_msg[:200]}\n\n"
                f"لطفاً به پشتیبانی اطلاع دهید.\n"
                f"📞 واتساپ: 09306186888")
            await bot.send_message(
                ADMIN_ID,
                f"❌ [EZHHAR] آپلود [{title}] ناموفق بعد از {max_retries} تلاش\n"
                f"کاربر: {user_id} | کد: {bill_no}\n"
                f"خطا: {error_msg[:200]}"
            )

    return last_result


async def _click_preparation(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """کلیک «تایید اطلاعات» در مرحله آماده‌سازی جهت دریافت وجه.
    ابتدا دکمه #btnCalculateCash (تایید اطلاعات / setPetitionToReadyForPaymentState) کلیک می‌شود.
    سپس در پاپ‌آپ sweet-alert دکمه «تایید اطلاعات» زده می‌شود.
    سپس پاپ‌آپ موفقیت با «بستن» بسته می‌شود.
    """
    for attempt in range(max_retries):
        await _close_popup(page)
        await asyncio.sleep(2)

        # کلیک دکمه «تایید اطلاعات» (setPetitionToReadyForPaymentState)
        clicked = await page.evaluate('''() => {
            // اول تلاش با id
            const btn = document.querySelector('#btnCalculateCash');
            if (btn && !btn.disabled) { btn.click(); return true; }
            // fallback: دکمه با ng-click=setPetitionToReadyForPaymentState
            const btns = Array.from(document.querySelectorAll('button[ng-click*="setPetitionToReadyForPaymentState"]'));
            if (btns.length > 0) { btns[0].click(); return true; }
            // fallback: دکمه با text «تایید اطلاعات»
            const textBtns = Array.from(document.querySelectorAll('button'));
            const tb = textBtns.find(b => b.innerText && b.innerText.trim().includes("تایید اطلاعات") && !b.disabled);
            if (tb) { tb.click(); return true; }
            return false;
        }''')

        if not clicked:
            logging.warning(f"[EZHHAR] دکمه تایید اطلاعات (preparation) پیدا نشد — تلاش {attempt+1}")

        await asyncio.sleep(40 if attempt > 0 else 12)

        # بررسی پاپ‌آپ تایید — باید «تایید اطلاعات» را بزنیم
        confirm_clicked = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const h2 = popup.querySelector('h2');
            if (h2 && h2.innerText.includes("آیا اطلاعات")) {
                const btn = popup.querySelector('button.confirm');
                if (btn) { btn.click(); return true; }
            }
            return false;
        }''')

        if confirm_clicked:
            await asyncio.sleep(5)

        # بررسی پاپ‌آپ موفقیت — «بستن» را بزنیم
        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const h2 = popup.querySelector('h2');
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && (h2.innerText.includes("آماده سازي") || h2.innerText.includes("بررسی و تایید"));
        }''')

        if success:
            # کلیک «بستن»
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(2)
            return True

        # بستن هر پاپ‌آپ خطای دیگر
        await _close_popup(page)
        await asyncio.sleep(30)
        await _close_success_popup(page)

    return False


async def _calculate_cost(page, bot: Bot, user_id: int, max_retries: int = 3) -> dict:
    """محاسبه هزینه اظهارنامه — پارس جدول هزینه‌ها و محاسبه مبلغ نهایی.

    جدول هزینه شامل چند ردیف با ستون مبلغ است.
    دو مبلغ کل وجود دارد:
      - costSum: مبلغ جمع کل (td سبز) — مقدار نمایش‌داده‌شده در جدول
      - mainTotal: جمع مبالغ تمام ردیف‌های فردی (td قرمز) — مبلغ اصلی فرمول

    منطق محاسبه:
      1. استخراج costSum از td سبز و mainTotal از جمع td های قرمز
      2. یافتن ۳ ردیف خاص و جمع مبالغ آن‌ها:
         - هزینه تطبیق اوراق با اصل (ردیف ۱)
         - هزینه خدمات الکترونیک قضایی (ردیف ۷)
         - هزینه پیامک اطلاع‌رسانی (ردیف ۸)
      3. فرمول:
         net = mainTotal − excluded_sum
         rounded = round_up_10k(net)
         intermediate = rounded + 450,000
         final = round_up_10k(intermediate + mainTotal)

    اگر جدول نمایش داده نشد، بعد از تلاش‌ها "cost_error" برمی‌گرداند.
    """
    for attempt in range(max_retries):
        await _close_popup(page)
        await asyncio.sleep(2)

        # بررسی آیا جدول هزینه قبلاً نمایش داده شده
        table_visible = await page.evaluate('''() => {
            const tds = Array.from(document.querySelectorAll('table td.color-green, table td.color-red'));
            return tds.length > 0;
        }''')

        if not table_visible:
            # کلیک دکمه «محاسبه هزینه دادرسی و تعرفه خدمات»
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnCalculateCash');
                if (btn && !btn.disabled) { btn.click(); return true; }
                const btns = Array.from(document.querySelectorAll('button[ng-click*="paymentCost"]'));
                if (btns.length > 0) { btns[0].click(); return true; }
                // fallback: text match
                const all = Array.from(document.querySelectorAll('button'));
                const tb = all.find(b => b.innerText && b.innerText.includes("محاسبه هزینه دادرسی") && !b.disabled);
                if (tb) { tb.click(); return true; }
                return false;
            }''')
            await asyncio.sleep(40)

            # ── بستن پاپ‌آپ خطا (اگر ظاهر شد) و کلیک مجدد ──────────
            error_popup_closed = await page.evaluate('''() => {
                // بستن sweet-alert خطا
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const h2 = popup.querySelector('h2');
                    if (h2 && !h2.innerText.includes("آماده")) {
                        const closeBtn = popup.querySelector('button.confirm, button.btn-info');
                        if (closeBtn) { closeBtn.click(); return true; }
                    }
                }
                // بستن alert-danger خطا
                const alertEl = document.querySelector('.alert-danger');
                if (alertEl && alertEl.offsetParent !== null) {
                    const closeBtns = Array.from(document.querySelectorAll('button'));
                    const c = closeBtns.find(b => b.innerText && b.innerText.trim() === "بستن");
                    if (c) { c.click(); return true; }
                }
                return false;
            }''')
            if error_popup_closed:
                logging.info(f"[EZHHAR] پاپ‌آپ خطا بسته شد — کلیک مجدد دکمه محاسبه هزینه")
                await asyncio.sleep(3)
                # کلیک مجدد دکمه محاسبه هزینه بعد از بستن خطا
                await page.evaluate('''() => {
                    const btn = document.querySelector('#btnCalculateCash');
                    if (btn && !btn.disabled) { btn.click(); return; }
                    const btns = Array.from(document.querySelectorAll('button[ng-click*="paymentCost"]'));
                    if (btns.length > 0) { btns[0].click(); return; }
                    const all = Array.from(document.querySelectorAll('button'));
                    const tb = all.find(b => b.innerText && b.innerText.includes("محاسبه هزینه دادرسی") && !b.disabled);
                    if (tb) { tb.click(); }
                }''')
                await asyncio.sleep(40)

        # اگر هنوز جدول نیست و تلاش‌های بیشتری باقی‌مانده، با فاصله ۴۰ ثانیه دوباره تلاش کن
        if attempt < 2:
            table_visible = await page.evaluate('''() => {
                const tds = Array.from(document.querySelectorAll('table td.color-green, table td.color-red'));
                return tds.length > 0;
            }''')
            if not table_visible:
                logging.warning(f"[EZHHAR] جدول هزینه نمایش داده نشد — تلاش مجدد با فاصله ۴۰ ثانیه")
                await asyncio.sleep(40)
                await page.evaluate('''() => {
                    const btn = document.querySelector('#btnCalculateCash');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await asyncio.sleep(10)

        await _close_popup(page)

        # استخراج تمام مبالغ از جدول
        cost_data = await page.evaluate('''() => {
            // استخراج مبلغ جمع کل (td.color-green)
            const greenTds = Array.from(document.querySelectorAll('table td.color-green'));
            let costSum = 0;
            for (const td of greenTds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 0) {
                    costSum = parseInt(text);
                }
            }

            // استخراج مبالغ ردیف‌ها (td.color-red)
            const redTds = Array.from(document.querySelectorAll('table td.color-red'));
            let rowAmounts = [];
            for (const td of redTds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 0) {
                    rowAmounts.push(parseInt(text));
                }
            }

            // استخراج نام هزینه‌ها
            const labels = [];
            const rows = Array.from(document.querySelectorAll('table tr'));
            for (const row of rows) {
                const tds = Array.from(row.querySelectorAll('td'));
                if (tds.length >= 3) {
                    const label = tds[1].innerText.trim();
                    const amount = tds[2].innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                    if (label && /^[0-9]+$/.test(amount) && parseInt(amount) > 0) {
                        labels.push({label, amount: parseInt(amount)});
                    }
                }
            }

            // استخراج مبلغ اصلی = جمع مبالغ تمام ردیف‌ها (red tds)
            // این مبلغ همان مجموع costSum قبل از کسر است — فرمول روی این مبلغ اعمال می‌شود
            let mainTotal = 0;
            for (const amt of rowAmounts) {
                mainTotal += amt;
            }
            // fallback: اگر ردیفی پیدا نشد، از td سبز استفاده کن
            if (mainTotal === 0) {
                mainTotal = costSum;
            }

            return {
                costSum: costSum,
                mainTotal: mainTotal,
                rowAmounts: rowAmounts,
                labels: labels
            };
        }''')

        if cost_data and cost_data.get("costSum", 0) > 0:
            cost_sum = cost_data["costSum"]
            main_total = cost_data.get("mainTotal", cost_sum)
            labels = cost_data.get("labels", [])

            logging.info(f"[EZHHAR] costSum={cost_sum}, mainTotal={main_total}, labels={labels}")

            # رند بالا به نزدیک‌ترین ۱۰,۰۰۰ ریال
            def round_up_to_ten_thousand(amount: int) -> int:
                if amount <= 0:
                    return 0
                return ((amount + 9999) // 10000) * 10000

            # یافتن مبالغ ۳ ردیف خاص از جدول بر اساس نام
            # ۱. هزینه تطبیق اوراق با اصل
            # ۲. هزینه خدمات الکترونیک قضایی
            # ۳. هزینه پیامک اطلاع رسانی
            EXCLUDED_LABELS = [
                "تطبيق اوراق",       # هزینه تطبیق اوراق با اصل
                "الكترونيك قضايي",  # هزینه خدمات الکترونیک قضایی
                "پيامك",             # هزینه پیامک اطلاع رسانی
            ]

            excluded_sum = 0
            for item in labels:
                label_text = item.get("label", "")
                for excl in EXCLUDED_LABELS:
                    if excl in label_text:
                        excluded_sum += item.get("amount", 0)
                        break

            # فرمول محاسبه هزینه اظهارنامه:
            # قدم ۱: مبلغ اصلی منهای ۳ هزینه کسرشونده
            net_amount = main_total - excluded_sum
            # قدم ۲: رند به بالا به نزدیک‌ترین ۱۰,۰۰۰
            rounded_net = round_up_to_ten_thousand(net_amount)
            # قدم ۳: اضافه کردن ۴۵۰,۰۰۰ ریال
            intermediate = rounded_net + 450_000
            # قدم ۴: جمع با مبلغ اصلی
            total_with_original = intermediate + main_total
            # قدم ۵: رند نهایی به بالا به نزدیک‌ترین ۱۰,۰۰۰
            final_total = round_up_to_ten_thousand(total_with_original)

            logging.info(
                f"[EZHHAR] محاسبه هزینه: mainTotal={main_total}, "
                f"excluded_sum={excluded_sum}, net={net_amount}, "
                f"rounded_net={rounded_net}, intermediate={intermediate}, "
                f"total_with_original={total_with_original}, final_total={final_total}"
            )

            return {
                "cost_sum": cost_sum,
                "main_total": main_total,
                "excluded_sum": excluded_sum,
                "net_amount": net_amount,
                "rounded_net": rounded_net,
                "intermediate": intermediate,
                "total_with_original": total_with_original,
                "final_total": final_total,
                "labels": labels,
            }

        await asyncio.sleep(10)

    # جدول هزینه پس از تلاش‌ها نمایش داده نشد
    return {"cost_sum": 0, "final_total": 0, "cost_error": True}


async def _print_ezhharnameh(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    pdf_path = f"ezhharnameh_{bill_no}.pdf"
    try:
        async def click_print():
            await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && (
                    el.innerText.includes("چاپ اوليه") || el.innerText.includes("چاپ اولیه")
                ));
                if (t) {
                    const box = t.closest('.box');
                    if (box) box.click();
                }
            }''')

        async with browser_context.expect_page(timeout=20000) as new_page_info:
            await click_print()

        print_page = await new_page_info.value
        await print_page.wait_for_load_state("load", timeout=30000)
        await asyncio.sleep(8)
        await check_and_handle_expiry(print_page, bot, user_id)
        await print_page.pdf(path=pdf_path, format="A4")
        await print_page.close()
    except Exception as e:
        logging.error(f"[EZHHAR] خطا در چاپ: {e}")
        try:
            await page.pdf(path=pdf_path, format="A4")
        except Exception:
            pass

        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="click_print", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
    return pdf_path


async def _extract_bill_no(page) -> str:
    try:
        val = await page.evaluate('''() => {
            const inp = document.querySelector('#txtBillNo, #txtPetitionNo');
            return inp ? inp.value : "";
        }''')
        return val or "نامشخص"
    except Exception:
        return "نامشخص"


async def _close_success_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _get_error_text(page):
    text = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        const btn = popup.querySelector('button.confirm');
        if (btn) btn.click();
        return msg || null;
    }''')
    if text:
        await asyncio.sleep(1)
    return text


async def _download_images(bot: Bot, file_ids: list, user_id: int) -> list:
    paths = []
    for i, file_id in enumerate(file_ids):
        try:
            file_info = await bot.get_file(file_id)
            ext = "jpg"
            if file_info.file_path:
                ext = file_info.file_path.split(".")[-1].lower()
                if ext not in ("jpg", "jpeg", "png"):
                    ext = "jpg"
            path = f"ezhhar_img_{user_id}_{i}.{ext}"
            await bot.download_file(file_info.file_path, path)
            paths.append(path)
        except Exception as e:
            logging.error(f"[EZHHAR] خطا در دانلود تصویر {i}: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_download_images", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
    return paths


async def _auto_delete_pending_ezhhar(bot: Bot, user_id: int, timeout_seconds: int = 3600):
    """پس از timeout_seconds ثانیه، اگر هنوز درخواست اظهارنامه در انتظار ویرایش شناسه ملی باشد، حذف می‌شود."""
    await asyncio.sleep(timeout_seconds)
    pending = runtime_state.pending_ezhhar_sana_fix.pop(user_id, None)
    if pending:
        logging.info(f"[EZHHAR] حذف خودکار درخواست اظهارنامه کاربر {user_id} بعد از {timeout_seconds} ثانیه بدون اقدام.")
        try:
            await bot.send_message(
                user_id,
                "⏰ *درخواست اظهارنامه شما حذف شد.*\n\n"
                "بعد از ۱ ساعت هیچ اقدامی انجام نشد و درخواست به‌صورت خودکار حذف گردید.\n"
                "در صورت نیاز، مجدداً از منوی اصلی اقدام فرمایید.")
        except Exception as e:
            logging.error(f"[EZHHAR] خطا در ارسال پیام حذف خودکار به کاربر {user_id}: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_auto_delete_pending_ezhhar", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
