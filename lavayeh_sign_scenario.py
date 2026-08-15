"""
سناریوی اخذ امضای الکترونیک لایحه در سامانه ثنا.

جریان کلی:
  ۱. ناوبری به بخش «ارایه و پیگیری لایحه» → انتخاب radio → جستجو با کد رهگیری
  ۲. صبر ۳۰ ثانیه تا بارگذاری صفحه جدید
  ۳. ورود به مرحله «اخذ امضای الکترونیک»
  ۴. یافتن جدول اشخاص قابل امضا
  ۵. ارسال کد موقت برای شخص انتخاب‌شده (actions.sendTempPassword)
  ۶. وارد کردن کد و کلیک «امضاء ثنا» (actions.getPersonDataSign)

ناوبری جدید (مطابق درخواست):
  - کلیک «ارایه و پیگیری لایحه»
  - انتخاب radio #rdbGetPetition (value=2)
  - وارد کردن کد رهگیری در #billNo
  - کلیک جستجو #btnGetJSSBill
  - صبر ۳۰ ثانیه
  - کلیک «اخذ امضای الکترونیک»
"""

import asyncio
import logging

from aiogram import Bot

import runtime_state
from browser_helpers import (
    check_and_handle_expiry,
    goto_url_with_retry,
    human_delay,
    resilient_sleep,
    safe_click_by_text,
    wait_for_angular_idle,
    wait_for_horizontal_loading_bar,
    click_sana_main_menu)
from config import ADMIN_ID


async def navigate_to_sign_page(
    bot: Bot,
    user_id: int,
    tracking_code: str) -> bool:
    """
    ناوبری به صفحه اخذ امضای لایحه.
    مسیر:
      ۱. رفتن به صفحه اصلی سامانه
      ۲. کلیک «ارایه و پیگیری لایحه»
      ۳. انتخاب radio #rdbGetPetition (value=2)
      ۴. وارد کردن کد رهگیری در #billNo
      ۵. کلیک جستجو #btnGetJSSBill
      ۶. صبر ۳۰ ثانیه
      ۷. کلیک «اخذ امضای الکترونیک»

    Returns True اگر صفحه جدول امضا ظاهر شد.
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        logging.error("[SIGN] sana_page is None")
        return False

    try:
        # ── ۱. رفتن به صفحه اصلی ────────────────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return False
        await human_delay(3.0, 5.0)

        # ── ۲. کلیک روی «ارایه و پیگیری لایحه» ─────────────────────────
        # نکته مهم: «اظهارنامه» عمداً exclude شده تا با آیتم منوی اظهارنامه
        # تداخل نکند. از click_sana_main_menu استفاده می‌شود که فقط داخل
        # a.list-group-item جستجو می‌کند و هرگز به div/span/li عمومی‌تر
        # escalate نمی‌شود (که می‌توانست باعث کلیک روی آیتم اشتباه شود).
        clicked = await click_sana_main_menu(
            sana_page, "ارایه و پیگیری لایحه", exclude_texts=["اظهارنامه"],
            timeout_sec=15, prefix="LAVAYEH_SIGN")
        if not clicked:
            logging.error("[SIGN] منوی «ارایه و پیگیری لایحه» پیدا نشد")
            return False
        await resilient_sleep(sana_page, 5, bot, user_id)

        # ── ۳. انتخاب radio #rdbGetPetition (value=2) ───────────────────
        await sana_page.evaluate('''() => {
            const radio = document.querySelector('#rdbGetPetition');
            if (radio) { radio.click(); return true; }
            // fallback: radio با value=2
            const radios = Array.from(document.querySelectorAll('input[type="radio"][name*="rdbSelectPetitionType"]'));
            const r = radios.find(r => r.value === "2");
            if (r) { r.click(); return true; }
            return false;
        }''')
        await asyncio.sleep(1)

        # ── ۴. وارد کردن کد رهگیری در #billNo ───────────────────────────
        await _fill_input(sana_page, "#billNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        # ── ۵. کلیک جستجو #btnGetJSSBill ─────────────────────────────────
        await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSBill');
            if (btn) { btn.click(); return; }
            // fallback
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')

        # ── ۶. صبر ۳۰ ثانیه تا بارگذاری صفحه جدید ─────────────────────
        await asyncio.sleep(30)

        # بستن هر پاپ‌آپ خطایی
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 2, bot, user_id)

        # ── ۷. کلیک «اخذ امضای الکترونیک» ──────────────────────────────
        # نکته مهم: اگر این کد رهگیری قبلاً در همین نشست به مرحله امضا رفته
        # باشد، سامانه معمولاً دیگر باکس «اخذ امضای الکترونیک» را نشان
        # نمی‌دهد و مستقیم جدول امضا نمایان است. در این حالت نباید سعی کنیم
        # آن را کلیک کنیم، وگرنه safe_click_by_text با NavigationResetError
        # کل تلاش را باطل می‌کند.
        table_already_visible = await _check_lavayeh_sign_table_exists(sana_page)
        if not table_already_visible:
            clicked_sign = await sana_page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
                if (t) {
                    const box = t.closest('.box');
                    if (box) { box.click(); return true; }
                }
                return false;
            }''')
            if not clicked_sign:
                try:
                    await safe_click_by_text(sana_page, "اخذ امضا", bot, user_id)
                except Exception as click_err:
                    if not await _check_lavayeh_sign_table_exists(sana_page):
                        raise click_err
                    logging.info(
                        "[SIGN] باکس «اخذ امضای الکترونیک» پیدا نشد، "
                        "ولی جدول امضا از قبل موجود بود — ادامه می‌دهیم."
                    )
            await resilient_sleep(sana_page, 6, bot, user_id)

        # ── ۸. بررسی جدول امضا — اگر نبود، ریلود و تلاش مجدد ─────────
        table_exists = await sana_page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            return rows.length > 0;
        }''')

        if not table_exists:
            logging.warning("[SIGN] جدول امضا ظاهر نشد — ریلود و تلاش مجدد")
            await sana_page.reload()
            await resilient_sleep(sana_page, 8, bot, user_id)
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # دوباره کلیک روی اخذ امضا
            clicked_sign2 = await sana_page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
                if (t) {
                    const box = t.closest('.box');
                    if (box) { box.click(); return true; }
                }
                return false;
            }''')
            if clicked_sign2:
                await resilient_sleep(sana_page, 6, bot, user_id)

        return True

    except Exception as e:
        logging.error(f"[SIGN] navigate_to_sign_page error: {e}")
        return False


async def get_signable_persons(
    bot: Bot,
    user_id: int) -> list:
    """
    اشخاص قابل امضا را از جدول استخراج می‌کند.
    اگر جدولی وجود نداشت، ناوبری مجدد انجام نمی‌دهد (فرض بر این است که
    صفحه قبلاً از طریق navigate_to_sign_page باز شده است).

    Returns:
        list of dicts: [{idx, name, person_type, canSend, divVisible}]
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return []

    try:
        persons_info = await sana_page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            return rows.map((tr, idx) => {
                // نام شخص — توجه: ستون «نوع اخذ امضاء» هم همین کلاس‌ها را دارد
                // و در DOM جلوتر از ستون نام قرار می‌گیرد، پس حتماً باید
                // ng-binding را هم شرط بگذاریم تا با آن اشتباه گرفته نشود.
                let nameTd = tr.querySelector(
                    'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle.ng-binding'
                );
                if (!nameTd) {
                    // fallback: همان کلاس‌ها ولی متنی که شامل «از طریق» نباشد
                    const candidates = tr.querySelectorAll(
                        'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle'
                    );
                    for (const c of candidates) {
                        const t = c.innerText.trim();
                        if (t && !t.includes("از طریق")) { nameTd = c; break; }
                    }
                }
                const name = nameTd ? nameTd.innerText.trim() : "";

                // نوع شخص (وکیل، نماینده، مدیرعامل، ...)
                const typeSpans = tr.querySelectorAll('span[ng-if*="PersonType"]');
                let personType = "";
                for (const sp of typeSpans) {
                    if (sp.getBoundingClientRect().width > 0) {
                        personType = sp.innerText.trim();
                    }
                }

                // اگر از span متن نگرفتیم، نوع شخص را از scope انگولار (کد عددی) بخوان
                if (!personType) {
                    try {
                        const scope = angular.element(tr).scope();
                        if (scope && scope.item) {
                            const pt = scope.item.PersonType || scope.item.JSSPersonType;
                            if (pt === 6) personType = "وکیل";
                            else if (pt === 3) personType = "نماینده";
                            else if (pt === 4) personType = "مدیرعامل";
                        }
                    } catch(e) {}
                }

                // آیا div ارسال کد نمایش دارد؟
                const sendDiv = tr.querySelector(
                    'div[ng-if*="!(item.NationalityCode"]'
                );
                const divVisible = sendDiv &&
                    window.getComputedStyle(sendDiv).display !== "none";

                // آیا دکمه ارسال کد فعال هست؟
                const sendBtn = tr.querySelector(
                    'button[ng-click*="sendTempPassword"]'
                );
                const canSend = divVisible && sendBtn && !sendBtn.disabled;

                return { idx, name, personType, canSend, divVisible };
            });
        }''')

        logging.info(f"[SIGN] persons_info: {persons_info}")
        return persons_info or []

    except Exception as e:
        logging.error(f"[SIGN] get_signable_persons error: {e}")
        return []


async def _check_lavayeh_sign_table_exists(page) -> bool:
    """بررسی وجود جدول امضا برای لایحه در صفحه فعلی"""
    return await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll(
            'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
        ));
        return rows.length > 0;
    }''')


async def send_sign_code_for_person(
    bot: Bot,
    user_id: int,
    row_idx: int,
    person_name: str,
    tracking_code: str = "") -> bool:
    """
    ارسال کد موقت برای یک ردیف مشخص از جدول امضا.
    حداکثر ۳ بار تلاش می‌کند.

    نکته مهم: چون یک صفحه مرورگر مشترک بین همه کاربران است، ممکن است بین
    فاز ناوبری و این فاز، تسک‌های کاربران دیگر صفحه را عوض کرده باشند —
    به همین دلیل ابتدا وجود جدول را بررسی و در صورت نیاز مجدداً ناوبری
    می‌کنیم.

    Returns True اگر کد ارسال شد (یا قبلاً ارسال شده بود).
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return False

    # ── بررسی اینکه آیا صفحه هنوز روی جدول صحیح لایحه است ──
    table_ok = await _check_lavayeh_sign_table_exists(sana_page)
    if not table_ok and tracking_code:
        logging.warning(
            f"[SIGN] صفحه قبل از ارسال کد، به‌روز نیست — ناوبری مجدد برای کاربر {user_id}"
        )
        nav_ok = await navigate_to_sign_page(bot, user_id, tracking_code)
        if not nav_ok:
            logging.error(f"[SIGN] ناوبری مجدد قبل از ارسال کد ناموفق — کاربر {user_id}")
            return False

    for attempt in range(3):
        clicked = await sana_page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const btn = rows[idx].querySelector('button[ng-click*="sendTempPassword"]');
            if (btn && !btn.disabled) {{ btn.click(); return true; }}
            return false;
        }}''', row_idx)

        if not clicked:
            logging.warning(f"[SIGN] دکمه ارسال کد برای ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

        # انتظار برای پاپ‌آپ
        popup_result = await _wait_for_popup_result(sana_page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(sana_page)
            logging.info(f"[SIGN] کد موقت برای ردیف {row_idx} ({person_name}) ارسال شد.")
            return True

        elif popup_result == "already_sent":
            await _close_any_popup(sana_page)
            logging.info(f"[SIGN] کد قبلاً ارسال شده برای ردیف {row_idx}")
            return True

        else:
            await _close_any_popup(sana_page)
            logging.warning(f"[SIGN] خطا در ارسال کد ردیف {row_idx} (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

    return False


async def submit_sign_code_for_person(
    bot: Bot,
    user_id: int,
    row_idx: int,
    code: str) -> dict:
    """
    کد را در فیلد وارد می‌کند و دکمه «امضاء ثنا» را می‌زند.
    حداکثر ۳ بار تلاش می‌کند.

    Returns:
        dict: {"success": bool, "error": str}
        error values: "wrong_code", "timeout", "error"
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return {"success": False, "error": "sana_page is None"}

    for attempt in range(3):
        # وارد کردن کد
        filled = await sana_page.evaluate(f'''(args) => {{
            const idx = args.idx;
            const code = args.code;
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const inp = rows[idx].querySelector('input[id^="txtTempPassword"]');
            if (!inp) return false;
            inp.value = code;
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
            // trigger angular ng-model
            const scope = angular.element(inp).scope();
            if (scope) {{
                scope.$apply(() => {{
                    const key = inp.getAttribute("ng-model");
                    if (key) {{
                        const parts = key.split(".");
                        let obj = scope;
                        for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
                        obj[parts[parts.length - 1]] = code;
                    }}
                }});
            }}
            return true;
        }}''', {"idx": row_idx, "code": code})

        if not filled:
            logging.warning(f"[SIGN] وارد کردن کد در ردیف {row_idx} ناموفق (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        await asyncio.sleep(1)

        # کلیک دکمه «امضاء ثنا»
        clicked = await sana_page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const btn = rows[idx].querySelector(
                'button[ng-click*="getPersonDataSign"]'
            );
            if (btn) {{
                btn.disabled = false;
                btn.click();
                return true;
            }}
            return false;
        }}''', row_idx)

        if not clicked:
            logging.warning(f"[SIGN] دکمه امضاء ثنا در ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        # انتظار برای نتیجه
        popup_result = await _wait_for_sign_popup(sana_page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(sana_page)
            logging.info(f"[SIGN] امضای ردیف {row_idx} موفق.")
            return {"success": True}
        elif popup_result == "wrong_code":
            await _close_any_popup(sana_page)
            logging.info(f"[SIGN] رمز موقت نادرست — ردیف {row_idx}")
            return {"success": False, "error": "wrong_code"}
        elif popup_result == "sana_not_registered":
            await _close_any_popup(sana_page)
            logging.warning(f"[SIGN] امضا در سامانه ثنا ثبت نشده — ردیف {row_idx}")
            return {"success": False, "error": "sana_not_registered"}
        else:
            await _close_any_popup(sana_page)
            logging.warning(f"[SIGN] امضای ردیف {row_idx} ناموفق: {popup_result} (تلاش {attempt+1})")

            # بازگشت به مرحله اخذ امضا
            clicked_sign = await sana_page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
                if (t) {
                    const box = t.closest('.box');
                    if (box) { box.click(); return true; }
                }
                return false;
            }''')
            if not clicked_sign and not await _check_lavayeh_sign_table_exists(sana_page):
                try:
                    await safe_click_by_text(sana_page, "اخذ امضا", bot, user_id)
                except Exception as click_err:
                    if not await _check_lavayeh_sign_table_exists(sana_page):
                        raise click_err
                    logging.info(
                        "[SIGN] retry: باکس «اخذ امضای الکترونیک» پیدا نشد، "
                        "ولی جدول امضا از قبل موجود بود — ادامه می‌دهیم."
                    )
            await asyncio.sleep(6)

    return {"success": False, "error": "max_attempts"}


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_input(page, selector: str, value: str):
    """پر کردن فیلد ورودی"""
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[SIGN] _fill_input({selector}) failed: {e}")


async def _close_any_popup(page) -> bool:
    """بستن هر پنجره پاپ‌آپ (موفق یا خطا)"""
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


async def _wait_for_popup_result(page, timeout_sec: int = 55) -> str:
    """
    منتظر می‌ماند تا پاپ‌آپ نتیجه ارسال کد ظاهر شود.
    Returns:
        "success"      — ارسال موفق
        "already_sent" — قبلاً ارسال شده
        "error"        — هر خطای دیگر
        "timeout"      — timeout
    """
    for _ in range(timeout_sec * 2):
        result = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const text = h2 ? h2.innerText.trim() : "";
            const successIcon = popup.querySelector('.sa-icon.sa-success');
            const errorIcon = popup.querySelector('.sa-icon.sa-error');
            const isSuccessVisible = successIcon &&
                window.getComputedStyle(successIcon).display !== "none";
            const isErrorVisible = errorIcon &&
                window.getComputedStyle(errorIcon).display !== "none";

            if (isSuccessVisible) {
                if (text.includes("ارسال شد")) return "success";
                return "success";
            }
            if (isErrorVisible) {
                if (text.includes("10 دقیقه") || text.includes("۱۰ دقیقه")) {
                    return "already_sent";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)

    return "timeout"


async def _wait_for_sign_popup(page, timeout_sec: int = 55) -> str:
    """
    منتظر پاپ‌آپ نتیجه امضا می‌ماند.
    Returns: "success" | "wrong_code" | "sana_not_registered" | "error" | "timeout"

    پیام‌های مورد انتظار:
      - موفق (آیکون سبز): "امضاء با موفقیت در صفحه چاپ درج گردید"
      - موفق (آیکون زرد/هشدار): "امضاء « name » در صفحه ی چاپ درج شده است"
      - خطا (آیکون قرمز): "خطای سرویس ثنا   : رمز موقت نادرست است"
      - امضا ثبت‌نشده در ثنا: "امضای شخص ... در سامانه ثنا درج نشده است"
    """
    for _ in range(timeout_sec * 2):
        result = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const text = h2 ? h2.innerText.trim() : "";
            const successIcon = popup.querySelector('.sa-icon.sa-success');
            const warningIcon = popup.querySelector('.sa-icon.sa-warning');
            const errorIcon = popup.querySelector('.sa-icon.sa-error');

            const isSuccessVisible = successIcon &&
                window.getComputedStyle(successIcon).display !== "none";
            const isWarningVisible = warningIcon &&
                window.getComputedStyle(warningIcon).display !== "none";
            const isErrorVisible = errorIcon &&
                window.getComputedStyle(errorIcon).display !== "none";

            // امضا در سامانه ثنا ثبت نشده — «امضای شخص ... در سامانه ثنا درج نشده است»
            // (این پیام هرگز در حالت موفق ظاهر نمی‌شود؛ صرف‌نظر از آیکون بررسی می‌شود)
            if (text.includes("در سامانه ثنا درج نشده")) return "sana_not_registered";

            // موفقیت اصلی — آیکون سبز
            if (isSuccessVisible) return "success";

            // هشدار ولی واقعاً موفق — "امضاء « name » در صفحه ی چاپ درج شده است"
            if (isWarningVisible && text.includes("درج شده")) return "success";

            // خطا — رمز موقت نادرست
            if (isErrorVisible) {
                if (text.includes("رمز موقت نادرست") || text.includes("نادرست")) {
                    return "wrong_code";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)
    return "timeout"
