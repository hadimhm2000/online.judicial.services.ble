""" سناریوی کامل ثبت لایحه در سامانه قضایی ثنا. (اصلاح شده - نسخه 3) """
import asyncio
import logging
import os
import base64
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, soft_click_if_exists,
    goto_url_with_retry, human_delay, force_click_by_text,
    safe_click_by_text, safe_type, wait_for_angular_idle)


class LavayehFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


TITLE_SEARCH_MAP = {
    "لایحه دفاعیه": ("دفا", 0),
    "صدور اجرائیه": ("اجرائ", 0),
    "اعتراض به نظر کارشناس": ("کارشن", 1),
    "اعتراض به قرار رد دفتر": ("قرار", 1),
    "سایر عناوین": ("دفا", 0),
}

AGENT_TYPE_VALUES = {
    "مدیرعامل": "0091000010000008",
    "نماینده": "0091000010000007",
}


def _text_to_editor_html(text: str) -> str:
    if not text:
        return "&nbsp;"
    lines = text.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace(" ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p>&nbsp;</p>")
    return "".join(parts)


async def process_lavayeh_task(data: dict, bot: Bot):
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]
    title = data.get("lavayeh_title", "لایحه دفاعیه")
    system_title = data.get("lavayeh_system_title", "لایحه دفاعیه")
    tracking_code = data.get("lavayeh_tracking_code", "")
    province = data.get("lavayeh_province", "")
    row_number = data.get("lavayeh_row_number", 1)
    persons = data.get("lavayeh_persons", [])
    lavayeh_text = data.get("lavayeh_text", "")
    attachment_groups = data.get("lavayeh_attachments", [])
    has_images = len(attachment_groups) > 0
    total_image_count = sum(len(g.get("images", [])) for g in attachment_groups)

    # ═══════════════════════════════════════════════════════════════
    # بررسی روش ثبت: شماره پرونده یا شماره بایگانی
    # ═══════════════════════════════════════════════════════════════
    tracking_method = data.get("tracking_method", "case_number")
    archive_number = data.get("lavayeh_archive_number", "") or ""
    branch_name = data.get("lavayeh_branch_name", "") or ""
    branch_code = data.get("lavayeh_branch_code", "") or ""

    logging.info(
        f"[LAVAYEH] user={user_id} title={title} method={tracking_method} "
        f"tracking_code={tracking_code} province={province} row={row_number} "
        f"archive_number={archive_number} branch_code={branch_code} "
        f"persons={len(persons)} attachment_groups={len(attachment_groups)} images={total_image_count}"
    )

    await bot.send_message(
        user_id,
        f"⏳ در حال ثبت لایحه...\n"
        f"عنوان: *{title}* | روش: *{'شماره بایگانی' if tracking_method == 'archive_number' else 'شماره پرونده'}*")

    await bot.send_message(
        ADMIN_ID,
        f"🔄 [LAVAYEH] شروع ثبت برای کاربر {user_id}\n"
        f"عنوان: {title} | روش: {tracking_method}\n"
        f"کد شعبه: {branch_code} | بایگانی: {archive_number} | پرونده: {tracking_code}"
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

            # باگ رفع شد: استفاده از system_title به‌جای title خام تا انتخاب
            # «سایر عناوین» مثل «لایحه دفاعیه» در سامانه ثبت شود.
            search_kw, row_idx = TITLE_SEARCH_MAP.get(system_title, ("دفا", 0))
            await _select_bill_type(sana_page, search_kw, row_idx, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            await _click_taqdim_lavayeh(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            await _click_step_box(sana_page, "ثبت و ويرايش لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ═══════════════════════════════════════════════════════════════
            # مرحله اصلی: اطلاعات پرونده
            # ═══════════════════════════════════════════════════════════════
            await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            logging.info(f"[LAVAYEH] ═══ Checking tracking_method: {tracking_method} ═══")

            if tracking_method == "archive_number":
                # ═══════════════════════════════════════════════════════
                # مسیر شماره بایگانی
                # ═══════════════════════════════════════════════════════
                logging.info(f"[LAVAYEH] ═══ ARCHIVE NUMBER METHOD STARTED ═══")
                logging.info(f"[LAVAYEH] branch_code={branch_code}, archive_number={archive_number}")

                # مرحله 1: کلیک روی رادیو باتن شماره بایگانی (value="2")
                logging.info(f"[LAVAYEH] Step 1: Clicking radio button rdbCaseInfo2...")
                radio_clicked = await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('input#rdbCaseInfo2');
                    if (rdb) {
                        rdb.click();
                        rdb.checked = true;
                        rdb.dispatchEvent(new Event('change', { bubbles: true }));
                        try {
                            const scope = angular.element(rdb).scope();
                            if (scope) scope.$apply();
                        } catch(e) {}
                        return true;
                    }
                    return false;
                }''')
                
                if not radio_clicked:
                    # Fallback: پیدا کردن با selector دیگر
                    radio_clicked = await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[name="rdbCaseInfo"][value="2"]');
                        if (rdb) {
                            rdb.click();
                            return true;
                        }
                        return false;
                    }''')
                
                if not radio_clicked:
                    logging.error(f"[LAVAYEH] Could not click rdbCaseInfo2!")
                    await bot.send_message(user_id, "⚠️ رادیو باتن شماره بایگانی پیدا نشد.")
                    return
                
                await resilient_sleep(sana_page, 2, bot, user_id)

                # مرحله 2: وارد کردن کد 5 رقمی واحد قضایی (شعبه)
                if branch_code:
                    logging.info(f"[LAVAYEH] Step 2: Filling txtCourtCode with {branch_code}...")
                    await sana_page.evaluate('''(code) => {
                        const inp = document.querySelector('#txtCourtCode');
                        if (inp) {
                            inp.value = code;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            try {
                                const scope = angular.element(inp).scope();
                                if (scope && scope.viewModel) {
                                    scope.viewModel.unitCode = code;
                                    if (scope.actions && scope.actions.getUnitByCodeWithBranch) {
                                        scope.actions.getUnitByCodeWithBranch(code);
                                    }
                                    scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }''', branch_code)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                else:
                    logging.error(f"[LAVAYEH] branch_code is empty!")
                    await bot.send_message(user_id, "⚠️ کد شعبه وارد نشده است.")
                    return

                # مرحله 3: وارد کردن شماره بایگانی
                if archive_number:
                    logging.info(f"[LAVAYEH] Step 3: Filling txtCaseArchiveNo with {archive_number}...")
                    await sana_page.evaluate('''(num) => {
                        const inp = document.querySelector('#txtCaseArchiveNo');
                        if (inp) {
                            inp.value = num;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            try {
                                const scope = angular.element(inp).scope();
                                if (scope && scope.viewModel) {
                                    scope.viewModel.caseArchiveNo = num;
                                    scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }''', archive_number)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                else:
                    logging.error(f"[LAVAYEH] archive_number is empty!")
                    await bot.send_message(user_id, "⚠️ شماره بایگانی وارد نشده است.")
                    return

                # مرحله 4: کلیک روی دکمه صحت‌سنجی (btnAddHst2)
                logging.info(f"[LAVAYEH] Step 4: Clicking validate button (btnAddHst2)...")
                await _click_validate_with_retry_archive(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 10, bot, user_id)

                # بررسی موفقیت
                table_ok = await _wait_for_case_table(sana_page, bot, user_id)
                if not table_ok:
                    logging.error(f"[LAVAYEH] Archive validation failed!")
                    await bot.send_message(
                        user_id,
                        "⚠️ *استعلام پرونده با خطا مواجه شد.*\n\n"
                        "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
                        "🔢 شماره بایگانی\n"
                        "🏛 کد شعبه (5 رقمی)\n\n"
                        "سپس مجدداً «ثبت لایحه» را شروع کنید.")
                    await bot.send_message(
                        ADMIN_ID, 
                        f"❌ [LAVAYEH] صحت‌سنجی بایگانی کاربر {user_id} ناموفق.\n"
                        f"branch_code={branch_code}, archive_number={archive_number}"
                    )
                    runtime_state.active_lavayeh_users.discard(user_id)
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=archive_number, doc_name=title,
                        note="صحت‌سنجی شماره بایگانی ناموفق"
                    )
                    return

                logging.info(f"[LAVAYEH] ═══ ARCHIVE NUMBER METHOD SUCCESSFUL ═══")

            else:
                # ═══════════════════════════════════════════════════════
                # مسیر شماره پرونده (کد قبلی)
                # ═══════════════════════════════════════════════════════
                logging.info(f"[LAVAYEH] ═══ CASE NUMBER METHOD STARTED ═══")
                logging.info(f"[LAVAYEH] tracking_code={tracking_code}, province={province}, row={row_number}")

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
                        "🔢 شماره پرونده\n"
                        "🔢 ردیف فرعی\n"
                        "🏙 استان\n\n"
                        "سپس مجدداً «ثبت لایحه» را شروع کنید.")
                    await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی پرونده کاربر {user_id} ناموفق.")
                    runtime_state.active_lavayeh_users.discard(user_id)
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=tracking_code, doc_name=title,
                        note="صحت‌سنجی پرونده ناموفق"
                    )
                    return

                logging.info(f"[LAVAYEH] ═══ CASE NUMBER METHOD SUCCESSFUL ═══")

            # ═══════════════════════════════════════════════════════════════
            # ادامه مراحل مشترک
            # ═══════════════════════════════════════════════════════════════
            await _click_step_label(sana_page, "ارائه كننده لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for person in persons:
                ptype = person.get("person_type", "شخص حقیقی")
                # ... (بقیه کد مانند قبل)
                # اینجا کد افزودن اشخاص را قرار دهید

            # ... (بقیه مراحل: متن لایحه، منضمات، آماده‌سازی، محاسبه هزینه، چاپ)

            # در انتها:
            logging.info(f"[LAVAYEH] ═══ TASK COMPLETED SUCCESSFULLY ═══")
            return

        except LavayehFatalError as e:
            runtime_state.active_lavayeh_users.discard(user_id)
            logging.info(f"[LAVAYEH] خطای قطعی برای user={user_id}: {e}")
            await log_event(
                "خطای سامانه", "لایحه", str(user_id), user_id,
                tracking_code=tracking_code or archive_number, doc_name=title,
                note=f"خطای قطعی: {str(e)[:200]}"
            )
            return

        except Exception as e:
            logging.error(f"[LAVAYEH] تلاش {attempt + 1} ناموفق برای user={user_id}: {e}")
            if attempt < max_attempts - 1:
                logging.info(f"[LAVAYEH] Retrying...")
                await asyncio.sleep(5)
            else:
                await bot.send_message(user_id, "❌ ثبت لایحه با خطا مواجه شد. لطفاً مجدداً تلاش کنید.")
                await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] تمام تلاش‌ها برای کاربر {user_id} ناموفق بود.")
                runtime_state.active_lavayeh_users.discard(user_id)
                return


# ═══════════════════════════════════════════════════════════════════════════════
# تابع صحت‌سنجی برای شماره بایگانی
# ═══════════════════════════════════════════════════════════════════════════════

async def _click_validate_with_retry_archive(page, bot: Bot, user_id: int):
    """
    کلیک روی دکمه صحت‌سنجی اطلاعات برای شماره بایگانی.
    از دکمه btnAddHst2 استفاده می‌کند.
    """
    for attempt in range(5):
        logging.info(f"[LAVAYEH] _click_validate_with_retry_archive attempt {attempt + 1}")
        
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst2');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        }''')
        
        if not clicked:
            logging.warning(f"[LAVAYEH] btnAddHst2 not found or disabled")
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        
        await asyncio.sleep(12)
        
        closed = await _close_error_popup(page)
        if closed:
            logging.warning(f"[LAVAYEH] Error popup closed, retrying...")
            await asyncio.sleep(5)
            continue
        
        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        
        if has_table:
            logging.info(f"[LAVAYEH] Archive validation successful on attempt {attempt + 1}")
            return
        
        await asyncio.sleep(5)
    
    logging.warning(f"[LAVAYEH] Archive validation failed after 5 attempts")


# ═══════════════════════════════════════════════════════════════════════════════
# توابع کمکی (این‌ها را از کد اصلی خود کپی کنید)
# ═══════════════════════════════════════════════════════════════════════════════

async def _click_menu_item(page, text: str, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _select_bill_type(page, search_kw: str, row_idx: int, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _click_taqdim_lavayeh(page, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _click_step_label(page, step_name: str, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _fill_input(page, selector: str, value: str, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _select_province(page, province: str, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _click_validate_with_retry(page, bot: Bot, user_id: int):
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _wait_for_case_table(page, bot: Bot, user_id: int, timeout_sec: int = 30) -> bool:
    # کد اصلی خود را اینجا قرار دهید
    pass

async def _close_error_popup(page) -> bool:
    # کد اصلی خود را اینجا قرار دهید
    pass
