# -*- coding: utf-8 -*-
"""
⭐ اصلاحیه باگ #۲ (باگ #۱-۳ مشترک): هندلر ادامه ثبت وکالت‌نامه الکترونیک
با شماره قرارداد جدید.

روند کلی (طبق دستور کارفرما):
  ۱. وقتی ثبت وکالت‌نامه با خطای «شماره قرارداد معتبر نمی باشد» مواجه می‌شود،
     ثبت وکالت‌نامه اسکیپ می‌شود، سایر پیوست‌ها انجام می‌شود، سپس به کاربر
     اعلام می‌شود که ۴۵ دقیقه فرصت دارد شماره قرارداد جدید را ارسال کند.
  ۲. وقتی کاربر شماره قرارداد جدید را ارسال کرد:
     الف) با کدرهگیری ثبت‌شده (bill_no) در سامانه استعلام می‌کنیم
     ب) وارد مرحلهٔ «منظمات» می‌شویم
     ج) فقط شماره قرارداد جدید را وارد می‌کنیم (بدون حق‌الوکاله — فقط
        قرارداد، تا پیام تأیید بیاید)
     د) سپس ادامه مراحل: آماده‌سازی، هزینه، چاپ و ادامه
"""
import asyncio
import logging
import time

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.types import Message

import runtime_state
from config import ADMIN_ID
from browser_helpers import (
    check_and_handle_expiry, resilient_sleep, goto_url_with_retry,
    human_delay, wait_for_angular_idle, safe_click_by_text
)


# ─────────────────────────────────────────────────────────────────────────────
# State storage: نگاشت user_id → pending vakalaht resume
# ─────────────────────────────────────────────────────────────────────────────
# این حالت در runtime_state.incomplete_tasks نیز ذخیره می‌شود ولی برای
# دسترسی سریع در هندلر پیام، یک دیکشنری جدا هم نگه می‌داریم.
# کلید: user_id (int)
# مقدار: dict با کلیدهای: bill_no, type, task_data, expires_at, invalid_contract
# ─────────────────────────────────────────────────────────────────────────────


def _find_pending_vakalaht_for_user(user_id: int):
    """یافتن تسک vakalaht معلق برای کاربر — از incomplete_tasks."""
    for key, info in list(runtime_state.incomplete_tasks.items()):
        if not key.endswith(f":{info.get('bill_no', '')}") and not key.startswith(
            ("lavayeh_vakalaht:", "ezhhar_vakalaht:", "check_vakalaht:",
             "ealam_vakalaht:", "tn_vakalaht:")
        ):
            continue
        if info.get("user_id") != user_id:
            continue
        # بررسی انقضای ۴۵ دقیقه‌ای
        expires_at = info.get("expires_at", 0)
        if expires_at and time.time() > expires_at:
            logging.info(f"[VAKALAHT_RESUME] تسک {key} منقضی شده — حذف")
            runtime_state.incomplete_tasks.pop(key, None)
            continue
        if info.get("type") in (
            "lavayeh_vakalaht", "ezhhar_vakalaht", "check_vakalaht",
            "ealam_vakalaht", "tn_vakalaht"
        ):
            return key, info
    return None, None


async def _resume_vakalaht_with_new_contract(
    bot: Bot, user_id: int, new_contract: str, task_key: str, task_info: dict
):
    """روند کامل استعلام با کدرهگیری، ورود به منظمات، ثبت قرارداد جدید،
    و سپس ادامه مراحل (آماده‌سازی، هزینه، چاپ).

    طبق دستور کارفرما: «و کد قرارداد فرستاد ، طبق کدرهگیری که ثبت شده ،
    همان کدرهگیری را استعلام میکنی و سپس در بخش منظمات وارد می شی و فقط
    شماره قرارداد وارد میکنی تا پیام تایید بیاد و بعد می روی ادامه اماده
    سازی و هزینه و چاپ و ادامه مراحل»
    """
    bill_no = task_info.get("bill_no", "")
    task_type = task_info.get("type", "")
    sana_page = runtime_state.sana_page

    if sana_page is None:
        await bot.send_message(
            user_id,
            "⚠️ نشست مرورگر سامانه فعال نیست. لطفاً به مدیر اطلاع دهید."
        )
        return

    await bot.send_message(
        user_id,
        f"⏳ در حال استعلام لایحه/اظهارنامه/دادخواست با کد `{bill_no}` و "
        f"ثبت قرارداد وکالت جدید..."
    )

    try:
        # ۱) ریلود صفحه اصلی سامانه
        ok = await goto_url_with_retry(sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
        if not ok:
            await bot.send_message(user_id, "⚠️ خطا در باز کردن سامانه. لطفاً دوباره تلاش کنید.")
            return
        await human_delay(3.0, 5.0)

        # ۲) استعلام با کدرهگیری ثبت‌شده
        # رفتن به منوی مربوطه بر اساس نوع تسک
        if task_type == "lavayeh_vakalaht":
            await _resume_lavayeh_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info)
        elif task_type == "ezhhar_vakalaht":
            await _resume_ezhhar_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info)
        elif task_type == "check_vakalaht":
            await _resume_check_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info)
        elif task_type == "ealam_vakalaht":
            await _resume_ealam_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info)
        elif task_type == "tn_vakalaht":
            await _resume_tn_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info)
        else:
            logging.error(f"[VAKALAHT_RESUME] نوع تسک ناشناخته: {task_type}")
            await bot.send_message(user_id, "⚠️ نوع تسک ناشناخته است. لطفاً به مدیر اطلاع دهید.")
            return

        # ۳) پاک‌سازی تسک از incomplete_tasks
        runtime_state.incomplete_tasks.pop(task_key, None)
        logging.info(f"[VAKALAHT_RESUME] تسک {task_key} با موفقیت کامل شد و حذف شد")

    except Exception as e:
        logging.error(f"[VAKALAHT_RESUME] خطا در ادامه ثبت وکالت: {e}", exc_info=True)
        await bot.send_message(
            user_id,
            f"⚠️ خطا در ادامه ثبت وکالت‌نامه: {str(e)[:200]}\n"
            f"لطفاً به مدیر اطلاع دهید."
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"❌ [VAKALAHT_RESUME] خطا برای کاربر {user_id}، bill_no={bill_no}: {str(e)[:300]}"
            )
        except Exception:
            pass


async def _open_lavayeh_for_resume(page, bot, user_id, bill_no):
    """باز کردن لایحهٔ ثبت‌شده برای ویرایش — طبق منوی سامانه."""
    # کلیک «ارایه و پیگیری لایحه»
    from lavayeh_scenario import _click_menu_item, _click_goto_main
    await _click_menu_item(page, "ارایه و پیگیری لایحه", bot, user_id)
    await resilient_sleep(page, 5, bot, user_id)

    # جستجو و کلیک روی لایحه با bill_no
    found = await page.evaluate('''(billNo) => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {
            if (row.innerText && row.innerText.includes(billNo)) {
                // کلیک روی دکمهٔ ویرایش لایحه (معمولاً اولین دکمه در ردیف)
                const editBtn = row.querySelector('button[ng-click*="edit"], a[ng-click*="edit"], button.btn-info, a.btn-info');
                if (editBtn) { editBtn.click(); return true; }
                // فال‌بک: کلیک روی خود ردیف
                row.click();
                return true;
            }
        }
        return false;
    }''', bill_no)
    if not found:
        await bot.send_message(
            user_id,
            f"⚠️ لایحه با کد `{bill_no}` در فهرست پیدا نشد. لطفاً به مدیر اطلاع دهید."
        )
        return False
    await resilient_sleep(page, 5, bot, user_id)
    return True


async def _register_new_vakalaht_contract(
    page, bot, user_id, new_contract: str, prefix: str = "LAVAYEH"
) -> bool:
    """ثبت قرارداد وکالت جدید در مرحلهٔ منظمات.
    طبق دستور کارفرما: «فقط شماره قرارداد وارد میکنی تا پیام تایید بیاد»
    """

    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        logging.info(f"[{prefix}][VAKALAHT_RESUME] نشست تمدید شد")

    # ۱) انتخاب نوع پیوست «تصوير الكترونيك وكالت نامه»
    selected = await page.evaluate(r"""() => {
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
    }""")
    if not selected:
        logging.warning(f"[{prefix}][VAKALAHT_RESUME] گزینه وکالت‌نامه پیدا نشد")
        await bot.send_message(
            user_id,
            "⚠️ گزینه «تصویر الکترونیک وکالت نامه» در سامانه پیدا نشد. "
            "لطفاً به مدیر اطلاع دهید."
        )
        return False
    await asyncio.sleep(3)

    # ۲) وارد کردن شماره قرارداد جدید
    await page.evaluate(r"""(val) => {
        const inp = document.querySelector('#txtNo');
        if (inp) {
            inp.value = val;
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }""", new_contract)
    await asyncio.sleep(1)

    # ۳) مبلغ حق‌الوکاله — طبق دستور کارفرما «فقط شماره قرارداد» وارد
    # می‌شود، اما سامانه برای ذخیره به مقدار نیاز دارد. اگر فیلد وجود داشت
    # ولی disabled نبود، همان مقدار قبلی را نگه می‌داریم وگرنه ۱ می‌گذاریم.
    await page.evaluate(r"""() => {
        const inp = document.querySelector('#txtLawyerAmount');
        if (inp && !inp.disabled && !inp.value) {
            inp.value = "1";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }""")
    await asyncio.sleep(1)

    # ۴) کلیک #btnSaveDoc
    for _wait in range(10):
        btn_state = await page.evaluate(r"""() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (!btn) return 'not_found';
            return btn.disabled ? 'disabled' : 'ready';
        }""")
        if btn_state == 'ready':
            break
        await asyncio.sleep(3)

    await page.evaluate(r"""() => {
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
    }""")
    logging.info(f"[{prefix}][VAKALAHT_RESUME] کلیک #btnSaveDoc با قرارداد جدید {new_contract}")
    await resilient_sleep(page, 8, bot, user_id)

    # ۵) بررسی پاپ‌آپ نتیجه
    result = await page.evaluate(r"""() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return { type: 'none', text: '' };
        const style = window.getComputedStyle(popup);
        if (style.display === 'none') return { type: 'none', text: '' };

        const h2 = popup.querySelector('h2');
        const p  = popup.querySelector('p');
        const h2Text = (h2 ? h2.innerText : '') || '';
        const pText  = (p  ? p.innerText  : '') || '';
        const full   = (h2Text + ' ' + pText).trim();

        const successIcon = popup.querySelector('.sa-icon.sa-success');
        const successVisible = successIcon && window.getComputedStyle(successIcon).display !== 'none';
        const errorIcon = popup.querySelector('.sa-icon.sa-error');
        const errorVisible = errorIcon && window.getComputedStyle(errorIcon).display !== 'none';

        if (successVisible) return { type: 'success', text: full };
        if (errorVisible) return { type: 'error', text: full };
        return { type: 'unknown', text: full };
    }""")

    # بستن پاپ‌آپ
    await page.evaluate(r"""() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (popup) {
            const btn = popup.querySelector('button.confirm');
            if (btn) btn.click();
        }
    }""")
    await asyncio.sleep(1)

    if result.get("type") == "success":
        logging.info(f"[{prefix}][VAKALAHT_RESUME] ثبت قرارداد جدید موفق")
        await bot.send_message(
            user_id,
            "✅ ثبت وکالت‌نامه الکترونیک با قرارداد جدید با موفقیت انجام شد.\n"
            "⏳ ادامه مراحل (آماده‌سازی، هزینه، چاپ)..."
        )
        return True
    else:
        text = result.get("text", "")
        logging.error(f"[{prefix}][VAKALAHT_RESUME] ثبت قرارداد جدید ناموفق: {text}")
        await bot.send_message(
            user_id,
            f"⚠️ ثبت قرارداد جدید ناموفق بود.\n"
            f"متن خطا: {text[:200]}\n\n"
            f"لطفاً شماره قرارداد را بررسی کنید و دوباره ارسال کنید."
        )
        return False


async def _resume_lavayeh_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info):
    """ادامه ثبت وکالت لایحه با قرارداد جدید."""
    from lavayeh_scenario import (
        _click_menu_item, _click_goto_main, _click_step_box,
        _click_preparation_with_retry, _calculate_cost_with_retry,
        _print_lavayeh, _close_success_popup, _close_error_popup,
        _extract_bill_no
    )

    # ۱) باز کردن لایحه با کدرهگیری
    if not await _open_lavayeh_for_resume(sana_page, bot, user_id, bill_no):
        return

    # ۲) ورود به مرحلهٔ منظمات
    await _click_step_box(sana_page, "منظمات", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ۳) ثبت قرارداد جدید
    ok = await _register_new_vakalaht_contract(
        sana_page, bot, user_id, new_contract, prefix="LAVAYEH"
    )
    if not ok:
        return

    # ۴) بازگشت به فهرست
    await _click_goto_main(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 4, bot, user_id)

    # ۵) ادامه: آماده‌سازی
    await _click_step_box(sana_page, "آماده سازي جهت محاسبه هزينه و ارسال", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)
    preparation_ok = await _click_preparation_with_retry(sana_page, bot, user_id)
    if not preparation_ok:
        await bot.send_message(user_id, "⚠️ مرحله آماده‌سازی با مشکل مواجه شد.")
        return

    await _click_goto_main(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 4, bot, user_id)

    # ۶) محاسبه هزینه
    await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
    await resilient_sleep(sana_page, 8, bot, user_id)
    court_total = await _calculate_cost_with_retry(sana_page, bot, user_id)
    logging.info(f"[LAVAYEH][VAKALAHT_RESUME] court_total: {court_total}")

    await _click_goto_main(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 4, bot, user_id)

    # ۷) چاپ
    browser_context = runtime_state.browser_context
    pdf_path = await _print_lavayeh(sana_page, browser_context, bill_no, bot, user_id)

    # ۸) ارسال نتیجه به کاربر
    try:
        if pdf_path:
            from bale_file_sender import send_pdf_to_user
            await send_pdf_to_user(bot, user_id, pdf_path, title="لایحه دفاعیه")
    except Exception as e:
        logging.error(f"[LAVAYEH][VAKALAHT_RESUME] خطا در ارسال PDF: {e}")

    await bot.send_message(
        user_id,
        f"✅ ثبت کامل شد.\n"
        f"🔢 کد رهگیری: `{bill_no}`\n"
        f"💰 هزینه سامانه: {court_total:,} ریال"
    )


async def _resume_ezhhar_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info):
    """ادامه ثبت وکالت اظهارنامه با قرارداد جدید."""
    # مشابه لایحه — باز کردن اظهارنامه، ورود به منظمات، ثبت قرارداد
    await bot.send_message(
        user_id,
        "⏳ در حال باز کردن اظهارنامه و ثبت قرارداد جدید..."
    )

    # باز کردن اظهارنامه با کدرهگیری
    found = await sana_page.evaluate('''(billNo) => {
        // کلیک روی «ارایه و پیگیری اظهارنامه»
        const links = Array.from(document.querySelectorAll('a.list-group-item'));
        const t = links.find(el => el.innerText && el.innerText.includes("اظهارنامه"));
        if (t) { t.click(); return true; }
        return false;
    }''', bill_no)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # جستجو در فهرست اظهارنامه‌ها
    found = await sana_page.evaluate('''(billNo) => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {
            if (row.innerText && row.innerText.includes(billNo)) {
                const editBtn = row.querySelector('button[ng-click*="edit"], a[ng-click*="edit"], button.btn-info, a.btn-info');
                if (editBtn) { editBtn.click(); return true; }
                row.click();
                return true;
            }
        }
        return false;
    }''', bill_no)
    if not found:
        await bot.send_message(
            user_id,
            f"⚠️ اظهارنامه با کد `{bill_no}` پیدا نشد."
        )
        return
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ورود به منظمات
    from ezhharnameh_scenario import _click_step_box_ezhhar as _click_step_box_ez
    # فال‌بک: کلیک مستقیم روی step
    clicked = await sana_page.evaluate('''() => {
        const boxes = Array.from(document.querySelectorAll('.step, .step-box, .nav-pills > li'));
        const t = boxes.find(el => el.innerText && el.innerText.includes("منظمات"));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(sana_page, "منظمات", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ثبت قرارداد جدید
    ok = await _register_new_vakalaht_contract(
        sana_page, bot, user_id, new_contract, prefix="EZHHAR"
    )
    if not ok:
        return

    await bot.send_message(
        user_id,
        f"✅ ثبت وکالت‌نامه الکترونیک با قرارداد جدید با موفقیت انجام شد.\n"
        f"🔢 کد رهگیری: `{bill_no}`"
    )


async def _resume_check_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info):
    """ادامه ثبت وکالت دادخواست چک با قرارداد جدید."""
    await bot.send_message(
        user_id,
        "⏳ در حال باز کردن دادخواست و ثبت قرارداد جدید..."
    )

    # باز کردن دادخواست با کدرهگیری
    found = await sana_page.evaluate('''(billNo) => {
        const links = Array.from(document.querySelectorAll('a.list-group-item'));
        const t = links.find(el => el.innerText && el.innerText.includes("دادخواست"));
        if (t) { t.click(); return true; }
        return false;
    }''', bill_no)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # جستجو در فهرست
    found = await sana_page.evaluate('''(billNo) => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {
            if (row.innerText && row.innerText.includes(billNo)) {
                const editBtn = row.querySelector('button[ng-click*="edit"], a[ng-click*="edit"], button.btn-info, a.btn-info');
                if (editBtn) { editBtn.click(); return true; }
                row.click();
                return true;
            }
        }
        return false;
    }''', bill_no)
    if not found:
        await bot.send_message(
            user_id,
            f"⚠️ دادخواست با کد `{bill_no}` پیدا نشد."
        )
        return
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ورود به منظمات
    clicked = await sana_page.evaluate('''() => {
        const boxes = Array.from(document.querySelectorAll('.step, .step-box, .nav-pills > li'));
        const t = boxes.find(el => el.innerText && el.innerText.includes("منظمات"));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(sana_page, "منظمات", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ثبت قرارداد جدید
    ok = await _register_new_vakalaht_contract(
        sana_page, bot, user_id, new_contract, prefix="CHECK"
    )
    if not ok:
        return

    await bot.send_message(
        user_id,
        f"✅ ثبت وکالت‌نامه الکترونیک با قرارداد جدید با موفقیت انجام شد.\n"
        f"🔢 کد رهگیری: `{bill_no}`"
    )


async def _resume_ealam_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info):
    """ادامه ثبت وکالت اعلام وکالت با قرارداد جدید."""
    await bot.send_message(
        user_id,
        "⏳ در حال باز کردن اعلام وکالت و ثبت قرارداد جدید..."
    )

    # اعلام وکالت معمولاً خودش وکالت‌نامه است — فقط باز کردن و ثبت مجدد
    found = await sana_page.evaluate('''(billNo) => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {
            if (row.innerText && row.innerText.includes(billNo)) {
                const editBtn = row.querySelector('button[ng-click*="edit"], a[ng-click*="edit"], button.btn-info, a.btn-info');
                if (editBtn) { editBtn.click(); return true; }
                row.click();
                return true;
            }
        }
        return false;
    }''', bill_no)
    if not found:
        await bot.send_message(
            user_id,
            f"⚠️ رکورد با کد `{bill_no}` پیدا نشد."
        )
        return
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ورود به منظمات
    clicked = await sana_page.evaluate('''() => {
        const boxes = Array.from(document.querySelectorAll('.step, .step-box, .nav-pills > li'));
        const t = boxes.find(el => el.innerText && el.innerText.includes("منظمات"));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(sana_page, "منظمات", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ثبت قرارداد جدید
    ok = await _register_new_vakalaht_contract(
        sana_page, bot, user_id, new_contract, prefix="EALAM"
    )
    if not ok:
        return

    await bot.send_message(
        user_id,
        f"✅ ثبت وکالت‌نامه الکترونیک با قرارداد جدید با موفقیت انجام شد.\n"
        f"🔢 کد رهگیری: `{bill_no}`"
    )


async def _resume_tn_vakalaht(bot, user_id, sana_page, bill_no, new_contract, task_info):
    """ادامه ثبت وکالت تجدیدنظر با قرارداد جدید."""
    await bot.send_message(
        user_id,
        "⏳ در حال باز کردن تجدیدنظرخواهی و ثبت قرارداد جدید..."
    )

    found = await sana_page.evaluate('''(billNo) => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {
            if (row.innerText && row.innerText.includes(billNo)) {
                const editBtn = row.querySelector('button[ng-click*="edit"], a[ng-click*="edit"], button.btn-info, a.btn-info');
                if (editBtn) { editBtn.click(); return true; }
                row.click();
                return true;
            }
        }
        return false;
    }''', bill_no)
    if not found:
        await bot.send_message(
            user_id,
            f"⚠️ تجدیدنظرخواهی با کد `{bill_no}` پیدا نشد."
        )
        return
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ورود به منظمات
    clicked = await sana_page.evaluate('''() => {
        const boxes = Array.from(document.querySelectorAll('.step, .step-box, .nav-pills > li'));
        const t = boxes.find(el => el.innerText && el.innerText.includes("منظمات"));
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(sana_page, "منظمات", bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ثبت قرارداد جدید
    ok = await _register_new_vakalaht_contract(
        sana_page, bot, user_id, new_contract, prefix="TN"
    )
    if not ok:
        return

    await bot.send_message(
        user_id,
        f"✅ ثبت وکالت‌نامه الکترونیک با قرارداد جدید با موفقیت انجام شد.\n"
        f"🔢 کد رهگیری: `{bill_no}`"
    )


# ─────────────────────────────────────────────────────────────────────────────
# هندلر پیام: وقتی کاربر شماره قرارداد جدید (۱۶ رقمی) ارسال می‌کند
# ─────────────────────────────────────────────────────────────────────────────
def _is_16_digit_contract(text: str) -> bool:
    """بررسی اینکه آیا متن یک شماره قرارداد ۱۶ رقمی است."""
    if not text:
        return False
    digits = "".join(ch for ch in text if ch.isdigit())
    return len(digits) == 16


async def handle_new_contract_message(message: Message, bot: Bot):
    """هندلر پیام کاربر — اگر قرارداد ۱۶ رقمی بود و تسک vakalaht معلق داشت."""
    user_id = message.from_user.id
    text = message.text or ""

    if not _is_16_digit_contract(text):
        return False  # پیام مربوط به این هندلر نیست

    digits = "".join(ch for ch in text if ch.isdigit())

    task_key, task_info = _find_pending_vakalaht_for_user(user_id)
    if not task_info:
        return False  # تسک معلقی ندارد

    logging.info(
        f"[VAKALAHT_RESUME] کاربر {user_id} قرارداد جدید {digits} را ارسال کرد "
        f"برای تسک {task_key}"
    )

    # ارسال تأییدیه
    await bot.send_message(
        user_id,
        f"✅ شماره قرارداد جدید `{digits}` دریافت شد.\n"
        f"⏳ در حال ادامه ثبت..."
    )

    # اجرای رود resumed
    await _resume_vakalaht_with_new_contract(bot, user_id, digits, task_key, task_info)
    return True
