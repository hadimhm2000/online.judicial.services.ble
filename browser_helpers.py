"""
توابع کمکی مرورگر: کلیک/تایپ ایمن، تشخیص و مدیریت انقضای نشست و باگ GetLegalPersonType،
خواب هوشمند، لود ایمن صفحه.
"""
import asyncio
import logging
import random

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from keyboards import admin_login_kb

# آدرسی که سامانه‌ی ثنا هنگام انقضای نشست کاربر را به آن ریدایرکت می‌کند.
# (SSO — صفحه‌ی جدید لاگین که با فرم قدیمی #txtUsername متفاوت است)
SESSION_LOGIN_REDIRECT_PREFIXES = [
    "https://iehraz2.adliran.ir/Login/Authenticate",
    "https://iehraz.adliran.ir/Login/Authenticate",
]


# پیام خطای کدملی اشتباه / عدم ثبت‌نام ثنا
NATIONAL_ID_ERROR_MSG = (
    "❌ *خطا در پردازش کدملی*\n\n"
    "کدملی وارد شده اشتباه است یا فرد در سامانه ثنا ثبت‌نام ندارد.\n\n"
    "لطفاً کدملی را بررسی کرده و در صورت اطمینان از صحت آن،\n"
    "اطمینان حاصل فرمایید که فرد در سامانه ثنا ثبت‌نام انجام داده است.\n\n"
    "فرآیند متوقف شد. لطفاً از ابتدا اقدام فرمایید."
)


class NationalIdError(Exception):
    """خطای کدملی اشتباه یا عدم ثبت‌نام ثنا — فرآیند باید متوقف شود."""
    pass


def is_login_redirect_url(url: str) -> bool:
    """آیا URL فعلی صفحه، ریدایرکت انقضای نشست به آدرس لاگین ثناست؟"""
    return bool(url) and any(url.startswith(p) for p in SESSION_LOGIN_REDIRECT_PREFIXES)


class NavigationResetError(Exception):
    """
    خطایی که وقتی رخ می‌ده که یک انحراف/گم‌شدگی در صفحه (مثل باگ GetLegalPersonType
    یا پیدا نشدن یک عنصر حتی بعد از صبر کافی) تشخیص داده شده و صفحه از قبل به یک
    نقطه‌ی امن (Offices/Index) navigate شده. گرفتن این خطا نباید دوباره go_back یا
    هر ناوبری دیگه‌ای انجام بده — فقط باید مستقیم به بالا raise بشه تا حلقه‌ی
    بیرونی سناریو، کل تسک رو از نو (از همون نقطه‌ی امن) شروع کنه.
    """
    pass


# ================= توابع شبه‌انسانی =================
async def human_delay(min_sec=1.5, max_sec=3.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def force_click_by_text(page, text):
    await page.evaluate(f'''() => {{
        const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
        for (let tag of tags) {{
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim() === "{text}");
            if (target) {{
                target.click();
                return;
            }}
        }}
        for (let tag of tags) {{
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim().includes("{text}"));
            if (target) {{
                target.click();
                return;
            }}
        }}
    }}''')

async def soft_click_if_exists(page, text):
    """کلیک اختیاری — فقط اگر عنصر موجود باشد"""
    exists = await page.evaluate('''(txt) => {
        const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
        for (let tag of tags) {
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
            if (target) {
                const rect = target.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
        }
        return false;
    }''', text)
    if exists:
        await force_click_by_text(page, text)
        await asyncio.sleep(1.5)
        logging.info(f"soft_click_if_exists: clicked '{text}'.")
    else:
        logging.info(f"soft_click_if_exists: '{text}' not present — skipping.")

async def human_type(page, locator_string, text):
    try:
        input_elem = page.locator(locator_string).first
        await input_elem.hover()
        await human_delay(0.5, 1.0)
        await input_elem.click()
        await input_elem.fill("")
        for char in text:
            await input_elem.type(char, delay=random.randint(100, 300))
        await human_delay(0.5, 1.0)
        await input_elem.blur()
        return True
    except Exception as e:
        logging.warning(f"human_type failed for selector '{locator_string}': {e}")
        return False

# ================= توابع ایمن و ضد اختلال =================

async def dismiss_expiry_popup(page) -> bool:
    """
    بستن پاپ‌آپ انقضا/اعلان نشست روی صفحه اصلی.

    پس از لاگین مجدد مدیر، این تابع دکمه بستن پاپ‌آپ را می‌زند تا صفحه
    از همان مرحله قبلی ادامه یابد (بدون ری‌لود یا ریست).

    انواع پاپ‌آپ پشتیبانی‌شده:
      1. مدال Bootstrap (.modal-dialog) با دکمه .close / "بستن"
      2. sweet-alert (.sweet-alert.showSweetAlert)
      3. هر عنصر visible با متن دقیق "بستن"
    """
    try:
        closed = await page.evaluate('''() => {
            // 1. Bootstrap modal close buttons
            const modalClose = document.querySelector(
                '.modal-dialog .close, .modal-dialog button.close, ' +
                '.modal-dialog button[data-dismiss="modal"], ' +
                '.modal.in .close, .modal.fade.in .close'
            );
            if (modalClose) {
                const rect = modalClose.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    modalClose.click();
                    return "modal_close";
                }
            }

            // 2. "بستن" button inside modal
            const modalDialog = document.querySelector('.modal-dialog, .modal.fade.in');
            if (modalDialog) {
                const tags = ['button', 'a', 'span'];
                for (const tag of tags) {
                    const elements = Array.from(modalDialog.querySelectorAll(tag));
                    const target = elements.find(el =>
                        el.innerText && el.innerText.trim() === "بستن"
                    );
                    if (target) {
                        const rect = target.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            target.click();
                            return "modal_bastan";
                        }
                    }
                }
            }

            // 3. sweet-alert
            let btn = document.querySelector(
                '.sweet-alert.showSweetAlert button.confirm, button.confirm'
            );
            if (btn) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) { btn.click(); return "sweet_alert"; }
            }

            // 4. Any visible element with text "بستن"
            const allTags = ['button', 'a', 'span', 'div'];
            for (const tag of allTags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el =>
                    el.innerText && el.innerText.trim() === "بستن"
                );
                if (target) {
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) { target.click(); return "global_bastan"; }
                }
            }
            return null;
        }''')
    except Exception as e:
        logging.warning(f"dismiss_expiry_popup: error while closing popup: {e}")
        return False

    if closed:
        logging.info(f"dismiss_expiry_popup: popup closed ({closed}).")
        await asyncio.sleep(1.5)
    else:
        logging.info("dismiss_expiry_popup: no popup found to close (possibly already closed).")
    return bool(closed)


async def handle_session_expired(bot: Bot, user_id: int, page=None):
    """
    مدیریت هوشمند انقضای نشست ثنا:
      ۱) به مدیر اطلاع می‌دهد و یک تب جدید برای لاگین مجدد باز می‌کند
         (تب اصلی/صفحه‌ی در حال کار — که پاپ‌آپ خطا رویش نمایش داده شده —
         دست‌نخورده باقی می‌ماند تا وضعیت/مرحله‌ی فعلی از دست نرود).
      ۲) منتظر می‌ماند تا مدیر دکمه‌ی تایید لاگین را در ربات بزند.
      ۳) تب لاگین را می‌بندد.
      ۴) روی همان صفحه‌ی اصلی (page)، دکمه‌ی «بستن» پاپ‌آپ خطا را می‌زند
         تا صفحه دقیقاً از همان‌جا که متوقف شده بود قابل ادامه باشد.
    """
    await bot.send_message(ADMIN_ID, "⚠️ *اعتبار نشست سامانه (ثنا) به اتمام رسیده است.*\nدر حال باز کردن تب جدید...")

    login_page = await runtime_state.browser_context.new_page()
    try:
        await login_page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=60000)
        runtime_state.login_event.clear()

        await bot.send_message(ADMIN_ID, "🔑 *لاگین مجدد ثنا:*\nپنجره ورود جدید باز شده است. لطفا لاگین کنید و دکمه زیر را بفشارید 👇", reply_markup=admin_login_kb)
        await runtime_state.login_event.wait()
    except Exception as e:
        logging.error(f"Error in handle_session_expired page navigation: {e}")
    finally:
        await login_page.close()

    # ── بازگرداندن صفحه‌ی اصلی به سامانه ─────────────────────────────────────
    if page is not None:
        if is_login_redirect_url(page.url):
            # صفحه به آدرس لاگین (iehraz2) ریدایرکت شده بود؛ باید صریحاً
            # به سامانه برگردد چون پاپ‌آپی برای بستن وجود ندارد.
            try:
                await page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=30000)
                await asyncio.sleep(2)
            except Exception as e:
                logging.warning(f"handle_session_expired: could not navigate main page back after iehraz2 redirect: {e}")
        else:
            # ── بستن پاپ‌آپ خطا روی صفحه‌ی اصلی تا همان مرحله بدون ریست ادامه پیدا کند ──
            try:
                await dismiss_expiry_popup(page)
            except Exception as e:
                logging.warning(f"handle_session_expired: could not dismiss popup on main page: {e}")

    await bot.send_message(ADMIN_ID, "✅ *نشست با موفقیت تمدید شد.* ادامه‌ی فرآیند از همان مرحله...")
    await asyncio.sleep(2)

async def detect_concurrent_login_popup(page) -> bool:
    """
    تشخیص پاپ‌آپ ورود همزمان (concurrent login) در سامانه ثنا.

    این پاپ‌آپ شامل:
      - آیکون خطا (sa-error با animateErrorIcon)
      - متن: «ورود به سامانه در صفحه یا رایانه ای دیگر»
      - متن: «اعتبار ورود قبلی ... منقضی شده است»

    ⭐ این تابع باید در تمام بخش‌ها فراخوانی شود:
      - لایحه (lavayeh_scenario / lavayeh_handlers)
      - اظهارنامه (ezhharnameh_scenario / ezhharnameh_handlers)
      - اعلام وکالت (ealam_vakalaht_scenario / ealam_vakalaht_handlers)
      - استعلامات و زیرمجموعه‌های بخش درخواست‌ها

    بازگشت: True اگر پاپ‌آپ ورود همزمان ظاهر شده باشد
    """
    is_concurrent = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;

        // بررسی آیکون خطا
        const errorIcon = popup.querySelector('.sa-icon.sa-error');
        if (!errorIcon) return false;
        if (window.getComputedStyle(errorIcon).display === 'none') return false;

        // بررسی متن پاپ‌آپ
        const popupText = popup.innerText || "";
        const isConcurrent =
            popupText.includes("رایانه ای دیگر") ||
            popupText.includes("رایانه ای ديگر") ||
            (popupText.includes("اعتبار ورود") && popupText.includes("منقضی")) ||
            popupText.includes("منقضي شده");

        return isConcurrent;
    }''')
    return bool(is_concurrent)


async def wait_for_angular_idle(page):
    """منتظر ماندن برای پایداری انگولار"""
    try:
        await page.evaluate('''() => {
            return new Promise((resolve) => {
                let attempts = 0;
                const check = () => {
                    attempts++;
                    if (attempts > 50) { resolve(); return; }
                    if (typeof angular !== 'undefined') {
                        const body = document.body || document.querySelector('[ng-app]');
                        if (body) {
                            try {
                                const injector = angular.element(body).injector();
                                if (injector) {
                                    const $http = injector.get('$http');
                                    if ($http && $http.pendingRequests && $http.pendingRequests.length > 0) {
                                        setTimeout(check, 100);
                                        return;
                                    }
                                }
                            } catch (e) { setTimeout(check, 100); return; }
                        }
                    }
                    resolve();
                };
                check();
            });
        }''')
    except Exception as e:
        logging.warning(f"Error waiting for angular idle: {e}")

async def check_and_handle_expiry(page, bot: Bot, user_id: int):
    """بررسی انقضای نشست

    پاپ‌آپ‌های شناسایی‌شده:
      - مدال «از ساعت ورود شما می‌گذرد» (اعلان تمدید نشست — Bootstrap modal)
      - مدال «ورود قبلی منقضی» / «رایانه ای دیگر» (سشن منقضی‌شده)
      - ریدایرکت به صفحه لاگین
      - انحراف GetLegalPersonType
    """
    if "GetLegalPersonType" in page.url:
        logging.warning("⚠️ انحراف به GetLegalPersonType شناسایی شد!")
        try:
            await page.goto("https://sakha2.adliran.ir/Offices/Index")
            await asyncio.sleep(4)
        except:
            pass
        raise NavigationResetError("GetLegalPersonType redirect occurred. Navigated to Offices/Index and restarting task...")

    # ── ریدایرکت به صفحه‌ی لاگین جدید ثنا (iehraz2) ────────────────────────
    if is_login_redirect_url(page.url):
        logging.warning(f"⚠️ ریدایرکت به صفحه لاگین ثنا (iehraz2) شناسایی شد! URL: {page.url}")
        await handle_session_expired(bot, user_id, page=page)
        return True

    is_expired = await page.evaluate('''() => {
        // ── ۱. بررسی مدال تمدید نشست: «X از ساعت ورود شما می‌گذرد» ──
        const modal = document.querySelector('.modal-dialog, .modal.fade.in, .modal-content');
        if (modal) {
            const modalText = modal.innerText || "";
            if (modalText.includes("از ساعت ورود شما می‌گذرد") ||
                modalText.includes("از ساعت ورود شما مي‌گذرد") ||
                modalText.includes("از ساعت ورود شما می‌گذرد") ||
                modalText.includes("اصل اولویت") ||
                modalText.includes("احراز هویت") ||
                modalText.includes("تمدید کنید") ||
                modalText.includes("تمديد کنيد")) {
                return "session_timeout_modal";
            }
        }

        // ── ۲. بررسی sweet-alert خطای سشن ──
        const sweetPopup = document.querySelector('.sweet-alert.showSweetAlert');
        if (sweetPopup) {
            const popupText = sweetPopup.innerText || "";
            if (popupText.includes("منقضی") || popupText.includes("منقضي") ||
                popupText.includes("رایانه ای دیگر") || popupText.includes("رایانه ای ديگر") ||
                popupText.includes("ورود قبلی") || popupText.includes("ورود قبلي") ||
                popupText.includes("اعتبار ورود") || popupText.includes("خطای دسترسی کاربر")) {
                return "session_sweet_alert";
            }
        }

        // ── ۳. بررسی متن کلی صفحه ──
        const text = document.body ? document.body.innerText : "";
        const hasExpiryText = text.includes("منقضی") || text.includes("منقضي") ||
                              text.includes("رایانه ای دیگر") || text.includes("رایانه ای ديگر") ||
                              text.includes("ورود قبلی") || text.includes("ورود قبلي") ||
                              text.includes("خطای دسترسی کاربر") || text.includes("نشست شما") ||
                              text.includes("اعتبار ورود") ||
                              text.includes("از ساعت ورود شما می‌گذرد") ||
                              text.includes("اصل اولویت و احراز هویت");

        // ── ۴. بررسی ریدایرکت به صفحه لاگین ──
        const isLoginPage = document.querySelector(
            '#txtUsername, #txtPassword, input[name="txtUsername"], input[placeholder*="کد ملی"]'
        ) !== null;

        if (hasExpiryText) return "session_body_text";
        if (isLoginPage) return "login_redirect";
        return null;
    }''')
    
    if is_expired:
        logging.warning(f"⚠️ انقضای/اعلان نشست شناسایی شد (نوع: {is_expired}) — شروع فرآیند لاگین مجدد مدیر...")
        await handle_session_expired(bot, user_id, page=page)
        # توجه: دیگر Exception raise نمی‌کنیم. برگرداندن True به فراخوان‌کننده
        # اجازه می‌دهد که همان مرحله (همان کلیک/تایپ/انتظار) را دوباره امتحان کند
        # به‌جای این‌که کل تسک از ابتدا ری‌استارت شود.
        return True

    return False

async def check_and_handle_load_error(page):
    """بررسی خطاهای لود صفحه"""
    has_load_error = await page.evaluate('''() => {
        const text = document.body ? document.body.innerText : "";
        const isErr = text.includes("تاخیر در اجرای سرویس") || text.includes("سرویس با خطا") || text.includes("خطا در فراخوانی");
        const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
        if (isErr && closeBtn) {
            const rect = closeBtn.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                closeBtn.click();
                return true;
            }
        }
        return false;
    }''')
    
    if has_load_error:
        logging.warning("Initial load error detected. Closing modal and reloading page...")
        await asyncio.sleep(3)
        await page.reload()
        await asyncio.sleep(5)
        return True
    return False


async def detect_national_id_error(page) -> bool:
    """تشخیص خطای «تاریخچه اولویت بندی شده ... در سیستم موجود نمی باشد».

    این خطا وقتی رخ می‌دهد که کدملی وارد شده اشتباه است یا فرد در ثنا ثبت‌نام ندارد.
    باید باعث توقف فوری فرآیند و اطلاع‌رسانی به کاربر شود.
    """
    try:
        error_text = await page.evaluate('''() => {
            // ۱. بررسی sweet-alert popup
            const sweet = document.querySelector('.sweet-alert.showSweetAlert');
            if (sweet) {
                const t = sweet.innerText || "";
                if (t.includes("تاریخچه اولویت") || t.includes("تاريخچه اولويت")) return t;
            }
            // ۲. بررسی مدال
            const modal = document.querySelector('.modal-dialog, .modal-content');
            if (modal) {
                const t = modal.innerText || "";
                if (t.includes("تاریخچه اولویت") || t.includes("تاريخچه اولويت")) return t;
            }
            // ۳. بررسی متن کلی صفحه
            const body = document.body ? document.body.innerText : "";
            if (body.includes("تاریخچه اولویت") || body.includes("تاريخچه اولويت")) return body;
            return null;
        }''')
        if error_text:
            logging.error(f"[NATIONAL_ID_ERROR] خطای کدملی/ثنا شناسایی شد: {error_text[:200]}")
            return True
        return False
    except Exception as e:
        logging.warning(f"detect_national_id_error: error: {e}")
        return False


async def check_national_id_error_or_continue(page, bot: Bot, user_id: int):
    """بررسی خطای کدملی/ثنا + انقضای نشست.

    اگر خطای کدملی تشخیص داده شود → NationalIdError raise می‌کند (فرآیند متوقف).
    اگر نشست منقضی شده → handle می‌شود.
    """
    # ابتدا چک خطای کدملی
    if await detect_national_id_error(page):
        try:
            await bot.send_message(user_id, NATIONAL_ID_ERROR_MSG)
        except Exception:
            pass
        raise NationalIdError("خطای کدملی یا عدم ثبت‌نام ثنا")

    # سپس چک انقضای نشست
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    return had_expiry


async def resilient_sleep(page, seconds, bot: Bot, user_id: int):
    """خواب هوشمند با چک انقضا"""
    for _ in range(int(seconds)):
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info("Session expiry intercepted during sleep.")
            return True
        await asyncio.sleep(1)
    return False

async def wait_for_horizontal_loading_bar(page, bot: Bot, user_id: int, timeout: int = 60):
    """
    منتظر ماندن تا نوار لودینگ افقی بالای صفحه ناپدید شود.
    این تابع پس از هر عملیات استعلام/ثبت موقت/جستجو فراخوانی شود.

    مقدار بازگشتی (نکته‌ی مهم: قبلاً این تابع فقط True/False برمی‌گرداند و
    متن واقعی خطای سامانه برای همیشه گم می‌شد — کد فراخوان‌کننده در
    lavayeh_scenario.py انتظار متن واقعی خطا یا رشته‌ی "SESSION_EXPIRED" را
    دارد، نه یک بولین؛ اگر بولین True برگردد، پیام ««True»» به کاربر نشان
    داده می‌شود که کاملاً بی‌معنی است):
      - اگر session منقضی شده باشد → رشته‌ی "SESSION_EXPIRED" را برمی‌گرداند.
      - اگر خطای واقعی سامانه (پاپ‌آپ/متن صفحه) ظاهر شود → متن دقیق خطا را
        به‌صورت رشته برمی‌گرداند.
      - اگر بدون خطا تمام شود → False برمی‌گرداند.
    """
    had_error = False
    error_text_result = None
    try:
        await page.evaluate('''(timeout) => {
            return new Promise((resolve) => {
                let checks = 0;
                const maxChecks = timeout;
                const interval = setInterval(() => {
                    checks++;
                    if (checks >= maxChecks) {
                        clearInterval(interval);
                        resolve(false);
                        return;
                    }
                    // بررسی نوار لودینگ افقی بالای صفحه
                    const loaders = document.querySelectorAll(
                        '.blockUI, .blockOverlay, .loading-mask, .ajax-loader, ' +
                        '.spinner, .loading, #loading, .progress-bar, ' +
                        '.nprogress, .bar-loading, [ng-show*="loading"]'
                    );
                    let anyVisible = false;
                    for (const loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") {
                            anyVisible = true;
                            break;
                        }
                    }
                    // همچنین بررسی Angular pending requests
                    if (!anyVisible && typeof angular !== 'undefined') {
                        try {
                            const body = document.body || document.querySelector('[ng-app]');
                            if (body) {
                                const injector = angular.element(body).injector();
                                if (injector) {
                                    const $http = injector.get('$http');
                                    if ($http && $http.pendingRequests && $http.pendingRequests.length > 0) {
                                        anyVisible = true;
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    if (!anyVisible) {
                        clearInterval(interval);
                        resolve(false);
                    }
                }, 500);
            });
        }''', timeout)
    except Exception as e:
        logging.warning(f"wait_for_horizontal_loading_bar: error while waiting: {e}")

    await asyncio.sleep(1)

    # بررسی session expiry بعد از لودینگ
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        had_error = True

    if not had_error:
        # بررسی آیا خطایی در صفحه ظاهر شده (پاپ‌آپ یا متن خطا)
        page_error = await page.evaluate('''() => {
            const text = document.body ? document.body.innerText : "";

            // 1. Bootstrap modal session timeout
            const modal = document.querySelector('.modal-dialog, .modal.fade.in, .modal-content');
            if (modal) {
                const modalText = modal.innerText || "";
                if (modalText.includes("از ساعت ورود شما می‌گذرد") ||
                    modalText.includes("اصل اولویت") ||
                    modalText.includes("احراز هویت")) {
                    return "session_expired";
                }
            }

            // 2. sweet-alert error/session popup — متن تمیز را فقط از h2+p
            // می‌سازیم (نه کل innerText که شامل متن دکمه «بستن» هم می‌شود)
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                const h2 = popup.querySelector('h2');
                const p = popup.querySelector('p');
                const cleanMsg = [h2 ? h2.innerText.trim() : '', p ? p.innerText.trim() : '']
                    .filter(Boolean).join(' - ').trim();
                const popupText = cleanMsg || (popup.innerText || "").trim();
                if (popupText.includes("منقضی") || popupText.includes("منقضی") ||
                    popupText.includes("رایانه ای دیگر") || popupText.includes("رایانه ای دیگر") ||
                    popupText.includes("اعتبار ورود") || popupText.includes("ورود قبلی") ||
                    popupText.includes("ورود قبلی")) {
                    return "session_expired";
                }
                const errorIcon = popup.querySelector('.sa-icon.sa-error');
                if (errorIcon && window.getComputedStyle(errorIcon).display !== 'none') {
                    return popupText || "خطای نامشخص در سامانه";
                }
            }

            // 3. Page body load errors
            if (text.includes("تاخیر در اجرای سرویس") || text.includes("سرویس با خطا") ||
                text.includes("خطا در فراخوانی") || text.includes("خطای سرور")) {
                return text.substring(0, 200);
            }
            return null;
        }''')

        if page_error == "session_expired":
            logging.warning("wait_for_horizontal_loading_bar: session expiry detected in popup after loading")
            # بستن پاپ‌آپ
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(1)
            await handle_session_expired(bot, user_id, page=page)
            had_error = True
            error_text_result = "SESSION_EXPIRED"
        elif page_error:
            logging.warning(f"wait_for_horizontal_loading_bar: page error after loading: {page_error}")
            # بستن پاپ‌آپ خطا
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(1)
            had_error = True
            error_text_result = page_error

    if had_error:
        return error_text_result
    return False


async def goto_url_with_retry(page, url, bot: Bot, user_id: int, timeout=30000):
    """لود ایمن صفحه با retry"""
    for load_attempt in range(3):
        try:
            await page.goto(url, timeout=timeout)
            await page.wait_for_load_state("load", timeout=timeout)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                # نشست تمدید شد؛ همین URL را دوباره لود می‌کنیم (بدون کم شدن از
                # بودجه‌ی retry، چون این یک شکست واقعی نبود بلکه یک وقفه بود)
                await page.goto(url, timeout=timeout)
                await page.wait_for_load_state("load", timeout=timeout)
            had_error = await check_and_handle_load_error(page)
            if had_error:
                continue
            return True
        except PlaywrightTimeoutError:
            logging.warning(f"Timeout loading page {url} (Attempt {load_attempt+1}/3)")
            await asyncio.sleep(3)
        except Exception as e:
            logging.error(f"Error loading page {url} (Attempt {load_attempt+1}/3): {e}")
            await asyncio.sleep(3)
            
    await bot.send_message(user_id, "⚠️ متاسفانه ارتباط با سامانه قضایی در حال حاضر با اختلال مواجه است.")
    return False

async def safe_click_by_text(page, text, bot: Bot, user_id: int, retry_count=3):
    """کلیک ایمن روی دکمه‌ها"""
    for attempt in range(retry_count):
        try:
            for _ in range(60):
                is_loading = await page.evaluate('''() => {
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading');
                    for (let loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") {
                            return true;
                        }
                    }
                    return false;
                }''')
                if not is_loading:
                    break
                await asyncio.sleep(0.5)

            await wait_for_angular_idle(page)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                # نشست تمدید و پاپ‌آپ بسته شد؛ همین مرحله (پیدا کردن/کلیک '{text}')
                # را از نو امتحان می‌کنیم — نه این‌که کل تسک ری‌استارت شود.
                logging.info(f"safe_click_by_text: session renewed mid-step for '{text}', retrying this step.")
                continue

            btn_exists = False
            for _grace in range(6):
                btn_exists = await page.evaluate(''' (txt) => {
                    const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
                    for (let tag of tags) {
                        const elements = Array.from(document.querySelectorAll(tag));
                        const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
                        if (target) return true;
                    }
                    return false;
                } ''', text)
                if btn_exists:
                    break
                # ممکنه آنگولار هنوز رندر نکرده باشه؛ قبل از اینکه "پیدا نشد" رو
                # قطعی بدونیم و go_back بزنیم (که خودش ریسک پرت‌شدن به یک صفحه‌ی
                # نامرتبط توی تاریخچه رو داره)، یکم بیشتر صبر می‌کنیم.
                await asyncio.sleep(1)

            if not btn_exists:
                logging.warning(
                    f"Option '{text}' not found even after grace period. "
                    f"go_back() is unreliable on this site (lands on stale/unrelated "
                    f"history entries like GetLegalPersonType) — resetting to Offices/Index instead."
                )
                try:
                    await page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass
                raise NavigationResetError(
                    f"'{text}' not found on page. Navigated to Offices/Index and restarting task..."
                )

            await force_click_by_text(page, text)
            await asyncio.sleep(2.5)
            
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info(f"safe_click_by_text: session renewed right after clicking '{text}', retrying this step.")
                continue
            
            error_details = await page.evaluate('''() => {
                const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
                if (closeBtn) {
                    const rect = closeBtn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                        closeBtn.click();
                        return { found: true };
                    }
                }
                const hasAlert = document.querySelector('.sweet-alert.showSweetAlert, .alert-danger, .error') !== null;
                return { found: false, hasAlert: hasAlert };
            }''')
            
            if error_details['found']:
                logging.warning(f"Error dialog detected on clicking '{text}'. Retrying...")
                await asyncio.sleep(3)
                continue
                
            if error_details['hasAlert']:
                logging.warning("Error alert visible. Going back one page...")
                await page.go_back()
                await asyncio.sleep(5)
                continue
            
            return True
            
        except Exception as e:
            if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                # این خطاها خودشون قبلاً ناوبری ریکاوری (goto) رو انجام داده‌ن؛
                # یک go_back اضافه دقیقاً همزمان با اون goto رقابت می‌کنه و باعث قطع
                # ارتباط درایور با کروم می‌شه. باید فوراً raise بشه تا حلقه‌ی
                # بیرونی (در lavayeh_scenario) کل تسک رو از Offices/Index ریستارت کنه.
                raise e
            logging.error(f"Error in safe_click_by_text '{text}' (Attempt {attempt+1}/{retry_count}): {e}")
            try:
                await page.go_back()
                await asyncio.sleep(5)
            except:
                pass
            await asyncio.sleep(2)
            
    raise Exception(f"Failed to click '{text}' after multiple retries.")

async def safe_type(page, selector, text, bot: Bot, user_id: int, retry_count=3):
    """تایپ ایمن اطلاعات داخل اینپوت‌ها"""
    for attempt in range(retry_count):
        try:
            for _ in range(60):
                is_loading = await page.evaluate('''() => {
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading');
                    for (let loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") {
                            return true;
                        }
                    }
                    return false;
                }''')
                if not is_loading:
                    break
                await asyncio.sleep(0.5)

            await wait_for_angular_idle(page)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info(f"safe_type: session renewed mid-step for '{selector}', retrying this step.")
                continue

            elem_exists = False
            for _grace in range(6):
                elem_exists = await page.locator(selector).count() > 0
                if elem_exists:
                    break
                await asyncio.sleep(1)

            if not elem_exists:
                logging.warning(
                    f"Selector '{selector}' not found even after grace period. "
                    f"go_back() is unreliable on this site — resetting to Offices/Index instead."
                )
                try:
                    await page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass
                raise NavigationResetError(
                    f"Selector '{selector}' not found. Navigated to Offices/Index and restarting task..."
                )

            success = await human_type(page, selector, text)
            if success:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    logging.info(f"safe_type: session renewed right after typing into '{selector}', retrying this step.")
                    continue

                error_details = await page.evaluate('''() => {
                    const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
                    if (closeBtn) {
                        const rect = closeBtn.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                            closeBtn.click();
                            return { found: true };
                        }
                    }
                    const hasAlert = document.querySelector('.sweet-alert.showSweetAlert, .alert-danger, .error') !== null;
                    return { found: false, hasAlert: hasAlert };
                }''')
                
                if error_details['found']:
                    await asyncio.sleep(3)
                    continue
                    
                if error_details['hasAlert']:
                    await page.go_back()
                    await asyncio.sleep(5)
                    continue
                    
                return True
            await asyncio.sleep(2)
        except Exception as e:
            if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                raise e
            logging.error(f"Error safe_typing in '{selector}' (Attempt {attempt+1}/{retry_count}): {e}")
            try:
                await page.go_back()
                await asyncio.sleep(5)
            except:
                pass
            await asyncio.sleep(2)
            
    raise Exception(f"Failed to type in '{selector}' after multiple retries.")


# ══════════════════════════════════════════════════════════════════════════════
# کلیک ایمن روی آیتم‌های منوی اصلی سامانه (a.list-group-item)
# ══════════════════════════════════════════════════════════════════════════════
async def click_sana_main_menu(
    page,
    text: str,
    exclude_texts: list = None,
    timeout_sec: int = 15,
    prefix: str = "MENU") -> bool:
    """
    کلیک روی آیتم منوی اصلی سامانه (تگ <a class="list-group-item">).

    ویژگی‌ها:
      - فقط داخل a.list-group-item جستجو می‌کند (نه div/span/li عمومی‌تر)
      - آیتم‌هایی که متن exclude_texts را شامل شوند را نادیده می‌گیرد
      - اگر چند لینک هم‌زمان مطابقت داشتند، کوتاه‌ترین (دقیق‌ترین) را انتخاب می‌کند
      - تا timeout_sec ثانیه صبر می‌کند (برای رندر آنگولار)

    Returns:
        True اگر کلیک موفق بود، False در غیر این صورت.
    """
    if exclude_texts is None:
        exclude_texts = []

    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        result = await page.evaluate('''(args) => {
            const text = args.text;
            const excludes = args.excludes;
            const links = Array.from(document.querySelectorAll('a.list-group-item'));
            let candidates = links.filter(a => {
                const t = (a.innerText || "").trim();
                if (!t.includes(text)) return false;
                for (const ex of excludes) {
                    if (t.includes(ex)) return false;
                }
                // فقط آیتم‌های قابل مشاهده
                const rect = a.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                return true;
            });
            if (candidates.length === 0) return null;
            // کوتاه‌ترین متن = دقیق‌ترین تطبیق
            candidates.sort((a, b) => {
                return (a.innerText || "").trim().length - (b.innerText || "").trim().length;
            });
            candidates[0].click();
            return (candidates[0].innerText || "").trim();
        }''', {"text": text, "excludes": exclude_texts})

        if result:
            logging.info(f"[{prefix}] کلیک روی منو: '{result}'")
            return True

        await asyncio.sleep(1)

    logging.warning(f"[{prefix}] آیتم منوی '{text}' پیدا نشد (timeout={timeout_sec}s")
    return False

