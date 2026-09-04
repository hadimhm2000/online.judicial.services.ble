"""
سناریوهای اصلی اتوماسیون: ورود دستی به سامانه، پردازش هر تسک و worker پس‌زمینه.
"""
import asyncio
import logging
import os

from aiogram import Bot
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import runtime_state
from bale_file_sender import send_document_direct
from config import ADMIN_ID, DEBUG_LOG_REQUESTS, FEES, get_fee
from sheets import log_event
from panel_sync import register_case_to_panel as _register_case_to_panel_sync
from panel_sync import register_failed_inquiry_to_panel


async def register_inquiry_to_panel(
    user_id, full_name, tracking_code, doc_category,
    doc_subcategory=None, fee=0, result_summary=None):
    """
    ⭐ v1.3 — ثبت استعلام در پنل ادمین با feeStatus=PAID.

    ریشه‌ی تغییر: این تابع «فقط بعد از پرداخت موفق کیف پول بله» صدا زده می‌شود
    (داخل process_task که پس از successful_payment اجرا می‌شود)؛ ولی نسخهٔ
    قبلی استعلام را با fee_status=UNPAID ثبت می‌کرد. نتیجه: استعلام‌های
    پرداخت‌شده هرگز وارد «درآمد» و «سود» پنل نمی‌شدند و در کارت «پرداخت
    نشده» انباشته می‌شدند. طبق قاعدهٔ سود («هر مبلغی که بابت استعلام‌ها
    پرداخت شده مستقیماً وارد سود شود»)، ثبت با PAID انجام می‌شود.
    """
    return await _register_case_to_panel_sync(
        bale_user_id=str(user_id),
        full_name=full_name,
        service_type="INQUIRY",
        status="COMPLETED",
        tracking_code=tracking_code,
        document_category=doc_category,
        sub_category=doc_subcategory,
        fee=fee,
        fee_status="PAID",
        result_summary=result_summary,
    )
from keyboards import admin_login_kb, confirm_single_kb, confirm_cart_kb
from browser_helpers import (
    human_delay, force_click_by_text, soft_click_if_exists, human_type,
    handle_session_expired, wait_for_angular_idle, check_and_handle_expiry,
    check_and_handle_load_error, resilient_sleep, goto_url_with_retry,
    safe_click_by_text, safe_type, NavigationResetError, NationalIdError,
    wait_for_horizontal_loading_bar, is_login_redirect_url,
    detect_national_id_error, check_national_id_error_or_continue,
    detect_concurrent_login_popup,
    NATIONAL_ID_ERROR_MSG)
from sana_profile_report import extract_sana_profile, build_sana_profile_pdf


# ══════════════════════════════════════════════════════════════════════════════
# PRE_CHECK — استعلام تعداد پیوست در تب جدید (بدون دستکاری sana_page)
# ══════════════════════════════════════════════════════════════════════════════

async def _process_pre_check_on_new_page(data: dict, bot: Bot, _retry: bool = False):
    """
    استعلام تعداد پیوست‌ها در یک تب جدید — بدون دستکاری sana_page.
    همان روند استعلام کد رهگیری را در تب جدید پیاده‌سازی می‌کند
    تا روند ثبت پرونده در sana_page مختل نشود.

    اگر نشست منقضی باشد، به مدیر اطلاع داده و منتظر لاگین مجدد او می‌ماند،
    سپس همین تسک را یک‌بار به‌صورت خودکار از نو تلاش می‌کند (_retry جلوی
    حلقه‌ی بی‌نهایت را می‌گیرد).
    """
    browser_context = runtime_state.browser_context
    user_id = data['user_id']
    tracking_code = data.get('tracking_code', '')
    category = data.get('doc_category', '')
    subcategory = data.get('doc_subcategory')
    doc_name = subcategory if subcategory else category

    page = None
    try:
        page = await browser_context.new_page()

        # ── ۱. رفتن به صفحه اصلی ─────────────────────────────────
        await page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # بررسی انقضا نشست (فرم قدیمی یا ریدایرکت جدید به iehraz2)
        is_login = await page.query_selector('#txtUsername')
        if is_login or is_login_redirect_url(page.url):
            if _retry:
                # قبلاً یک‌بار مدیر لاگین کرده و باز هم منقضی است؛ برای جلوگیری
                # از حلقه‌ی بی‌نهایت، دیگر تلاش خودکار نمی‌کنیم.
                await bot.send_message(user_id, "⚠️ نشست سامانه همچنان منقضی است. لطفاً کمی بعد دوباره تلاش کنید.")
                return

            logging.warning(f"[PRE_CHECK] نشست منقضی — اطلاع به مدیر و انتظار لاگین مجدد (کد: {tracking_code})")
            await handle_session_expired(bot, user_id, page=page)

            try:
                await page.close()
            except Exception:
                pass
            page = None

            # ── تلاش مجدد خودکار همین تسک، بعد از لاگین مدیر ─────────
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        # ── ۲. ناوبری به بخش مورد نظر ─────────────────────────────
        nav_map = {
            "لایحه": ["ارایه و پیگیری لایحه"],
            "اظهارنامه": ["ارایه و پیگیری اظهارنامه"],
            "شکواییه": ["ارایه و پیگیری شکواییه"],
            "دادخواست بدوی": ["ارایه و پیگیری دادخواست", "دادخواست بدوی"],
            "دعاوی دادگاههای صلح": ["دعاوی دادگاههای صلح", "دعاوی حقوقی"],
            "دعاوی اعتراضی": ["دعاوی اعتراضی", subcategory],
            "دعاوی طاری": ["ارایه و پیگیری دعاوی طاری", subcategory],
            "دیوان عدالت اداری": ["دیوان عدالت اداری", subcategory],
            "شورای حل اختلاف": ["شورای حل اختلاف (صلح و سازش)", subcategory],
        }
        steps = nav_map.get(category, [])
        if not steps:
            logging.error(f"[PRE_CHECK] دسته نامشخص: {category}")
            return

        for i, step in enumerate(steps):
            if not step:
                continue
            await force_click_by_text(page, step)
            await asyncio.sleep(2 if i < len(steps) - 1 else 5)

        # لایحه: انتخاب رادیو #rdbGetPetition (value=2) به‌جای "جستجوی لایحه"
        if category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        ):
            # ابتدا منتظر ظاهر شدن رادیوباتن می‌مانیم
            try:
                await page.wait_for_selector('#rdbGetPetition', state='visible', timeout=10000)
            except Exception:
                logging.error("[PRE_CHECK] رادیوباتن #rdbGetPetition یافت نشد")
                await bot.send_message(user_id, "⚠️ صفحه سامانه بارگذاری نشد.")
                return
            # کلیک با فعال‌سازی AngularJS digest
            await page.evaluate('''() => {
                const radio = document.querySelector('#rdbGetPetition');
                if (radio) {
                    radio.checked = true;
                    radio.click();
                    if (window.angular) {
                        try {
                            const scope = angular.element(radio).scope();
                            if (scope) scope.$apply();
                        } catch(e) {}
                    }
                }
            }''')
            await asyncio.sleep(4)

        # ── ۳. وارد کردن کد رهگیری ────────────────────────────────
        try:
            await page.wait_for_selector('#txtPetitionNo, #billNo', timeout=15000)
        except Exception:
            await bot.send_message(user_id, "⚠️ صفحه سامانه بارگذاری نشد.")
            return

        # لایحه: فیلد ورودی کدرهگیری #billNo
        # FIX: استفاده از page.evaluate به جای page.fill برای سازگاری کامل با AngularJS
        # و جلوگیری از خطای Frame.fill() missing 'value' در صورت وجود فریم/iframe
        if category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        ):
            fill_selector = '#billNo'
        else:
            fill_selector = '#txtPetitionNo, #billNo'

        fill_ok = await page.evaluate('''(args) => {
            const sel = args.sel;
            const val = args.val;
            const el = document.querySelector(sel);
            if (!el) return false;
            el.focus();
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            try {
                const scope = angular.element(el).scope();
                if (scope) {
                    scope.$apply(() => {
                        const key = el.getAttribute('ng-model');
                        if (key) {
                            const parts = key.split('.');
                            let obj = scope;
                            for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
                            obj[parts[parts.length - 1]] = val;
                        }
                    });
                }
            } catch(e) {}
            el.dispatchEvent(new Event('blur', { bubbles: true }));
            return true;
        }''', {"sel": fill_selector, "val": tracking_code})
        if not fill_ok:
            logging.warning(f"[PRE_CHECK] fill failed for selector '{fill_selector}'")
        await asyncio.sleep(1.5)

        # ── ۴. کلیک جستجو ────────────────────────────────────────
        # لایحه: دکمه #btnGetJSSBill  |  سایر: #btnGetJSSPetition
        if category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        ):
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnGetJSSBill');
                if (btn) { btn.click(); return; }
            }''')
        else:
            await page.evaluate('''() => {
                const exactBtn = document.querySelector('#btnGetJSSPetition');
                if (exactBtn) { exactBtn.click(); return; }
                const exactBtn2 = document.querySelector('#btnGetJSSBill');
                if (exactBtn2) { exactBtn2.click(); return; }
            }''')
        await asyncio.sleep(3)

        # منتظر لودینگ
        await _precheck_wait_loading(page)

        # ── ۵. بستن پاپ‌آپ خطا (اگر بود) ─────────────────────────────
        await _precheck_dismiss_error(page)

        # ── ۵-ب. بررسی پاپ‌آپ ورود همزمان (concurrent login) ─────────
        is_concurrent = await detect_concurrent_login_popup(page)
        if is_concurrent:
            if _retry:
                await bot.send_message(user_id, "⚠️ نشست سامانه همچنان منقضی است (ورود همزمان از دستگاه دیگر). لطفاً کمی بعد دوباره تلاش کنید.")
                return
            logging.warning(f"[PRE_CHECK] پاپ‌آپ ورود همزمان تشخیص داده شد — اطلاع به مدیر برای لاگین مجدد (کد: {tracking_code})")
            await handle_session_expired(bot, user_id, page=page)
            try:
                await page.close()
            except Exception:
                pass
            page = None
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        # ── بررسی خطای «کد رهگیری معتبر نیست» ────────────────────────
        invalid_code_popup = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                const t = popup.innerText || "";
                if (t.includes("معتبر نیست")) return true;
            }
            return false;
        }''')
        if invalid_code_popup:
            try:
                await page.locator('.sweet-alert.showSweetAlert button.confirm').click(timeout=5000)
            except Exception:
                pass
            await bot.send_message(user_id, "❌ کدرهگیری یا نوع خدمت را اشتباه وارد نموده‌اید.")
            return

        # ── ۶. بررسی عدم یافتن پرونده ─────────────────────────────
        not_found = await page.evaluate('''() => {
            const alert = document.querySelector('.alert-danger');
            if (alert && alert.offsetParent !== null) return true;
            const text = document.body ? document.body.innerText : '';
            return text.includes('یافت نشد');
        }''')
        if not_found:
            await bot.send_message(user_id, f"❌ پرونده‌ای با کد `{tracking_code}` یافت نگردید.")
            return

        # بررسی مجدد انقضای نشست (ممکن است حین جستجو رخ داده باشد)
        is_login = await page.query_selector('#txtUsername')
        if is_login or is_login_redirect_url(page.url):
            if _retry:
                await bot.send_message(user_id, "⚠️ نشست سامانه همچنان منقضی است. لطفاً کمی بعد دوباره تلاش کنید.")
                return
            logging.warning(f"[PRE_CHECK] نشست منقضی حین جستجو — اطلاع به مدیر (کد: {tracking_code})")
            await handle_session_expired(bot, user_id, page=page)
            try:
                await page.close()
            except Exception:
                pass
            page = None
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        # ── ۷. بررسی مجدد پاپ‌آپ ورود همزمان قبل از منضمات ─
        is_concurrent_2 = await detect_concurrent_login_popup(page)
        if is_concurrent_2:
            if _retry:
                await bot.send_message(user_id, "⚠️ نشست سامانه پیش از شمارش پیوست منقضی شد. لطفاً کمی بعد دوباره تلاش کنید.")
                return
            logging.warning(f"[PRE_CHECK] پاپ‌آپ ورود همزمان قبل از منضمات — اطلاع به مدیر (کد: {tracking_code})")
            await handle_session_expired(bot, user_id, page=page)
            try:
                await page.close()
            except Exception:
                pass
            page = None
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        # ── ۸. کلیک «منضمات» و شمارش ────────────────────────────
        # بررسی وجود تب «منضمات» قبل از کلیک
        mozamatat_exists = await page.evaluate('''() => {
            const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div', 'td'];
            for (let tag of tags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el => el.innerText && el.innerText.trim().includes("منضمات"));
                if (target) {
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) return true;
                }
            }
            return false;
        }''')
        if not mozamatat_exists:
            total_attachments_count = 0
            logging.info(f"[PRE_CHECK] تب منضمات یافت نشد — تعداد پیوست: 0 (کد: {tracking_code})")
        else:
            await force_click_by_text(page, "منضمات")
            await asyncio.sleep(5)

            total_attachments_count = await page.evaluate('''() => {
                const tbody = document.querySelector('tbody');
                if (!tbody) return 0;
                const trs = Array.from(tbody.querySelectorAll('tr'));
                const isIgnored = (title) => {
                    const t = title.replace(/\\u200c/g, ' ');
                    return t.includes("قرارداد الکترونیک") &&
                           (t.includes("وکالت نامه") || t.includes("وکالتنامه"));
                };
                const rows_data = trs.map((tr, index) => {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length >= 6) {
                        const title = tds[2].innerText.trim();
                        const countText = tds[5].innerText.trim();
                        const count = parseInt(countText) || 0;
                        return { index, title, count };
                    }
                    return null;
                }).filter(r => r !== null && !isIgnored(r.title));
                const has_sig = rows_data.length > 0 &&
                    (rows_data[0].title.includes("امضا") || rows_data[0].title.includes("امضاء"));
                const start = has_sig ? 1 : 0;
                let sum = 0;
                for (let i = start; i < rows_data.length; i++) { sum += rows_data[i].count; }
                return sum;
            }''')

        # ── ۸. ارسال نتیجه به کاربر ─────────────────────────────────
        calculated_fee = FEES["کد رهگیری با منضمات"] + total_attachments_count * 5000

        user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
        user_data = await user_state.get_data()
        flow_type = user_data.get('flow_type', 'single')

        await user_state.update_data(
            payment_fee=calculated_fee,
            need_attachments=True,
            total_attachments=total_attachments_count
        )

        from states import Form
        await user_state.set_state(Form.confirm_opt)

        kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
        action_text = (
            "تایید نهایی و دریافت فاکتور پرداخت"
            if flow_type == "single"
            else "تایید و افزودن این مورد به سبد خرید"
        )

        confirm_msg = (
            f"📋 *اطلاعات استعلام با منضمات:*\n\n"
            f"کد پیگیری: `{tracking_code}`\n"
            f"سند: *{doc_name}*\n"
            f"📎 تعداد پیوست: *{total_attachments_count} برگ*\n"
            f"💰 فاکتور: ۵۰,۰۰۰ + ({total_attachments_count} × ۵,۰۰۰) = *{calculated_fee:,} تومان*\n\n"
            f"آیا {action_text} فرمایید؟"
        )
        await bot.send_message(user_id, confirm_msg, reply_markup=kb)
        await bot.send_message(ADMIN_ID, f"✅ [PRE_CHECK] تعداد پیوست {tracking_code}: {total_attachments_count} (تب جدید)")

    except Exception as e:
        logging.error(f"[PRE_CHECK] خطا در تب جدید: {e}")

        # FIX: منطق تلاش مجدد — ریلود صفحه و تلاش مجدد یک‌بار
        if not _retry:
            logging.warning(f"[PRE_CHECK] تلاش مجدد با ریلود صفحه (کد: {tracking_code})")
            try:
                if page:
                    await page.reload(timeout=30000, wait_until="domcontentloaded")
                    await asyncio.sleep(5)
            except Exception:
                pass
            # بستن تب فعلی و ایجاد تب جدید
            try:
                if page:
                    await page.close()
            except Exception:
                pass
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_process_pre_check_on_new_page (retry)", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
            await bot.send_message(ADMIN_ID, f"⚠️ [PRE_CHECK] خطا، تلاش مجدد با ریلود: {e}")
            # تلاش مجدد خودکار
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        # تلاش دوم هم ناموفق بود — اطلاع به مدیر برای لاگین مجدد
        logging.error(f"[PRE_CHECK] تلاش مجدد پس از ریلود هم ناموفق (کد: {tracking_code})")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_pre_check_on_new_page (final)", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await bot.send_message(ADMIN_ID, f"❌ [PRE_CHECK] خطا پس از ریلود: {e} — نیاز به لاگین مجدد")

        # بررسی آیا مشکل انقضای نشست است
        is_login_page = False
        if page:
            try:
                is_login_page = await page.query_selector('#txtUsername') is not None or is_login_redirect_url(page.url)
            except Exception:
                pass

        if is_login_page:
            await handle_session_expired(bot, user_id, page=page)
            try:
                await page.close()
            except Exception:
                pass
            # تلاش سوم پس از لاگین مجدد مدیر
            return await _process_pre_check_on_new_page(data, bot, _retry=True)

        await bot.send_message(
            user_id,
            "⚠️ خطا در استعلام پیوست‌ها. لطفاً دوباره تلاش کنید."
        )
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def _precheck_wait_loading(page, timeout=60):
    """منتظر ناپدید شدن لودینگ در صفحه PRE_CHECK."""
    try:
        await page.evaluate('''(timeout) => {
            return new Promise((resolve) => {
                let checks = 0;
                const maxChecks = timeout * 2;
                const interval = setInterval(() => {
                    checks++;
                    if (checks >= maxChecks) { clearInterval(interval); resolve(false); return; }
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading, .progress-bar, .nprogress, .bar-loading, [ng-show*="loading"]');
                    let anyVisible = false;
                    for (const loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== 'none') { anyVisible = true; break; }
                    }
                    if (!anyVisible) { clearInterval(interval); resolve(false); }
                }, 500);
            });
        }''', timeout)
    except Exception:
        pass
    await asyncio.sleep(1)


async def _precheck_dismiss_error(page):
    """بستن پاپ‌آپ خطای 'لطفا اطلاعات خواسته شده را به درستی وارد نمایید' و تلاش مجدد."""
    has_error = await page.evaluate('''() => {
        const text = document.body ? document.body.innerText : '';
        return text.includes('لطفا اطلاعات خواسته شده را به درستی وارد نمایید');
    }''')
    if has_error:
        try:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const closeBtn = btns.find(b => (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm"));
                if (closeBtn) closeBtn.click();
            }''')
            await asyncio.sleep(2)
            await page.evaluate('''() => {
                const exactBtn = document.querySelector('#btnGetJSSPetition');
                if (exactBtn) { exactBtn.click(); return; }
                const exactBtn2 = document.querySelector('#btnGetJSSBill');
                if (exactBtn2) { exactBtn2.click(); return; }
            }''')
            await asyncio.sleep(3)
            await _precheck_wait_loading(page)
        except Exception:
            pass


async def _wait_for_mobile_search_table(page, timeout_sec: int = 30):
    """
    منتظر آماده شدن نتیجه‌ی جستجوی شماره همراه می‌ماند.
    خروجی: (ready: bool, has_results: bool)
    - ready=True, has_results=True   → جدول با حداقل یک ردیف نتیجه آماده است.
    - ready=True, has_results=False  → سامانه جستجو را کامل کرده ولی «تعداد کل اشخاص یافت شده» صفر بوده (نتیجه‌ای نیست).
    - ready=False                    → هیچ‌کدام از حالت‌های بالا در بازه‌ی زمانی داده‌شده رخ نداد (تاخیر سامانه).
    """
    for _ in range(timeout_sec):
        result = await page.evaluate('''() => {
            const tbody = document.querySelector('tbody');
            const hasRows = tbody !== null && tbody.querySelectorAll('tr').length > 0;
            if (hasRows) return {ready: true, hasResults: true};

            const bodyText = document.body.innerText || "";
            const match = bodyText.match(/تعداد کل اشخاص یافت شده\\s*:?\\s*([0-9۰-۹]+)/);
            if (match) {
                const faDigits = "۰۱۲۳۴۵۶۷۸۹";
                const toEng = (s) => s.split('').map(ch => {
                    const idx = faDigits.indexOf(ch);
                    return idx >= 0 ? String(idx) : ch;
                }).join('');
                const count = parseInt(toEng(match[1]), 10);
                return {ready: true, hasResults: count > 0};
            }
            return {ready: false, hasResults: false};
        }''')
        if result['ready']:
            return True, result['hasResults']
        await asyncio.sleep(1)
    return False, False


async def wait_for_manual_login(bot: Bot):
    sana_page = runtime_state.sana_page
    try:
        await sana_page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=60000)
        runtime_state.login_event.clear()
        await bot.send_message(
            ADMIN_ID,
            "⚠️ *نیاز به لاگین دستی:*\nپنجره مرورگر باز شده است. "
            "لطفاً وارد سامانه شوید و دکمه زیر را کلیک نمایید 👇",
            reply_markup=admin_login_kb
        )
        await runtime_state.login_event.wait()
        return True
    except Exception as e:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST_ATTACHMENTS — تست بخش منضمات بدون ایجاد کدرهگیری جدید
# ══════════════════════════════════════════════════════════════════════════════

async def _process_test_attachments(data: dict, bot: Bot):
    """
    تست بخش منضمات: ناوبری به پرونده، ورود به تب منضمات و آپلود مدارک.
    از همان حلقه resilient_upload_attachment_groups استفاده می‌کند.
    """
    sana_page = runtime_state.sana_page
    user_id = data['user_id']
    tracking_code = data.get('tracking_code')
    category = data.get('doc_category')
    test_attachments = data.get('test_attachments', [])

    downloaded_paths = []

    try:
        success = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not success:
            await bot.send_message(user_id, "❌ خطا در اتصال به سامانه.")
            return

        await human_delay(4.0, 6.0)

        # ── ناوبری به بخش مورد نظر ─────────────────────────────────────
        if category == "لایحه":
            await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
        elif category == "اظهارنامه":
            await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        # ── تنظیم رادیو و ورود کدرهگیری ──────────────────────────────
        if category == "لایحه":
            radio_clicked = await sana_page.evaluate('''() => {
                const radio = document.querySelector('#rdbGetPetition');
                if (radio) { radio.click(); return true; }
                return false;
            }''')
            if not radio_clicked:
                await safe_click_by_text(sana_page, "جستجوی لایحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

        try:
            await sana_page.wait_for_selector('#txtPetitionNo, #billNo', timeout=15000)
        except Exception:
            await bot.send_message(user_id, "❌ صفحه کارتابل لود نشد.")
            return

        if category == "لایحه":
            await safe_type(sana_page, '#billNo', tracking_code, bot, user_id)
        else:
            selector = '#txtPetitionNo, #billNo, input[name="txtPetitionNo"], input[name="billNo"]'
            await safe_type(sana_page, selector, tracking_code, bot, user_id)
        await resilient_sleep(sana_page, 2, bot, user_id)

        # ── کلیک دکمه جستجو ───────────────────────────────────────────
        if category == "لایحه":
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnGetJSSBill');
                if (btn) { btn.click(); return; }
            }''')
        else:
            await sana_page.evaluate('''() => {
                const exactBtn = document.querySelector('#btnGetJSSPetition');
                if (exactBtn) { exactBtn.click(); return; }
                const btns = Array.from(document.querySelectorAll('button'));
                const searchBtn = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
                if (searchBtn) searchBtn.click();
            }''')

        await asyncio.sleep(3)
        await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

        # ── بستن پاپ‌آپ‌ها ────────────────────────────────────────────
        await sana_page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const closeBtn = btns.find(b =>
                (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm")
            );
            if(closeBtn) closeBtn.click();
        }''')
        await resilient_sleep(sana_page, 2, bot, user_id)

        if (
            await sana_page.locator(".alert-danger").is_visible()
            or await sana_page.locator('text="اطلاعاتی یافت نشد"').is_visible()
        ):
            await bot.send_message(user_id, f"❌ پرونده‌ای با کد `{tracking_code}` یافت نگردید.")
            return

        # ── ورود به تب منضمات ────────────────────────────────────────
        mozamatat_exists = await sana_page.evaluate('''() => {
            const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div', 'td'];
            for (let tag of tags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el => el.innerText && el.innerText.trim().includes("منضمات"));
                if (target) {
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) return true;
                }
            }
            return false;
        }''')

        if not mozamatat_exists:
            await bot.send_message(user_id, "📄 این درخواست فاقد بخش منضمات است.")
            return

        await safe_click_by_text(sana_page, "منضمات", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        # ── دانلود تصاویر از بله و آماده‌سازی گروه‌ها ──────────────
        if not test_attachments:
            await bot.send_message(user_id, "⚠️ هیچ مدرکی برای آپلود ارسال نشده است.")
            return

        await bot.send_message(user_id, "📥 در حال دانلود تصاویر از بله...")

        from upload_helpers import download_images_from_bale

        groups_with_paths = []
        for group in test_attachments:
            group_title = group.get("title", "مستندات")
            group_file_ids = group.get("images", [])
            if not group_file_ids:
                continue
            group_paths = await download_images_from_bale(bot, group_file_ids, user_id)
            downloaded_paths.extend(group_paths)
            groups_with_paths.append({"title": group_title, "paths": group_paths})

        if not groups_with_paths:
            await bot.send_message(user_id, "⚠️ هیچ تصویری برای آپلود وجود ندارد.")
            return

        total_imgs = sum(len(g["paths"]) for g in groups_with_paths)
        await bot.send_message(
            user_id,
            f"✅ {total_imgs} تصویر دانلود شد. در حال آپلود به سامانه..."
        )

        # ── آپلود منضمات با همان حلقه اصلی ──────────────────────────
        from upload_helpers import resilient_upload_attachment_groups

        upload_result = await resilient_upload_attachment_groups(
            sana_page, groups_with_paths, bot, user_id,
            prefix="TEST")

        if upload_result["success"]:
            await bot.send_message(
                user_id,
                f"✅ تست منضمات موفق بود!\n\n"
                f"🏷 گروه‌های موفق: {len(upload_result['successful_groups'])}"
            )
            await bot.send_message(
                ADMIN_ID,
                f"🧪 تست منضمات موفق\n"
                f"کد: {tracking_code} | نوع: {category}\n"
                f"گروه‌ها: {len(upload_result['successful_groups'])} موفق"
            )
        else:
            failed = upload_result["failed_groups"][0] if upload_result["failed_groups"] else {}
            failed_title = failed.get('title', '?')
            failed_error = failed.get('error', 'نامشخص')
            await bot.send_message(
                user_id,
                f"❌ تست منضمات ناموفق\n\n"
                f"عنوان مشکل‌دار: {failed_title}\n"
                f"خطا: {failed_error}"
            )
            await bot.send_message(
                ADMIN_ID,
                f"❌ تست منضمات ناموفق\n"
                f"کد: {tracking_code} | نوع: {category}\n"
                f"خطا: {failed_error}"
            )

    except Exception as e:
        logging.error(f"[TEST-ATT] خطا در تست منضمات: {e}", exc_info=True)
        await bot.send_message(user_id, f"❌ خطا در تست منضمات: {str(e)[:200]}")
    finally:
        # پاکسازی فایل‌های دانلود‌شده
        for path in downloaded_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


async def _bulk_progress_note_result(bot: Bot, user_id: int, tracking_code: str, doc_name: str, is_invalid: bool) -> bool:
    """اگر این استعلام بخشی از یک دستهٔ چندموردی (کارت خرید یا فایل اکسل) باشد،
    نتیجه را در پیشرفت دسته ثبت می‌کند و در صورت اتمام دسته، گزارش نهاییِ
    کدرهگیری‌های نامعتبر را (در صورت وجود) برای کاربر ارسال می‌کند و فرصت
    ۳۰ دقیقه‌ای اصلاح رایگان را فعال می‌کند.
    خروجی True یعنی این آیتم بخشی از یک دسته بود و توسط این تابع مدیریت شد؛
    در این حالت نباید هیچ پیام تک‌موردی دیگری برای همین خطا فرستاده شود."""
    progress = runtime_state.bulk_inquiry_progress.get(user_id)
    if not progress:
        return False
    if is_invalid:
        progress["invalid"].append({"tracking_code": tracking_code, "doc_name": doc_name})
    progress["remaining"] -= 1
    if progress["remaining"] <= 0:
        runtime_state.bulk_inquiry_progress.pop(user_id, None)
        invalid_list = progress.get("invalid", [])
        if invalid_list:
            import datetime as _dt
            from states import Form
            lines = "\n".join(f"• `{it['tracking_code']}` ({it['doc_name']})" for it in invalid_list)
            await bot.send_message(
                user_id,
                f"⚠️ *استعلام دسته‌جمعی شما به پایان رسید.*\n\n"
                f"کدرهگیری‌های زیر نامعتبر بودند:\n{lines}\n\n"
                f"⏰ شما *{runtime_state.INVALID_TRACKING_RETRY_MINUTES} دقیقه* فرصت دارید تا این موارد را اصلاح "
                f"و بدون پرداخت هزینه‌ی مجدد دوباره ارسال نمایید.\n\n"
                f"لطفاً کدرهگیری صحیح را ارسال نمایید:"
            )
            runtime_state.invalid_tracking_retry[user_id] = {
                "expires_at": _dt.datetime.now() + _dt.timedelta(minutes=runtime_state.INVALID_TRACKING_RETRY_MINUTES),
                "remaining": len(invalid_list),
                "template_job": progress.get("template_job", {}),
            }
            try:
                user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
                await user_state.set_state(Form.waiting_for_corrected_tracking_code)
            except Exception as e:
                logging.error(f"[BULK-INQUIRY] خطا در تنظیم state اصلاح: {e}")
    return True


async def _handle_invalid_tracking_code(bot: Bot, user_id: int, data: dict, tracking_code: str, doc_name: str):
    """مدیریت خطای «کد رهگیری نامعتبر است» که سامانه نشان می‌دهد —
    هم برای استعلام تکی و هم برای هر آیتم از استعلام دسته‌جمعی (کارت/اکسل)."""
    was_batch_item = await _bulk_progress_note_result(bot, user_id, tracking_code, doc_name, is_invalid=True)
    if was_batch_item:
        return
    # ── حالت تک‌موردی: بلافاصله به کاربر اطلاع بده و فرصت رایگان بده ──
    import datetime as _dt
    from states import Form
    await bot.send_message(
        user_id,
        f"❌ کدرهگیری‌ای که وارد نموده‌اید اشتباه است.\n\n"
        f"⏰ شما *{runtime_state.INVALID_TRACKING_RETRY_MINUTES} دقیقه* فرصت دارید تا بدون پرداخت هزینه‌ی مجدد، "
        f"کدرهگیری صحیح را ارسال و دوباره استعلام بگیرید.\n\n"
        f"لطفاً کدرهگیری جدید را ارسال نمایید:"
    )
    runtime_state.invalid_tracking_retry[user_id] = {
        "expires_at": _dt.datetime.now() + _dt.timedelta(minutes=runtime_state.INVALID_TRACKING_RETRY_MINUTES),
        "remaining": 1,
        "template_job": dict(data),
    }
    try:
        user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
        await user_state.set_state(Form.waiting_for_corrected_tracking_code)
    except Exception as e:
        logging.error(f"[INQUIRY] خطا در تنظیم state اصلاح کدرهگیری: {e}")


async def process_task(data, bot: Bot):
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data['user_id']
    query_type = data.get('query_type')
    tracking_code = data.get('tracking_code')
    category = data.get('doc_category')
    subcategory = data.get('doc_subcategory')
    need_attachments = data.get('need_attachments', False)
    task_type = data.get('task_type', 'PRINT')

    # ── سناریوی لایحه ثبت ─────────────────────────────────────────────────
    if task_type == "LAVAYEH_SUBMIT":
        try:
            from lavayeh_scenario import process_lavayeh_task
            await process_lavayeh_task(data, bot)
        except NationalIdError:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception as e:
            logging.error(f"[LAVAYEH_SUBMIT] خطا: {e}", exc_info=True)
            await bot.send_message(user_id, f"❌ خطایی در فرآیند ثبت لایحه رخ داد. فرآیند متوقف شد.\nلطفاً مجدداً از ابتدا اقدام فرمایید.")
        finally:
            # پاکسازی وضعیت فعال حتی در صورت خطا
            runtime_state.active_lavayeh_users.discard(user_id)
        return

    # ── سناریوی اعلام وکالت ────────────────────────────────────────────────
    if task_type == "EALAM_VAKALAHT_SUBMIT":
        try:
            from ealam_vakalaht_scenario import process_ealam_vakalaht_task
            await process_ealam_vakalaht_task(data, bot)
        except NationalIdError:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception as e:
            logging.error(f"[EALAM_VAKALAHT_SUBMIT] خطا: {e}", exc_info=True)
            await bot.send_message(user_id, f"❌ خطایی در فرآیند اعلام وکالت رخ داد. فرآیند متوقف شد.\nلطفاً مجدداً از ابتدا اقدام فرمایید.")
        finally:
            # پاکسازی وضعیت فعال حتی در صورت خطا
            runtime_state.active_lavayeh_users.discard(user_id)
        return

    # ── سناریوی ثبت اظهارنامه ─────────────────────────────────────────────
    if task_type == "EZHHARNAMEH_SUBMIT":
        try:
            from ezhharnameh_scenario import process_ezhharnameh_task
            await process_ezhharnameh_task(data, bot)
        except NationalIdError:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception as e:
            logging.error(f"[EZHHARNAMEH_SUBMIT] خطا: {e}", exc_info=True)
            await bot.send_message(user_id, f"❌ خطایی در فرآیند ثبت اظهارنامه رخ داد. فرآیند متوقف شد.\nلطفاً مجدداً از ابتدا اقدام فرمایید.")
        return

    # ── سناریوی ثبت دعاوی چک ──────────────────────────────────────────────
    if task_type == "CHECK_SUBMIT":
        try:
            from check_scenario import process_check_task
            await process_check_task(data, bot)
        except NationalIdError:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception as e:
            logging.error(f"[CHECK_SUBMIT] خطا: {e}", exc_info=True)
            await bot.send_message(user_id, f"❌ خطایی در فرآیند ثبت دادخواست چک رخ داد. فرآیند متوقف شد.\nلطفاً مجدداً از ابتدا اقدام فرمایید.")
        return

    # ── سناریوهای دعاوی اعتراضی ────────────────────────────────────────
    TN_TASK_TYPES = [
        "TN_APPEAL", "TN_REHEARING", "TN_SUPREME",
        "TN_CIVIL_REVIEW", "TN_CRIMINAL_REVIEW",
        "TN_THIRD_PARTY", "TN_PROSECUTOR_OBJECTION",
    ]
    if task_type in TN_TASK_TYPES:
        try:
            from tajdid_nazar_scenario import process_tajdid_nazar_task
            await process_tajdid_nazar_task(data, bot)
        except NationalIdError:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception as e:
            logging.error(f"[{task_type}] خطا: {e}", exc_info=True)
            await bot.send_message(user_id, f"❌ خطایی در فرآیند ثبت دعوی اعتراضی رخ داد. فرآیند متوقف شد.\nلطفاً مجدداً از ابتدا اقدام فرمایید.")
        return

    # ── سناریوی ارسال کد امضا ─────────────────────────────────────────────
    if task_type == "LAVAYEH_SEND_SIGN_CODE":
        await _process_lavayeh_send_sign_code(data, bot)
        return

    # ── سناریوی ثبت کد امضا ───────────────────────────────────────────────
    if task_type == "LAVAYEH_SUBMIT_SIGN":
        await _process_lavayeh_submit_sign(data, bot)
        return

    # ── سناریوی ارسال کد امضا دعوی اعتراضی — مستقل از لایحه ─────────────────
    if task_type == "TN_SEND_SIGN_CODE":
        await _process_tn_send_sign_code(data, bot)
        return

    # ── سناریوی ثبت کد امضا دعوی اعتراضی — مستقل از لایحه ────────────────────
    if task_type == "TN_SUBMIT_SIGN":
        await _process_tn_submit_sign(data, bot)
        return

    # ── سناریوی ارسال کد امضا اظهارنامه ────────────────────────────────────
    if task_type == "EZHHARNAMEH_SEND_SIGN_CODE":
        await _process_ezhharnameh_send_sign_code(data, bot)
        return

    # ── سناریوی ثبت کد امضا اظهارنامه ────────────────────────────────────
    if task_type == "EZHHARNAMEH_SUBMIT_SIGN":
        await _process_ezhharnameh_submit_sign(data, bot)
        return

    # ── سناریوی تست منضمات (مدیر) ─────────────────────────────────────────
    if task_type == "TEST_ATTACHMENTS":
        await _process_test_attachments(data, bot)
        return

    max_task_attempts = 3
    for task_attempt in range(max_task_attempts):
        try:
            if (await sana_page.locator('text="خطای دسترسی کاربر!"').is_visible() or
                    await sana_page.locator("text=ورود قبلی منقضی").is_visible()):
                await bot.send_message(ADMIN_ID, "⚠️ نشست سامانه منقضی شده است.")
                await wait_for_manual_login(bot)

            success = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not success:
                return

            await human_delay(4.0, 6.0)

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۱: استعلام شماره تماس
            # ────────────────────────────────────────────────────────────────
            if query_type == "شماره تماس":
                phone_number = tracking_code
                await bot.send_message(ADMIN_ID, f"🔄 شروع استخراج اشخاص برای موبایل {phone_number}...")

                await safe_click_by_text(sana_page, "ارایه و پیگیری شکواییه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                await safe_type(sana_page, '#txtPetitionNo, #billNo', "1400220968161114", bot, user_id)
                await sana_page.evaluate('''() => {
                    const exactBtn = document.querySelector('#btnGetJSSPetition') || document.querySelector('#btnGetJSSBill');
                    if(exactBtn) exactBtn.click();
                }''')
                await resilient_sleep(sana_page, 8, bot, user_id)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const closeBtn = btns.find(b => (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm"));
                    if(closeBtn) closeBtn.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)

                await safe_click_by_text(sana_page, "ثبت و اصلاح شكوائيه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)
                await safe_click_by_text(sana_page, "مشتكي عنه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const btn = btns.find(b => b.hasAttribute('tooltip') && b.getAttribute('tooltip').includes("خوانده یابی"));
                    if(btn) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                await sana_page.evaluate('''() => {
                    const radio = document.querySelector('#searchPersonTypeByMobileNo');
                    if(radio) radio.click();
                }''')
                await safe_type(sana_page, '#txtMobileNoFromSearch', phone_number, bot, user_id)

                search_clicked = await sana_page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const searchBtn = buttons.find(b => b.innerText && b.innerText.trim().includes("جستجوی شماره همراه"));
                    if (searchBtn) { searchBtn.click(); return true; }
                    return false;
                }''')
                if not search_clicked:
                    await safe_click_by_text(sana_page, "جستجوی شماره همراه", bot, user_id)

                # منتظر ناپدید شدن لودینگ افقی بالای صفحه
                await asyncio.sleep(2)
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=30)

                # بررسی وجود پیام خطای ثنا (عدم ثبت شماره همراه)
                await asyncio.sleep(3)
                alert_message = await sana_page.evaluate('''() => {
                    const alerts = document.querySelectorAll('div.alert-info, div.alert-dismissable');
                    for (let alert of alerts) {
                        const msgDiv = alert.querySelector('div[ng-bind-html]');
                        if (msgDiv && msgDiv.innerText) {
                            const text = msgDiv.innerText.trim();
                            if (text.includes('پایگاه داده ثنا') && text.includes('ثبت نشده است')) {
                                return text;
                            }
                        }
                    }
                    return null;
                }''')
                
                if alert_message:
                    logging.warning(f"[PHONE_SEARCH] پیام خطای ثنا برای شماره {phone_number}: {alert_message}")
                    await bot.send_message(
                        user_id,
                        f"⚠️ *پیام سامانه:*\\n\\n{alert_message}\\n\\n"
                        "فرآیند متوقف شد.")
                    await bot.send_message(ADMIN_ID, f"⚠️ [PHONE_SEARCH] خطای ثنا برای {phone_number} (کاربر {user_id}): {alert_message}")
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id, full_name=data.get('full_name', ''),
                            tracking_code=phone_number, doc_category="شماره تماس",
                            error_details=alert_message, error_step="sana_alert",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق موبایل: {panel_err}")
                    return

                table_ready, has_results = await _wait_for_mobile_search_table(sana_page, timeout_sec=30)
                if table_ready and not has_results:
                    await safe_click_by_text(sana_page, "بستن", bot, user_id)
                    await bot.send_message(user_id, f"❌ براساس شماره {phone_number}، موردی یافت نشد.")
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id, full_name=data.get('full_name', ''),
                            tracking_code=phone_number, doc_category="شماره تماس",
                            error_details="موردی یافت نشد", error_step="no_results",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق موبایل: {panel_err}")
                    return

                if not table_ready:
                    retry_clicked = await sana_page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const searchBtn = buttons.find(b => b.innerText && b.innerText.trim().includes("جستجوی شماره همراه"));
                        if (searchBtn) { searchBtn.click(); return true; }
                        return false;
                    }''')
                    if not retry_clicked:
                        await safe_click_by_text(sana_page, "جستجوی شماره همراه", bot, user_id)
                    # منتظر ناپدید شدن لودینگ
                    await asyncio.sleep(2)
                    await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=30)
                    table_ready, has_results = await _wait_for_mobile_search_table(sana_page, timeout_sec=30)
                    if table_ready and not has_results:
                        await safe_click_by_text(sana_page, "بستن", bot, user_id)
                        await bot.send_message(user_id, f"❌ براساس شماره {phone_number}، موردی یافت نشد.")
                        try:
                            await register_failed_inquiry_to_panel(
                                user_id=user_id, full_name=data.get('full_name', ''),
                                tracking_code=phone_number, doc_category="شماره تماس",
                                error_details="موردی یافت نشد (تلاش دوم)", error_step="no_results",
                            )
                        except Exception as panel_err:
                            logger.warning(f"خطا در ثبت استعلام ناموفق موبایل: {panel_err}")
                        return

                if not table_ready:
                    await bot.send_message(
                        user_id,
                        f"⚠️ *استعلام شماره تماس {phone_number} با تاخیر سامانه مواجه شد و نتیجه‌ای دریافت نشد.*\n\n"
                        "لطفاً کمی بعد دوباره تلاش کنید.")
                    await bot.send_message(ADMIN_ID, f"⚠️ [PHONE_SEARCH] جدول نتایج برای موبایل {phone_number} (کاربر {user_id}) حتی بعد از تلاش دوم ظاهر نشد.")
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id, full_name=data.get('full_name', ''),
                            tracking_code=phone_number, doc_category="شماره تماس",
                            error_details="جدول نتایج ظاهر نشد (تایم‌اوت)", error_step="table_timeout",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق موبایل: {panel_err}")
                    return

                persons = await sana_page.evaluate('''() => {
                    function toEng(str) {
                        const p = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
                        const a = ['٠','١','٢','٣','٤','٥','٦','٧','٨','٩'];
                        let res = str;
                        for(let i=0; i<10; i++) {
                            res = res.split(p[i]).join(i).split(a[i]).join(i);
                        }
                        return res;
                    }
                    const rows = Array.from(document.querySelectorAll('tbody tr'));
                    const data = [];
                    rows.forEach(tr => {
                        const tds = tr.querySelectorAll('td');
                        if(tds.length > 5) {
                            let nat_id = "";
                            for(let td of tds) {
                                const text = toEng(td.innerText.trim());
                                if(/^[0-9]{10}$/.test(text)) nat_id = text;
                            }
                            if(nat_id) data.push({nat_id: nat_id});
                        }
                    });
                    return data;
                }''')

                await safe_click_by_text(sana_page, "بستن", bot, user_id)
                await resilient_sleep(sana_page, 2, bot, user_id)
                if not persons:
                    await bot.send_message(user_id, f"❌ براساس شماره {phone_number}، موردی یافت نشد.")
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id, full_name=data.get('full_name', ''),
                            tracking_code=phone_number, doc_category="شماره تماس",
                            error_details="موردی یافت نشد", error_step="no_persons_extracted",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق موبایل: {panel_err}")
                    return

                await bot.send_message(ADMIN_ID, f"✅ تعداد {len(persons)} شخص یافت شد.")

                for idx, person in enumerate(persons):
                    nat_id = person['nat_id']
                    try:
                        print_url = f"https://sakha2.adliran.ir/Report/RealPersonPrint.aspx?no={nat_id}"
                        success_print = await goto_url_with_retry(sana_page, print_url, bot, user_id)
                        if not success_print:
                            return
                        await check_and_handle_expiry(sana_page, bot, user_id)
                        try:
                            await sana_page.wait_for_selector('text=شناسنامه', timeout=15000)
                            await asyncio.sleep(2)
                        except Exception:
                            await asyncio.sleep(5)

                        # ── استخراج تمیز داده (عکس + اطلاعات) از صفحه‌ی چاپ ──
                        # توجه: صفحه‌ی اصلی sana_page اصلاً دست‌کاری نمی‌شود؛
                        # فقط داده خوانده می‌شود و در یک صفحه‌ی جدید و تمیز رندر
                        # و پرینت می‌گردد (مستقل از لوگو/نکات امنیتی/فوتر و ...).
                        profile_data = await extract_sana_profile(sana_page)

                        if not profile_data:
                            await bot.send_message(
                                ADMIN_ID,
                                f"⚠️ استخراج اطلاعات پروفایل {nat_id} ناموفق بود (ساختار صفحه یافت نشد)."
                            )
                        else:
                            pdf_path = f"report_phone_{phone_number}_{idx}.pdf"
                            built = await build_sana_profile_pdf(
                                browser_context, profile_data, pdf_path, national_id=nat_id
                            )
                            if built and os.path.exists(pdf_path):
                                await send_document_direct(
                                    user_id, pdf_path,
                                    caption=f"📄 مشخصات ثنا (پروفایل {idx+1})"
                                )
                                os.remove(pdf_path)
                            else:
                                await bot.send_message(
                                    ADMIN_ID, f"⚠️ ساخت PDF برای پروفایل {nat_id} ناموفق بود."
                                )

                        await sana_page.go_back()
                        await asyncio.sleep(3)

                    except Exception as e:
                        if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                            raise e
                        await bot.send_message(ADMIN_ID, f"❌ خطا در پروفایل {nat_id}: {e}")

                        try:
                            from bug_reporter import report_bug
                            await report_bug(bot, where="process_task", error=e,
                                             user_id=user_id,
                                             page=getattr(runtime_state, "sana_page", None))
                        except Exception:
                            pass

                # ── ثبت استعلام شماره تماس در پنل ادمین ──
                try:
                    await register_inquiry_to_panel(
                        user_id=user_id,
                        full_name=data.get('full_name', ''),
                        tracking_code=phone_number,
                        doc_category="شماره تماس",
                        fee=data.get('payment_fee', 0),
                        result_summary=f"استعلام شماره تماس - {len(persons)} نفر یافت شد"
                    )
                except Exception as panel_err:
                    logger.warning(f"خطا در ثبت استعلام شماره تماس: {panel_err}")

                await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                await bot.send_message(ADMIN_ID, f"✅ پردازش موبایل {phone_number} تمام شد.")
                return

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۳: استعلام کد ملی
            # ────────────────────────────────────────────────────────────────
            elif query_type == "کد ملی":
                national_id = tracking_code
                await bot.send_message(ADMIN_ID, f"🔄 استعلام ثنا برای کد ملی {national_id}...")

                print_url = f"https://sakha2.adliran.ir/Report/RealPersonPrint.aspx?no={national_id}"
                success_print = await goto_url_with_retry(sana_page, print_url, bot, user_id)
                if not success_print:
                    return
                await asyncio.sleep(3)
                await check_and_handle_expiry(sana_page, bot, user_id)

                has_error = await sana_page.evaluate('''() => {
                    const text = document.body.innerText || "";
                    return text.includes("اطلاعاتی با این شماره ملی ثبت نشده است") || text.includes("ثبت نشده است");
                }''')

                if has_error:
                    await bot.send_message(user_id, f"❌ کدملی `{national_id}` فاقد ثبت‌نام ثنا می‌باشد.")
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id,
                            full_name=data.get('full_name', ''),
                            tracking_code=national_id,
                            doc_category="کد ملی",
                            error_details="کدملی فاقد ثبت‌نام ثنا",
                            error_step="lookup_not_found",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق کد ملی: {panel_err}")
                    await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                    return

                try:
                    await sana_page.wait_for_selector('text=شناسنامه', timeout=15000)
                    await asyncio.sleep(2)
                except Exception:
                    await asyncio.sleep(5)

                # ── استخراج تمیز داده (عکس + اطلاعات) از صفحه‌ی چاپ ──
                # صفحه‌ی اصلی sana_page اصلاً دست‌کاری نمی‌شود؛ فقط داده خوانده
                # می‌شود و در یک صفحه‌ی جدید و کاملاً تمیز رندر و پرینت می‌گردد
                # (مستقل از لوگو/نکات امنیتی/فوتر/افزونه‌های مرورگر و غیره).
                profile_data = await extract_sana_profile(sana_page)

                if not profile_data:
                    await bot.send_message(
                        user_id, f"❌ استخراج اطلاعات ثنا برای کدملی `{national_id}` ناموفق بود."
                    )
                    try:
                        await register_failed_inquiry_to_panel(
                            user_id=user_id,
                            full_name=data.get('full_name', ''),
                            tracking_code=national_id,
                            doc_category="کد ملی",
                            error_details="استخراج اطلاعات پروفایل ناموفق بود (ساختار صفحه یافت نشد)",
                            error_step="profile_extraction",
                        )
                    except Exception as panel_err:
                        logger.warning(f"خطا در ثبت استعلام ناموفق کد ملی: {panel_err}")
                    await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                    return

                pdf_path = f"report_national_{national_id}.pdf"
                built = await build_sana_profile_pdf(
                    browser_context, profile_data, pdf_path, national_id=national_id
                )

                if built and os.path.exists(pdf_path):
                    await send_document_direct(user_id, pdf_path, caption=f"📄 مشخصات ثنا برای کدملی: `{national_id}`")
                    os.remove(pdf_path)
                else:
                    await bot.send_message(
                        user_id, f"❌ ساخت PDF برای کدملی `{national_id}` ناموفق بود."
                    )

                # ── ثبت استعلام کد ملی در پنل ادمین ──
                try:
                    await register_inquiry_to_panel(
                        user_id=user_id,
                        full_name=data.get('full_name', ''),
                        tracking_code=national_id,
                        doc_category="کد ملی",
                        fee=data.get('payment_fee', 0),
                        result_summary=f"استعلام کد ملی - {national_id}"
                    )
                except Exception as panel_err:
                    logger.warning(f"خطا در ثبت استعلام کد ملی: {panel_err}")

                await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                await bot.send_message(ADMIN_ID, f"✅ پردازش کد ملی {national_id} تمام شد.")
                return

            # ────────────────────────────────────────────────────────────────
            # PRE_CHECK — استعلام پیوست در تب جدید (بدون دخالت به sana_page)
            # ────────────────────────────────────────────────────────────────
            elif task_type == 'PRE_CHECK':
                await _process_pre_check_on_new_page(data, bot)
                return

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۲: استعلام کد رهگیری پرونده
            # ────────────────────────────────────────────────────────────────
            elif query_type == "کد رهگیری":
                from states import Form

                if category == "لایحه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
                elif category == "اظهارنامه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
                elif category == "شکواییه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری شکواییه", bot, user_id)
                elif category == "دادخواست بدوی":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دادخواست", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, "دادخواست بدوی", bot, user_id)
                elif category == "دعاوی دادگاههای صلح":
                    await safe_click_by_text(sana_page, "دعاوی دادگاههای صلح", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, "دعاوی حقوقی", bot, user_id)
                elif category == "دعاوی اعتراضی":
                    await safe_click_by_text(sana_page, "دعاوی اعتراضی", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "دعاوی طاری":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دعاوی طاری", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "دیوان عدالت اداری":
                    await safe_click_by_text(sana_page, "دیوان عدالت اداری", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "شورای حل اختلاف":
                    await safe_click_by_text(sana_page, "شورای حل اختلاف (صلح و سازش)", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                if category == "لایحه" or (
                    category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
                ):
                    # ابتدا منتظر ظاهر شدن رادیوباتن می‌مانیم
                    try:
                        await sana_page.wait_for_selector('#rdbGetPetition', state='visible', timeout=10000)
                    except Exception:
                        logging.error("[INQUIRY] رادیوباتن #rdbGetPetition یافت نشد")
                        raise Exception("رادیوباتن استعلام لایحه یافت نشد.")
                    # کلیک با فعال‌سازی AngularJS digest
                    await sana_page.evaluate('''() => {
                        const radio = document.querySelector('#rdbGetPetition');
                        if (radio) {
                            radio.checked = true;
                            radio.click();
                            if (window.angular) {
                                try {
                                    const scope = angular.element(radio).scope();
                                    if (scope) scope.$apply();
                                } catch(e) {}
                            }
                        }
                    }''')
                    await resilient_sleep(sana_page, 4, bot, user_id)

                try:
                    await sana_page.wait_for_selector('#txtPetitionNo, #billNo', timeout=15000)
                except Exception:
                    raise Exception("صفحه کارتابل لود نشد.")

                # لایحه: فیلد ورودی کدرهگیری #billNo
                if category == "لایحه" or (
                    category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
                ):
                    await safe_type(sana_page, '#billNo', tracking_code, bot, user_id)
                else:
                    selector = '#txtPetitionNo, #billNo, input[name="txtPetitionNo"], input[name="billNo"]'
                    await safe_type(sana_page, selector, tracking_code, bot, user_id)
                await resilient_sleep(sana_page, 2, bot, user_id)

                # لایحه: دکمه جستجو #btnGetJSSBill
                if category == "لایحه" or (
                    category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
                ):
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnGetJSSBill');
                        if (btn) { btn.click(); return; }
                    }''')
                else:
                    await sana_page.evaluate('''() => {
                        const exactBtn = document.querySelector('#btnGetJSSPetition');
                        if (exactBtn) { exactBtn.click(); return; }
                        const btns = Array.from(document.querySelectorAll('button'));
                        const searchBtn = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
                        if (searchBtn) searchBtn.click();
                    }''')

                doc_name = subcategory if subcategory else category
                await bot.send_message(ADMIN_ID, f"⏳ استعلام «{doc_name}»...")

                # منتظر ناپدید شدن لودینگ افقی بالای صفحه
                await asyncio.sleep(3)
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

                # ── بررسی خطای «کد رهگیری معتبر نیست» ────────────────────
                # این چک باید قبل از بستن خودکار پاپ‌آپ‌ها (پایین‌تر) انجام شود،
                # چون در غیر این صورت متن خطا قبل از خواندن، بسته می‌شود.
                invalid_code_popup = await sana_page.evaluate('''() => {
                    const popup = document.querySelector('.sweet-alert.showSweetAlert');
                    if (popup) {
                        const t = popup.innerText || "";
                        if (t.includes("معتبر نیست")) return true;
                    }
                    return false;
                }''')
                if invalid_code_popup:
                    try:
                        await sana_page.locator('.sweet-alert.showSweetAlert button.confirm').click(timeout=5000)
                    except Exception:
                        pass
                    # اطلاع به مدیر
                    try:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ [INQUIRY_FAIL] کاربر {user_id} — کدرهگیری نامعتبر — کد: `{tracking_code}` — نوع: {doc_name}"
                        )
                    except Exception:
                        pass
                    await _handle_invalid_tracking_code(bot, user_id, data, tracking_code, doc_name)
                    return

                if (
                    await sana_page.locator('text="لطفا اطلاعات خواسته شده را به درستی وارد نمایید"').is_visible()
                    or await sana_page.locator('button:has-text("بستن")').is_visible()
                ):
                    await safe_click_by_text(sana_page, "بستن", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await sana_page.evaluate('''() => {
                        const exactBtn = document.querySelector('#btnGetJSSPetition');
                        if (exactBtn) { exactBtn.click(); return; }
                        const btns = Array.from(document.querySelectorAll('button'));
                        const searchBtn = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
                        if (searchBtn) searchBtn.click();
                    }''')
                    # منتظر ناپدید شدن لودینگ
                    await asyncio.sleep(3)
                    await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const closeBtn = btns.find(b =>
                        (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm")
                    );
                    if(closeBtn) closeBtn.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)

                if (
                    await sana_page.locator(".alert-danger").is_visible()
                    or await sana_page.locator('text="اطلاعاتی یافت نشد"').is_visible()
                ):
                    await bot.send_message(user_id, f"❌ پرونده‌ای با کد `{tracking_code}` یافت نگردید.")
                    await _bulk_progress_note_result(bot, user_id, tracking_code, doc_name, is_invalid=False)
                    return

                # ── PRINT ─────────────────────────────────────────────────
                else:
                    saved_attachments = []
                    try:
                        async def click_print_box():
                            await sana_page.evaluate('''() => {
                                const headings = Array.from(document.querySelectorAll('h5, button, a'));
                                const printHeading = headings.find(h => h.innerText && (
                                    h.innerText.includes("چاپ اوليه") ||
                                    h.innerText.includes("چاپ اولیه") ||
                                    h.innerText.includes("چاپ")
                                ));
                                if (printHeading) {
                                    const box = printHeading.closest('.box');
                                    if (box) box.click();
                                    else printHeading.click();
                                }
                            }''')

                        async with browser_context.expect_page(timeout=15000) as new_page_info:
                            await click_print_box()

                        print_page = await new_page_info.value
                        await print_page.wait_for_load_state()
                        await resilient_sleep(print_page, 8, bot, user_id)
                        await check_and_handle_expiry(print_page, bot, user_id)

                        pdf_path = f"report_{tracking_code}.pdf"
                        await print_page.pdf(path=pdf_path, format="A4")
                        await print_page.close()

                        if need_attachments:
                            saved_attachments.append((pdf_path, f"📄 استعلام کد پیگیری: `{tracking_code}`"))
                        else:
                            await send_document_direct(user_id, pdf_path, caption=f"📄 استعلام کد پیگیری: `{tracking_code}`")
                            os.remove(pdf_path)

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام کد رهگیری - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"خطا در ثبت استعلام: {panel_err}")

                    except Exception as print_err:
                        logging.error(f"خطا در چاپ: {print_err}")
                        await bot.send_message(user_id, "⚠️ چاپ پرونده با خطا مواجه شد.")

                        try:
                            await register_failed_inquiry_to_panel(
                                user_id=user_id, full_name=data.get('full_name', ''),
                                tracking_code=tracking_code, doc_category=category,
                                doc_subcategory=subcategory,
                                error_details=str(print_err), error_step="print_document",
                            )
                        except Exception as panel_err:
                            logger.warning(f"خطا در ثبت استعلام ناموفق کد پیگیری: {panel_err}")

                        try:
                            from bug_reporter import report_bug
                            await report_bug(bot, where="process_task_attachment", error=e,
                                             user_id=user_id,
                                             page=getattr(runtime_state, "sana_page", None))
                        except Exception:
                            pass
                        raise Exception("Failed to print the document.")

                    if need_attachments:
                        # ── بررسی وجود تب «منضمات» قبل از کلیک ─────
                        mozamatat_exists = await sana_page.evaluate('''() => {
                            const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div', 'td'];
                            for (let tag of tags) {
                                const elements = Array.from(document.querySelectorAll(tag));
                                const target = elements.find(el => el.innerText && el.innerText.trim().includes("منضمات"));
                                if (target) {
                                    const rect = target.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) return true;
                                }
                            }
                            return false;
                        }''')
                        if not mozamatat_exists:
                            # تب منضمات وجود ندارد — فایل اصلی را ارسال و اسکیپ کن
                            for path, caption in saved_attachments:
                                if os.path.exists(path):
                                    await send_document_direct(user_id, path, caption=caption)
                                    os.remove(path)
                            await bot.send_message(user_id, "📄 این درخواست فاقد بخش منضمات است.")

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام بدون منضمات - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"خطا در ثبت استعلام: {panel_err}")

                            await _bulk_progress_note_result(bot, user_id, tracking_code, doc_name, is_invalid=False)
                            return

                        await safe_click_by_text(sana_page, "منضمات", bot, user_id)
                        await resilient_sleep(sana_page, 5, bot, user_id)

                        rows_data = await sana_page.evaluate('''() => {
                            const tbody = document.querySelector('tbody');
                            if (!tbody) return [];
                            const trs = Array.from(tbody.querySelectorAll('tr'));
                            return trs.map((tr, index) => {
                                const tds = tr.querySelectorAll('td');
                                if (tds.length >= 6) {
                                    const title = tds[2].innerText.trim();
                                    const countText = tds[5].innerText.trim();
                                    const count = parseInt(countText) || 0;
                                    return { index, title, count };
                                }
                                return null;
                            }).filter(r => r !== null);
                        }''')

                        def _is_ignored_attachment(title: str) -> bool:
                            t = (title or "").replace("\u200c", " ")
                            return "قرارداد الکترونیک" in t and ("وکالت نامه" in t or "وکالتنامه" in t)

                        rows_data = [r for r in rows_data if not _is_ignored_attachment(r.get('title', ''))]

                        has_signature_row = (
                            len(rows_data) > 0 and
                            ("امضا" in rows_data[0]['title'] or "امضاء" in rows_data[0]['title'])
                        )
                        data_rows = rows_data[1:] if has_signature_row else rows_data
                        real_rows = [r for r in data_rows if r['count'] > 0]

                        if not real_rows:
                            for path, caption in saved_attachments:
                                if os.path.exists(path):
                                    await send_document_direct(user_id, path, caption=caption)
                                    os.remove(path)
                            await bot.send_message(user_id, "📄 این درخواست فاقد پیوست واقعی است.")

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام بدون پیوست واقعی - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"خطا در ثبت استعلام: {panel_err}")

                        else:
                            await bot.send_message(
                                user_id,
                                f"📎 تعداد {len(real_rows)} ردیف پیوست کشف شد. در حال استخراج..."
                            )
                            try:
                                for r in real_rows:
                                    row_idx = r['index']
                                    row_title = r['title']
                                    row_count = r['count']

                                    await sana_page.evaluate('window.scrollTo(0, 0)')
                                    await resilient_sleep(sana_page, 2, bot, user_id)

                                    await sana_page.evaluate('''(idx) => {
                                        const tbody = document.querySelector('tbody');
                                        if (tbody) {
                                            const trs = tbody.querySelectorAll('tr');
                                            if (trs.length > idx) {
                                                const btn = trs[idx].querySelector('button[ng-click*="editDocument"]');
                                                if (btn) btn.click();
                                            }
                                        }
                                    }''', row_idx)
                                    await resilient_sleep(sana_page, 5, bot, user_id)

                                    btn_count = await sana_page.evaluate('''() => {
                                        const btns = Array.from(document.querySelectorAll('button'));
                                        return btns.filter(b => b.innerText && b.innerText.includes("نمایش و چاپ")).length;
                                    }''')

                                    if btn_count == 0:
                                        await bot.send_message(
                                            user_id, f"⚠️ فایل پیوستی در بخش «{row_title}» یافت نشد."
                                        )
                                    else:
                                        for btn_idx in range(btn_count):
                                            btn_success = False
                                            for attempt in range(4):
                                                att_page = None
                                                try:
                                                    async with browser_context.expect_page(timeout=20000) as att_page_info:
                                                        await sana_page.evaluate(f'''(b_idx) => {{
                                                            const btns = Array.from(document.querySelectorAll('button'));
                                                            const printBtns = btns.filter(b => b.innerText && b.innerText.includes("نمایش و چاپ"));
                                                            if (printBtns.length > b_idx) {{ printBtns[b_idx].click(); }}
                                                        }}''', btn_idx)

                                                    att_page = await att_page_info.value
                                                    await resilient_sleep(att_page, 5, bot, user_id)
                                                    await check_and_handle_expiry(att_page, bot, user_id)

                                                    import base64
                                                    pdf_data_base64 = await att_page.evaluate('''async () => {
                                                        const embed = document.querySelector('embed[type="application/pdf"], embed[src*="pdf"], iframe[src*="pdf"]');
                                                        let pdfUrl = null;
                                                        if (embed && embed.src) pdfUrl = embed.src;
                                                        else {
                                                            const iframe = document.querySelector('iframe');
                                                            if (iframe && iframe.src) pdfUrl = iframe.src;
                                                        }
                                                        if (pdfUrl) {
                                                            try {
                                                                const response = await fetch(pdfUrl);
                                                                const blob = await response.blob();
                                                                return new Promise((resolve, reject) => {
                                                                    const reader = new FileReader();
                                                                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                                                    reader.onerror = reject;
                                                                    reader.readAsDataURL(blob);
                                                                });
                                                            } catch(e) { return null; }
                                                        }
                                                        return null;
                                                    }''')

                                                    att_pdf_path = f"attachment_{tracking_code}_{row_idx}_{btn_idx}.pdf"
                                                    if pdf_data_base64:
                                                        with open(att_pdf_path, 'wb') as pdf_file:
                                                            pdf_file.write(base64.b64decode(pdf_data_base64))
                                                    else:
                                                        await resilient_sleep(att_page, 8, bot, user_id)
                                                        await att_page.pdf(path=att_pdf_path, format="A4")

                                                    await att_page.close()
                                                    saved_attachments.append(
                                                        (att_pdf_path, f"📎 پیوست {btn_idx+1} — «{row_title}»")
                                                    )
                                                    btn_success = True
                                                    break

                                                except Exception as att_err:
                                                    if "Session expired" in str(att_err):
                                                        raise att_err
                                                    logging.error(f"خطا در پیوست {btn_idx}: {att_err}")
                                                    try:
                                                        await att_page.close()
                                                    except Exception:
                                                        pass
                                                    await asyncio.sleep(3)

                                            if not btn_success:
                                                await bot.send_message(
                                                    user_id, f"❌ پیوست {btn_idx+1} از «{row_title}» ناموفق."
                                                )

                                    await sana_page.evaluate('window.scrollTo(0, 0)')
                                    await resilient_sleep(sana_page, 2.5, bot, user_id)

                                if saved_attachments:
                                    await bot.send_message(user_id, f"📥 در حال ارسال {len(saved_attachments)} فایل...")
                                    for path, caption in saved_attachments:
                                        try:
                                            if os.path.exists(path):
                                                await send_document_direct(user_id, path, caption=caption)
                                                os.remove(path)
                                        except Exception as send_err:
                                            logging.error(f"خطا در ارسال {path}: {send_err}")

                                await bot.send_message(user_id, "✅ استخراج منضمات کاملاً تمام شد.")

                                # ── ثبت استعلام در پنل ادمین ──
                                try:
                                    await register_inquiry_to_panel(
                                        user_id=user_id,
                                        full_name=data.get('full_name', ''),
                                        tracking_code=tracking_code,
                                        doc_category=category,
                                        doc_subcategory=subcategory,
                                        fee=data.get('payment_fee', 0),
                                        result_summary=f"استعلام با منضمات - {doc_name} - {len(real_rows)} پیوست"
                                    )
                                except Exception as panel_err:
                                    logger.warning(f"خطا در ثبت استعلام: {panel_err}")

                            except Exception as loop_err:
                                if "Session expired" in str(loop_err):
                                    raise loop_err
                                for path, _ in saved_attachments:
                                    try:
                                        if os.path.exists(path):
                                            os.remove(path)
                                    except Exception:
                                        pass
                                raise loop_err
                    await _bulk_progress_note_result(bot, user_id, tracking_code, doc_name, is_invalid=False)
                    return

            break

        except Exception as task_err:
            logging.error(f"تلاش {task_attempt+1} ناموفق: {task_err}")
            if task_attempt < max_task_attempts - 1:
                await bot.send_message(ADMIN_ID, f"⚠️ فرآیند با خطا مواجه شد. تلاش مجدد {task_attempt+2}...")

                try:
                    from bug_reporter import report_bug
                    await report_bug(bot, where="process_task_retry", error=task_err,
                                     user_id=user_id,
                                     page=getattr(runtime_state, "sana_page", None))
                except Exception:
                    pass
                await sana_page.reload()
                await asyncio.sleep(5)
            else:
                doc_name = f"{category} - {subcategory}" if subcategory else category

                # ── ذخیره در disrupted_users (فرصت تکرار بدون پرداخت) ──
                import datetime
                from handlers import DISRUPTED_RETRY_MINUTES, SAMANEH_WRONG_TYPE_ERROR

                runtime_state.disrupted_users[user_id] = {
                    "timestamp": datetime.datetime.now(),
                    "job_data": data,
                    "notified": True,
                }

                # ── اطلاع‌رسانی به کاربر با دکمه‌ی تلاش مجدد ──
                from keyboards import disrupted_retry_kb
                try:
                    error_detail = SAMANEH_WRONG_TYPE_ERROR if ('کد دفتر' in str(task_err) or 'مبلغ پرونده' in str(task_err)) else 'عملیات استعلام موفق نبود.'
                    await bot.send_message(
                        user_id,
                        f"⚠️ *سامانه قضایی با اختلال مواجه است.*\n\n"
                        f"❌ {error_detail}\n\n"
                        f"🔧 شما تا *{DISRUPTED_RETRY_MINUTES} دقیقه* فرصت دارید بدون پرداخت مجدد، "
                        f"از منوی اصلی گزینه‌ی شروع (/start) را بزنید تا تلاش مجدد انجام شود.",
                        reply_markup=disrupted_retry_kb)
                except Exception as send_err:
                    logging.error(f"خطا در ارسال پیام disrupted به کاربر: {send_err}")

                # ── اطلاع‌رسانی به مدیر (جزئیات کامل) ──
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"🚨 *اختلال در استعلام — disrupted ذخیره شد*\n\n"
                        f"👤 کاربر: `{user_id}`\n"
                        f"نوع: {query_type}\n"
                        f"کد رهگیری: `{tracking_code or ''}`\n"
                        f"سند: {doc_name}\n"
                        f"خطا: `{str(task_err)[:300]}`\n\n"
                        f"✅ کاربر تا {DISRUPTED_RETRY_MINUTES} دقیقه فرصت تلاش مجدد دارد.\n"
                        f"📋 وضعیت صف: {runtime_state.job_queue.qsize()} تسک در انتظار")
                except Exception:
                    pass

                await log_event(
                    "خطای سامانه (disrupted)", query_type, str(user_id), user_id,
                    tracking_code=tracking_code or "", doc_name=doc_name or "",
                    note=f"پس از {max_task_attempts} تلاش: {str(task_err)[:200]}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ارسال کد امضا
# ══════════════════════════════════════════════════════════════════════════════
async def _process_lavayeh_send_sign_code(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    phase = data.get("phase", "navigate")
    sign_menu_path = data.get("sign_menu_path")

    from lavayeh_sign_handlers import (
        on_lavayeh_sign_persons_loaded,
        on_lavayeh_sign_code_sent_success,
        on_lavayeh_sign_code_sent_failure)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        from lavayeh_sign_scenario import (
            navigate_to_sign_page,
            get_signable_persons,
            send_sign_code_for_person)

        if phase == "navigate":
            # فاز ۱: ناوبری به صفحه امضا و دریافت لیست اشخاص
            await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ناوبری به صفحه امضا برای کاربر {user_id}")
            nav_ok = await navigate_to_sign_page(bot, user_id, tracking_code, menu_path=sign_menu_path)

            if not nav_ok:
                await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [SIGN] ناوبری ناموفق برای کاربر {user_id}")
                return

            # دریافت لیست اشخاص
            persons = await get_signable_persons(bot, user_id)
            await on_lavayeh_sign_persons_loaded(bot, user_id, persons, user_state)

        elif phase == "send_code":
            # فاز ۲: ارسال کد برای شخص انتخاب‌شده
            target_row_indices = data.get("target_row_indices", [])
            await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ارسال کد امضا برای کاربر {user_id}")

            sign_info = runtime_state.pending_lavayeh_sign.get(user_id, {})
            all_persons = sign_info.get("sign_persons", [])

            results = []
            for row_idx in target_row_indices:
                person = next((p for p in all_persons if p["idx"] == row_idx), None)
                person_name = person.get("name", f"شخص {row_idx + 1}") if person else f"شخص {row_idx + 1}"
                success = await send_sign_code_for_person(bot, user_id, row_idx, person_name, tracking_code)
                results.append({
                    "idx": row_idx,
                    "name": person_name,
                    "person_type": person.get("personType", "") if person else "",
                    "sent": success,
                })
                # فاصله ۳۰ ثانیه بین ارسال کد هر شخص
                if row_idx != target_row_indices[-1]:
                    await asyncio.sleep(30)

            any_sent = any(r["sent"] for r in results)
            if any_sent:
                await on_lavayeh_sign_code_sent_success(bot, user_id, results, user_state)
                await bot.send_message(ADMIN_ID, f"✅ [SIGN] کد امضا برای کاربر {user_id} ارسال شد.")
            else:
                await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [SIGN] ارسال کد امضا برای کاربر {user_id} ناموفق.")

    except Exception as e:
        logging.error(f"[SIGN] خطا در _process_lavayeh_send_sign_code: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_lavayeh_send_sign_code", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ثبت کد امضا
# ══════════════════════════════════════════════════════════════════════════════
async def _process_lavayeh_submit_sign(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    row_idx = data.get("row_idx", 0)
    code = data.get("code", "")

    from lavayeh_sign_handlers import (
        on_lavayeh_sign_submit_success,
        on_lavayeh_sign_submit_failure,
        on_lavayeh_sign_wrong_code,
        on_lavayeh_sign_sana_not_registered)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        from lavayeh_sign_scenario import submit_sign_code_for_person

        await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ثبت امضا برای کاربر {user_id}")
        result = await submit_sign_code_for_person(
            bot, user_id, row_idx, code
        )

        if result["success"]:
            await on_lavayeh_sign_submit_success(bot, user_id, row_idx, user_state)
            await bot.send_message(ADMIN_ID, f"✅ [SIGN] امضای لایحه کاربر {user_id} موفق (ردیف {row_idx}).")
        else:
            error = result.get("error", "")
            if "wrong_code" in error:
                await on_lavayeh_sign_wrong_code(bot, user_id, row_idx, user_state)
            elif "sana_not_registered" in error:
                await on_lavayeh_sign_sana_not_registered(bot, user_id, "امضای شخص در سامانه ثنا درج نشده است", user_state)
                await bot.send_message(ADMIN_ID, f"❌ [SIGN] امضا در ثنا ثبت نیست — کاربر {user_id}.")
            else:
                await on_lavayeh_sign_submit_failure(bot, user_id, user_state)

    except Exception as e:
        logging.error(f"[SIGN] خطا در _process_lavayeh_submit_sign: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_lavayeh_submit_sign", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_lavayeh_sign_submit_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش امضای دعوی اعتراضی — مستقل از لایحه
# ══════════════════════════════════════════════════════════════════════════════
async def _process_tn_send_sign_code(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    sign_menu_path = data.get("sign_menu_path")
    phase = data.get("phase", "navigate")

    from tajdid_nazar_handlers import (
        on_tn_sign_persons_loaded,
        on_tn_sign_code_sent_success,
        on_tn_sign_code_sent_failure)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        from lavayeh_sign_scenario import (
            navigate_to_sign_page,
            get_signable_persons,
            send_sign_code_for_person)

        if phase == "navigate":
            await bot.send_message(ADMIN_ID, f"🔄 [TN-SIGN] ناوبری به صفحه امضا برای کاربر {user_id}")
            nav_ok = await navigate_to_sign_page(bot, user_id, tracking_code, menu_path=sign_menu_path)

            if not nav_ok:
                await on_tn_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [TN-SIGN] ناوبری ناموفق برای کاربر {user_id}")
                return

            persons = await get_signable_persons(bot, user_id)
            await on_tn_sign_persons_loaded(bot, user_id, persons, user_state)

        elif phase == "send_code":
            target_row_indices = data.get("target_row_indices", [])
            await bot.send_message(ADMIN_ID, f"🔄 [TN-SIGN] ارسال کد امضا برای کاربر {user_id}")

            sign_info = runtime_state.pending_tn_sign.get(user_id, {})
            all_persons = sign_info.get("sign_persons", [])

            results = []
            for row_idx in target_row_indices:
                person = next((p for p in all_persons if p["idx"] == row_idx), None)
                person_name = person.get("name", f"شخص {row_idx + 1}") if person else f"شخص {row_idx + 1}"
                success = await send_sign_code_for_person(bot, user_id, row_idx, person_name, tracking_code)
                results.append({
                    "idx": row_idx,
                    "name": person_name,
                    "person_type": person.get("personType", "") if person else "",
                    "sent": success,
                })
                if row_idx != target_row_indices[-1]:
                    await asyncio.sleep(30)

            any_sent = any(r["sent"] for r in results)
            if any_sent:
                await on_tn_sign_code_sent_success(bot, user_id, results, user_state)
                await bot.send_message(ADMIN_ID, f"✅ [TN-SIGN] کد امضا برای کاربر {user_id} ارسال شد.")
            else:
                await on_tn_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [TN-SIGN] ارسال کد امضا برای کاربر {user_id} ناموفق.")

    except Exception as e:
        logging.error(f"[TN-SIGN] خطا در _process_tn_send_sign_code: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_tn_send_sign_code", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_tn_sign_code_sent_failure(bot, user_id, user_state)


async def _process_tn_submit_sign(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    row_idx = data.get("row_idx", 0)
    code = data.get("code", "")

    from tajdid_nazar_handlers import (
        on_tn_sign_submit_success,
        on_tn_sign_submit_failure,
        on_tn_sign_wrong_code,
        on_tn_sign_sana_not_registered)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        from lavayeh_sign_scenario import submit_sign_code_for_person

        await bot.send_message(ADMIN_ID, f"🔄 [TN-SIGN] ثبت امضا برای کاربر {user_id}")
        result = await submit_sign_code_for_person(
            bot, user_id, row_idx, code
        )

        if result["success"]:
            await on_tn_sign_submit_success(bot, user_id, row_idx, user_state)
            await bot.send_message(ADMIN_ID, f"✅ [TN-SIGN] امضای دعوی اعتراضی کاربر {user_id} موفق (ردیف {row_idx}).")
        else:
            error = result.get("error", "")
            if "wrong_code" in error:
                await on_tn_sign_wrong_code(bot, user_id, row_idx, user_state)
            elif "sana_not_registered" in error:
                await on_tn_sign_sana_not_registered(bot, user_id, "امضای شخص در سامانه ثنا درج نشده است", user_state)
                await bot.send_message(ADMIN_ID, f"❌ [TN-SIGN] امضا در ثنا ثبت نیست — کاربر {user_id}.")
            else:
                await on_tn_sign_submit_failure(bot, user_id, user_state)

    except Exception as e:
        logging.error(f"[TN-SIGN] خطا در _process_tn_submit_sign: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_tn_submit_sign", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_tn_sign_submit_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ارسال کد امضا اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
async def _process_ezhharnameh_send_sign_code(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    phase = data.get("phase", "navigate")

    # هندلرها بیرون از try ایمپورت می‌شوند تا در بلوک except در دسترس باشند
    from lavayeh_sign_handlers import (
        on_ezhhar_sign_persons_loaded,
        on_ezhhar_sign_code_sent_success,
        on_ezhhar_sign_code_sent_failure)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        # ایمپورت سناریو داخل try — اگر روزی ImportError داد، به‌جای کرش
        # browser_worker، به مسیر شکست نرم هدایت می‌شود.
        from ezhharnameh_sign_scenario import (
            navigate_to_ezhhar_sign_page,
            get_ezhhar_signable_persons,
            send_ezhhar_sign_code_for_person)

        if phase == "navigate":
            await bot.send_message(ADMIN_ID, f"🔄 [EZHHAR_SIGN] ناوبری به صفحه امضا اظهارنامه برای کاربر {user_id}")
            nav_ok = await navigate_to_ezhhar_sign_page(bot, user_id, tracking_code)
            if not nav_ok:
                await on_ezhhar_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR_SIGN] ناوبری ناموفق برای کاربر {user_id}")
                return

            persons = await get_ezhhar_signable_persons(bot, user_id)

            # لاگ جزئیات اشخاص برای دیباگ
            for p in persons:
                name_status = "✓" if p.get("name") else "✗ EMPTY"
                logging.info(f"[EZHHAR_SIGN] شخص ردیف {p.get('idx')}: name={name_status} '{p.get('name', '')}' type='{p.get('personType', '')}' canSend={p.get('canSend')} divVisible={p.get('divVisible')}")

            await on_ezhhar_sign_persons_loaded(bot, user_id, persons, user_state)
            names_summary = ", ".join([p.get('name', 'نامشخص') for p in persons])
            await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] لیست اشخاص اظهارنامه برای کاربر {user_id} دریافت شد ({len(persons)} نفر): {names_summary}")

        elif phase == "send_code":
            target_row_indices = data.get("target_row_indices", [])
            await bot.send_message(ADMIN_ID, f"🔄 [EZHHAR_SIGN] ارسال کد امضا اظهارنامه برای کاربر {user_id}")

            sign_info = runtime_state.pending_ezhhar_sign.get(user_id, {})
            all_persons = sign_info.get("sign_persons", [])

            results = []
            for row_idx in target_row_indices:
                person = next((p for p in all_persons if p["idx"] == row_idx), None)
                person_name = person.get("name", "") if person else ""
                if not person_name:
                    person_name = f"شخص {row_idx + 1}"
                    logging.warning(f"[EZHHAR_SIGN] نام خالی برای ردیف {row_idx} — از '{person_name}' استفاده می‌شود")
                success = await send_ezhhar_sign_code_for_person(bot, user_id, row_idx, person_name, tracking_code)
                results.append({"idx": row_idx, "name": person_name, "person_type": person.get("personType", "") if person else "", "sent": success})
                if row_idx != target_row_indices[-1]:
                    await asyncio.sleep(30)

            any_sent = any(r["sent"] for r in results)
            if any_sent:
                await on_ezhhar_sign_code_sent_success(bot, user_id, results, user_state)
                await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] کد امضا اظهارنامه برای کاربر {user_id} ارسال شد.")
            else:
                await on_ezhhar_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR_SIGN] ارسال کد امضا اظهارنامه برای کاربر {user_id} ناموفق.")

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در _process_ezhharnameh_send_sign_code: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_ezhharnameh_send_sign_code", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_ezhhar_sign_code_sent_failure(bot, user_id, user_state)


async def _process_ezhharnameh_submit_sign(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    row_idx = data.get("row_idx", 0)
    code = data.get("code", "")

    from lavayeh_sign_handlers import (
        on_ezhhar_sign_submit_success,
        on_ezhhar_sign_submit_failure,
        on_ezhhar_sign_wrong_code,
        on_ezhhar_sign_sana_not_registered)

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        from ezhharnameh_sign_scenario import submit_ezhhar_sign_code

        await bot.send_message(ADMIN_ID, f"🔄 [EZHHAR_SIGN] ثبت امضا اظهارنامه برای کاربر {user_id}")
        result = await submit_ezhhar_sign_code(bot, user_id, tracking_code, row_idx, code)

        if result["success"]:
            await on_ezhhar_sign_submit_success(bot, user_id, row_idx, user_state)
            await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] امضای اظهارنامه کاربر {user_id} موفق (ردیف {row_idx}).")
        else:
            error = result.get("error", "")
            if "wrong_code" in error:
                await on_ezhhar_sign_wrong_code(bot, user_id, row_idx, user_state)
            elif "sana_not_registered" in error:
                await on_ezhhar_sign_sana_not_registered(bot, user_id, "امضای شخص در سامانه ثنا درج نشده است", user_state)
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR_SIGN] امضا در ثنا ثبت نیست — کاربر {user_id}.")
            else:
                await on_ezhhar_sign_submit_failure(bot, user_id, user_state)

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در _process_ezhharnameh_submit_sign: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_process_ezhharnameh_submit_sign", error=e,
                             user_id=user_id, bill_no=tracking_code,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await on_ezhhar_sign_submit_failure(bot, user_id, user_state)


async def _attach_debug_listeners(sana_page):
    if DEBUG_LOG_REQUESTS:
        sana_page.on(
            "request",
            lambda req: logging.info(f"[DEBUG-REQ] {req.method} {req.url}")
            if "GetLegalPersonType" in req.url else None
        )
        sana_page.on(
            "framenavigated",
            lambda frame: logging.info(f"[DEBUG-NAV] {frame.url}")
            if frame == sana_page.main_frame else None
        )


async def _launch_fresh_browser(bot: Bot, wait_login: bool = True):
    """
    ساخت یک browser + context + page کاملاً تازه با استفاده از
    runtime_state.playwright_instance (که خودش فقط یک‌بار در ابتدای اجرای
    browser_worker ساخته می‌شود و زنده می‌ماند). این تابع هم در استارت اولیه
    و هم در بازیابی بعد از کرش/بسته‌شدن مرورگر استفاده می‌شود — بدون نیاز
    به ری‌استارت کل پروسه‌ی ربات.
    """
    browser = await runtime_state.playwright_instance.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    runtime_state.browser = browser
    runtime_state.browser_context = await browser.new_context(
        viewport={'width': 1366, 'height': 768}
    )
    runtime_state.sana_page = await runtime_state.browser_context.new_page()
    await _attach_debug_listeners(runtime_state.sana_page)

    if wait_login:
        await wait_for_manual_login(bot)


def _is_browser_dead() -> bool:
    """بررسی سریع (بدون I/O) اینکه آیا صفحه/مرورگر فعلی از بین رفته است."""
    page = runtime_state.sana_page
    if page is None:
        return True
    try:
        if page.is_closed():
            return True
    except Exception:
        return True
    browser = runtime_state.browser
    if browser is not None:
        try:
            if not browser.is_connected():
                return True
        except Exception:
            return True
    return False


_BROWSER_CLOSED_ERROR_HINTS = (
    "target page, context or browser has been closed",
    "target closed",
    "browser has been closed",
    "has been closed",
    "connection closed",
    "context or browser has been closed",
)


def _looks_like_browser_closed_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(hint in msg for hint in _BROWSER_CLOSED_ERROR_HINTS)


async def ensure_browser_alive(bot: Bot, notify_admin: bool = True) -> bool:
    """
    اگر مرورگر/صفحه‌ی فعلی بسته یا قطع شده باشد، بدون ری‌استارت ربات یک
    مرورگر تازه می‌سازد و منتظر لاگین دستی ادمین می‌ماند. اگر مرورگر سالم
    باشد، کاری انجام نمی‌دهد. برمی‌گرداند: True اگر مرورگر (چه از قبل، چه
    بعد از بازسازی) سالم و آماده باشد.
    """
    async with runtime_state.browser_relaunch_lock:
        if not _is_browser_dead():
            return True

        logging.warning("[WORKER] مرورگر بسته/قطع شده — تلاش برای بازسازی بدون ری‌استارت ربات...")
        if notify_admin:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    "⚠️ *مرورگر پلی‌رایت بسته شده بود.*\n"
                    "در حال باز کردن مرورگر جدید — لطفاً منتظر درخواست لاگین بمانید."
                )
            except Exception:
                pass

        # ── بستن ایمن باقیمانده‌ی مرورگر قبلی (اگر چیزی مانده باشد) ──
        try:
            old_browser = runtime_state.browser
            if old_browser is not None:
                try:
                    if old_browser.is_connected():
                        await old_browser.close()
                except Exception:
                    pass
        except Exception:
            pass

        runtime_state.sana_page = None
        runtime_state.browser_context = None
        runtime_state.browser = None

        try:
            await _launch_fresh_browser(bot, wait_login=True)
        except Exception as relaunch_err:
            logging.critical(f"[WORKER] بازسازی مرورگر ناموفق: {relaunch_err}", exc_info=True)
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🚨 بازسازی مرورگر ناموفق بود: {str(relaunch_err)[:300]}\n"
                    "لطفاً وضعیت VPS/پروکسی را بررسی کنید."
                )
            except Exception:
                pass
            return False

        logging.info("[WORKER] مرورگر با موفقیت بازسازی شد و آماده‌ی پردازش است.")
        if notify_admin:
            try:
                await bot.send_message(ADMIN_ID, "✅ مرورگر با موفقیت بازسازی شد. صف کارها ادامه می‌یابد.")
            except Exception:
                pass
        return True


async def _browser_watchdog(bot: Bot, interval_seconds: int = 20):
    """
    تسک پس‌زمینه‌ای که هر چند ثانیه یک‌بار بررسی می‌کند مرورگر زنده است یا
    نه — حتی وقتی صف کارها خالی است و هیچ تسکی در حال پردازش نیست. این‌طور
    اگر مرورگر بین دو تسک بسته شود، به‌محض رسیدن تسک بعدی معطل باز شدن
    دوباره‌ی مرورگر نمی‌ماند (چون از قبل بازسازی شده).
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            if _is_browser_dead():
                await ensure_browser_alive(bot)
        except Exception as e:
            logging.error(f"[WATCHDOG] خطا در بررسی سلامت مرورگر: {e}")


async def browser_worker(bot: Bot):
    runtime_state.playwright_instance = await async_playwright().start()
    try:
        await _launch_fresh_browser(bot, wait_login=True)

        # ── واچ‌داگ پس‌زمینه برای تشخیص/ترمیم خودکار بسته‌شدن مرورگر ──
        asyncio.create_task(_browser_watchdog(bot))

        # ── حلقه‌ی اصلی با حفاظت در برابر کرش ──
        while True:
            data = None
            try:
                data = await runtime_state.job_queue.get()

                # بررسی سلامت مرورگر قبل از پردازش؛ اگر بسته بود، بدون
                # ری‌استارت ربات دوباره بازش کن و بعد همین تسک را پردازش کن
                if not await ensure_browser_alive(bot):
                    # بازسازی ناموفق بود؛ تسک را به انتهای صف برگردان تا از
                    # بین نرود و بعداً (وقتی مرورگر درست شد) دوباره تلاش شود
                    await runtime_state.job_queue.put(data)
                    runtime_state.job_queue.task_done()
                    await asyncio.sleep(10)
                    continue

                try:
                    await process_task(data, bot)
                except Exception as task_err:
                    if _looks_like_browser_closed_error(task_err):
                        logging.warning(
                            f"[WORKER] مرورگر حین پردازش تسک بسته شد؛ بازسازی و تلاش مجدد: {task_err}"
                        )
                        if await ensure_browser_alive(bot):
                            # یک بار دیگر همین تسک را با مرورگر تازه امتحان کن
                            await process_task(data, bot)
                        else:
                            raise
                    else:
                        raise

                runtime_state.job_queue.task_done()
            except KeyboardInterrupt:
                logging.warning("[WORKER] KeyboardIntercept دریافت شد — خروج.")
                break
            except Exception as critical_err:
                logging.critical(f"[WORKER] خطای بحرانی در حلقه‌ی browser_worker: {critical_err}", exc_info=True)
                # ── گزارش کامل باگ (traceback + اسکرین‌شات + زمینه) به مدیر ──
                try:
                    from bug_reporter import report_bug
                    _d = data or {}
                    await report_bug(
                        bot,
                        where="browser_worker (حلقه‌ی اصلی)",
                        error=critical_err,
                        user_id=_d.get("user_id"),
                        bill_no=_d.get("tracking_code") or _d.get("bill_no"),
                        page=getattr(runtime_state, "sana_page", None),
                        context={k: _d.get(k) for k in ("task_type", "query_type", "phase", "doc_category") if _d.get(k) is not None},
                        level="critical")
                except Exception:
                    # اگر گزارش‌گر هم خطا داد، حداقل یک پیام کوتاه بفرست
                    try:
                        await bot.send_message(ADMIN_ID, f"🚨🚨 خطای بحرانی در browser_worker: {str(critical_err)[:300]}")
                    except Exception:
                        pass
                # ذخیره‌ی فوری حالت
                try:
                    from persistence import save_runtime_state
                    save_runtime_state()
                except Exception:
                    pass
                try:
                    runtime_state.job_queue.task_done()
                except ValueError:
                    pass
    finally:
        # این finally عملاً هرگز در حالت عادی اجرا نمی‌شود (حلقه‌ی بالا
        # فقط با KeyboardInterrupt می‌شکند)، ولی برای پاکسازی درست در
        # صورت خروج کامل پروسه، playwright را می‌بندیم.
        try:
            if runtime_state.playwright_instance is not None:
                await runtime_state.playwright_instance.stop()
        except Exception:
            pass
