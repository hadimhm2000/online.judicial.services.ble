# -*- coding: utf-8 -*-
"""
⭐ اصلاحیه ۱۴۰۵/۰۶ — سناریوی تکمیل «شماره قرارداد وکالت» پس از پنجرهٔ ۴۵ دقیقه‌ای
═══════════════════════════════════════════════════════════════════════════════

وقتی در بخش منضمات (ثبت لایحه / اعلام وکالت / اظهارنامه / ثبت دادخواست /
دعاوی اعتراضی) پاپ‌آپ «شماره قرارداد الکترونیک وکالت «...» معتبر نمی باشد»
نمایش داده شود:
  - مرحلهٔ ثبت قرارداد اسکیپ و سایر پیوست‌های کاربر انجام می‌شود (در
    سناریوهای اصلی)
  - به کاربر اعلام می‌شود شماره قرارداد اشتباه است و ۴۵ دقیقه فرصت دارد
    کد قرارداد جدید را ارسال کند (nid_fix_window.start_contract_fix)
  - و کد قرارداد فرستاد، طبق کدرهگیری که ثبت شده، همان کدرهگیری استعلام
    می‌شود، سپس در بخش منضمات وارد می‌شویم، شماره قرارداد جدید و «مقدار
    تمبر» (حق‌الوکالهٔ کاربر) در فیلدهای مربوط درج، بلافاصله «ثبت و ویرایش
    پیوست» کلیک و پاپ‌آپ‌ها بررسی می‌شوند؛ پس از تایید، «بازگشت به فهرست» و
    ادامهٔ آماده‌سازی و هزینه و چاپ و ادامهٔ مراحل.

این ماژول همان «ادامهٔ ثبت» را پیاده‌سازی می‌کند — تسک CONTRACT_FIX_SUBMIT:
  ۱. استعلام کدرهگیری ثبت‌شده (bill_no) از منوی مربوط به هر سرویس
  ۲. ورود به مرحله «منضمات»
  ۳. انتخاب «تصوير الكترونيك وكالت نامه» + درج شماره قرارداد جدید
     + درج مقدار تمبر در «مبلغ حق الوکاله» (#txtLawyerAmount — همیشه،
     طبق دستور کارفرما) + کلیک بلافاصلهٔ «ثبت و ویرایش پیوست»
  ۴. انتظار پاپ‌آپ موفقیت و بستن آن
  ۵. آماده‌سازی → محاسبه هزینه → چاپ PDF → ارسال نتیجه به کاربر
  ۶. بستن پنجرهٔ ۴۵ دقیقه‌ای
"""
import asyncio
import logging
import os

from aiogram import Bot

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, goto_url_with_retry,
    human_delay, safe_click_by_text, wait_for_horizontal_loading_bar,
    handle_session_expired, wait_for_angular_idle)

# مسیر منوی پیش‌فرض هر سرویس (برای استعلام کدرهگیری)
MENU_BY_FLOW = {
    "lavayeh": ["ارایه و پیگیری لایحه"],
    "ealam": ["ارایه و پیگیری لایحه"],
    "ezhharnameh": ["ارایه و پیگیری اظهارنامه"],
    # check/tn از task_data["_contract_fix_menu_path"] / case_type استفاده می‌کنند
}


# ══════════════════════════════════════════════════════════════════════════════
# ناوبری — استعلام پرونده با کدرهگیری
# ══════════════════════════════════════════════════════════════════════════════

async def _resolve_menu_path(flow: str, task_data: dict) -> list:
    """تعیین مسیر منوی استعلام بر اساس سرویس (عین مسیر ثبت/امضای همان سرویس)."""
    custom = task_data.get("_contract_fix_menu_path")
    if isinstance(custom, list) and custom:
        return custom

    if flow == "check":
        # همان منطق process_check_task: دادگاه صلح → دعاوی صلح؛ بقیه → بدوی
        court_type = (task_data.get("check_court_type") or "").strip()
        amount = task_data.get("check_amount", 0) or 0
        from check_scenario import CHECK_AASAR_TITLES, CHECK_NO_AMOUNT_TITLES
        request_title = task_data.get("check_request_title", "")
        is_aasar_title = request_title in CHECK_AASAR_TITLES
        if is_aasar_title:
            is_high = (court_type != "صلح")
        elif request_title in CHECK_NO_AMOUNT_TITLES:
            is_high = True
        else:
            is_high = amount > 1_000_000_000
        if is_high:
            return ["ارایه و پیگیری دادخواست", "دادخواست بدوی"]
        return ["دعاوی دادگاههای صلح", "دعاوی حقوقی"]

    if flow == "tn":
        # دعاوی اعتراضی — زیرمنوی همان نوع دعوی (الگوی ناوبری امضا)
        case_type = task_data.get("case_type", "")
        if case_type:
            return [case_type]
        return ["دعاوی اعتراضی"]

    return MENU_BY_FLOW.get(flow, ["ارایه و پیگیری لایحه"])


async def _click_menus(page, menu_path: list, bot: Bot, user_id: int):
    """کلیک روی مسیر منوی استعلام (a.list-group-item + li زیرمنو)."""
    for i, menu_text in enumerate(menu_path):
        clicked = await page.evaluate('''(text) => {
            const items = Array.from(document.querySelectorAll(
                'a.list-group-item, li.list-group-item'));
            const t = items.find(el => {
                const tx = (el.innerText || "").trim();
                return tx === text || tx.includes(text);
            });
            if (t) { t.click(); return true; }
            return false;
        }''', menu_text)
        if not clicked:
            try:
                await safe_click_by_text(page, menu_text, bot, user_id)
            except Exception:
                pass
        await resilient_sleep(page, 5, bot, user_id)


async def _query_bill_by_tracking_code(page, bill_no: str, bot: Bot, user_id: int) -> bool:
    """استعلام پرونده با کدرهگیری — الگوی ناوبری امضا:
    ۱) اگر #rdbGetPetition وجود داشت → رادیو value=2 → #billNo → #btnGetJSSBill
    ۲) وگرنه اگر #txtPetitionNo بود → مستقیم #txtPetitionNo → #btnGetJSSPetition
    (دقیقاً عین دستور کارفرما: «طبق کدرهگیری که ثبت شده، همان کدرهگیری را
    استعلام میکنی»)
    """
    # ── تشخیص الگوی صفحه ──
    has_radio = await page.evaluate('''() => !!document.querySelector('#rdbGetPetition')''')
    has_petition_field = False
    if not has_radio:
        has_petition_field = await page.evaluate(
            '''() => { const el = document.querySelector('#txtPetitionNo');
                      return !!(el && el.offsetParent !== null); }''')

    if has_radio:
        try:
            await page.wait_for_selector('#rdbGetPetition', state='visible', timeout=10000)
        except Exception:
            pass
        await page.evaluate('''() => {
            const radio = document.querySelector('#rdbGetPetition');
            if (radio) {
                radio.checked = true;
                radio.click();
                if (window.angular) {
                    try { angular.element(radio).scope().$apply(); } catch(e) {}
                }
            }
        }''')
        await asyncio.sleep(1)

        try:
            await page.wait_for_selector('#billNo', state='visible', timeout=15000)
        except Exception:
            pass
        await page.fill('#billNo', bill_no)
        await asyncio.sleep(1)
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSBill');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')
    elif has_petition_field:
        await page.fill('#txtPetitionNo', bill_no)
        await asyncio.sleep(1)
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')
    else:
        logging.warning("[CONTRACT-FIX] نه رادیو #rdbGetPetition و نه فیلد #txtPetitionNo پیدا نشد")
        return False

    # ── انتظار بارگذاری پرونده ──
    await asyncio.sleep(15)
    await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
    try:
        from browser_helpers import check_and_handle_expiry as _che
        await _che(page, bot, user_id)
    except Exception:
        pass
    # بستن پاپ‌آپ احتمالی
    await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (popup) { const b = popup.querySelector('button.confirm'); if (b) b.click(); }
    }''')
    await resilient_sleep(page, 3, bot, user_id)

    # ── اعتبارسنجی: جدول پرونده یا باکس‌های مراحل باید ظاهر شده باشند ──
    ok = await page.evaluate('''() => {
        const rows = document.querySelectorAll('table tbody tr').length;
        const boxes = Array.from(document.querySelectorAll('.box h5'));
        return rows > 0 || boxes.some(el =>
            (el.innerText || '').includes('منضمات') ||
            (el.innerText || '').includes('آماده'));
    }''')
    return bool(ok)


# ══════════════════════════════════════════════════════════════════════════════
# ثبت وکالت‌نامه الکترونیک — فقط شماره قرارداد جدید
# ══════════════════════════════════════════════════════════════════════════════

async def _enter_attachments_section(page, bot: Bot, user_id: int) -> bool:
    """کلیک باکس «منضمات» با تلاش مجدد."""
    from lavayeh_scenario import _click_step_box as _lav_step_box
    for attempt in range(3):
        await _lav_step_box(page, "منضمات", bot, user_id)
        await resilient_sleep(page, 5, bot, user_id)
        has_error = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-error');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if not has_error:
            # بررسی اینکه فرم منضمات واقعاً باز شده (سلکت نوع پیوست موجود است)
            ready = await page.evaluate(
                '''() => !!document.querySelector('#attachmentType')''')
            if ready:
                return True
            logging.warning(
                f"[CONTRACT-FIX] فرم منضمات باز نشد (تلاش {attempt+1}/3)")
        await asyncio.sleep(3)
    return False


async def _register_new_contract(page, contract_number: str, stamp_amount_value: int,
                                 bot: Bot, user_id: int) -> str:
    """درج شماره قرارداد جدید در فرم «تصوير الكترونيك وكالت نامه».

    ⭐ اصلاحیهٔ دوم ۱۴۰۵/۰۶ (طبق دستور کارفرما):
      بعد از درج شماره قرارداد، «مقدار تمبری که از قبل کاربر وارد کرده بود»
      حتماً در فیلد «مبلغ حق الوکاله» (#txtLawyerAmount) درج می‌شود و
      بلافاصله دکمهٔ «ثبت و ویرایش پیوست» (#btnSaveDoc) کلیک و سپس
      پاپ‌آپ‌ها بررسی می‌شوند. (نسخهٔ قبلی مبلغ را فقط به‌عنوان فال‌بکِ
      «دکمهٔ غیرفعال» درج می‌کرد؛ چون ng-disabled دکمه فقط به
      viewModel.loading وابسته است، مبلغ هیچ‌وقت درج نمی‌شد، فرم نامعتبر
      بی‌صدا رد می‌شد و هیچ پاپ‌آپی ظاهر نمی‌شد — ریشهٔ باگ گزارش‌شده.)

    خروجی: "success" | "invalid_contract" | "failed"
    """
    from upload_helpers import (
        click_save_doc_once, wait_save_doc_popup_result, close_save_doc_popup,
        fill_input_angular, _get_table_rows_text)

    for attempt in range(3):
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(2)

        # بستن هر پاپ‌آپ باقی‌مانده از تلاش قبل (در صورت وجود)
        await close_save_doc_popup(page)

        # ۰) اطمینان از باز بودن فرم منضمات — بازیابی از حالت خراب تلاش قبل
        form_open = await page.evaluate('''() => {
            const el = document.querySelector('#attachmentType');
            if (!el) return false;
            const st = window.getComputedStyle(el);
            return st.display !== 'none' && st.visibility !== 'hidden';
        }''')
        if not form_open:
            logging.info("[CONTRACT-FIX] فرم منضمات باز نیست — بازگشایی...")
            if not await _enter_attachments_section(page, bot, user_id):
                logging.warning(f"[CONTRACT-FIX] بازگشایی فرم منضمات ناموفق (تلاش {attempt+1}/3)")
                await asyncio.sleep(5)
                continue

        # ۱) انتخاب نوع پیوست
        selected = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel) return false;
            const opts = Array.from(sel.options);
            const opt = opts.find(o =>
                o.text.includes("تصوير الكترونيك وكالت نامه") ||
                o.text.includes("تصویر الکترونیک وکالت نامه") ||
                o.text.includes("الكترونيك وكالت"));
            if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change")); return true; }
            return false;
        }''')
        if not selected:
            logging.warning(f"[CONTRACT-FIX] گزینه «تصویر الکترونیک وکالت نامه» پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(3)

        # ۲) شماره قرارداد جدید (#txtNo) — همگام‌سازی کامل AngularJS
        await fill_input_angular(page, "#txtNo", contract_number, prefix="CONTRACT-FIX")
        await asyncio.sleep(1)

        # ۳) ⭐ درج مقدار تمبر در «مبلغ حق الوکاله» (#txtLawyerAmount) — همیشه
        #    طبق دستور کارفرما: بعد از شماره قرارداد، مبلغ تمبری که از قبل
        #    کاربر وارد کرده بود درج و بلافاصله دکمهٔ ثبت زده می‌شود.
        #    (fill_input_angular ماندگاری مقدار را کنترل و در صورت نیاز
        #     دوباره درج می‌کند)
        if stamp_amount_value:
            await fill_input_angular(page, "#txtLawyerAmount", int(stamp_amount_value),
                                     prefix="CONTRACT-FIX")
            await asyncio.sleep(1)
        else:
            logging.warning("[CONTRACT-FIX] مقدار تمبری در پنجرهٔ ۴۵ دقیقه‌ای ذخیره نشده بود — فقط شماره قرارداد درج می‌شود")

        # ۴) کنترل وجود دکمهٔ ثبت قبل از کلیک (جلوگیری از حلقهٔ not_found)
        btn_visible = False
        for _btn_wait in range(3):
            btn_visible = await page.evaluate('''() => {
                const el = document.querySelector('#btnSaveDoc');
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return st.display !== 'none' && st.visibility !== 'hidden';
            }''')
            if btn_visible:
                break
            await asyncio.sleep(3)
        if not btn_visible:
            logging.warning(f"[CONTRACT-FIX] #btnSaveDoc در فرم نیست — بازگشایی منضمات (تلاش {attempt+1})")
            try:
                await _enter_attachments_section(page, bot, user_id)
            except Exception as _re:
                logging.warning(f"[CONTRACT-FIX] بازگشایی منضمات ناموفق: {_re}")
            await asyncio.sleep(3)
            continue

        # ۵) کلیک «ثبت و ویرایش پیوست» + انتظار قطعی پاپ‌آپ
        clicked = await click_save_doc_once(page, prefix="CONTRACT-FIX")
        if not clicked:
            logging.warning(f"[CONTRACT-FIX] کلیک #btnSaveDoc انجام نشد (تلاش {attempt+1})")
            try:
                await _enter_attachments_section(page, bot, user_id)
            except Exception:
                pass
            await asyncio.sleep(3)
            continue

        popup = await wait_save_doc_popup_result(page, timeout_sec=45, prefix="CONTRACT-FIX")

        if popup["status"] == "none":
            # پاپ‌آپی ظاهر نشد — شاید ثبت بدون پاپ‌آپ انجام شده باشد؛
            # جدول منضمات بررسی می‌شود تا ثبتِ تکراری رخ ندهد.
            await asyncio.sleep(3)
            try:
                _rows = await _get_table_rows_text(page, max_rows=15)
            except Exception:
                _rows = []
            if any(("الكترونيك وكالت" in r) or ("الکترونیک وکالت" in r) for r in _rows):
                logging.info("[CONTRACT-FIX] پاپ‌آپی ظاهر نشد ولی ردیف «تصوير الكترونيك وكالت نامه» در جدول منضمات موجود است — ثبت موفق در نظر گرفته می‌شود.")
                await close_save_doc_popup(page)
                return "success"

        if popup["status"] == "success":
            from upload_helpers import close_success_popup as _uh_close
            await _uh_close(page)
            logging.info("[CONTRACT-FIX] پیوست « تصوير الكترونيك وكالت نامه » با موفقیت ثبت گردید.")
            return "success"

        if popup["status"] == "invalid_contract":
            await close_save_doc_popup(page)
            logging.error(f"[CONTRACT-FIX] کد قرارداد جدید «{contract_number}» هم معتبر نیست: {popup['text'][:150]}")
            return "invalid_contract"

        if popup["status"] == "session":
            logging.warning(f"[CONTRACT-FIX] ورود همزمان/انقضای نشست — لاگین مجدد: {popup['text'][:150]}")
            await close_save_doc_popup(page)
            try:
                await handle_session_expired(bot, user_id, page=page)
            except Exception:
                pass
            await asyncio.sleep(5)
            continue

        if popup["status"] == "error":
            logging.warning(f"[CONTRACT-FIX] خطای ثبت: {popup['text'][:200]} (تلاش {attempt+1})")
            await close_save_doc_popup(page)
            await asyncio.sleep(5)
            continue

        await asyncio.sleep(5)

    return "failed"


# ══════════════════════════════════════════════════════════════════════════════
# دنبالهٔ ثبت — آماده‌سازی، هزینه، چاپ و ارسال نتیجه (بر اساس سرویس)
# ══════════════════════════════════════════════════════════════════════════════

async def _finish_bill_style(page, flow: str, bill_no: str,
                             bot: Bot, user_id: int) -> dict:
    """آماده‌سازی + هزینه + چاپ برای سرویس‌های لایحه‌محور (لایحه/اعلام وکالت/
    اظهارنامه/دعاوی اعتراضی — همان صفحهٔ مشترک سامانه)."""
    from lavayeh_scenario import (
        _click_step_box as _lav_step_box, _click_goto_main as _lav_goto_main,
        _click_preparation_with_retry as _prep, _calculate_cost_with_retry as _cost,
        _print_lavayeh as _print)

    prep_box = ("آماده سازي جهت محاسبه هزينه و ارسال" if flow in ("lavayeh", "ealam")
                else "آماده سازي جهت دريافت وجه")

    await _lav_step_box(page, prep_box, bot, user_id)
    await resilient_sleep(page, 5, bot, user_id)
    if not await _prep(page, bot, user_id):
        return {"success": False, "error": "آماده‌سازی ناموفق"}
    await _lav_goto_main(page, bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    await _lav_step_box(page, "محاسبه و دريافت هزينه", bot, user_id)
    await resilient_sleep(page, 8, bot, user_id)
    cost_info = await _cost(page, bot, user_id)
    if isinstance(cost_info, dict):
        court_total = int(cost_info.get("final_total", 0) or cost_info.get("main_total", 0) or 0)
    else:
        court_total = int(cost_info or 0)

    await _lav_goto_main(page, bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    pdf_path = await _print(page, runtime_state.browser_context, bill_no, bot, user_id)
    return {"success": True, "cost": court_total, "pdf_path": pdf_path}


async def _finish_check(page, bill_no: str, branch_code: str,
                        bot: Bot, user_id: int) -> dict:
    """آماده‌سازی (تایید اطلاعات) + هزینه + چاپ برای ثبت دادخواست (چک/اعسار)."""
    from check_scenario import (
        _click_step_box as _chk_step_box, _extract_cost_data, _print_check)

    await _chk_step_box(page, "آماده سازي جهت دريافت وجه", bot, user_id)
    await resilient_sleep(page, 5, bot, user_id)

    # کد صلاحیت دادگاه
    if branch_code:
        await page.evaluate('''(code) => {
            const inp = document.querySelector('#txtSendUnitCode');
            if (inp) {
                inp.value = code;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }''', branch_code)
        await asyncio.sleep(2)

    # تایید اطلاعات (#btnCalculateCash) + پاپ‌آپ تایید — عین process_check_task
    confirm_ok = False
    for _attempt in range(4):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnCalculateCash') ||
                        Array.from(document.querySelectorAll('button'))
                            .find(b => b.innerText.includes("تایید اطلاعات"));
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            confirm_ok = True  # از قبل تایید شده
            break
        await wait_for_horizontal_loading_bar(page, bot, user_id)
        await resilient_sleep(page, 5, bot, user_id)

        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(3)
            continue

        popup_text = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            return ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim();
        }''')
        if not popup_text:
            confirm_ok = True
            break
        if "تایید" in popup_text or "تاييد" in popup_text:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('.sweet-alert button.confirm'));
                const t = btns.find(b => b.innerText.includes("تایید"));
                if (t) t.click();
            }''')
            await wait_for_horizontal_loading_bar(page, bot, user_id)
            await resilient_sleep(page, 5, bot, user_id)
            continue
        # پاپ‌آپ دیگر (خطا) → بستن و تلاش مجدد
        await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) { const b = popup.querySelector('button.confirm'); if (b) b.click(); }
        }''')
        await asyncio.sleep(4)

    if not confirm_ok:
        logging.warning("[CONTRACT-FIX][CHECK] تایید اطلاعات بعد از ۴ تلاش قطعی نشد — ادامه با احتیاط")

    await resilient_sleep(page, 5, bot, user_id)

    cost_data = await _extract_cost_data(page)
    final_total = int((cost_data or {}).get("final_total", 0) or 0)

    pdf_path = await _print_check(page, runtime_state.browser_context, bill_no, bot, user_id)
    return {"success": True, "cost": final_total, "pdf_path": pdf_path}


# ══════════════════════════════════════════════════════════════════════════════
# تسک اصلی
# ══════════════════════════════════════════════════════════════════════════════

async def process_contract_fix_task(data: dict, bot: Bot):
    """تسک CONTRACT_FIX_SUBMIT — ثبت قرارداد جدید و ادامهٔ مراحل ثبت.

    ورودی:
      {
        "task_type": "CONTRACT_FIX_SUBMIT",
        "user_id": int,
        "flow": "lavayeh"|"ealam"|"ezhharnameh"|"check"|"tn",
        "bill_no": str,
        "contract_number": str,
        "stamp_amount_value": int,
        "task_data": dict,
      }
    """
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]
    flow = data.get("flow", "lavayeh")
    bill_no = str(data.get("bill_no", "") or "")
    contract_number = str(data.get("contract_number", "") or "")
    stamp_amount_value = int(data.get("stamp_amount_value", 0) or 0)
    task_data = data.get("task_data") or {}

    flow_labels = {
        "lavayeh": "لایحه", "ealam": "اعلام وکالت", "ezhharnameh": "اظهارنامه",
        "check": "دادخواست", "tn": "دعاوی اعتراضی",
    }
    flow_label = flow_labels.get(flow, flow)

    logging.info(
        f"[CONTRACT-FIX] شروع: user={user_id} flow={flow} bill={bill_no} "
        f"contract={contract_number} stamp={stamp_amount_value}")

    await bot.send_message(
        user_id,
        f"⏳ در حال ثبت قرارداد جدید و ادامهٔ ثبت {flow_label}...\n"
        f"🔢 کد رهگیری: `{bill_no}`\n📑 کد قرارداد: `{contract_number}`",
        parse_mode="Markdown")

    menu_path = await _resolve_menu_path(flow, task_data)

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
            if not ok:
                return
            await human_delay(3.0, 5.0)
            await check_and_handle_expiry(sana_page, bot, user_id)

            # ── ۱. استعلام کدرهگیری ثبت‌شده ──
            await _click_menus(sana_page, menu_path, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            queried = await _query_bill_by_tracking_code(sana_page, bill_no, bot, user_id)
            if not queried:
                logging.warning(
                    f"[CONTRACT-FIX] استعلام کدرهگیری {bill_no} موفق نشد (تلاش {attempt+1})")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5)
                    continue
                await bot.send_message(
                    user_id,
                    f"⚠️ استعلام پرونده با کد رهگیری `{bill_no}` انجام نشد.\n"
                    f"لطفاً با پشتیبانی در تماس باشید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CONTRACT-FIX] استعلام کدرهگیری {bill_no} برای کاربر {user_id} "
                    f"ناموفق — قرارداد جدید {contract_number} ثبت نشد.")
                return

            # ── ۲. ورود به منضمات ──
            if not await _enter_attachments_section(sana_page, bot, user_id):
                await bot.send_message(
                    user_id,
                    f"⚠️ ورود به بخش منضمات برای کد رهگیری `{bill_no}` انجام نشد.\n"
                    f"لطفاً با پشتیبانی در تماس باشید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CONTRACT-FIX] ورود به منضمات کاربر {user_id} ناموفق | کد: {bill_no}")
                return

            # ── ۳. ثبت شماره قرارداد جدید ──
            status = await _register_new_contract(
                sana_page, contract_number, stamp_amount_value, bot, user_id)

            if status == "invalid_contract":
                # کد جدید هم نامعتبر — پنجره تا پایان مهلت باز می‌ماند
                await bot.send_message(
                    user_id,
                    f"❌ کد قرارداد «{contract_number}» نیز در سامانه معتبر نیست.\n\n"
                    f"⏰ تا پایان مهلت ۴۵ دقیقه‌ای می‌توانید کد دیگری ارسال فرمائید.",
                    parse_mode="Markdown")
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CONTRACT-FIX] کد قرارداد جدید {contract_number} برای کاربر "
                    f"{user_id} (کد: {bill_no}) هم نامعتبر بود.")
                return

            if status != "success":
                logging.error(f"[CONTRACT-FIX] ثبت قرارداد ناموفق (تلاش {attempt+1})")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5)
                    continue
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت قرارداد در بخش منضمات با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CONTRACT-FIX] ثبت قرارداد جدید {contract_number} برای کاربر "
                    f"{user_id} (کد: {bill_no}) ناموفق.")
                return

            # ── ۴. بازگشت به فهرست و ادامهٔ آماده‌سازی/هزینه/چاپ ──
            from lavayeh_scenario import _click_goto_main as _lav_goto_main
            await _lav_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            if flow in ("check",):
                branch_code = task_data.get("check_branch_code", "")
                result = await _finish_check(sana_page, bill_no, branch_code, bot, user_id)
            else:
                result = await _finish_bill_style(sana_page, flow, bill_no, bot, user_id)

            if not result.get("success"):
                await bot.send_message(
                    user_id,
                    f"⚠️ مرحله آماده‌سازی/هزینه با مشکل مواجه شد.\n"
                    f"🔢 کد رهگیری: `{bill_no}`\n"
                    f"قرارداد وکالت با کد `{contract_number}` ثبت شده است؛ "
                    f"ادامهٔ مراحل توسط پشتیبانی پیگیری می‌شود.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CONTRACT-FIX] آماده‌سازی/هزینه پس از ثبت قرارداد ناموفق | "
                    f"کاربر {user_id} | کد: {bill_no} | خطا: {result.get('error', '')}")
                return

            court_total = result.get("cost", 0)
            pdf_path = result.get("pdf_path", "")

            # ── ۵. ارسال نتیجه (فاکتور + امضا) — عین سناریوی اصلی هر سرویس ──
            await _send_result(bot, user_id, flow, task_data, bill_no,
                               pdf_path, court_total, contract_number)

            # ── ۶. بستن پنجرهٔ ۴۵ دقیقه‌ای + ثبت رویداد ──
            try:
                import nid_fix_window
                nid_fix_window.pop_contract_fix(user_id)
            except Exception:
                pass

            await log_event(
                "ثبت", flow_label, str(user_id), user_id,
                tracking_code=bill_no, doc_name=flow_label,
                note=f"کد قرارداد جدید {contract_number} ثبت و مراحل ادامه یافت | هزینه: {court_total:,} ریال")

            await bot.send_message(
                ADMIN_ID,
                f"✅ [CONTRACT-FIX] کد قرارداد جدید {contract_number} برای کاربر {user_id} "
                f"ثبت و ادامهٔ مراحل ({flow_label} — کد: {bill_no}) انجام شد. "
                f"هزینه: {court_total:,} ریال")
            return

        except Exception as e:
            logging.error(f"[CONTRACT-FIX] تلاش {attempt+1} ناموفق برای user={user_id}: {e}", exc_info=True)
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="process_contract_fix_task", error=e,
                                 user_id=user_id, bill_no=bill_no, page=sana_page)
            except Exception:
                pass
            if attempt < max_attempts - 1:
                try:
                    from lavayeh_scenario import _reload_page_with_settle
                    await _reload_page_with_settle(sana_page, prefix="CONTRACT-FIX")
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ادامهٔ ثبت با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CONTRACT-FIX] پس از {max_attempts} تلاش ناموفق | کاربر {user_id} | "
                    f"کد: {bill_no} | قرارداد: {contract_number}")


async def _send_result(bot: Bot, user_id: int, flow: str, task_data: dict,
                       bill_no: str, pdf_path: str, court_total: int,
                       contract_number: str):
    """ارسال نتیجهٔ نهایی — عین سناریوی اصلی هر سرویس (فاکتور + امضا)."""
    from lavayeh_handlers import send_lavayeh_result
    from panel_sync import upsert_case_to_panel

    def _persons_national_ids(persons):
        return ", ".join([
            p.get("national_id", "") for p in (persons or []) if p.get("national_id")
        ])

    try:
        if flow in ("lavayeh", "ealam", "ezhharnameh", "check", "tn"):
            if flow in ("lavayeh", "ealam"):
                persons = task_data.get("lavayeh_persons", [])
                title = task_data.get("lavayeh_title", "لایحه دفاعیه")
                if flow == "ealam":
                    title = "اعلام وکالت"
                service_type = "EALAM_VAKALAHT" if flow == "ealam" else "LAVAYEH"
                await send_lavayeh_result(
                    bot, user_id, pdf_path, court_total,
                    tracking_code=bill_no,
                    national_ids=_persons_national_ids(persons),
                    lavayeh_title=title,
                    lavayeh_province=task_data.get("lavayeh_province", ""),
                    lavayeh_row_number=task_data.get("lavayeh_row_number", 1),
                    lavayeh_persons=persons,
                    skip_fee_calc=True,
                    service_type=service_type)
            elif flow == "ezhharnameh":
                declarants = task_data.get("ezhhar_declarants", [])
                subject = task_data.get("ezhharnameh_subject", "اظهارنامه")
                await send_lavayeh_result(
                    bot, user_id, pdf_path, court_total,
                    tracking_code=bill_no,
                    national_ids=_persons_national_ids(declarants),
                    lavayeh_title=f"اظهارنامه — {subject}",
                    lavayeh_province="",
                    lavayeh_row_number=1,
                    lavayeh_persons=declarants,
                    skip_fee_calc=True,
                    is_ezhharnameh=True,
                    prepaid=task_data.get("prepaid", False))
            elif flow == "check":
                plaintiffs = task_data.get("check_plainiffs", [])
                request_title = task_data.get("check_request_title", "دادخواست")
                sign_menu_path = task_data.get("_contract_fix_menu_path") or \
                    ["ارایه و پیگیری دادخواست", "دادخواست بدوی"]
                await send_lavayeh_result(
                    bot, user_id, pdf_path, court_total,
                    tracking_code=bill_no,
                    national_ids=_persons_national_ids(plaintiffs),
                    lavayeh_title=f"دادخواست چک — {request_title}" if request_title else "دادخواست",
                    lavayeh_province="",
                    lavayeh_row_number=1,
                    lavayeh_persons=plaintiffs,
                    skip_fee_calc=True,
                    is_ezhharnameh=False,
                    service_type="CHECK",
                    sign_menu_path=sign_menu_path)
            elif flow == "tn":
                # دعاوی اعتراضی — روال مستقل خودش (send_tajdid_nazar_result)
                from tajdid_nazar_handlers import send_tajdid_nazar_result
                appellants = task_data.get("tn_appellants", [])
                case_type = task_data.get("case_type", "دعاوی اعتراضی")
                file_no = task_data.get("tn_file_no", "")
                await send_tajdid_nazar_result(
                    bot, user_id, pdf_path, court_total,
                    tracking_code=bill_no,
                    national_ids=_persons_national_ids(appellants),
                    case_type=case_type,
                    file_no=file_no,
                    tn_persons=appellants,
                    cost_info={})
        else:
            raise ValueError(f"flow نامشخص: {flow}")

        # آپدیت پنل
        try:
            await upsert_case_to_panel(
                bale_user_id=user_id, full_name=str(user_id),
                service_type={"lavayeh": "LAVAYEH", "ealam": "EALAM_VAKALAHT",
                              "ezhharnameh": "EZHHARNAMEH", "check": "CHECK",
                              "tn": "TAJDID_NAZAR"}.get(flow, "LAVAYEH"),
                status="PROCESSING",
                tracking_code=bill_no or None,
                result_summary=f"کد قرارداد جدید {contract_number} ثبت و مراحل ادامه یافت",
            )
        except Exception as panel_err:
            logging.warning(f"[CONTRACT-FIX] خطا در آپدیت پنل: {panel_err}")

    except Exception as send_err:
        logging.error(f"[CONTRACT-FIX] خطا در ارسال نتیجه: {send_err}", exc_info=True)
        # فال‌بک: PDF + کد قرارداد برای کاربر ارسال شود تا چیزی گم نشود
        try:
            await bot.send_message(
                user_id,
                f"✅ کد قرارداد «{contract_number}» در سامانه ثبت شد.\n"
                f"🔢 کد رهگیری: `{bill_no}`\n"
                f"💰 هزینه سامانه: {court_total:,} ریال\n\n"
                f"⚠️ ارسال خودکار فاکتور با خطا مواجه شد — پشتیبانی پیگیری می‌کند.",
                parse_mode="Markdown")
            if pdf_path and os.path.exists(pdf_path):
                from bale_file_sender import send_document_direct
                await send_document_direct(user_id, pdf_path)
        except Exception:
            pass
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [CONTRACT-FIX] خطا در ارسال نتیجه به کاربر {user_id} — "
            f"کد: {bill_no} | قرارداد: {contract_number} | خطا: {str(send_err)[:200]}")
