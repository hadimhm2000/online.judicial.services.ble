# -*- coding: utf-8 -*-
"""سناریوی اخذ امضای الکترونیک اظهارنامه در سامانه ثنا.

جریان کلی (رویکرد دو فازی مشابه لایحه):

فاز ۱ (ناوبری):
  ۱. رفتن به صفحه اصلی سامانه
  ۲. کلیک «ارایه و پیگیری اظهارنامه» (#menu12Container)
  ۳. بررسی صحت صفحه — مطمئن شدن #txtPetitionNo وجود دارد
  ۴. وارد کردن کد رهگیری در #txtPetitionNo
  ۵. کلیک جستجو #btnGetJSSPetition
  ۶. بررسی پاپ‌آپ بازیابی — اگر غیر از «بازیابی اظهارنامه با موفقیت» بود → ریلود
  ۷. ورود به مرحله «اخذ امضای الکترونیک»
  ۸. صبر و بررسی جدول اشخاص قابل امضا

فاز ۲ (ارسال کد):
  ارسال کد موقت برای شخص انتخاب‌شده

فاز ۳ (ثبت کد):
  ناوبری مجدد به صفحه امضا
  وارد کردن کد در فیلد
  کلیک امضای ثنا
  بررسی نتیجه

نکته مهم: ناوبری بدون radio button انجام می‌شود — مستقیم فیلد و جستجو.
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# فاز ۱ — ناوبری به صفحه امضا و دریافت لیست اشخاص
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _click_ezhhar_menu(page) -> bool:
    """
    کلیک روی منوی «ارایه و پیگیری اظهارنامه».

    از click_sana_main_menu استفاده می‌کند که:
      - فقط داخل a.list-group-item جستجو می‌کند (نه در div/span/li عمومی‌تر
        که چند لینک را با هم دربر می‌گیرند و می‌توانند باعث کلیک روی آیتم
        اشتباه شوند — مثلاً لایحه به‌جای اظهارنامه)
      - «لایحه» را صریحاً exclude می‌کند
      - اگر چند لینک هم‌زمان مطابقت داشتند، کوتاه‌ترین (دقیق‌ترین) را انتخاب می‌کند

    توجه: دیگر از #menu12Container استفاده نمی‌شود — آن آیدی بر اساس ترتیب
    پویای منو در هر حساب تعیین می‌شود و می‌تواند در حساب‌های مختلف به آیتم
    دیگری (مثلاً لایحه) اشاره کند.
    """
    return await click_sana_main_menu(
        page, "ارایه و پیگیری اظهارنامه", exclude_texts=["لایحه"],
        timeout_sec=15, prefix="EZHHAR_SIGN")


async def _verify_ezhhar_page_loaded(page) -> bool:
    """
    بررسی می‌کند که آیا صفحه اظهارنامه بارگذاری شده است.
    نشانه‌ها:
      - #txtPetitionNo وجود دارد
      - #btnGetJSSPetition وجود دارد
      - #billNo (فیلد لایحه) وجود ندارد
    """
    result = await page.evaluate('''() => {
        const petitionInput = document.querySelector('#txtPetitionNo');
        const petitionBtn = document.querySelector('#btnGetJSSPetition');
        const billInput = document.querySelector('#billNo');
        return {
            hasPetitionNo: !!petitionInput,
            hasPetitionBtn: !!petitionBtn,
            hasBillNo: !!billInput,
            petitionVisible: petitionInput ? (petitionInput.offsetParent !== null || window.getComputedStyle(petitionInput).display !== 'none') : false,
        };
    }''')
    logging.info(f"[EZHHAR_SIGN] verify page: {result}")
    return result.get("hasPetitionNo", False) and result.get("hasPetitionBtn", False) and not result.get("hasBillNo", False)


async def navigate_to_ezhhar_sign_page(
    bot: Bot,
    user_id: int,
    tracking_code: str) -> bool:
    """
    ناوبری به صفحه اخذ امضای اظهارنامه.
    مسیر:
      ۱. رفتن به صفحه اصلی سامانه
      ۲. کلیک «ارایه و پیگیری اظهارنامه» (#menu12Container)
      ۳. بررسی صحت صفحه (اطمینان از #txtPetitionNo)
      ۴. وارد کردن کد رهگیری در #txtPetitionNo
      ۵. کلیک جستجو #btnGetJSSPetition
      ۶. بررسی پاپ‌آپ بازیابی — اگر غیر موفق بود → ریلود و تکرار
      ۷. کلیک «اخذ امضای الکترونیک»
      ۸. بررسی جدول اشخاص (با صبر و تلاش مجدد)

    Returns True اگر صفحه جدول امضا ظاهر شد.
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        logging.error("[EZHHAR_SIGN] sana_page is None")
        return False

    for nav_attempt in range(3):
        try:
            # ── ۱. رفتن به صفحه اصلی ───────────────────────────────────────
            ok = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not ok:
                continue
            await human_delay(3.0, 5.0)

            # ── ۲. کلیک روی «ارایه و پیگیری اظهارنامه» ────────────────────────
            clicked = await _click_ezhhar_menu(sana_page)
            if not clicked:
                # fallback: کلیک با متن دقیق (شامل «اظهارنامه»، بدون «لایحه»).
                # _verify_ezhhar_page_loaded پایین‌تر تضمین می‌کند به بخش درست رسیده‌ایم.
                logging.warning(f"[EZHHAR_SIGN] منو اظهارنامه با روش اصلی پیدا نشد (تلاش {nav_attempt+1}) — fallback با متن")
                try:
                    clicked = await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
                except Exception as menu_err:
                    logging.warning(f"[EZHHAR_SIGN] fallback متن منو اظهارنامه ناموفق: {menu_err}")
                    clicked = False
            if not clicked:
                logging.warning(f"[EZHHAR_SIGN] منو اظهارنامه پیدا نشد (تلاش {nav_attempt+1}) — تلاش مجدد ناوبری")
                continue
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. بررسی صحت صفحه — مطمئن شدن در بخش اظهارنامه هستیم ──────
            page_ok = await _verify_ezhhar_page_loaded(sana_page)
            if not page_ok:
                logging.warning(f"[EZHHAR_SIGN] صفحه اظهارنامه بارگذاری نشد — احتمالاً در بخش اشتباه هستیم (تلاش {nav_attempt+1})")
                # تلاش مجدد: دوباره به صفحه اصلی برگردیم
                await goto_url_with_retry(
                    sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
                )
                await human_delay(2.0, 3.0)
                continue

            await wait_for_angular_idle(sana_page)

            # ── ۴. وارد کردن کد رهگیری در #txtPetitionNo ───────────────
            fill_ok = await _fill_input(sana_page, "#txtPetitionNo", tracking_code)
            if not fill_ok:
                logging.warning(f"[EZHHAR_SIGN] فیلد #txtPetitionNo پر نشد (تلاش {nav_attempt+1})")
                continue
            await resilient_sleep(sana_page, 1, bot, user_id)

            # ── ۵. کلیک جستجو #btnGetJSSPetition ─────────────────────────────
            # فقط دکمه مخصوص اظهارنامه — بدون fallback به دکمه عمومی
            search_clicked = await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnGetJSSPetition');
                if (btn) { btn.click(); return true; }
                return false;
            }''')
            if not search_clicked:
                logging.warning(f"[EZHHAR_SIGN] دکمه #btnGetJSSPetition پیدا نشد (تلاش {nav_attempt+1})")
                continue

            # صبر اولیه
            await asyncio.sleep(3)

            # منتظر لودینگ
            await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

            # بستن هر پاپ‌آپ خطایی
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # ── ۶. بررسی پاپ‌آپ تایید بازیابی ───────────────────────────────
            recovery_ok = await _check_recovery_popup(sana_page, bot, user_id)
            if not recovery_ok:
                logging.warning("[EZHHAR_SIGN] پاپ‌آپ بازیابی تایید نشد — ریلود")
                await sana_page.reload()
                await resilient_sleep(sana_page, 8, bot, user_id)
                await _close_any_popup(sana_page)
                await resilient_sleep(sana_page, 3, bot, user_id)

            # ── ۷. ورود به مرحله «اخذ امضای الکترونیک» ─────────────────────
            # نکته مهم: اگر این کد رهگیری قبلاً در همین نشست به مرحله امضا
            # رفته باشد، سامانه معمولاً دیگر باکس «اخذ امضای الکترونیک» را
            # نشان نمی‌دهد و مستقیم جدول امضا نمایان است. در این حالت باید
            # این مرحله را رد کنیم؛ در غیر این صورت safe_click_by_text با
            # NavigationResetError کل تلاش را باطل می‌کند.
            table_already_visible = await _check_sign_table_exists(sana_page)
            if not table_already_visible:
                clicked_sign = await _click_sign_section(sana_page)
                if not clicked_sign:
                    try:
                        await safe_click_by_text(sana_page, "اخذ امضا", bot, user_id)
                    except Exception as click_err:
                        # ممکن است در همین لحظه جدول ظاهر شده باشد؛ قبل از
                        # اینکه خطا را قطعی بدانیم، یک‌بار دیگر چک می‌کنیم.
                        if not await _check_sign_table_exists(sana_page):
                            raise click_err
                        logging.info(
                            "[EZHHAR_SIGN] باکس «اخذ امضای الکترونیک» پیدا نشد، "
                            "ولی جدول امضا از قبل موجود بود — ادامه می‌دهیم."
                        )
                await resilient_sleep(sana_page, 6, bot, user_id)

            # ── ۸. بررسی جدول — اگر نبود، ریلود و تلاش مجدد ─────────────
            table_exists = await _check_sign_table_exists(sana_page)

            if not table_exists:
                logging.warning("[EZHHAR_SIGN] جدول امضا ظاهر نشد — ریلود و تلاش مجدد")
                await sana_page.reload()
                await resilient_sleep(sana_page, 8, bot, user_id)
                await _close_any_popup(sana_page)
                await resilient_sleep(sana_page, 3, bot, user_id)

                clicked_sign2 = await _click_sign_section(sana_page)
                if clicked_sign2:
                    await resilient_sleep(sana_page, 6, bot, user_id)

                # بررسی نهایی
                table_exists = await _check_sign_table_exists(sana_page)
                if not table_exists:
                    logging.error("[EZHHAR_SIGN] جدول امضا حتی بعد از ریلود ظاهر نشد")
                    if nav_attempt < 2:
                        continue
                    return False

            # موفقیت
            return True

        except Exception as e:
            logging.error(f"[EZHHAR_SIGN] navigate_to_ezhhar_sign_page error (تلاش {nav_attempt+1}): {e}")
            continue

    return False


async def get_ezhhar_signable_persons(
    bot: Bot,
    user_id: int) -> list:
    """
    اشخاص قابل امضا اظهارنامه را از جدول استخراج می‌کند.
    فرض بر این است که صفحه قبلاً از طریق navigate_to_ezhhar_sign_page باز شده است.

    اگر نام‌ها خالی بودند، چند بار تلاش مجدد با صبر انجام می‌دهد.

    Returns:
        list of dicts: [{idx, name, personType, canSend, divVisible}]
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return []

    # تلاش چندباره برای استخراج نام‌ها — ممکن است Angular هنوز داده را پر نکرده باشد
    for extract_attempt in range(5):
        try:
            persons_info = await _extract_persons_from_table(sana_page)

            if not persons_info:
                logging.warning(f"[EZHHAR_SIGN] لیست اشخاص خالی بود (تلاش {extract_attempt+1})")
                await asyncio.sleep(5)
                continue

            # بررسی آیا حداقل یک نام پر شده
            has_any_name = any(p.get("name", "") for p in persons_info)
            if has_any_name:
                logging.info(f"[EZHHAR_SIGN] persons_info: {persons_info}")
                return persons_info

            # نام‌ها خالی هستند — صبر کن و دوباره تلاش کن
            logging.warning(f"[EZHHAR_SIGN] نام اشخاص خالی بود (تلاش {extract_attempt+1}) — صبر ۵ ثانیه")
            await asyncio.sleep(5)

            # شاید نیاز به کلیک مجدد روی اخذ امضا باشد
            if extract_attempt == 2:
                clicked = await _click_sign_section(sana_page)
                if clicked:
                    await resilient_sleep(sana_page, 6, bot, user_id)

        except Exception as e:
            logging.error(f"[EZHHAR_SIGN] get_ezhhar_signable_persons error (تلاش {extract_attempt+1}): {e}")
            await asyncio.sleep(3)

    # آخرین تلاش
    try:
        persons_info = await _extract_persons_from_table(sana_page)
        logging.info(f"[EZHHAR_SIGN] persons_info (آخرین تلاش): {persons_info}")
        return persons_info or []
    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] get_ezhhar_signable_persons final error: {e}")
        return []


async def _extract_persons_from_table(page) -> list:
    """
    استخراج اشخاص از جدول امضا.
    از چند انتخاب‌گر CSS مختلف برای استخراج نام استفاده می‌کند.
    """
    return await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll(
            'table tbody tr[ng-repeat*="thePetitionPersonSignableList"]'
        ));
        if (rows.length === 0) return [];

        return rows.map((tr, idx) => {
            // ── استخراج نام — چند روش مختلف ──
            let name = "";

            // روش ۱: سلول با کلاس‌های خاص + ng-binding
            // توجه: ستون «نوع اخذ امضاء» («از طریق ثنا / از طریق دستگاه پد امضاء»)
            // دقیقاً همین کلاس‌ها را دارد و در DOM جلوتر از ستون نام است — بدون
            // شرط ng-binding، آن ستون به‌جای نام واقعی گرفته می‌شود.
            const nameTd1 = tr.querySelector(
                'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle.ng-binding'
            );
            if (nameTd1) name = nameTd1.innerText.trim();

            // روش ۱ب: همان کلاس‌ها بدون ng-binding، ولی رد کردن ستون نوع امضا
            if (!name) {
                const candidates = tr.querySelectorAll(
                    'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle'
                );
                for (const c of candidates) {
                    const t = c.innerText.trim();
                    if (t && !t.includes("از طریق")) { name = t; break; }
                }
            }

            // روش ۲: سلول با کلاس font-yekan (کمتر سخت‌گیرانه) — باز هم رد کردن نوع امضا
            if (!name) {
                const tds2 = tr.querySelectorAll('td.font-yekan');
                for (const td of tds2) {
                    const t = td.innerText.trim();
                    if (t && !t.includes("از طریق")) { name = t; break; }
                }
            }

            // روش ۳: از طریق مدل Angular — خواندن مستقیم از scope
            if (!name) {
                try {
                    const scope = angular.element(tr).scope();
                    if (scope && scope.item) {
                        name = (scope.item.Name || scope.item.name ||
                                scope.item.FullName || scope.item.fullName ||
                                scope.item.PersonName || "").trim();
                    }
                } catch(e) {}
            }

            // روش ۴: هر td که متن فارسی دارد (آخرین راه)
            if (!name) {
                const tds = tr.querySelectorAll('td');
                for (const td of tds) {
                    const text = td.innerText.trim();
                    // متن فارسی — حداقل ۲ حرف و بدون اعداد خالص
                    if (text.length >= 2 && !/^[0-9۰-۹]+$/.test(text)
                        && !text.includes("ارسال") && !text.includes("ثبت")
                        && !text.includes("درج") && !text.includes("حذف")
                        && !text.includes("نوع") && !text.includes("از طریق")) {
                        name = text;
                        break;
                    }
                }
            }

            // ── نوع شخص ──
            let personType = "";
            const typeSpans = tr.querySelectorAll('span[ng-if*="PersonType"]');
            for (const sp of typeSpans) {
                if (sp.getBoundingClientRect().width > 0) {
                    personType = sp.innerText.trim();
                }
            }

            // از scope هم نوع شخص را بخوان
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

            // ── آیا div ارسال کد نمایش دارد؟ ──
            const sendDiv = tr.querySelector(
                'div[ng-if*="!(item.NationalityCode"]'
            );
            const divVisible = sendDiv &&
                window.getComputedStyle(sendDiv).display !== "none";

            // ── آیا دکمه ارسال کد فعال هست؟ ──
            const sendBtn = tr.querySelector(
                'button[ng-click*="sendTempPassword"]'
            );
            const canSend = divVisible && sendBtn && !sendBtn.disabled;

            return { idx, name, personType, canSend, divVisible };
        });
    }''')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# فاز ۲ — ارسال کد موقت برای یک شخص
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_ezhhar_sign_code_for_person(
    bot: Bot,
    user_id: int,
    row_idx: int,
    person_name: str,
    tracking_code: str = "") -> bool:
    """
    ارسال کد موقت برای یک ردیف مشخص از جدول امضای اظهارنامه.
    حداکثر ۳ بار تلاش می‌کند.

    نکته مهم: چون یک صفحه مرورگر مشترک بین همه کاربران است، ممکن است بین
    فاز ناوبری (فاز ۱) و این فاز، تسک‌های کاربران دیگر صفحه را عوض کرده
    باشند — به همین دلیل ابتدا وجود جدول را بررسی و در صورت نیاز مجدداً
    ناوبری می‌کنیم.

    Returns True اگر کد ارسال شد (یا قبلاً ارسال شده بود).
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return False

    # ── بررسی اینکه آیا صفحه هنوز روی جدول صحیح اظهارنامه است ──
    # (صفحه مرورگر مشترک است و ممکن است تسک کاربر دیگری آن را عوض کرده باشد)
    table_ok = await _check_sign_table_exists(sana_page)
    if table_ok:
        # بررسی اینکه واقعاً در بخش اظهارنامه هستیم، نه لایحه
        page_ok = await _verify_ezhhar_page_loaded(sana_page)
        table_ok = table_ok and page_ok

    if not table_ok and tracking_code:
        logging.warning(
            f"[EZHHAR_SIGN] صفحه قبل از ارسال کد، به‌روز نیست — ناوبری مجدد برای کاربر {user_id}"
        )
        nav_ok = await navigate_to_ezhhar_sign_page(bot, user_id, tracking_code)
        if not nav_ok:
            logging.error(f"[EZHHAR_SIGN] ناوبری مجدد قبل از ارسال کد ناموفق — کاربر {user_id}")
            return False

    for attempt in range(3):
        clicked = await sana_page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="thePetitionPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const btn = rows[idx].querySelector('button[ng-click*="sendTempPassword"]');
            if (btn && !btn.disabled) {{ btn.click(); return true; }}
            return false;
        }}''', row_idx)

        if not clicked:
            logging.warning(f"[EZHHAR_SIGN] دکمه ارسال کد برای ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

        popup_result = await _wait_for_popup_result(sana_page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(sana_page)
            logging.info(f"[EZHHAR_SIGN] کد موقت برای ردیف {row_idx} ({person_name}) ارسال شد.")
            return True

        elif popup_result == "already_sent":
            await _close_any_popup(sana_page)
            logging.info(f"[EZHHAR_SIGN] کد قبلاً ارسال شده برای ردیف {row_idx}")
            return True

        elif popup_result == "service_delay":
            await _close_any_popup(sana_page)
            logging.warning(f"[EZHHAR_SIGN] تاخیر در اجرای سرویس برای ردیف {row_idx} (تلاش {attempt+1}) — صبر ۱۵ ثانیه و تکرار")
            await asyncio.sleep(15)
            continue

        else:
            await _close_any_popup(sana_page)
            logging.warning(f"[EZHHAR_SIGN] خطا در ارسال کد ردیف {row_idx} (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# فاز ۳ — ثبت کد امضا
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def submit_ezhhar_sign_code(
    bot: Bot,
    user_id: int,
    tracking_code: str,
    row_idx: int,
    code: str) -> dict:
    """
    کد دریافت‌شده از کاربر را در سامانه وارد و امضا می‌کند.
    ناوبری مجدد به صفحه امضا، وارد کردن کد، کلیک امضای ثنا.

    Returns:
        dict: {"success": bool, "error": str}
        error values: "wrong_code", "sana_not_registered", "timeout", "error", "max_attempts"
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return {"success": False, "error": "sana_page is None"}

    try:
        # ── ناوبری مجدد به صفحه اخذ امضا ─────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return {"success": False, "error": "خطا در بارگذاری صفحه"}

        await human_delay(3.0, 5.0)

        # کلیک منوی اظهارنامه — با تابع ایمن click_sana_main_menu (+ fallback متنی)
        clicked = await _click_ezhhar_menu(sana_page)
        if not clicked:
            logging.warning("[EZHHAR_SIGN] فاز۳: منو اظهارنامه با روش اصلی پیدا نشد — fallback با متن")
            try:
                clicked = await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
            except Exception as menu_err:
                logging.warning(f"[EZHHAR_SIGN] فاز۳: fallback متن منو ناموفق: {menu_err}")
                clicked = False
        if not clicked:
            return {"success": False, "error": "منوی اظهارنامه پیدا نشد"}
        await resilient_sleep(sana_page, 5, bot, user_id)

        # بررسی صحت صفحه
        page_ok = await _verify_ezhhar_page_loaded(sana_page)
        if not page_ok:
            logging.error("[EZHHAR_SIGN] در فاز ۳، صفحه اظهارنامه بارگذاری نشد")
            return {"success": False, "error": "خطا در بارگذاری صفحه اظهارنامه"}

        await wait_for_angular_idle(sana_page)

        # مستقیم فیلد و جستجو — بدون radio
        await _fill_input(sana_page, "#txtPetitionNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        # فقط دکمه مخصوص اظهارنامه
        search_clicked = await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not search_clicked:
            logging.error("[EZHHAR_SIGN] دکمه #btnGetJSSPetition در فاز ۳ پیدا نشد")
            return {"success": False, "error": "دکمه جستجو یافت نشد"}

        await asyncio.sleep(3)
        await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 3, bot, user_id)

        # بررسی پاپ‌آپ بازیابی
        recovery_ok = await _check_recovery_popup(sana_page, bot, user_id)
        if not recovery_ok:
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

        clicked_sign = await _click_sign_section(sana_page)
        if not clicked_sign and not await _check_sign_table_exists(sana_page):
            try:
                await safe_click_by_text(sana_page, "اخذ امضا", bot, user_id)
            except Exception as click_err:
                if not await _check_sign_table_exists(sana_page):
                    raise click_err
                logging.info(
                    "[EZHHAR_SIGN] فاز ۳: باکس «اخذ امضای الکترونیک» پیدا نشد، "
                    "ولی جدول امضا از قبل موجود بود — ادامه می‌دهیم."
                )
        await resilient_sleep(sana_page, 6, bot, user_id)

        # ── وارد کردن کد و کلیک امضا ──────────────────────────────────
        result = await _enter_code_and_sign(sana_page, row_idx, code, bot, user_id)
        return result

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] submit_ezhhar_sign_code error: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_input(page, selector: str, value: str) -> bool:
    """پر کردن فیلد ورودی — برمی‌گرداند موفق بود یا خیر"""
    try:
        elem = page.locator(selector).first
        await elem.wait_for(state="visible", timeout=10000)
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
        return True
    except Exception as e:
        logging.warning(f"[EZHHAR_SIGN] _fill_input({selector}) failed: {e}")
        return False


async def _click_sign_section(page) -> bool:
    """کلیک روی بخش «اخذ امضای الکترونیک»"""
    return await page.evaluate('''() => {
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
        if (t) {
            const box = t.closest('.box');
            if (box) { box.click(); return true; }
        }
        return false;
    }''')


async def _check_sign_table_exists(page) -> bool:
    """بررسی وجود جدول امضا"""
    return await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll(
            'table tbody tr[ng-repeat*="thePetitionPersonSignableList"]'
        ));
        return rows.length > 0;
    }''')


async def _close_any_popup(page) -> bool:
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


async def _check_recovery_popup(page, bot: Bot, user_id: int) -> bool:
    """
    بررسی پاپ‌آپ بازیابی اظهارنامه.
    فقط اگر «بازیابی اظهارنامه با موفقیت» بود → بستن و True.
    هر پیام دیگری → False (باید ریلود شود).
    """
    result = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const h2 = popup.querySelector('h2');
        const text = h2 ? h2.innerText.trim() : "";
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        const isSuccessVisible = successIcon &&
            window.getComputedStyle(successIcon).display !== "none";

        if (isSuccessVisible && text.includes("بازیابی")) {
            return "recovery_success";
        }
        if (isSuccessVisible) {
            return "success";
        }
        return text || "other";
    }''')

    if result == "recovery_success":
        await _close_any_popup(page)
        return True
    elif result == "success":
        await _close_any_popup(page)
        return True
    elif result and result != "other":
        await _close_any_popup(page)
        return False
    elif result == "other":
        await _close_any_popup(page)
        return True

    return True


async def _wait_for_popup_result(page, timeout_sec: int = 55) -> str:
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
                if (text.includes("تاخیر") || text.includes("تأخیر")) {
                    return "service_delay";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)

    return "timeout"


async def _enter_code_and_sign(
    page, row_idx: int, code: str, bot: Bot, user_id: int
) -> dict:
    """
    کد را در فیلد وارد کرده و دکمه امضای ثنا را می‌زند.

    Returns:
        dict: {"success": bool, "error": str}
        error values: "wrong_code", "sana_not_registered", "timeout", "error", "max_attempts"
    """
    for attempt in range(3):
        filled = await page.evaluate(f'''(args) => {{
            const idx = args.idx;
            const code = args.code;
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="thePetitionPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const inp = rows[idx].querySelector('input[id^="txtTempPassword"]');
            if (!inp) return false;
            inp.value = code;
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
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
            logging.warning(f"[EZHHAR_SIGN] وارد کردن کد در ردیف {row_idx} ناموفق (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        await asyncio.sleep(1)

        clicked = await page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="thePetitionPersonSignableList"]'
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
            logging.warning(f"[EZHHAR_SIGN] دکمه امضاء ثنا در ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        popup_result = await _wait_for_sign_popup(page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(page)
            logging.info(f"[EZHHAR_SIGN] امضای ردیف {row_idx} موفق.")
            return {"success": True}
        elif popup_result == "wrong_code":
            await _close_any_popup(page)
            logging.info(f"[EZHHAR_SIGN] رمز موقت نادرست — ردیف {row_idx}")
            return {"success": False, "error": "wrong_code"}
        elif popup_result == "sana_not_registered":
            await _close_any_popup(page)
            logging.info(f"[EZHHAR_SIGN] امضا در ثنا ثبت نیست — ردیف {row_idx}")
            return {"success": False, "error": "sana_not_registered"}
        elif popup_result == "service_delay":
            await _close_any_popup(page)
            logging.warning(f"[EZHHAR_SIGN] تاخیر در اجرای سرویس — ردیف {row_idx} (تلاش {attempt+1}) — صبر ۱۵ ثانیه و تکرار")
            await asyncio.sleep(15)
            continue
        else:
            await _close_any_popup(page)
            logging.warning(f"[EZHHAR_SIGN] امضای ردیف {row_idx} ناموفق: {popup_result} (تلاش {attempt+1})")

            clicked_sign = await _click_sign_section(page)
            if not clicked_sign and not await _check_sign_table_exists(page):
                try:
                    await safe_click_by_text(page, "اخذ امضا", bot, user_id)
                except Exception as click_err:
                    if not await _check_sign_table_exists(page):
                        raise click_err
                    logging.info(
                        "[EZHHAR_SIGN] retry: باکس «اخذ امضای الکترونیک» پیدا نشد، "
                        "ولی جدول امضا از قبل موجود بود — ادامه می‌دهیم."
                    )
            await asyncio.sleep(6)

    return {"success": False, "error": "max_attempts"}


async def _wait_for_sign_popup(page, timeout_sec: int = 55) -> str:
    """
    منتظر پاپ‌آپ نتیجه امضا.
    Returns: "success" | "wrong_code" | "sana_not_registered" | "service_delay" | "error" | "timeout"

    پیام‌های مورد انتظار:
      - موفق (آیکون سبز): "امضاء با موفقیت در صفحه چاپ درج گردید"
      - موفق (آیکون زرد/هشدار): "امضاء « name » در صفحه ی چاپ درج شده است"
      - خطا (آیکون قرمز): "خطای سرویس ثنا   : رمز موقت نادرست است"
      - خطا: "امضای شخص فلان در سامانه ثنا درج نشده است"
      - خطا: "خطا: تاخیر در اجرای سرویس" → تکرار همان مرحله
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

            if (isSuccessVisible) return "success";

            // هشدار ولی واقعاً موفق — "امضاء « name » در صفحه ی چاپ درج شده است"
            if (isWarningVisible && text.includes("درج شده")) return "success";

            if (isErrorVisible) {
                if (text.includes("رمز موقت نادرست") || text.includes("نادرست")) {
                    return "wrong_code";
                }
                // تشخیص خطای "امضای شخص ... در سامانه ثنا درج نشده است"
                if (text.includes("در سامانه ثنا درج نشده")) {
                    return "sana_not_registered";
                }
                // تاخیر در اجرای سرویس — باید بستن پاپ‌آپ و تکرار همان مرحله
                if (text.includes("تاخیر") || text.includes("تأخیر")) {
                    return "service_delay";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)
    return "timeout"
