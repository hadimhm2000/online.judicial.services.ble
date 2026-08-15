"""
سناریوی ثبت اعلام وکالت در سامانه قضایی ثنا.

جریان:
  ۱. ناوبری به «ارایه و پیگیری لایحه»
  ۲. جستجوی عنوان «اعلام و» و انتخاب اولین ردیف
  ۳. کلیک «تقدیم لایحه»
  ۴. پر کردن اطلاعات پرونده (شماره پرونده، ردیف فرعی، استان)
  ۵. صحت‌سنجی پرونده
  ۶. مرحله «ارائه کننده لایحه» — انتخاب وکیل + کدملی
  ۷. مرحله «متن» — وارد کردن متن لایحه
  ۸. ثبت موقت
  ۹. مرحله «منضمات» — انتخاب «تصویر الکترونیک وکالت نامه» + شماره قرارداد + مبلغ تمبر
  ۱۰. بارگذاری تصاویر مدارک (در صورت وجود)
  ۱۱. آماده‌سازی و محاسبه هزینه
  ۱۲. چاپ PDF
  ۱۳. ارسال نتیجه به کاربر
"""
import asyncio
import logging
import html as html_lib


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
import os

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


class EalamFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


async def process_ealam_vakalaht_task(data: dict, bot: Bot):
    """پردازش تسک اعلام وکالت"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]

    lawyers = data.get("ealam_lawyers", [])
    contracts = data.get("ealam_contracts", [])
    stamp_amount = data.get("ealam_stamp_amount", 0)
    stamp_type = data.get("ealam_stamp_type", "")
    lavayeh_text = data.get("ealam_lavayeh_text", "")
    attachment_groups = data.get("ealam_attachments", [])
    tracking_code = data.get("lavayeh_tracking_code", "")
    province = data.get("lavayeh_province", "")
    row_number = data.get("lavayeh_row_number", 1)

    # بررسی روش ثبت: شماره پرونده یا شماره بایگانی
    tracking_method = data.get("tracking_method", "case_number")
    archive_number = data.get("lavayeh_archive_number", "")
    branch_code = data.get("lavayeh_branch_code", "")

    logging.info(
        f"[EALAM] user={user_id} lawyers={lawyers} contracts={contracts} "
        f"stamp={stamp_amount} ({stamp_type}) tracking={tracking_code} "
        f"method={tracking_method} archive={archive_number} branch_code={branch_code}"
    )

    await bot.send_message(
        user_id,
        f"⏳ *در حال ثبت اعلام وکالت...*\n"
        f"وکیل(ها): {', '.join([f'`{l}`' for l in lawyers])}")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [EALAM] شروع ثبت اعلام وکالت برای کاربر {user_id}\n"
        f"وکلا: {lawyers} | قراردادها: {contracts}"
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
            if not ok:
                return
            await human_delay(3.0, 5.0)

            # ── ۱. کلیک «ارایه و پیگیری لایحه» ─────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a.list-group-item'));
                const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری لایحه"));
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. جستجوی عنوان «اعلام و» در dropdown ────────────────────
            await _select_ealam_bill_type(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # ── ۳. کلیک «تقدیم لایحه» ───────────────────────────────────
            await _click_taqdim_lavayeh(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            # ── ۴. کلیک مرحله «ثبت و ویرایش لایحه» ─────────────────────
            await _click_step_box(sana_page, "ثبت و ويرايش لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۵. اطلاعات پرونده ────────────────────────────────────────
            await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            if tracking_method == "archive_number":
                # ── مسیر شماره بایگانی ──────────────────────────────────
                # کلیک روی رادیو باتن شماره بایگانی (value=2)
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('input[type="radio"][name="rdbCaseInfo"][value="2"]#rdbCaseInfo2');
                    if (rdb) rdb.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)

                # وارد کردن کد ۵ رقمی واحد قضایی (بر اساس شعبه انتخابی)
                if branch_code:
                    await _fill_input(sana_page, "#txtCourtCode", branch_code)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    # صبر برای لود اطلاعات واحد قضایی بعد از وارد کردن کد
                    await sana_page.evaluate('''() => {
                        const inp = document.querySelector('#txtCourtCode');
                        if (inp) {
                            inp.dispatchEvent(new Event("input", { bubbles: true }));
                            inp.dispatchEvent(new Event("change", { bubbles: true }));
                        }
                    }''')
                    await resilient_sleep(sana_page, 2, bot, user_id)

                # وارد کردن شماره بایگانی
                if archive_number:
                    await _fill_input(sana_page, "#txtCaseArchiveNo", archive_number)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                # کلیک روی دکمه صحت‌سنجی (btnAddHst2)
                await _click_validate_archive(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 10, bot, user_id)

                # بررسی موفقیت
                table_ok = await _wait_for_case_table(sana_page)
                if not table_ok:
                    await bot.send_message(
                        user_id,
                        "⚠️ *استعلام پرونده با خطا مواجه شد.*\n\n"
                        "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
                        "🔢 شماره بایگانی\n🏛 کد شعبه\n\n"
                        "سپس مجدداً «اعلام وکالت» را شروع کنید.")
                    return
            else:
                # ── مسیر شماره پرونده (کد قبلی) ─────────────────────────
                if tracking_code:
                    await _fill_input(sana_page, "#txtCaseNo", tracking_code)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                await _fill_input(sana_page, "#txtSubNo", str(row_number))
                await resilient_sleep(sana_page, 1, bot, user_id)

                if province:
                    await _select_province(sana_page, province, bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)

                # صحت‌سنجی
                await _click_validate(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 10, bot, user_id)

                table_ok = await _wait_for_case_table(sana_page)
                if not table_ok and tracking_code:
                    await bot.send_message(
                        user_id,
                        "⚠️ *استعلام پرونده با خطا مواجه شد.*\n\n"
                        "لطفاً شماره پرونده، ردیف فرعی و استان را بررسی کنید.\n"
                        "مجدداً «اعلام وکالت» را شروع کنید.")
                    return

            # ── ۶. مرحله «ارائه کننده لایحه» ────────────────────────────
            await _click_step_label(sana_page, "ارائه كننده لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for lawyer_nat_id in lawyers:
                await _add_lawyer_person(sana_page, lawyer_nat_id, bot, user_id)
                await resilient_sleep(sana_page, 8, bot, user_id)

            # ── ۷. مرحله «متن» ───────────────────────────────────────────
            await _click_step_label(sana_page, "متن", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            stored_html = data.get("ealam_lavayeh_text_html", "")
            await _fill_text_editor(sana_page, lavayeh_text, bot, user_id, stored_html=stored_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

            # ── ۸. ثبت موقت ──────────────────────────────────────────────
            await _click_save_temp_with_retry(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            lavayeh_bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[EALAM] bill_no: {lavayeh_bill_no}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۹. مرحله «منضمات» — ثبت وکالت‌نامه الکترونیک ──────────
            await _click_step_box(sana_page, "منضمات", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # تعیین مبلغ فیلد txtLawyerAmount: stamp_amount * 100 / 3
            # اگر تمبر نیازی نیست (stamp_type == "بدون تمبر")، مقدار 1 قرار می‌دهیم
            if stamp_type == "بدون تمبر" or stamp_amount == 0:
                lawyer_amount_value = 1
            elif stamp_amount and stamp_amount > 0:
                lawyer_amount_value = int(stamp_amount * 100 / 3)
            else:
                lawyer_amount_value = 1

            # شماره قرارداد اول
            first_contract = contracts[0] if contracts else ""

            vakalaht_ok = await _upload_electronic_vakalaht(
                sana_page, first_contract, lawyer_amount_value, bot, user_id
            )

            if not vakalaht_ok:
                # اطلاع به کاربر و پایان
                bill_no = await _extract_bill_no(sana_page)
                await bot.send_message(
                    user_id,
                    f"⚠️ *خطا در ثبت وکالت‌نامه الکترونیک.*\n\n"
                    f"کد رهگیری لایحه: `{bill_no}`\n\n"
                    f"جهت ادامه ثبت با شماره *09306186888* در واتساپ پیام دهید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [EALAM] آپلود وکالت‌نامه الکترونیک برای کاربر {user_id} ناموفق. کد: {bill_no}"
                )
                return

            # آپلود سایر پیوست‌ها (در صورت وجود)
            if attachment_groups:
                # دانلود تصاویر
                groups_with_paths = []
                for group in attachment_groups:
                    group_paths = await _download_images_from_bale(
                        bot, group.get("images", []), user_id
                    )
                    groups_with_paths.append({"title": group.get("title", "مستندات"), "paths": group_paths})

                for group in groups_with_paths:
                    await _upload_other_attachment(
                        sana_page, group["title"], group["paths"], bot, user_id
                    )
                    for p in group["paths"]:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۰. آماده‌سازی ───────────────────────────────────────────
            await _click_step_box(sana_page, "آماده سازي جهت محاسبه هزينه و ارسال", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            preparation_ok = await _click_preparation_with_retry(sana_page, bot, user_id)
            if not preparation_ok:
                bill_no = await _extract_bill_no(sana_page)
                await bot.send_message(
                    user_id,
                    f"⚠️ مرحله آماده‌سازی با مشکل مواجه شد.\n"
                    f"کد رهگیری: `{bill_no}`\n"
                    f"با شماره *09306186888* در واتساپ پیام دهید.")
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۱. محاسبه هزینه ─────────────────────────────────────────
            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            court_total = await _calculate_cost_with_retry(sana_page, bot, user_id)
            logging.info(f"[EALAM] court_total: {court_total}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. چاپ PDF ──────────────────────────────────────────────
            pdf_path = await _print_lavayeh(sana_page, browser_context, lavayeh_bill_no, bot, user_id)

            # ── ۱۳. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result
            national_ids = ", ".join(lawyers)
            combined_tracking = (
                f"{tracking_code} | کد لایحه: {lavayeh_bill_no}"
                if lavayeh_bill_no else tracking_code
            )

            await send_lavayeh_result(
                bot, user_id, pdf_path, court_total,
                tracking_code=combined_tracking,
                national_ids=national_ids,
                lavayeh_title="اعلام وکالت",
                lavayeh_province=province,
                lavayeh_row_number=row_number,
                lavayeh_persons=[{"person_type": "وکیل", "national_id": l} for l in lawyers],
                skip_fee_calc=True)

            await bot.send_message(
                ADMIN_ID,
                f"✅ [EALAM] ثبت اعلام وکالت کاربر {user_id} موفق. هزینه: {court_total:,} تومان"
            )
            await log_event(
                "ثبت موقت", "اعلام وکالت", str(user_id), user_id,
                tracking_code=lavayeh_bill_no or tracking_code, doc_name="اعلام وکالت",
                note=f"اعلام وکالت ثبت موفق | هزینه: {court_total:,} تومان"
            )
            await register_case(
                event_type="ثبت موقت", full_name=str(user_id), user_id=user_id,
                trackingCode=lavayeh_bill_no or tracking_code or "", documentCategory="اعلام وکالت",
                note=f"اعلام وکالت ثبت موفق | هزینه: {court_total:,} تومان")
            return

        except EalamFatalError as e:
            logging.error(f"[EALAM] خطای قطعی user={user_id}: {e}")
            await bot.send_message(user_id, f"⚠️ *خطای قطعی:* {str(e)[:200]}")
            await log_event(
                "خطای سامانه", "اعلام وکالت", str(user_id), user_id,
                tracking_code=tracking_code, doc_name="اعلام وکالت",
                note=f"خطای قطعی: {str(e)[:200]}"
            )
            await register_case(
                event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                trackingCode=tracking_code or "", documentCategory="اعلام وکالت",
                errorDetails=f"خطای قطعی: {str(e)[:200]}", errorStep="FATAL_ERROR")
            return

        except Exception as e:
            logging.error(f"[EALAM] تلاش {attempt+1} ناموفق user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(ADMIN_ID, f"⚠️ [EALAM] تلاش {attempt+1} ناموفق. ریلود...\nخطا: {str(e)[:300]}")
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت اعلام وکالت با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(ADMIN_ID, f"❌ [EALAM] کاربر {user_id} پس از {max_attempts} تلاش ناموفق.")
                await log_event(
                    "خطای سامانه", "اعلام وکالت", str(user_id), user_id,
                    tracking_code=tracking_code, doc_name="اعلام وکالت",
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
                )
                await register_case(
                    event_type="خطای سامانه", full_name=str(user_id), user_id=user_id,
                    trackingCode=tracking_code or "", documentCategory="اعلام وکالت",
                    errorDetails=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}", errorStep="MAX_RETRIES_EXCEEDED")
                try:
                    from bug_reporter import report_bug
                    await report_bug(bot, where="process_ealam_vakalaht_task", error=e,
                                     user_id=user_id,
                                     page=getattr(runtime_state, "sana_page", None))
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

async def _select_ealam_bill_type(page, bot: Bot, user_id: int):
    """انتخاب نوع لایحه «اعلام وکالت» از dropdown"""
    search_input = page.locator('.ui-select-search').first
    opened = False
    for _ in range(4):
        await page.evaluate('''() => {
            const btn = document.querySelector('.ui-select-toggle');
            if (btn) btn.click();
        }''')
        try:
            await search_input.wait_for(state="visible", timeout=4000)
            opened = True
            break
        except PlaywrightTimeoutError:
            await asyncio.sleep(1.5)

    if not opened:
        raise Exception("ui-select dropdown باز نشد.")

    await search_input.fill("")
    await search_input.type("اعلام و", delay=150)
    await asyncio.sleep(2)

    # انتخاب اولین ردیف
    clicked = await page.evaluate('''() => {
        const choices = Array.from(document.querySelectorAll(
            '.ui-select-choices-row, .ui-select-choices div[ng-repeat]'
        ));
        const visible = choices.filter(el => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        });
        if (visible.length > 0) { visible[0].click(); return true; }
        const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
        const vl = lis.filter(el => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        });
        if (vl.length > 0) { vl[0].click(); return true; }
        return false;
    }''')
    if not clicked:
        logging.warning("[EALAM] نتوانست عنوان «اعلام وکالت» را انتخاب کند")


async def _click_taqdim_lavayeh(page, bot: Bot, user_id: int):
    for _ in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="setJSSBillType"]');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "تقدیم لایحه", bot, user_id)
        await asyncio.sleep(3)
        await _close_error_popup(page)
        await asyncio.sleep(4)
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

    # مسیر کلیک مستقیم از safe_click_by_text عبور نمی‌کند؛ اینجا هم صریحاً
    # چک انقضا انجام می‌شود (نقطه‌ای که کلیک روی «منضمات» قبلاً بدون این چک بود).
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


async def _fill_input(page, selector: str, value: str):
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[EALAM] _fill_input({selector}) failed: {e}")


async def _select_province(page, province: str, bot: Bot, user_id: int):
    await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button.ui-select-toggle'));
        const btn = btns.find(b => {
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

    await page.evaluate('''(args) => {
        const { prov, isTehranExcl, isTehranCityOnly } = args;
        const normalize = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC')
            .replace(/\\u0643/g, '\\u06A9')
            .replace(/\\u200c/g, ' ')
            .trim();
        const normProv = normalize(prov);
        const items = Array.from(document.querySelectorAll('.ui-select-choices-row-inner, .ui-select-choices div'));

        if (isTehranExcl) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                (normalize(el.innerText).includes("به جز") || normalize(el.innerText).includes("بجز")));
            if (target) { target.click(); return; }
        } else if (isTehranCityOnly) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                !normalize(el.innerText).includes("به جز") && !normalize(el.innerText).includes("بجز"));
            if (target) { target.click(); return; }
        }

        const exact = items.find(el => el.innerText && normalize(el.innerText) === normProv);
        if (exact) { exact.click(); return; }
        const fallback = items.find(el => el.innerText && normalize(el.innerText).includes(normProv));
        if (fallback) fallback.click();
    }''', {"prov": province, "isTehranExcl": is_tehran_excl, "isTehranCityOnly": is_tehran_city_only})


async def _click_validate(page, bot: Bot, user_id: int):
    for _ in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst1');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        await asyncio.sleep(12)
        await _close_error_popup(page)
        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        if has_table:
            return
        await asyncio.sleep(5)


async def _click_validate_archive(page, bot: Bot, user_id: int):
    """کلیک دکمه صحت‌سنجی برای مسیر شماره بایگانی (btnAddHst2)"""
    for _ in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst2');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            # تلاش با متن دکمه
            clicked = await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.id === 'btnAddHst2' || 
                    (b.innerText && b.innerText.includes("صحت سنجی")));
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
        if not clicked:
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        await asyncio.sleep(12)
        await _close_error_popup(page)
        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        if has_table:
            return
        await asyncio.sleep(5)


async def _wait_for_case_table(page, timeout_sec: int = 30) -> bool:
    for _ in range(timeout_sec):
        has_table = await page.evaluate('''() => {
            const tbody = document.querySelector('table tbody');
            return tbody && tbody.querySelectorAll('tr').length > 0;
        }''')
        if has_table:
            return True
        await asyncio.sleep(1)
    return False


async def _wait_for_any_selector(page, selectors: list, timeout_sec: int = 15) -> str:
    """صبر می‌کند تا یکی از سلکتورهای داده‌شده روی صفحه ظاهر و قابل‌مشاهده شود؛ نام همان سلکتور را برمی‌گرداند یا None."""
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


async def _add_lawyer_person(page, national_id: str, bot: Bot, user_id: int):
    """افزودن وکیل در مرحله ارائه‌کننده لایحه"""
    # کلیک دکمه افزودن
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)

    await asyncio.sleep(3)

    # وارد کردن کدملی وکیل در فیلد txtNationalityCode
    # این فیلد برای ارائه‌کننده لایحه (وکیل) استفاده می‌شود
    candidate_selectors = [
        "#txtNationalityCode",
        "#txtRealIrNationalityCode1", 
        "#txtRealIrNationalityCode"
    ]
    found_selector = await _wait_for_any_selector(page, candidate_selectors, timeout_sec=15)

    if not found_selector:
        # هیچ‌کدام از سلکتورهای شناخته‌شده پیدا نشد — برای دیباگ، آی‌دی همه‌ی
        # اینپوت‌های موجود روی صفحه را لاگ می‌کنیم تا سلکتور درست پیدا شود
        visible_ids = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('input'))
                .filter(i => i.offsetParent !== null)
                .map(i => i.id || i.name || '(بدون id/name)');
        }''')
        logging.warning(f"[EALAM] فیلد کدملی وکیل پیدا نشد. اینپوت‌های قابل‌مشاهده روی صفحه: {visible_ids}")
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [EALAM] فیلد کدملی وکیل برای کاربر {user_id} پیدا نشد.\n"
            f"اینپوت‌های موجود: {visible_ids}"
        )
        return

    await _fill_input(page, found_selector, national_id)
    await asyncio.sleep(1)

    # استعلام از سامانه ثنا - کلیک دکمه استعلام
    await _click_sana_query(page, "actions.getLawyerDataWithSana", bot, user_id)


async def _click_sana_query(page, ng_click: str, bot: Bot, user_id: int, max_retries: int = 5):
    """کلیک دکمه استعلام و منتظر ماندن برای تکمیل"""
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EALAM] session renewed before query attempt {attempt+1}")
            continue

        # کلیک دکمه استعلام (آیکون refresh)
        clicked = await page.evaluate(f'''() => {{
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click}"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            return false;
        }}''')
        
        # اگر با ng-click پیدا نشد، سعی می‌کنیم با tooltip یا icon پیدا کنیم
        if not clicked:
            clicked = await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[tooltip*="استعلام ثنا"], button .glyphicon-refresh'));
                for (let btn of btns) {
                    const actualBtn = btn.tagName === 'BUTTON' ? btn : btn.closest('button');
                    if (actualBtn && !actualBtn.disabled) {
                        actualBtn.click();
                        return true;
                    }
                }
                return false;
            }''')
        
        if not clicked:
            logging.warning(f"[EALAM] دکمه استعلام پیدا نشد (تلاش {attempt+1})")

        # صبر اولیه
        await asyncio.sleep(3)

        # منتظر ناپدید شدن لودینگ افقی بالای صفحه
        had_loading_error = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if had_loading_error:
            logging.warning(f"[EALAM] خطا بعد از لودینگ استعلام — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از استعلام
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EALAM] session renewed after query attempt {attempt+1}")
            continue

        await _close_error_popup(page)

        # بررسی اینکه آیا داده‌ها از ثنا دریافت شده است
        extracted = await page.evaluate('''() => {
            const disabled = document.querySelector('input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"], input[disabled]');
            return disabled !== null;
        }''')
        if extracted:
            logging.info(f"[EALAM] داده‌های وکیل از ثنا دریافت شد")
            # اگر وکیل از ثنا استخراج شد، دکمه "ثبت موقت" یا "افزودن" را بزن
            await asyncio.sleep(2)
            await _click_add_lawyer_save(page, bot, user_id)
            return
        await asyncio.sleep(3)
    
    logging.warning(f"[EALAM] استعلام ثنا بعد از {max_retries} تلاش موفق نشد")


async def _click_add_lawyer_save(page, bot: Bot, user_id: int):
    """کلیک دکمه ثبت موقت بعد از افزودن وکیل"""
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnSave, button[ng-click*="setJSSBillData"]');
        if (btn && !btn.disabled) { 
            btn.click(); 
            return true; 
        }
        return false;
    }''')
    
    if not clicked:
        # جستجو با متن دکمه
        clicked = await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const saveBtn = btns.find(b => 
                b.innerText && (
                    b.innerText.includes('ثبت موقت') || 
                    b.innerText.includes('افزودن')
                )
            );
            if (saveBtn && !saveBtn.disabled) {
                saveBtn.click();
                return true;
            }
            return false;
        }''')
    
    if clicked:
        logging.info(f"[EALAM] دکمه ثبت موقت/افزودن کلیک شد")
        await asyncio.sleep(3)
    else:
        logging.warning(f"[EALAM] دکمه ثبت موقت پیدا نشد")


async def _fill_text_editor(page, text: str, bot: Bot, user_id: int, stored_html: str = ""):
    # استفاده از HTML ورد در صورت وجود، در غیر اینصورت تبدیل متنی
    text_html = stored_html if stored_html else _text_to_editor_html(text)
    await page.evaluate('''(html) => {
        const editor = document.querySelector('[contenteditable="true"][ta-bind]');
        if (editor) {
            editor.focus();
            editor.innerHTML = html;
            editor.dispatchEvent(new Event("input", { bubbles: true }));
            editor.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', text_html)
    await asyncio.sleep(1)

    # اعمال H3
    await page.evaluate('''() => {
        const editor = document.querySelector('[contenteditable="true"][ta-bind]');
        if (editor) {
            const range = document.createRange();
            range.selectNodeContents(editor);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
        }
    }''')
    await asyncio.sleep(0.5)
    await page.evaluate('''() => {
        const btn = document.querySelector('button[name="h3"]') ||
                    Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
        if (btn && !btn.disabled) btn.click();
    }''')
    await asyncio.sleep(0.5)


async def _click_save_temp_with_retry(page, bot: Bot, user_id: int, max_retries: int = 5):
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EALAM] session renewed before save attempt {attempt+1}")
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
            logging.warning(f"[EALAM] خطا بعد از لودینگ ثبت موقت — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از ثبت
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[EALAM] session renewed after save attempt {attempt+1}")
            continue

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            await _close_success_popup(page)
            return

        error_text = await _get_and_close_error_popup_text(page)
        if error_text:
            # بررسی session expiry در متن خطا
            if ("منقضی" in error_text or "منقضي" in error_text or
                "رایانه ای دیگر" in error_text or "اعتبار ورود" in error_text):
                logging.warning(f"[EALAM] session expiry in error text after save")
                await handle_session_expired(bot, user_id, page=page)
                continue

            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [EALAM] خطا در ثبت موقت کاربر {user_id}: {error_text}"
            )
            raise EalamFatalError(error_text)
        await asyncio.sleep(5)


async def _click_goto_main(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await soft_click_if_exists(page, "بازگشت به فهرست")


async def _upload_electronic_vakalaht(
    page, contract_number: str, lawyer_amount_value: int, bot: Bot, user_id: int
) -> bool:
    """
    انتخاب «تصویر الکترونیک وکالت نامه» و پر کردن فیلدهای مربوطه
    """
    for attempt in range(3):
        try:
            # بررسی انقضای نشست قبل از شروع این پیوست (بخش منضمات قبلاً این چک را نداشت)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info("[EALAM][منضمات] نشست در ابتدای ثبت وکالت‌نامه الکترونیک تمدید شد؛ ادامه از همین‌جا...")

            # انتخاب نوع پیوست «تصوير الكترونيك وكالت نامه» (value=object:2812)
            selected = await page.evaluate('''() => {
                const sel = document.querySelector('#attachmentType');
                if (!sel) return false;
                const opts = Array.from(sel.options);
                const opt = opts.find(o =>
                    o.text.includes("تصوير الكترونيك وكالت نامه") ||
                    o.text.includes("تصویر الکترونیک وکالت نامه") ||
                    o.text.includes("الكترونيك وكالت")
                );
                if (opt) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event("change"));
                    return true;
                }
                return false;
            }''')

            if not selected:
                logging.warning(f"[EALAM] گزینه «تصویر الکترونیک وکالت نامه» یافت نشد (تلاش {attempt+1})")
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(3)

            # پر کردن شماره وکالت‌نامه (txtNo)
            if contract_number:
                await page.evaluate(f'''() => {{
                    const inp = document.querySelector('#txtNo');
                    if (inp) {{
                        inp.value = "{contract_number}";
                        inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}
                }}''')
                await asyncio.sleep(1)

            # پر کردن مبلغ تمبر (txtLawyerAmount) — فقط عدد، بدون کاراکتر
            if lawyer_amount_value > 0:
                await page.evaluate(f'''() => {{
                    const inp = document.querySelector('#txtLawyerAmount');
                    if (inp) {{
                        // حذف disabled موقت
                        inp.removeAttribute('disabled');
                        inp.removeAttribute('ng-disabled');
                        inp.value = "{lawyer_amount_value}";
                        inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}
                }}''')
                await asyncio.sleep(1)

            # کلیک «ثبت و ویرایش پیوست»
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
                logging.info("[EALAM][منضمات] نشست حین انتظار برای ذخیره‌ی وکالت‌نامه تمدید شد؛ تلاش دوباره...")
                continue

            # بررسی نتیجه
            success = await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (!popup) return false;
                const icon = popup.querySelector('.sa-icon.sa-success');
                return icon && window.getComputedStyle(icon).display !== 'none';
            }''')

            if success:
                await _close_success_popup(page)
                logging.info("[EALAM] ثبت وکالت‌نامه الکترونیک موفق.")
                return True

            # خطا — بخوان و retry
            error_text = await _get_and_close_error_popup_text(page)
            if error_text:
                logging.warning(f"[EALAM] خطای ثبت وکالت‌نامه: {error_text} (تلاش {attempt+1})")
                await asyncio.sleep(5)
                continue

        except Exception as e:
            logging.error(f"[EALAM] _upload_electronic_vakalaht تلاش {attempt+1}: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_upload_electronic_vakalaht", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
            await asyncio.sleep(5)

    return False


async def _upload_other_attachment(page, title: str, image_paths: list, bot: Bot, user_id: int):
    """آپلود پیوست‌های اضافی (سایر ضمائم) — مقاوم (از upload_helpers)"""
    from upload_helpers import resilient_upload_attachment

    if not image_paths:
        return

    result = await resilient_upload_attachment(
        page, title, image_paths, bot, user_id,
        prefix="EALAM")

    if not result["success"]:
        logging.error(f"[EALAM] آپلود [{title}] ناموفق: {result.get('error')}")
        await bot.send_message(ADMIN_ID, f"❌ [EALAM] آپلود {title} ناموفق | کاربر: {user_id}")
    else:
        logging.info(f"[EALAM] آپلود [{title}] موفق")


async def _click_preparation_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """
    جریان آماده‌سازی:
    1. کلیک دکمه «آماده سازی» (btnPreparation)
    2. ظاهر شدن پاپ‌آپ تایید و کلیک روی «تایید و آماده سازی»
    3. ظاهر شدن پاپ‌آپ موفقیت و کلیک روی «بستن»
    """
    for attempt in range(max_retries):
        # ۱. کلیک دکمه آماده‌سازی
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnPreparation');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(5)

        # ۲. منتظر پاپ‌آپ تایید (با دکمه «تایید و آماده سازی»)
        confirmation_popup = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const btn = popup.querySelector('button.confirm');
            return btn && btn.innerText && btn.innerText.includes("تایید");
        }''')
        
        if confirmation_popup:
            # کلیک روی دکمه «تایید و آماده سازی»
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(40 if attempt > 0 else 12)

        # ۳. بررسی پاپ‌آپ موفقیت (با آیکون success و متن «آماده سازی»)
        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            const h2 = popup.querySelector('h2');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && h2.innerText.includes("آماده سازی");
        }''')
        
        if success:
            # کلیک روی دکمه «بستن» در پاپ‌آپ موفقیت
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(2)
            return True

        # اگر خطا بود، ببندیم و retry کنیم
        await _close_error_popup(page)
        await asyncio.sleep(30)
        await _close_success_popup(page)
    return False


async def _calculate_cost_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> int:
    """محاسبه هزینه اعلام وکالت — پارس جدول هزینه‌ها و محاسبه مبلغ کل.

    جدول هزینه شامل ردیف‌هایی با ستون مبلغ و یک ردیف «جمع کل هزینه»
    (با پس‌زمینه سبز) است.

    منطق محاسبه:
      1. استخراج مبلغ جمع کل (costSum) از td.color-green
      2. استخراج مبالغ ردیف‌ها از td.color-red
      3. کم کردن ردیف ۷ (تمبر مالیاتی ماده 103) و ردیف ۸ (تمبر سهم صندوق) از جمع کل
      4. رند بالا به نزدیک‌ترین ۱۰,۰۰۰ ریال
      5. اعمال فرمول کسر بر اساس بازه مبلغ:
         - تا ۲,۰۰۰,۰۰۰ ریال → کسر ۱۰۰,۰۰۰ ریال
         - ۲,۰۰۰,۰۰۱ تا ۳,۰۰۰,۰۰۰ → کسر ۲۸۰,۰۰۰ ریال
         - بالای ۳,۰۰۰,۰۰۱ → کسر ۴۰۰,۰۰۰ ریال
      6. مبلغ نهایی = مبلغ_رند + (مبلغ_رند − کسر)

    اگر جدول بعد از ۳۰ ثانیه نمایش داده نشد، دکمه
    «محاسبه هزینه دادرسی و تعرفه خدمات» کلیک می‌شود.
    """
    for attempt in range(max_retries):
        await _close_error_popup(page)
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
                const all = Array.from(document.querySelectorAll('button'));
                const tb = all.find(b => b.innerText && b.innerText.includes("محاسبه هزینه دادرسی") && !b.disabled);
                if (tb) { tb.click(); return true; }
                return false;
            }''')
            await asyncio.sleep(40)

            # بررسی مجدد — اگر هنوز جدول نیست، صبر بیشتر
            if attempt < 2:
                table_visible = await page.evaluate('''() => {
                    const tds = Array.from(document.querySelectorAll('table td.color-green, table td.color-red'));
                    return tds.length > 0;
                }''')
                if not table_visible:
                    logging.warning(f"[EALAM] جدول هزینه نمایش داده نشد — تلاش مجدد با فاصله ۴۰ ثانیه")
                    await asyncio.sleep(40)
                    await page.evaluate('''() => {
                        const btn = document.querySelector('#btnCalculateCash');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await asyncio.sleep(10)

        await _close_error_popup(page)

        # استخراج تمام مبالغ و نام ردیف‌ها از جدول
        cost_data = await page.evaluate('''() => {
            // استخراج مبلغ جمع کل (td.color-green — سلول سبز رنگ)
            const greenTds = Array.from(document.querySelectorAll('table td.color-green'));
            let costSum = 0;
            for (const td of greenTds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 0) {
                    costSum = parseInt(text);
                }
            }

            // استخراج مبالغ و نام ردیف‌ها
            const labels = [];
            const rows = Array.from(document.querySelectorAll('table tr'));
            for (const row of rows) {
                const tds = Array.from(row.querySelectorAll('td'));
                if (tds.length >= 3) {
                    const label = tds[1].innerText.trim();
                    const amountText = tds[2].innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                    if (label && /^[0-9]+$/.test(amountText)) {
                        labels.push({label: label, amount: parseInt(amountText), rowIndex: labels.length + 1});
                    }
                }
            }

            return {
                costSum: costSum,
                labels: labels
            };
        }''')

        if cost_data and cost_data.get("costSum", 0) > 0:
            cost_sum = cost_data["costSum"]
            labels = cost_data.get("labels", [])

            logging.info(f"[EALAM] costSum={cost_sum}, labels={labels}")

            # پیدا کردن مبلغ ردیف ۷ (تمبر مالیاتی ماده 103) و ردیف ۸ (تمبر سهم صندوق)
            stamp_tax = 0       # ردیف ۷: هزینه تمبر مالیاتی طبق ماده 103 م.م
            stamp_fund = 0      # ردیف ۸: هزینه تمبر سهم صندوق حمایت از وکلا و کارشناسان

            for item in labels:
                lbl = item.get("label", "")
                amt = item.get("amount", 0)
                if "تمبر مالياتي" in lbl or "تمبر مالیاتی" in lbl or "ماده 103" in lbl:
                    stamp_tax = amt
                elif "صندوق حمايت" in lbl or "صندوق حمایت" in lbl or "صندوق حمايت از وكلا" in lbl:
                    stamp_fund = amt

            # کم کردن ردیف ۷ و ۸ از جمع کل
            adjusted = cost_sum - stamp_tax - stamp_fund
            if adjusted < 0:
                adjusted = 0

            logging.info(
                f"[EALAM] محاسبه: costSum={cost_sum:,} - stamp_tax={stamp_tax:,} - stamp_fund={stamp_fund:,} = {adjusted:,}"
            )

            # رند بالا به نزدیک‌ترین ۱۰,۰۰۰ ریال
            remainder = adjusted % 10000
            if remainder == 0:
                rounded = adjusted
            else:
                rounded = adjusted + (10000 - remainder)

            # اعمال فرمول کسر
            if rounded <= 2_000_000:
                deduction = 100_000
            elif rounded <= 3_000_000:
                deduction = 280_000
            else:
                deduction = 400_000

            net = rounded - deduction
            final_total = rounded + net  # = 2 * rounded - deduction

            logging.info(
                f"[EALAM] محاسبه هزینه: adjusted={adjusted:,} -> rounded={rounded:,}, "
                f"deduction={deduction:,}, net={net:,}, final_total={final_total:,}"
            )

            return final_total

        await asyncio.sleep(10)

    logging.error(f"[EALAM] استخراج مبلغ پس از {max_retries} تلاش ناموفق (user={user_id})")
    return 0


async def _print_lavayeh(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    pdf_path = f"ealam_vakalaht_{bill_no}.pdf"
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
        logging.error(f"[EALAM] خطا در چاپ: {e}")
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
        if (btn) btn.click();
        return msg || null;
    }''')
    if text:
        await asyncio.sleep(1)
    return text


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
            path = f"ealam_img_{user_id}_{i}.{ext}"
            await bot.download_file(file_info.file_path, path)
            paths.append(path)
        except Exception as e:
            logging.error(f"[EALAM] خطا در دانلود تصویر {i} برای user {user_id}: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_download_images_from_bale", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
    return paths
