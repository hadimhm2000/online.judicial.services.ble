"""
سناریوی کامل ثبت لایحه در سامانه قضایی ثنا.
"""
import asyncio
import logging
import os
import time
import base64
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from admin_db import register_case
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, soft_click_if_exists,
    goto_url_with_retry, human_delay, force_click_by_text,
    safe_click_by_text, safe_type, wait_for_angular_idle,
    wait_for_horizontal_loading_bar, handle_session_expired)


class LavayehFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


TITLE_SEARCH_MAP = {
    "لایحه دفاعیه":                 ("دفا",    0),
    "صدور اجرائیه":                  ("اجرائ",  0),
    "اعتراض به نظر کارشناس":         ("کارشن",  1),
    "اعتراض به قرار رد دفتر":        ("قرار",   1),
    "درخواست ممنوعیت از خروج کشور":  ("ممن",    0),
    "درخواست کپی از مدارک پرونده":   ("کپی",    0),
    "درخواست مطالعه پرونده":         ("مطالع",  0),
    "سایر عناوین":                   ("دفا",    0),
}

AGENT_TYPE_VALUES = {
    "مدیرعامل":  "0091000010000008",
    "نماینده":   "0091000010000007",
}


def _text_to_editor_html(text: str) -> str:
    """
    متن خام دریافتی از کاربر (تلگرام) را به HTML تبدیل می‌کند طوری که
    فاصله‌ها و اینتر (خط جدید)های موجود در متن، دقیقاً همانطور که کاربر
    فرستاده حفظ شوند و در ادیتور سامانه (contenteditable) از بین نروند.
    """
    if not text:
        return "<p><br></p>"

    lines = text.split("\n")
    parts = []
    for line in lines:
        # escape می‌کنیم تا کاراکترهای HTML (< > &) متن کاربر، ساختار صفحه را خراب نکنند
        escaped = html_lib.escape(line, quote=False)

        # حفظ فاصله‌های ابتدای خط و فاصله‌های متوالی (که مرورگر معمولاً collapse می‌کند)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")

        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")

    return "".join(parts)


async def process_lavayeh_task(data: dict, bot: Bot):
    sana_page       = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id         = data["user_id"]

    title        = data.get("lavayeh_title", "لایحه دفاعیه")
    system_title = data.get("lavayeh_system_title", "لایحه دفاعیه")
    tracking_code = data.get("lavayeh_tracking_code", "")
    province      = data.get("lavayeh_province", "")
    row_number    = data.get("lavayeh_row_number", 1)
    persons       = data.get("lavayeh_persons", [])
    lavayeh_text  = data.get("lavayeh_text", "")
    attachment_groups = data.get("lavayeh_attachments", [])
    has_images    = len(attachment_groups) > 0
    total_image_count = sum(len(g.get("images", [])) for g in attachment_groups)
    total_image_count = sum(len(g.get("images", [])) for g in attachment_groups)
    
    # بررسی روش ثبت: شماره پرونده یا شماره بایگانی
    tracking_method = data.get("tracking_method", "case_number")
    archive_number = data.get("lavayeh_archive_number", "")
    branch_name = data.get("lavayeh_branch_name", "")
    branch_code = data.get("lavayeh_branch_code", "")

    logging.info(
        f"[LAVAYEH] user={user_id} title={title} code={tracking_code} "
        f"province={province} row={row_number} persons={len(persons)} "
        f"attachment_groups={len(attachment_groups)} images={total_image_count}"
    )

    await bot.send_message(
        user_id,
        f"⏳ در حال ثبت لایحه...\nعنوان: *{title}* | کد: `{tracking_code}`")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [LAVAYEH] شروع ثبت برای کاربر {user_id}\n"
        f"عنوان: {title} | کد: {tracking_code} | استان: {province}"
    )

    max_attempts = 3
    lavayeh_bill_no = ""
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
            if not ok:
                return
            await human_delay(3.0, 5.0)

            await _click_menu_item(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            search_kw, row_idx = TITLE_SEARCH_MAP.get(title, ("دفا", 0))
            await _select_bill_type(sana_page, search_kw, row_idx, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            await _click_taqdim_lavayeh(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            await _click_step_box(sana_page, "ثبت و ويرايش لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # بررسی روش ثبت: شماره پرونده یا شماره بایگانی
            if tracking_method == "archive_number":
                # مسیر شماره بایگانی
                # کلیک روی رادیو باتن شماره بایگانی
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('input[type="radio"][name="rdbCaseInfo"][value="2"]#rdbCaseInfo2');
                    if (rdb) rdb.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)
                
                # وارد کردن کد ۵ رقمی واحد قضایی (بر اساس شعبه انتخابی)
                if branch_code:
                    await _fill_input(sana_page, "#txtCourtCode", branch_code, bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                
                # وارد کردن شماره بایگانی
                await _fill_input(sana_page, "#txtCaseArchiveNo", archive_number, bot, user_id)
                await resilient_sleep(sana_page, 1, bot, user_id)
                
                # کلیک روی دکمه صحت‌سنجی
                await _click_validate_with_retry_archive(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 10, bot, user_id)
                
                # بررسی موفقیت
                table_ok = await _wait_for_case_table(sana_page, bot, user_id)
                if not table_ok:
                    await bot.send_message(
                        user_id,
                        "⚠️ *استعلام پرونده با خطا مواجه شد.*\n\n"
                        "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
                        "🔢 شماره بایگانی\n🏛 کد شعبه\n\n"
                        "سپس مجدداً «ثبت لایحه» را شروع کنید.")
                    await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی بایگانی کاربر {user_id} ناموفق.")
                    runtime_state.active_lavayeh_users.discard(user_id)
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=archive_number, doc_name=title,
                        note="صحت‌سنجی شماره بایگانی ناموفق"
                    )
                    await register_case(
                        event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                        trackingCode=archive_number or "", documentCategory=title,
                        errorDetails="صحت‌سنجی شماره بایگانی ناموفق", errorStep="VALIDATE_ARCHIVE")
                    return
            else:
                # مسیر شماره پرونده (کد قبلی)
                await _fill_input(sana_page, "#txtCaseNo", tracking_code, bot, user_id)
                await resilient_sleep(sana_page, 1, bot, user_id)

                await _fill_input(sana_page, "#txtSubNo", str(row_number), bot, user_id)
                await resilient_sleep(sana_page, 1, bot, user_id)

                await _select_province(sana_page, province, bot, user_id)
                await resilient_sleep(sana_page, 2, bot, user_id)

                await _click_validate_with_retry(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 10, bot, user_id)

                table_ok = await _wait_for_case_table(sana_page, bot, user_id)
                if not table_ok:
                    await bot.send_message(
                        user_id,
                        "⚠️ *استعلام پرونده با خطا مواجه شد.*\n\n"
                        "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
                        "🔢 شماره پرونده\n🔢 ردیف فرعی\n🏙 استان\n\n"
                        "سپس مجدداً «ثبت لایحه» را شروع کنید.")
                    await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی پرونده کاربر {user_id} ناموفق.")
                    runtime_state.active_lavayeh_users.discard(user_id)
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=tracking_code, doc_name=title,
                        note="صحت‌سنجی پرونده ناموفق"
                    )
                    await register_case(
                        event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                        trackingCode=tracking_code or "", documentCategory=title,
                        errorDetails="صحت‌سنجی پرونده ناموفق", errorStep="VALIDATE_CASE")
                    return


            await _click_step_label(sana_page, "ارائه كننده لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for person in persons:
                ptype = person.get("person_type", "شخص حقیقی")

                if ptype == "وکیل":
                    # برای وکیل از رادیو باتن value="6" استفاده می‌کنیم
                    await _click_add_person(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    # کلیک روی رادیو باتن وکیل — با fallback
                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[type="radio"][name="personType"][value="6"]#rdb6');
                        if (rdb) {
                            rdb.click();
                        } else {
                            const rdb2 = document.querySelector('input[type="radio"][value="6"]');
                            if (rdb2) rdb2.click();
                        }
                    }''')
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await wait_for_angular_idle(sana_page)

                    # پر کردن کدملی وکیل با روش چندگانه
                    filled = await _fill_national_id_field(sana_page, person["national_id"], bot, user_id)
                    if not filled:
                        logging.error(
                            f"[LAVAYEH] _fill_national_id_field: "
                            f"همه روش‌ها برای کدملی '{person['national_id']}' ناموفق بودند."
                        )
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(sana_page, "actions.callNationalityCode", bot, user_id)
                    await resilient_sleep(sana_page, 8, bot, user_id)

                elif ptype == "شخص حقیقی":
                    await _click_add_person(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    await _fill_input(sana_page, "#txtRealIrNationalityCode1", person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(sana_page, "actions.callNationalityCode", bot, user_id)
                    await resilient_sleep(sana_page, 8, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_person(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[type="radio"][value="3"]');
                        if (rdb) rdb.click();
                    }''')
                    await resilient_sleep(sana_page, 2, bot, user_id)

                    await _fill_input(sana_page, "#txtLegalIrNationalityCode", person.get("company_id", ""), bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(sana_page, "actions.callLegalNationalityCode", bot, user_id)
                    await resilient_sleep(sana_page, 8, bot, user_id)

                    # شماره ثبت شخص حقوقی (#txtLegalIrShSabt / RecordNo) — سامانه این فیلد را
                    # برای شخص حقوقی خصوصی اجباری می‌کند؛ همیشه «0» می‌گذاریم.
                    for _ in range(8):
                        _rec_ok = await sana_page.evaluate('''() => {
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
                        if _rec_ok:
                            logging.info("[LAVAYEH] شماره ثبت شخص حقوقی روی «0» تنظیم شد")
                            break
                        await resilient_sleep(sana_page, 1, bot, user_id)

                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[type="radio"][value="7"]');
                        if (rdb) rdb.click();
                    }''')
                    await resilient_sleep(sana_page, 2, bot, user_id)

                    rep_type = person.get("representative_type", "نماینده")
                    agent_value = AGENT_TYPE_VALUES.get(rep_type, "0091000010000007")
                    await sana_page.evaluate(f'''() => {{
                        const sel = document.querySelector('select[ng-model="viewModel.currentDeclarantPerson.AgentTypeId"]');
                        if (sel) {{
                            sel.value = "{agent_value}";
                            sel.dispatchEvent(new Event("change"));
                        }}
                    }}''')
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _fill_input(sana_page, "#txtRealIrNationalityCode", person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(
                        sana_page, "actions.callNationalityCode", bot, user_id,
                        btn_id="btnCallNationalityCode"
                    )
                    await resilient_sleep(sana_page, 8, bot, user_id)

            await _click_step_label(sana_page, "متن", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # استفاده از HTML ورد در صورت وجود، در غیر اینصورت تبدیل متنی
            stored_html = data.get("lavayeh_text_html", "")
            lavayeh_text_html = stored_html if stored_html else _text_to_editor_html(lavayeh_text)
            await sana_page.evaluate('''(html) => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    editor.focus();
                    editor.innerHTML = html;
                    editor.dispatchEvent(new Event("input", { bubbles: true }));
                    editor.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', lavayeh_text_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

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
                    editor.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(0.5)

            clicked_h3 = await sana_page.evaluate('''() => {
                const btn = document.querySelector('button[name="h3"]') ||
                            Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if not clicked_h3:
                logging.warning(f"[LAVAYEH] دکمه H3 پیدا نشد (user={user_id})")
            await resilient_sleep(sana_page, 1, bot, user_id)

            await _click_save_temp_with_retry(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            lavayeh_bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[LAVAYEH] bill_no: {lavayeh_bill_no} (user={user_id})")

            # ذخیره کدرهگیری در گوگل شیت + اطلاع به مدیر
            if lavayeh_bill_no:
                await log_event("ثبت موقت", "لایحه", str(user_id), user_id,
                                tracking_code=lavayeh_bill_no, doc_name=title,
                                note=f"لایحه ثبت موقت شد | عنوان: {title}")
                await register_case(
                    event_type="ثبت موقت", full_name=str(user_id), user_id=user_id,
                    trackingCode=lavayeh_bill_no or "", documentCategory=title,
                    note=f"لایحه ثبت موقت شد | عنوان: {title}")
                await bot.send_message(
                    ADMIN_ID,
                    f"📋 *ثبت موقت لایحه موفق*\n"
                    f"👤 کاربر: {user_id}\n"
                    f"🔢 کد رهگیری: `{lavayeh_bill_no}`\n"
                    f"📝 عنوان: {title}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            if has_images:
                await _click_step_box(sana_page, "منضمات", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                groups_with_paths = []
                for group in attachment_groups:
                    group_title = group.get("title", "مستندات")
                    group_file_ids = group.get("images", [])
                    group_paths = await _download_images_from_bale(bot, group_file_ids, user_id)
                    groups_with_paths.append({"title": group_title, "paths": group_paths})

                task_key = f"lavayeh:{lavayeh_bill_no}" if lavayeh_bill_no else None
                upload_ok = await _upload_attachment_groups(sana_page, groups_with_paths, bot, user_id,
                                                                 task_key=task_key)

                # ذخیره checkpoint با اطلاعات منضمات
                if task_key and upload_ok:
                    runtime_state.incomplete_tasks.pop(task_key, None)

                # اگر ناموفق بود، checkpoint از داخل _upload_attachment_groups ذخیره شده
                # فقط نیاز به ذخیره اطلاعات پایه تسک داریم
                if not upload_ok and lavayeh_bill_no:
                    from upload_helpers import build_incomplete_task_entry
                    import runtime_state as _rs
                    if task_key not in _rs.incomplete_tasks:
                        _rs.incomplete_tasks[task_key] = build_incomplete_task_entry(
                            bill_no=lavayeh_bill_no, user_id=user_id, task_type="lavayeh",
                            next_step="منضمات", task_data=data,
                            last_completed_step="ثبت موقت",
                            attachment_groups=attachment_groups)

                for group in groups_with_paths:
                    for p in group["paths"]:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                if not upload_ok:
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=tracking_code, doc_name=title,
                        note=f"آپلود پیوست‌ها ناموفق (کد لایحه: {lavayeh_bill_no})"
                    )
                    await register_case(
                        event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                        trackingCode=tracking_code or "", documentCategory=title,
                        errorDetails=f"آپلود پیوست‌ها ناموفق (کد لایحه: {lavayeh_bill_no})", errorStep="UPLOAD_ATTACHMENTS")
                    # پیام‌های خطا از داخل _upload_attachment_groups ارسال شده
                    # و incomplete_tasks هم آنجا ذخیره شده

                # ── اطمینان از بسته بودن popup و آماده بودن صفحه ──
                await _close_success_popup(sana_page)
                await _close_error_popup(sana_page)
                await asyncio.sleep(1)
                await wait_for_angular_idle(sana_page)
                await asyncio.sleep(1)

                logging.info(f"[LAVAYEH] پیوست‌ها تمام شد، بازگشت به فهرست... (user={user_id})")
                goto_ok = await _click_goto_main(sana_page, bot, user_id)
                if not goto_ok:
                    logging.warning(f"[LAVAYEH] بازگشت به فهرست بعد از منضمات ناموفق (user={user_id})")
                    # تلاش آخر: ریلود صفحه و رفتن به صفحه اصلی
                    await sana_page.reload()
                    await asyncio.sleep(5)
                await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_box(sana_page, "آماده سازي جهت محاسبه هزينه و ارسال", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            preparation_ok = await _click_preparation_with_retry(sana_page, bot, user_id)
            if not preparation_ok:
                await bot.send_message(ADMIN_ID, f"⚠️ [LAVAYEH] آماده‌سازی ناموفق — کاربر {user_id}")
                await bot.send_message(user_id, "⚠️ مرحله آماده‌سازی با مشکل مواجه شد.")
                runtime_state.active_lavayeh_users.discard(user_id)
                await log_event(
                    "خطای سامانه", "لایحه", str(user_id), user_id,
                    tracking_code=tracking_code, doc_name=title,
                    note=f"آماده‌سازی ناموفق (کد لایحه: {lavayeh_bill_no})"
                )
                await register_case(
                    event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                    trackingCode=tracking_code or "", documentCategory=title,
                    errorDetails=f"آماده‌سازی ناموفق (کد لایحه: {lavayeh_bill_no})", errorStep="PREPARATION")
                if lavayeh_bill_no:
                    runtime_state.incomplete_tasks[f"lavayeh:{lavayeh_bill_no}"] = {
                        "bill_no": lavayeh_bill_no, "user_id": user_id, "type": "lavayeh",
                        "last_completed_step": "منضمات", "next_step": "آماده‌سازی",
                        "task_data": data, "created_at": time.time(),
                    }
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            court_total = await _calculate_cost_with_retry(sana_page, bot, user_id)
            logging.info(f"[LAVAYEH] court_total: {court_total}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            pdf_path = await _print_lavayeh(sana_page, browser_context, tracking_code, bot, user_id)

            from lavayeh_handlers import send_lavayeh_result
            national_ids = ", ".join([p.get("national_id", "") for p in persons if p.get("national_id")])
            # ── ارسال نتیجه به همراه اطلاعات لازم برای مرحله امضا ──────
            # نکته مهم: باید فقط «کد رهگیری» خام (tracking_code) به مرحله امضا
            # برود، نه رشته ترکیبی — چون همین مقدار بعداً عیناً در فیلد
            # #billNo برای استعلام لایحه تایپ می‌شود. اطلاع از «کد لایحه» فقط
            # برای مدیر لاگ می‌شود، نه برای مرحله امضا.
            await send_lavayeh_result(
                bot, user_id, pdf_path, court_total,
                tracking_code=tracking_code,
                national_ids=national_ids,
                lavayeh_title=title,
                lavayeh_province=province,
                lavayeh_row_number=row_number,
                lavayeh_persons=persons)
            if lavayeh_bill_no:
                await bot.send_message(
                    ADMIN_ID,
                    f"ℹ️ [LAVAYEH] کد لایحه داخلی سامانه برای کاربر {user_id}: {lavayeh_bill_no}"
                )

            await bot.send_message(
                ADMIN_ID,
                f"✅ [LAVAYEH] ثبت لایحه کاربر {user_id} موفق. هزینه سامانه: {court_total:,} ریال"
            )
            await log_event(
                "ثبت", "لایحه", str(user_id), user_id,
                tracking_code=lavayeh_bill_no or tracking_code, doc_name=title,
                note=f"لایحه ثبت موفق | عنوان: {title} | هزینه: {court_total:,} ریال"
            )
            await register_case(
                event_type="ثبت", full_name=str(user_id), user_id=user_id,
                trackingCode=lavayeh_bill_no or tracking_code or "", documentCategory=title,
                note=f"لایحه ثبت موفق | عنوان: {title}")
            runtime_state.active_lavayeh_users.discard(user_id)
            return

        except LavayehFatalError as e:
            runtime_state.active_lavayeh_users.discard(user_id)
            logging.info(f"[LAVAYEH] خطای قطعی برای user={user_id}: {e}")
            await bot.send_message(
                user_id,
                f"⚠️ {str(e)}")
            await bot.send_message(
                ADMIN_ID,
                f"❌ [LAVAYEH] خطای قطعی کاربر {user_id}: {str(e)[:200]}"
            )
            await log_event(
                "خطای سامانه", "لایحه", str(user_id), user_id,
                tracking_code=tracking_code, doc_name=title,
                note=f"خطای قطعی: {str(e)[:200]}"
            )
            await register_case(
                event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                trackingCode=tracking_code or "", documentCategory=title,
                errorDetails=f"خطای قطعی: {str(e)[:200]}", errorStep="FATAL_ERROR")
            return

        except Exception as e:
            logging.error(f"[LAVAYEH] تلاش {attempt + 1} ناموفق برای user={user_id}: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="process_lavayeh_task", error=e,
                                 user_id=user_id, bill_no=tracking_code,
                                 page=sana_page)
            except Exception:
                pass
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [LAVAYEH] تلاش {attempt + 1} ناموفق. ریلود...\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت لایحه با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [LAVAYEH] کاربر {user_id} پس از {max_attempts} تلاش ناموفق."
                )
                runtime_state.active_lavayeh_users.discard(user_id)
                await log_event(
                    "خطای سامانه", "لایحه", str(user_id), user_id,
                    tracking_code=tracking_code, doc_name=title,
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
                )
                await register_case(
                    event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                    trackingCode=tracking_code or "", documentCategory=title,
                    errorDetails=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}", errorStep="MAX_RETRIES_EXCEEDED")


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _click_menu_item(page, text: str, bot: Bot, user_id: int):
    # اول تلاش کن در منوی اصلی (list-group-item) پیدا کنه
    clicked = await page.evaluate(f'''() => {{
        // جستجو در کنتینرهای منو (#menu13Container و مشابه)
        const menuContainers = document.querySelectorAll('[id*="menu"], .list-group, .sidebar-menu, .nav-menu, #menu13Container, #menu14Container');
        for (const container of menuContainers) {{
            const links = container.querySelectorAll('a.list-group-item, a, button, label, span, li, div');
            const target = Array.from(links).find(el => el.innerText && el.innerText.trim().includes("{text}") && el.offsetParent !== null);
            if (target) {{ target.click(); return true; }}
        }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, text, bot, user_id)


async def _select_bill_type(page, search_kw: str, row_idx: int, bot: Bot, user_id: int):
    search_input = page.locator('.ui-select-search').first
    opened = False

    for open_attempt in range(4):
        await page.evaluate('''() => {
            const btn = document.querySelector('.ui-select-toggle');
            if (btn) btn.click();
        }''')
        try:
            await search_input.wait_for(state="visible", timeout=4000)
            opened = True
            break
        except PlaywrightTimeoutError:
            logging.warning(f"[LAVAYEH] dropdown باز نشد (تلاش {open_attempt + 1})")
            await asyncio.sleep(1.5)

    if not opened:
        raise Exception("ui-select dropdown باز نشد.")

    await search_input.fill("")
    await search_input.type(search_kw, delay=150)
    await asyncio.sleep(2)

    clicked = await page.evaluate(f'''(idx) => {{
        const choices = Array.from(document.querySelectorAll('.ui-select-choices-row, .ui-select-choices div[ng-repeat]'));
        const visible = choices.filter(el => {{
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }});
        if (visible.length > idx) {{ visible[idx].click(); return true; }}
        const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
        const visLis = lis.filter(el => {{
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }});
        if (visLis.length > idx) {{ visLis[idx].click(); return true; }}
        return false;
    }}''', row_idx)

    if not clicked:
        logging.warning(f"[LAVAYEH] نتوانست ردیف {row_idx} برای '{search_kw}' را کلیک کند")


async def _click_taqdim_lavayeh(page, bot: Bot, user_id: int):
    for attempt in range(5):
        # بررسی مدال نشست قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(3)
            continue

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="setJSSBillType"]');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "تقدیم لایحه", bot, user_id)
        await asyncio.sleep(3)

        # بستن پاپ‌آپ sweet-alert (خطاهای سامانه غیرمرتبط با نشست)
        await _close_error_popup(page)
        await asyncio.sleep(1)

        # بررسی آیا مدال نشست باز شده (ممکنه حین کلیک ظاهر شده باشه)
        had_expiry2 = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry2:
            await asyncio.sleep(3)
            continue

        loaded = await page.evaluate('''() => {
            const steps = Array.from(document.querySelectorAll('.box h5, .step'));
            return steps.some(el => el.innerText && el.innerText.includes("ثبت"));
        }''')
        if loaded:
            return
        await asyncio.sleep(5)


async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const target = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (target) {{
            const box = target.closest('.box');
            if (box) {{ box.click(); return true; }}
        }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)
        return

    # مسیر کلیک مستقیم از safe_click_by_text عبور نمی‌کند، پس اینجا هم
    # صریحاً چک انقضا انجام می‌شود (این همان نقطه‌ای بود که کلیک روی
    # «منضمات» بدون بررسی انقضا انجام می‌شد).
    await asyncio.sleep(1.5)
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        logging.info(f"_click_step_box: session renewed after clicking box '{step_name}', retrying click.")
        await page.evaluate(f'''() => {{
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const target = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
            if (target) {{
                const box = target.closest('.box');
                if (box) box.click();
            }}
        }}''')
        await asyncio.sleep(1.5)


async def _click_step_label(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const steps = Array.from(document.querySelectorAll('.step'));
        const target = steps.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (target) {{ target.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _fill_input(page, selector: str, value: str, bot: Bot, user_id: int):
    """پر کردن یک فیلد با سلکتور مشخص — سازگار با AngularJS"""
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        # اطمینان از اطلاع AngularJS از تغییر مقدار
        await page.evaluate("""(sel) => {
            const el = document.querySelector(sel);
            if (el) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                try {
                    const scope = angular.element(el).scope();
                    if (scope) scope.$apply();
                } catch(e) {}
            }
        }""", selector)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[LAVAYEH] _fill_input({selector}) failed: {e}")


async def _wait_for_any_selector(page, selectors: list, timeout_sec: int = 15) -> str:
    """صبر می‌کند تا یکی از سلکتورهای داده‌شده روی صفحه ظاهر و قابل‌مشاهده شود"""
    for _ in range(timeout_sec * 2):
        found = await page.evaluate('''(sels) => {
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) return sel;
            }
            return null;
        }''', selectors)
        if found:
            return found
        await asyncio.sleep(0.5)
    return None


async def _fill_national_id_field(page, national_id: str, bot: Bot, user_id: int) -> bool:
    """
    پر کردن فیلد کدملی وکیل/شخص با چندین سلکتور و روش.
    وقتی نوع شخص «وکیل» انتخاب می‌شود، فرم AngularJS فیلدهای جدیدی
    نمایش می‌دهد و ممکن است آی‌دی فیلد کدملی متفاوت باشد.
    """
    candidate_selectors = [
        "#txtNationalityCode",
        "#txtRealIrNationalityCode1",
        "#txtRealIrNationalityCode",
        "input[name='RealIrNationalityCode']",
        "input[name='NationalityCode']",
        "input[ng-model*='NationalityCode']",
    ]
    found_selector = await _wait_for_any_selector(page, candidate_selectors, timeout_sec=15)

    if not found_selector:
        # هیچ‌کدام از سلکتورهای شناخته‌شده پیدا نشد — لاگ دیباگ
        visible_ids = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input'))
                .filter(i => i.offsetParent !== null)
                .map(i => ({id: i.id, name: i.name, type: i.type}));
        }""")
        logging.warning(
            f"[LAVAYEH] فیلد کدملی وکیل پیدا نشد. "
            f"اینپوت‌های قابل‌مشاهده روی صفحه: {visible_ids}"
        )
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [LAVAYEH] فیلد کدملی وکیل برای کاربر {user_id} پیدا نشد.\n"
            f"اینپوت‌های موجود: {str(visible_ids)[:500]}"
        )
        return False

    logging.info(f"[LAVAYEH] فیلد کدملی پیدا شد: {found_selector}")

    # ── روش ۱: Playwright fill ─────────────────────────────────────────
    try:
        elem = page.locator(found_selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(national_id)
        await elem.blur()
        actual = await elem.input_value()
        if actual == national_id:
            logging.info(
                f"[LAVAYEH] کدملی '{national_id}' با روش Playwright fill "
                f"در {found_selector} وارد شد"
            )
            await _dispatch_angular_events(page, found_selector)
            return True
    except Exception as e:
        logging.warning(f"[LAVAYEH] روش ۱ (Playwright fill) ناموفق: {e}")

    # ── روش ۲: JavaScript مستقیم + Angular ngModel ─────────────────────
    try:
        success = await page.evaluate("""(args) => {
            const { selector, value } = args;
            const el = document.querySelector(selector);
            if (!el) return false;
            el.focus();
            el.value = '';
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
            try {
                const ngEl = angular.element(el);
                const ctrl = ngEl.controller('ngModel');
                if (ctrl) {
                    ctrl.$setViewValue(value);
                    ctrl.$render();
                }
                const scope = ngEl.scope();
                if (scope) scope.$apply();
            } catch(e) {}
            return el.value === value;
        }""", {"selector": found_selector, "value": national_id})
        if success:
            logging.info(
                f"[LAVAYEH] کدملی '{national_id}' با روش JS مستقیم وارد شد"
            )
            return True
    except Exception as e:
        logging.warning(f"[LAVAYEH] روش ۲ (JS مستقیم) ناموفق: {e}")

    # ── روش ۳: تایپ حرف‌به‌حرف (شبه‌انسانی) ──────────────────────────
    try:
        elem = page.locator(found_selector).first
        await elem.click()
        await elem.fill("")
        for char in national_id:
            await elem.type(char, delay=100)
        await elem.blur()
        await _dispatch_angular_events(page, found_selector)
        actual = await elem.input_value()
        if actual == national_id:
            logging.info(
                f"[LAVAYEH] کدملی '{national_id}' با روش تایپ حرف‌به‌حرف وارد شد"
            )
            return True
    except Exception as e:
        logging.warning(f"[LAVAYEH] روش ۳ (تایپ حرف‌به‌حرف) ناموفق: {e}")

    return False


async def _dispatch_angular_events(page, selector: str):
    """ارسال رویدادهای لازم برای به‌روزرسانی مدل AngularJS"""
    await page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (!el) return;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        try {
            const scope = angular.element(el).scope();
            if (scope) scope.$apply();
        } catch(e) {}
    }""", selector)


async def _select_province(page, province: str, bot: Bot, user_id: int):
    await page.evaluate('''() => {
        const btn = Array.from(document.querySelectorAll('button.ui-select-toggle')).find(b => {
            return b.closest('[name="caseServer"]') ||
                   (b.innerText && b.innerText.includes("دادگستری"));
        });
        if (btn) btn.click();
    }''')
    await asyncio.sleep(2)

    is_tehran_excl = "تهران" in province and (
        "به‌جز" in province or "به جز" in province or "بجز" in province
    )
    is_tehran_city_only = "تهران" in province and not is_tehran_excl

    clicked = await page.evaluate('''(args) => {
        const { province, isTehranExcl, isTehranCityOnly } = args;

        // سامانه سنا از حروف عربی (ي، ك) استفاده می‌کند در حالی که مقدار ذخیره‌شده
        // در ربات با حروف فارسی (ی، ک) است. بدون یکسان‌سازی، هیچ گزینه‌ای مچ نمی‌شد
        // و همین باعث ارور «استان انتخاب نشد» بود.
        const normalize = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC')   // ي عربی -> ی فارسی
            .replace(/\\u0643/g, '\\u06A9')   // ك عربی -> ک فارسی
            .replace(/\\u200c/g, ' ')          // نیم‌فاصله -> فاصله ساده
            .trim();

        const normProvince = normalize(province);
        const items = Array.from(document.querySelectorAll('.ui-select-choices-row-inner, .ui-select-choices div'));

        if (isTehranExcl) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                (normalize(el.innerText).includes("به جز") || normalize(el.innerText).includes("بجز")));
            if (target) { target.click(); return true; }
        } else if (isTehranCityOnly) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                !normalize(el.innerText).includes("به جز") && !normalize(el.innerText).includes("بجز"));
            if (target) { target.click(); return true; }
        }

        const exact = items.find(el => el.innerText && normalize(el.innerText) === normProvince);
        if (exact) { exact.click(); return true; }
        const fallback = items.find(el => el.innerText && normalize(el.innerText).includes(normProvince));
        if (fallback) { fallback.click(); return true; }
        return false;
    }''', {"province": province, "isTehranExcl": is_tehran_excl, "isTehranCityOnly": is_tehran_city_only})

    if not clicked:
        logging.warning(f"[LAVAYEH] نتوانست استان '{province}' را انتخاب کند")


async def _click_validate_with_retry(page, bot: Bot, user_id: int):
    consecutive_errors = 0
    for attempt in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst1');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        await asyncio.sleep(12)

        error_text = await _get_and_close_error_popup_text(page)
        if error_text:
            consecutive_errors += 1
            logging.warning(f"[LAVAYEH] خطای صحت‌سنجی (تلاش {attempt+1}): {error_text}")
            # اگر خطا تکرار شد، احتمالاً اطلاعات پرونده اشتباه است
            if consecutive_errors >= 2:
                logging.error(f"[LAVAYEH] خطای صحت‌سنجی تکراری — قطع فرآیند")
                raise LavayehFatalError(
                    "خطا در استعلام پرونده. لطفاً شماره پرونده، ردیف فرعی و نام استان را بررسی کنید."
                )
            await asyncio.sleep(5)
            continue

        consecutive_errors = 0

        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        if has_table:
            return
        await asyncio.sleep(5)


async def _wait_for_case_table(page, bot: Bot, user_id: int, timeout_sec: int = 30) -> bool:
    for _ in range(timeout_sec):
        has_table = await page.evaluate('''() => {
            const tbody = document.querySelector('table tbody');
            return tbody && tbody.querySelectorAll('tr').length > 0;
        }''')
        if has_table:
            return True
        await asyncio.sleep(1)
    return False


async def _click_add_person(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)


async def _click_sana_query_with_retry(
    page, ng_click_contains: str, bot: Bot, user_id: int,
    btn_id: str = None, max_retries: int = 5
):
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[LAVAYEH] session renewed before query attempt {attempt+1}")
            continue

        by_id_js = (
            f'const byId = document.querySelector("#{btn_id}"); '
            f'if (byId && !byId.disabled) {{ byId.click(); return true; }}'
            if btn_id else ""
        )
        clicked = await page.evaluate(f'''() => {{
            {by_id_js}
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click_contains}"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            return false;
        }}''')

        if not clicked:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button.btn-warning'));
                const btn = btns.find(b => {
                    const tip = b.getAttribute("tooltip") || b.getAttribute("title") || "";
                    return tip.includes("استعلام") || tip.includes("ثنا");
                });
                if (btn && !btn.disabled) btn.click();
            }''')

        # صبر اولیه
        await asyncio.sleep(3)

        # منتظر ناپدید شدن لودینگ افقی بالای صفحه
        had_loading_error = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if had_loading_error:
            logging.warning(f"[LAVAYEH] خطا بعد از لودینگ استعلام — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از استعلام
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[LAVAYEH] session renewed after query attempt {attempt+1}")
            continue

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(5)
            continue

        extracted = await page.evaluate('''() => {
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"],' +
                'input[disabled]'
            );
            return disabled !== null;
        }''')
        if extracted:
            return
        await asyncio.sleep(3)


async def _click_save_temp_with_retry(page, bot: Bot, user_id: int, max_retries: int = 5):
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[LAVAYEH] session renewed before save attempt {attempt+1}")
            continue

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnSave');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "ثبت موقت", bot, user_id)

        # صبر اولیه
        await asyncio.sleep(3)

        # منتظر ناپدید شدن لودینگ
        had_loading_error = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if had_loading_error:
            logging.warning(f"[LAVAYEH] خطا بعد از لودینگ ثبت موقت — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از ثبت
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[LAVAYEH] session renewed after save attempt {attempt+1}")
            continue

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            const h2 = popup.querySelector('h2');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && (h2.innerText.includes("ثبت") || h2.innerText.includes("ویرایش") || h2.innerText.includes("موفقیت"));
        }''')

        if success:
            await _close_success_popup(page)
            return

        error_text = await _get_and_close_error_popup_text(page)
        if error_text:
            # بررسی session expiry در متن خطا
            if ("منقضی" in error_text or "منقضي" in error_text or
                "رایانه ای دیگر" in error_text or "اعتبار ورود" in error_text):
                logging.warning(f"[LAVAYEH] session expiry in error text after save")
                await handle_session_expired(bot, user_id, page=page)
                continue

            if "درج نشده" in error_text or ("شخص" in error_text and "سامانه" in error_text):
                await bot.send_message(
                    user_id,
                    f"⚠️ *خطا در ثبت موقت:*\n\n«{error_text}»\n\n"
                    "فرآیند متوقف شد. اطلاعات اشخاص را بررسی و مجدداً اقدام نمایید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [LAVAYEH] خطای قطعی در ثبت موقت کاربر {user_id}: {error_text}"
                )
                raise LavayehFatalError(error_text)

            logging.warning(f"[LAVAYEH] ثبت موقت: «{error_text}» (تلاش {attempt + 1})")
            await asyncio.sleep(5)
            continue

        await asyncio.sleep(5)


async def _click_goto_main(page, bot: Bot, user_id: int, max_retries: int = 5):
    """
    کلیک روی دکمه «بازگشت به فهرست» (#gotoMainPage) با مکانیزم retry.
    قبل از هر تلاش popup‌ها بسته شده و منتظر Angular idle می‌ماند.
    """
    for attempt in range(max_retries):
        # ── بستن هر popup باز (success یا error) ──
        await _close_success_popup(page)
        await _close_error_popup(page)
        await asyncio.sleep(0.5)

        # ── صبر برای Angular idle ──
        await wait_for_angular_idle(page)
        await asyncio.sleep(1)

        # ── روش ۱: کلیک مستقیم روی #gotoMainPage ──
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#gotoMainPage');
            if (btn && !btn.disabled) {
                btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                btn.click();
                return true;
            }
            return false;
        }''')
        if clicked:
            logging.info(f"[LAVAYEH] _click_goto_main: کلیک روی #gotoMainPage (تلاش {attempt+1})")
            await asyncio.sleep(2)
            return True

        # ── روش ۲: اجرای actions.gotoMainStep() از AngularJS scope ──
        clicked_via_scope = await page.evaluate('''() => {
            const btn = document.querySelector('#gotoMainPage') ||
                        document.querySelector('[ng-click*="gotoMainStep"]');
            if (btn) {
                try {
                    const scope = angular.element(btn).scope();
                    if (scope && scope.actions && scope.actions.gotoMainStep) {
                        scope.actions.gotoMainStep();
                        scope.$apply();
                        return true;
                    }
                } catch(e) {}
                btn.click();
                return true;
            }
            return false;
        }''')
        if clicked_via_scope:
            logging.info(f"[LAVAYEH] _click_goto_main: کلیک از طریق scope (تلاش {attempt+1})")
            await asyncio.sleep(2)
            return True

        # ── روش ۳: جستجوی متنی ──
        clicked_text = await page.evaluate('''() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const target = buttons.find(b =>
                b.innerText && b.innerText.includes("بازگشت به فهرست")
            );
            if (target && !target.disabled) {
                target.scrollIntoView({behavior: 'smooth', block: 'center'});
                target.click();
                return true;
            }
            return false;
        }''')
        if clicked_text:
            logging.info(f"[LAVAYEH] _click_goto_main: کلیک متنی (تلاش {attempt+1})")
            await asyncio.sleep(2)
            return True

        logging.warning(
            f"[LAVAYEH] _click_goto_main: تلاش {attempt+1}/{max_retries} ناموفق (user={user_id})"
        )
        await asyncio.sleep(2)

    # ── آخرین تلاش با soft_click ──
    await soft_click_if_exists(page, "بازگشت به فهرست")
    logging.warning(f"[LAVAYEH] _click_goto_main: همه تلاش‌ها ناموفق (user={user_id})")
    return False


MAX_IMAGE_BYTES = 450 * 1024


def _compress_image_if_needed(path: str, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    try:
        if os.path.getsize(path) <= max_bytes:
            return path
    except OSError:
        return path

    try:
        from PIL import Image
    except ImportError:
        logging.warning(f"[LAVAYEH] Pillow نصب نیست؛ فشرده‌سازی '{path}' انجام نشد.")
        return path

    try:
        img = Image.open(path).convert("RGB")
        out_path = os.path.splitext(path)[0] + "_compressed.jpg"

        quality = 90
        width, height = img.size
        while True:
            img.save(out_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(out_path) <= max_bytes or (quality <= 30 and width <= 600):
                break
            if quality > 30:
                quality -= 15
            else:
                width = int(width * 0.8)
                height = int(height * 0.8)
                img = img.resize((width, height), Image.LANCZOS)

        logging.info(f"[LAVAYEH] فشرده‌سازی '{path}': {os.path.getsize(out_path)} بایت")
        try:
            os.remove(path)
        except OSError:
            pass
        return out_path
    except Exception as e:
        logging.error(f"[LAVAYEH] خطا در فشرده‌سازی '{path}': {e}")
        return path


async def _download_images_from_bale(bot: Bot, file_ids: list, user_id: int) -> list:
    paths = []
    for i, file_id in enumerate(file_ids):
        try:
            file_info = await bot.get_file(file_id)
            ext = "jpg"
            if file_info.file_path:
                ext = file_info.file_path.split(".")[-1].lower()
                if ext not in ("jpg", "jpeg", "png"):
                    ext = "jpg"

            path = f"lavayeh_img_{user_id}_{i}.{ext}"
            await bot.download_file(file_info.file_path, path)
            path = _compress_image_if_needed(path)
            paths.append(path)
        except Exception as e:
            logging.error(f"[LAVAYEH] خطا در دانلود تصویر {i} برای user {user_id}: {e}")
    return paths


# ── آپلود منضمات (نسخه مقاوم — upload_helpers) ──────────────────

async def _upload_attachment_groups(page, groups_with_paths: list, bot: Bot, user_id: int,
                                       task_key: str = None) -> bool:
    from upload_helpers import resilient_upload_attachment_groups, build_incomplete_task_entry
    import runtime_state

    overall = await resilient_upload_attachment_groups(
        page, groups_with_paths, bot, user_id,
        prefix="LAVAYEH",
        task_key=task_key,
        incomplete_tasks=runtime_state.incomplete_tasks)

    if not overall["success"]:
        failed = overall["failed_groups"][0] if overall["failed_groups"] else {}
        failed_title = failed.get("title", "?")
        failed_error = failed.get("error", "نامشخص")
        failed_attempts = failed.get("attempts", 0)

        await bot.send_message(
            ADMIN_ID,
            f"❌ [LAVAYEH] آپلود مقاوم شکست خورد\n"
            f"   ردیف: {failed_title}\n"
            f"   خطا: {failed_error}\n"
            f"   تلاش‌ها: {failed_attempts}"
        )
        await bot.send_message(
            user_id,
            f"⚠️ سامانه در آپلود پیوست \u00ab{failed_title}\u00bb مشکل داشت."
        )
    return overall["success"]


# ── توابع قدیمی آپلود (برای سازگاری عقب‌نگهدار، دیگر فراخوانی نمی‌شوند) ──
# این توابع به‌صورت کامل با resilient_upload_attachment در upload_helpers جایگزین شدند.
# در صورت نیاز به دیباگ، می‌توانید مستقیم از upload_helpers استفاده کنید.

async def _upload_single_attachment_group(page, doc_title: str, image_paths: list, bot: Bot, user_id: int) -> bool:
    """placeholder — استفاده نشود. از upload_helpers.resilient_upload_attachment استفاده کنید."""
    logging.warning("[LAVAYEH] _upload_single_attachment_group فراخوانی شد! باید از upload_helpers استفاده شود.")
    from upload_helpers import resilient_upload_attachment
    r = await resilient_upload_attachment(page, doc_title, image_paths, bot, user_id, prefix="LAVAYEH")
    return r["success"]


# ── توابع کمکی قدیمی (بسیاری از آن‌ها هنوز در بخش‌های دیگر استفاده می‌شوند) ──
# _close_success_popup, _close_error_popup, _get_and_close_error_popup_text, _extract_bill_no
# و _click_preparation_with_retry, _calculate_cost_with_retry هنوز مورد نیاز هستند و دست‌نخورده باقی مانده‌اند.
# توابع زیر (آپلود-مشخص) دیگر از طریق _upload_attachment_groups فراخوانی نمیشوند
# اما ممکن است از جای دیگری ارجاع داده شده باشند؛ بنابراین نگه داشته میشوند.


async def _click_save_doc_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3):
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (!btn || btn.disabled) return;
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        ngEl.scope().$apply(() => { btn.click(); });
                        return;
                    }
                }
            } catch(e) {}
            btn.click();
            btn.dispatchEvent(new Event('click', { bubbles: true }));
        }''')

        had_expiry = await resilient_sleep(page, 8, bot, user_id)
        if had_expiry:
            logging.info("[LAVAYEH][منضمات] نشست حین انتظار برای ذخیره‌ی سند تمدید شد؛ تلاش دوباره...")
            continue

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            return

        await _close_error_popup(page)
        await asyncio.sleep(4)


async def _wait_for_upload_alerts(page, expected_count: int, bot: Bot, user_id: int, timeout_sec: int = 120) -> bool:
    # هر ۴ تکرار (≈ ۲ ثانیه) یک بار هم علاوه بر شمارش alertها، انقضای نشست را چک می‌کنیم
    for i in range(timeout_sec * 2):
        if i % 4 == 0:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info("[LAVAYEH][منضمات] نشست حین انتظار برای تایید آپلود تمدید شد؛ ادامه‌ی همین انتظار...")
                # بعد از تمدید، صفحه ممکنه رفرش/تغییر کرده باشه؛ کمی مکث و ادامه‌ی شمارش
                await asyncio.sleep(1)

        count = await page.evaluate('''() => {
            const alerts = Array.from(document.querySelectorAll('.alert-success [ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت ثبت گردید")).length;
        }''')
        if count >= expected_count:
            return True
        await asyncio.sleep(0.5)
    return False


async def _delete_uploaded_files(page, bot: Bot, user_id: int):
    while True:
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info("[LAVAYEH][منضمات] نشست حین حذف فایل‌های آپلودشده تمدید شد؛ ادامه...")

        deleted = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="removeAttachment"]');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not deleted:
            break
        await asyncio.sleep(2)


async def _click_apply_all_with_retry(page, expected_count: int, bot: Bot, user_id: int, max_retries: int = 2) -> bool:
    for attempt in range(max_retries):
        logging.info(f"[LAVAYEH][منضمات] اعمال همه — تلاش {attempt+1}/{max_retries}")

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (!btn) return;
            if (btn.disabled) return;
            // استفاده از scope.$apply برای اجرای صحیح ng-click در AngularJS
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        ngEl.scope().$apply(() => { btn.click(); });
                        return;
                    }
                }
            } catch(e) {}
            btn.click();
            btn.dispatchEvent(new Event('click', { bubbles: true }));
        }''')

        had_expiry = await resilient_sleep(page, 10, bot, user_id)
        if had_expiry:
            logging.info("[LAVAYEH][منضمات] نشست حین انتظار برای «اعمال همه» تمدید شد؛ تلاش دوباره...")
            continue

        confirmed = await page.evaluate(f'''() => {{
            const alerts = Array.from(document.querySelectorAll('[ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت تایید شد")).length >= {expected_count};
        }}''')
        if confirmed:
            return True

        # بررسی popup خطا
        error_text = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const icon = popup.querySelector('.sa-icon.sa-error');
            if (icon && window.getComputedStyle(icon).display !== 'none') {
                return h2 ? h2.innerText : 'خطا';
            }
            return null;
        }''')
        if error_text:
            logging.warning(f"[LAVAYEH][منضمات] خطا در اعمال همه (تلاش {attempt+1}): {error_text}")
            await resilient_sleep(page, 5, bot, user_id)
            continue

        # بررسی sweet-alert موفقیت
        success_popup = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success_popup:
            return True

        await resilient_sleep(page, 30, bot, user_id)

    return False


async def _click_preparation_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """
    آماده‌سازی لایحه با مدیریت کامل پاپ‌آپ‌ها:
      ۱) کلیک #btnPreparation
      ۲) پاپ‌آپ تأیید: «آیا آماده سازی ... مورد تأیید است؟» → کلیک «تایید و آماده سازی»
      ۳) صبر تا ناپدید شدن نوار لودینگ
      ۴) پاپ‌آپ موفقیت: «عملیات آماده سازی ... با موفقیت انجام شد» → کلیک «بستن»
      ۵) اگر خطا رخ داد → بستن خطا → تلاش مجدد از مرحله ۱
    """
    for attempt in range(max_retries):
        logging.info(f"[LAVAYEH] آماده‌سازی لایحه — تلاش {attempt + 1}/{max_retries} (user={user_id})")

        # ── مرحله ۱: کلیک دکمه آماده‌سازی ──
        btn_clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnPreparation');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        }''')
        if not btn_clicked:
            logging.warning(f"[LAVAYEH] دکمه #btnPreparation پیدا نشد یا غیرفعال بود (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        await asyncio.sleep(2)

        # ── مرحله ۲: انتظار برای پاپ‌آپ تأیید و کلیک «تایید و آماده سازی» ──
        confirm_clicked = False
        for _ in range(15):  # حداکثر ۷.۵ ثانیه انتظار
            popup_info = await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert.visible');
                if (!popup) return null;
                const h2 = popup.querySelector('h2');
                const h2Text = h2 ? h2.innerText.trim() : '';
                const infoIcon = popup.querySelector('.sa-icon.sa-info');
                const infoVisible = infoIcon && window.getComputedStyle(infoIcon).display !== 'none';
                // بررسی پاپ‌آپ تأیید: شامل «آیا آماده سازی» و آیکون info
                if (h2Text.includes('آیا آماده سازی') && infoVisible) {
                    const confirmBtn = popup.querySelector('button.confirm');
                    if (confirmBtn && confirmBtn.innerText.includes('تایید و آماده')) {
                        return { type: 'confirm_prep', h2: h2Text };
                    }
                }
                // بررسی پاپ‌آپ موفقیت (احتمال نادر که بدون تأیید ظاهر شود)
                const successIcon = popup.querySelector('.sa-icon.sa-success');
                if (successIcon && window.getComputedStyle(successIcon).display !== 'none' &&
                    h2Text.includes('آماده')) {
                    return { type: 'success', h2: h2Text };
                }
                // بررسی پاپ‌آپ خطا
                const errorIcon = popup.querySelector('.sa-icon.sa-error');
                if (errorIcon && window.getComputedStyle(errorIcon).display !== 'none') {
                    return { type: 'error', h2: h2Text };
                }
                // پاپ‌آپ ناشناخته دیگر (مثلاً خطای سیستم)
                const warningIcon = popup.querySelector('.sa-icon.sa-warning');
                if (warningIcon && window.getComputedStyle(warningIcon).display !== 'none') {
                    return { type: 'error', h2: h2Text };
                }
                return { type: 'unknown', h2: h2Text };
            }''')

            if popup_info is None:
                await asyncio.sleep(0.5)
                continue

            if popup_info['type'] == 'confirm_prep':
                # کلیک روی «تایید و آماده سازی»
                await page.evaluate('''() => {
                    const popup = document.querySelector('.sweet-alert.showSweetAlert.visible');
                    if (popup) {
                        const btn = popup.querySelector('button.confirm');
                        if (btn) btn.click();
                    }
                }''')
                logging.info(f"[LAVAYEH] پاپ‌آپ تأیید آماده‌سازی تأیید شد (تلاش {attempt+1})")
                confirm_clicked = True
                await asyncio.sleep(1)
                break

            elif popup_info['type'] == 'success':
                # بدون تأیید مستقیم موفقیت ظاهر شد
                await _close_success_popup(page)
                logging.info(f"[LAVAYEH] آماده‌سازی بدون تأیید موفق بود (تلاش {attempt+1})")
                return True

            elif popup_info['type'] == 'error':
                logging.warning(f"[LAVAYEH] خطا قبل از تأیید: {popup_info['h2']} (تلاش {attempt+1})")
                await _close_error_popup(page)
                await asyncio.sleep(2)
                break  # retry از ابتدا

            else:
                # پاپ‌آپ ناشناخته — بستن و تلاش مجدد
                logging.warning(f"[LAVAYEH] پاپ‌آپ ناشناخته: {popup_info['h2']} (تلاش {attempt+1})")
                await _close_error_popup(page)
                await asyncio.sleep(2)
                break

        if not confirm_clicked:
            # پاپ‌آپ تأیید ظاهر نشد — retry
            logging.warning(f"[LAVAYEH] پاپ‌آپ تأیید ظاهر نشد (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        # ── مرحله ۳: صبر تا ناپدید شدن نوار لودینگ (حداکثر ۶۰ ثانیه) ──
        logging.info(f"[LAVAYEH] انتظار برای اتمام لودینگ آماده‌سازی...")
        loading_gone = await page.evaluate('''() => {
            return new Promise((resolve) => {
                let checks = 0;
                const maxChecks = 120; // 120 × 0.5 = 60 ثانیه
                const interval = setInterval(() => {
                    checks++;
                    if (checks >= maxChecks) {
                        clearInterval(interval);
                        resolve('timeout');
                        return;
                    }
                    // بررسی نوار لودینگ آبی بالای صفحه
                    const bar = document.querySelector('.progress-bar.progress-bar-striped.progress-bar-animated.active');
                    if (bar) {
                        const style = window.getComputedStyle(bar);
                        if (style.display !== 'none' && bar.offsetWidth > 0) {
                            return; // هنوز لودینگ داره
                        }
                    }
                    // بررسی سایر لودینگ‌ها
                    const loaders = document.querySelectorAll(
                        '.blockUI, .blockOverlay, .loading-mask, .ajax-loader, ' +
                        '.spinner, .loading, #loading, .progress-bar'
                    );
                    let anyVisible = false;
                    for (const loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== 'none') {
                            anyVisible = true;
                            break;
                        }
                    }
                    if (!anyVisible) {
                        clearInterval(interval);
                        resolve('gone');
                    }
                }, 500);
            });
        }''')

        if loading_gone == 'timeout':
            logging.warning(f"[LAVAYEH] لودینگ آماده‌سازی طول کشید (تلاش {attempt+1})")

        await asyncio.sleep(2)  # صبر کوتاه بعد از لودینگ

        # ── مرحله ۴: بررسی نتیجه — پاپ‌آپ موفقیت یا خطا ──
        for _ in range(15):  # حداکثر ۷.۵ ثانیه
            result = await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert.visible');
                if (!popup) return null;
                const h2 = popup.querySelector('h2');
                const h2Text = h2 ? h2.innerText.trim() : '';
                const successIcon = popup.querySelector('.sa-icon.sa-success');
                const successVisible = successIcon && window.getComputedStyle(successIcon).display !== 'none';
                const errorIcon = popup.querySelector('.sa-icon.sa-error');
                const errorVisible = errorIcon && window.getComputedStyle(errorIcon).display !== 'none';
                const warningIcon = popup.querySelector('.sa-icon.sa-warning');
                const warningVisible = warningIcon && window.getComputedStyle(warningIcon).display !== 'none';

                if (successVisible && h2Text.includes('آماده')) {
                    return { type: 'success', h2: h2Text };
                }
                if (errorVisible || warningVisible) {
                    return { type: 'error', h2: h2Text };
                }
                // پاپ‌آپ بدون آیکون مشخص ولی شامل خطا
                if (h2Text.includes('خطا') || h2Text.includes('خطا')) {
                    return { type: 'error', h2: h2Text };
                }
                return { type: 'waiting', h2: h2Text };
            }''')

            if result is None:
                await asyncio.sleep(0.5)
                continue

            if result['type'] == 'success':
                await _close_success_popup(page)
                logging.info(f"[LAVAYEH] آماده‌سازی با موفقیت انجام شد (تلاش {attempt+1})")
                return True

            elif result['type'] == 'error':
                logging.warning(f"[LAVAYEH] خطا در آماده‌سازی: {result['h2']} (تلاش {attempt+1})")
                # بستن پاپ‌آپ خطا
                await _close_error_popup(page)
                await asyncio.sleep(2)
                # retry: دوباره کلیک آماده‌سازی
                break

            else:
                await asyncio.sleep(0.5)

        # اگر از حلقه داخلی خارج شدیم بدون موفقیت → تلاش مجدد کل
        await asyncio.sleep(3)

    logging.error(f"[LAVAYEH] آماده‌سازی پس از {max_retries} تلاش ناموفق (user={user_id})")
    return False


async def _calculate_cost_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> int:
    """
    ورود به مرحله «محاسبه و دريافت هزينه» و استخراج مبلغ نمایش‌داده‌شده.
    مبلغ خام (ریال) برمی‌گرداند — تبدیل/رند/فرمول در calculate_lavayeh_fee (config.py) انجام می‌شود.
    """
    for attempt in range(max_retries):
        await _close_error_popup(page)
        await asyncio.sleep(2)
        await wait_for_angular_idle(page)

        # ── استخراج مبلغ از جدول — سلکتور دقیق طبق ساختار صفحه ──
        raw = await page.evaluate('''() => {
            // روش ۱: سلکتور دقیق td با کلاس‌های خاص (طبق HTML واقعی صفحه)
            const td = document.querySelector(
                'td.font-yekan-number.color-green.font-size-18'
            );
            if (td) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 10000) {
                    return text;
                }
            }

            // روش ۲: جستجوی td حاوی jud-currency یا persioanval
            const currencyDivs = document.querySelectorAll('[jud-currency]');
            for (const div of currencyDivs) {
                const parentTd = div.closest('td');
                if (parentTd) {
                    const text = parentTd.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                    if (/^[0-9]+$/.test(text) && parseInt(text) > 10000) {
                        return text;
                    }
                }
            }

            // روش ۳: جستجوی کلی در تمام tdها (fallback)
            const tds = Array.from(document.querySelectorAll('table td'));
            for (let td of tds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 10000 && parseInt(text) < 100000000000) {
                    return text;
                }
            }
            return null;
        }''')

        if raw:
            try:
                amount = int(raw.replace(",", "").strip())
                # اگر عدد خیلی بزرگ بود (احتمالا واحد اشتباه)، لاگ بگیر
                if amount > 100_000_000:
                    amount = amount // 10
                logging.info(f"[LAVAYEH] مبلغ استخراج‌شده از سامانه: {amount:,} ریال (تلاش {attempt+1})")
                return amount
            except Exception as e:
                logging.warning(f"[LAVAYEH] خطا در تبدیل مبلغ '{raw}': {e}")

        logging.warning(f"[LAVAYEH] مبلغی در جدول پیدا نشد (تلاش {attempt+1}/{max_retries})")
        await asyncio.sleep(5)

    logging.error(f"[LAVAYEH] استخراج مبلغ پس از {max_retries} تلاش ناموفق (user={user_id})")
    return 0


async def _print_lavayeh(page, browser_context, tracking_code: str, bot: Bot, user_id: int):
    pdf_path = f"lavayeh_{tracking_code}.pdf"

    try:
        async def click_print():
            await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const target = heads.find(el => el.innerText && (
                    el.innerText.includes("چاپ اوليه") || el.innerText.includes("چاپ اولیه")
                ));
                if (target) {
                    const box = target.closest('.box');
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
        logging.error(f"[LAVAYEH] خطا در چاپ: {e}")

        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="click_print", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        try:
            await page.pdf(path=pdf_path, format="A4")
        except Exception:
            pass

    return pdf_path


async def _extract_bill_no(page) -> str:
    try:
        val = await page.evaluate('''() => {
            const inp = document.querySelector('#txtBillNo');
            return inp ? inp.value : "";
        }''')
        return val or "نامشخص"
    except Exception:
        return "نامشخص"


async def _close_error_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _get_and_close_error_popup_text(page):
    text = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); }
        return msg || 'خطای نامشخص';
    }''')
    if text:
        await asyncio.sleep(1)
    return text


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


async def _click_validate_with_retry_archive(page, bot: Bot, user_id: int):
    """
    کلیک روی دکمه صحت‌سنجی اطلاعات برای شماره بایگانی.
    این تابع مشابه _click_validate_with_retry است اما از دکمه btnAddHst2 استفاده می‌کند.
    """
    consecutive_errors = 0
    for attempt in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst2');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        await asyncio.sleep(12)

        error_text = await _get_and_close_error_popup_text(page)
        if error_text:
            consecutive_errors += 1
            logging.warning(f"[LAVAYEH] خطای صحت‌سنجی بایگانی (تلاش {attempt+1}): {error_text}")
            if consecutive_errors >= 2:
                logging.error(f"[LAVAYEH] خطای صحت‌سنجی بایگانی تکراری — قطع فرآیند")
                raise LavayehFatalError(
                    "خطا در استعلام پرونده. لطفاً شماره بایگانی و کد شعبه را بررسی کنید."
                )
            await asyncio.sleep(5)
            continue

        consecutive_errors = 0

        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        if has_table:
            logging.info(f"[LAVAYEH] صحت‌سنجی بایگانی موفق در تلاش {attempt+1}")
            return

    logging.warning(f"[LAVAYEH] صحت‌سنجی بایگانی ناموفق پس از 5 تلاش")
