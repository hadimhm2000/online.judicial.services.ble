"""

سناریوی ثبت دادخواست چک در سامانه قضایی ثنا.



جریان کلی:

  ۱. تعیین مسیر بر اساس مبلغ (بیش از ۱ میلیارد → بدوی، کمتر → صلح)

  ۲. کلیک «ثبت و اصلاح دادخواست»

  ۳. مرحله «شروع» — بررسی وکیل/نماینده

  ۴. مرحله «خواسته» — انتخاب موضوع، خواسته، مبلغ

  ۵. مرحله «خواهان» — افزودن اشخاص خواهان

  ۶. مرحله «خوانده» — افزودن اشخاص خوانده

  ۷. مرحله «وکیل» / «نماينده» (در صورت وجود)

  ۸. مرحله «مطلع/ گواه»

  ۹. مرحله «شرح» — وارد کردن شرح متن

  ۱۰. مرحله «دلايل» — دلایل اضافی

  ۱۱. ثبت موقت

  ۱۲. مرحله «منضمات» — آپلود تصاویر چک (با کدرهگیری)

  ۱۳. آماده‌سازی (وارد کردن کد صلاحیت دادگاه)

  ۱۴. محاسبه هزینه و دریافت مبلغ

  ۱۵. چاپ PDF

  ۱۶. ارسال نتیجه به کاربر

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
    handle_session_expired, wait_for_horizontal_loading_bar,
    detect_concurrent_login_popup)


logger = logging.getLogger(__name__)


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را به HTML امن برای ادیتور تبدیل می‌کند."""
    if not text:
        return "<p><br></p>"
    lines = text.split("\\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")
    return "".join(parts)


async def process_check_task(data: dict, bot: Bot):
    """پردازش تسک ثبت دادخواست چک"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]

    request_title = data.get("check_request_title", "")
    amount = data.get("check_amount", 0)
    khasteh_text = data.get("check_khasteh_text", "")
    tracking_no = data.get("check_tracking_no", "")
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    check_text = data.get("check_text", "")
    extra_text = data.get("check_extra_text", "")
    check_images = data.get("check_images", [])
    branch_code = data.get("check_branch_code", "")
    branch_name = data.get("check_branch_name", "")
    check_text_html = data.get("check_text_html", "")

    has_lawyer = any(p.get("person_type") == "وکیل" for p in plaintiffs)
    has_legal_plaintiff = any(p.get("person_type") == "شخص حقوقی" for p in plaintiffs)
    is_high_amount = amount > 1_000_000_000  # بیش از ۱ میلیارد ریال

    logging.info(
        f"[CHECK] user={user_id} title={request_title} amount={amount} "
        f"plaintiffs={len(plaintiffs)} defendants={len(defendants)} "
        f"is_high_amount={is_high_amount} branch={branch_code}"
    )

    await bot.send_message(
        user_id,
        f"🏦 *در حال ثبت دادخواست چک...*\\n"
        f"نوع خواسته: *{request_title}*\\n"
        f"مبلغ: *{amount:,} ریال*")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [CHECK] شروع ثبت دادخواست چک برای کاربر {user_id}\\n"
        f"نوع: {request_title} | مبلغ: {amount:,} | خواهان: {len(plaintiffs)} | خوانده: {len(defendants)}"
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

            # ── ۱. انتخاب مسیر بر اساس مبلغ ──────────────────────────────
            if is_high_amount:
                # مسیر: ارایه و پیگیری دادخواست → دادخواست بدوی
                clicked = await sana_page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a.list-group-item'));
                    const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری دادخواست"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دادخواست", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # کلیک «دادخواست بدوی»
                clicked = await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('li.list-group-item'));
                    const t = items.find(el => el.innerText && el.innerText.includes("دادخواست بدوی"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دادخواست بدوی", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)
            else:
                # مسیر: دعاوی دادگاههای صلح → دعاوی حقوقی
                clicked = await sana_page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a.list-group-item'));
                    const t = links.find(el => el.innerText && el.innerText.includes("دعاوی دادگاههای صلح"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دعاوی دادگاههای صلح", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # کلیک «دعاوی حقوقی»
                clicked = await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('li.list-group-item'));
                    const t = items.find(el => el.innerText && el.innerText.includes("دعاوی حقوقی"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دعاوی حقوقی", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. کلیک «ثبت و اصلاح دادخواست» ──────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const boxes = Array.from(document.querySelectorAll('.box'));
                const t = boxes.find(el => {
                    const h5 = el.querySelector('h5');
                    return h5 && h5.innerText && h5.innerText.includes("ثبت و اصلاح دادخواست");
                });
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ثبت و اصلاح دادخواست", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. مرحله «شروع» ────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "شروع");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # اگر وکیل/نماینده داشت → مشابه اظهارنامه
            if has_lawyer:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbLawyerOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)
            elif has_legal_plaintiff:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbAgentOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)

            # ── ۴. مرحله «خواسته» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خواسته");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خواسته", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ۴.۱ انتخاب «موضوع پرونده» → دعاوي عمومي حقوقي
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('.ui-select-toggle');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(2)

            # جستجو و انتخاب «دعاوي عمومي حقوقي»
            search_input = sana_page.locator('.ui-select-search').first
            try:
                await search_input.wait_for(state="visible", timeout=5000)
                await search_input.fill("")
                await search_input.type("دعاوي عمومي حقوقي", delay=100)
                await asyncio.sleep(3)

                await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'));
                    const visible = items.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visible.length > 0) {
                        const row = visible[0].closest('a, .ui-select-choices-row, li') || visible[0];
                        row.click();
                        return true;
                    }
                    return false;
                }''')
                await asyncio.sleep(3)
            except PlaywrightTimeoutError:
                logging.warning("[CHECK] dropdown موضوع پرونده باز نشد")

            # ۴.۲ کلیک «افزودن»
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnAddSection');
                if (btn && !btn.disabled) btn.click();
            }''')
            await resilient_sleep(sana_page, 3, bot, user_id)

            # ۴.۳ انتخاب نوع خواسته از dropdown
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('.ui-select-toggle.btn-info');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(2)

            if request_title == "صدور اجرائیه چک":
                # جستجوی «چک» و انتخاب «درخواست صدور اجرائیه نسبت به چک بلامحل»
                try:
                    search2 = sana_page.locator('.ui-select-search').first
                    await search2.wait_for(state="visible", timeout=5000)
                    await search2.fill("")
                    await search2.type("چک", delay=100)
                    await asyncio.sleep(10)  # ۱۰ ثانیه صبر

                    await sana_page.evaluate('''() => {
                        const items = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'));
                        const visible = items.filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        // اولویت: درخواست صدور اجرائیه نسبت به چک بلامحل
                        const target = visible.find(el => el.innerText.includes("صدور اجرائیه")) || visible[0];
                        if (target) {
                            const row = target.closest('a, .ui-select-choices-row, li') || target;
                            row.click();
                            return true;
                        }
                        return false;
                    }''')
                    await asyncio.sleep(3)
                except PlaywrightTimeoutError:
                    logging.warning("[CHECK] dropdown خواسته باز نشد")
            else:
                # مطالبه وجه چک
                try:
                    search2 = sana_page.locator('.ui-select-search').first
                    await search2.wait_for(state="visible", timeout=5000)
                    await search2.fill("")
                    await search2.type("چک", delay=100)
                    await asyncio.sleep(3)

                    await sana_page.evaluate('''() => {
                        const items = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'));
                        const visible = items.filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        const target = visible.find(el => el.innerText.includes("مطالبه وجه")) || visible[0];
                        if (target) {
                            const row = target.closest('a, .ui-select-choices-row, li') || target;
                            row.click();
                            return true;
                        }
                        return false;
                    }''')
                    await asyncio.sleep(3)
                except PlaywrightTimeoutError:
                    logging.warning("[CHECK] dropdown خواسته باز نشد")

            # ۴.۴ وارد کردن متن خواسته
            await sana_page.evaluate('''(text) => {
                const inp = document.querySelector('input[id^="txtDescription"]');
                if (inp) {
                    inp.value = text;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', khasteh_text)
            await asyncio.sleep(1)

            # ۴.۵ انتخاب «مبلغ معین»
            await sana_page.evaluate('''() => {
                const sel = document.querySelector('select[ng-model*="PriceType"]');
                if (sel) {
                    sel.value = "1";
                    sel.dispatchEvent(new Event("input", { bubbles: true }));
                    sel.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(1)

            # ۴.۶ وارد کردن مبلغ
            amount_str = str(amount)
            await sana_page.evaluate('''(val) => {
                const inp = document.querySelector('input[id^="txtPrice"]');
                if (inp) {
                    inp.focus();
                    inp.value = "";
                    inp.value = val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', amount_str)
            await asyncio.sleep(1)

            # ۴.۷ تیک‌های خسارت (فقط مطالبه وجه)
            if request_title == "مطالبه وجه چک":
                await sana_page.evaluate('''() => {
                    const rdbJudge = document.querySelector('#rdbJudgePrice');
                    if (rdbJudge && !rdbJudge.checked && !rdbJudge.disabled) rdbJudge.click();
                    const rdbDelay = document.querySelector('#rdbDelayPrice');
                    if (rdbDelay && !rdbDelay.checked && !rdbDelay.disabled) rdbDelay.click();
                }''')
                await asyncio.sleep(1)

            # ── ۵. مرحله «خواهان» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خواهان");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خواهان", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(plaintiffs):
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype == "وکیل":
                    continue  # وکیل در step جداگانه

                # کلیک افزودن
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                if ptype == "شخص حقوقی":
                    await _fill_legal_person(sana_page, person, bot, user_id, role="plaintiff", idx=idx)
                else:
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id, role="plaintiff", idx=idx)

                await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۶. مرحله «خوانده» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خوانده");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خوانده", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(defendants):
                ptype = person.get("person_type", "شخص حقیقی")

                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                if ptype == "شخص حقوقی":
                    await _fill_legal_person(sana_page, person, bot, user_id, role="defendant", idx=idx)
                else:
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id, role="defendant", idx=idx)

                await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷. مرحله «وکیل» ─────────────────────────────────────────
            if has_lawyer:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "وكيل");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "وكيل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, person in enumerate(plaintiffs):
                    if person.get("person_type") != "وکیل":
                        continue
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnAddSection');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_lawyer_person(sana_page, person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷.۵ مرحله «نماينده» (اگر حقوقی داشتیم) ──────────────────
            if has_legal_plaintiff:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "نماينده");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "نماينده", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                legal_pl = next((p for p in plaintiffs if p.get("person_type") == "شخص حقوقی"), {})
                rep_type = legal_pl.get("representative_type", "")
                nat_id = legal_pl.get("national_id", "")

                agent_value = "0091000010000008" if rep_type == "مدیرعامل" else "0091000010000010"

                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)
                await wait_for_angular_idle(sana_page)
                await asyncio.sleep(2)

                await sana_page.evaluate(f'''() => {{
                    const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
                    if (sel && !sel.disabled) {{
                        sel.value = "{agent_value}";
                        sel.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        sel.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}
                }}''')
                await asyncio.sleep(2)

                if nat_id:
                    for _try in range(5):
                        set_ok = await sana_page.evaluate(f'''() => {{
                            const inp = document.querySelector('#txtRealIrNationalityCode');
                            if (inp && !inp.disabled) {{
                                inp.value = "{nat_id}";
                                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}''')
                        if set_ok:
                            break
                        await asyncio.sleep(3)

                    # کلیک استعلام
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnCallNationalityCode');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۸. مرحله «مطلع/ گواه» ───────────────────────────────────
            if witnesses:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.includes("مطلع"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "مطلع", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for witness in witnesses:
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnAddSection');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, witness["national_id"], bot, user_id, role="witness")
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۹. مرحله «شرح» ──────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "شرح");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "شرح", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            full_text = check_text
            if extra_text:
                full_text += "\\n" + extra_text

            text_html = check_text_html if check_text_html else _text_to_editor_html(full_text)

            await sana_page.evaluate('''(html) => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    editor.focus();
                    editor.innerHTML = html;
                    editor.dispatchEvent(new Event("input", { bubbles: true }));
                    editor.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', text_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

            # ── ۱۰. مرحله «دلايل» ────────────────────────────────────────
            if extra_text:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "دلايل");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دلايل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                # تیک چک‌باکس و وارد کردن متن دلایل
                await sana_page.evaluate('''() => {
                    const chk = document.querySelector('input[type="checkbox"][id^="chk"]');
                    if (chk && !chk.checked && !chk.disabled) chk.click();
                }''')
                await asyncio.sleep(1)

                await sana_page.evaluate('''(text) => {
                    const ta = document.querySelector('textarea[id^="ReasonAttach"]');
                    if (ta) {
                        ta.value = text;
                        ta.dispatchEvent(new Event("input", { bubbles: true }));
                        ta.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', extra_text)
                await asyncio.sleep(1)

            # ── ۱۱. ثبت موقت ──────────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const t = btns.find(el => el.innerText && el.innerText.includes("ثبت موقت"));
                if (t && !t.disabled) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ثبت موقت", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            # استخراج شماره بایگانی
            bill_no = await sana_page.evaluate('''() => {
                const inp = document.querySelector('#txtBillNo');
                if (inp) return inp.value;
                const sp = document.querySelector('[ng-model*="BillNo"]');
                if (sp) return sp.innerText || sp.textContent;
                return "";
            }''')
            logging.info(f"[CHECK] bill_no={bill_no}")

            if bill_no:
                await log_event("ثبت موقت", "دادخواست چک", str(user_id), user_id,
                                tracking_code=bill_no, note=f"چک {request_title} | مبلغ: {amount:,}")
                await bot.send_message(
                    ADMIN_ID,
                    f"📋 *ثبت موقت دادخواست چک موفق*\\n"
                    f"👤 کاربر: {user_id}\\n"
                    f"🔢 کد بایگانی: `{bill_no}`\\n"
                    f"📝 نوع: {request_title}")

            # بازگشت به فهرست
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnGotoMainPage');
                if (btn && !btn.disabled) btn.click();
            }''')
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. مرحله «منضمات» — آپلود تصاویر چک ──────────────────
            if check_images:
                clicked = await sana_page.evaluate('''() => {
                    const boxes = Array.from(document.querySelectorAll('.box'));
                    const t = boxes.find(el => {
                        const h5 = el.querySelector('h5');
                        return h5 && h5.innerText && h5.innerText.includes("منضمات");
                    });
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "منضمات", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # دانلود تصاویر از بله
                image_paths = await _download_check_images(bot, check_images, user_id)

                if image_paths:
                    # انتخاب «تصوير چك و گواهينامه عدم پرداخت» از dropdown
                    await sana_page.evaluate('''() => {
                        const sel = document.querySelector('#attachmentType');
                        if (sel) {
                            // value="object:1912" = تصوير چك و گواهينامه عدم پرداخت
                            const opts = Array.from(sel.options);
                            const target = opts.find(o => o.innerText.includes("تصوير چك و گواهينامه عدم پرداخت"));
                            if (target) {
                                sel.value = target.value;
                                sel.dispatchEvent(new Event("input", { bubbles: true }));
                                sel.dispatchEvent(new Event("change", { bubbles: true }));
                            }
                        }
                    }''')
                    await asyncio.sleep(2)

                    # وارد کردن کدرهگیری
                    await sana_page.evaluate('''(val) => {
                        const inp = document.querySelector('#txtInqueryNo');
                        if (inp) {
                            inp.value = val;
                            inp.dispatchEvent(new Event("input", { bubbles: true }));
                            inp.dispatchEvent(new Event("change", { bubbles: true }));
                        }
                    }''', tracking_no)
                    await asyncio.sleep(1)

                    # کلیک ثبت و ویرایش پیوست
                    clicked = await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnSaveDoc');
                        if (btn && !btn.disabled) { btn.click(); return true; }
                        return false;
                    }''')
                    if clicked:
                        # صبر برای لودینگ و استعلام بانک مرکزی
                        await wait_for_horizontal_loading_bar(sana_page, bot, user_id)
                        await resilient_sleep(sana_page, 10, bot, user_id)

                        # بررسی موفقیت استعلام
                        success_popup = await sana_page.evaluate('''() => {
                            const popup = document.querySelector('.sweet-alert.showSweetAlert');
                            if (!popup) return null;
                            const h2 = popup.querySelector('h2');
                            return h2 ? h2.innerText : null;
                        }''')

                        if success_popup and "موفق" in success_popup:
                            logging.info(f"[CHECK] استعلام بانک مرکزی موفق")
                            # بستن پاپ‌آپ
                            await sana_page.evaluate('''() => {
                                const btn = document.querySelector('.sweet-alert .confirm');
                                if (btn) btn.click();
                            }''')
                            await asyncio.sleep(2)

                            # وارد کردن تعداد (عدر ۱) در فیلد Amount
                            await sana_page.evaluate('''() => {
                                const inp = document.querySelector('#txtDeductionAmount');
                                if (inp && !inp.disabled) {
                                    inp.value = "1";
                                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                                }
                            }''')
                            await asyncio.sleep(1)

                            # کلیک «ثبت و ویرایش پیوست»
                            await sana_page.evaluate('''() => {
                                const btn = document.querySelector('#btnSaveDoc');
                                if (btn && !btn.disabled) btn.click();
                            }''')
                            await resilient_sleep(sana_page, 5, bot, user_id)

                            # آپلود تصاویر
                            await _upload_check_images(sana_page, image_paths, bot, user_id)

                    # پاکسازی فایل‌های موقت
                    for p in image_paths:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                # بازگشت به فهرست
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnGotoMainPage');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۳. آماده‌سازی جهت دریافت وجه ────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const boxes = Array.from(document.querySelectorAll('.box'));
                const t = boxes.find(el => {
                    const h5 = el.querySelector('h5');
                    return h5 && h5.innerText && h5.innerText.includes("آماده سازي جهت دريافت وجه");
                });
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "آماده سازي", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # وارد کردن کد صلاحیت دادگاه
            if branch_code:
                await sana_page.evaluate('''(code) => {
                    const inp = document.querySelector('#txtSendUnitCode');
                    if (inp) {
                        inp.value = code;
                        inp.dispatchEvent(new Event("input", { bubbles: true }));
                        inp.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', branch_code)
                await asyncio.sleep(2)

            # کلیک «تایید اطلاعات»
            clicked = await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnCalculateCash') ||
                              Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes("تایید اطلاعات"));
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if clicked:
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # تایید پاپ‌آپ
                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('.sweet-alert button.confirm'));
                    const t = btns.find(b => b.innerText.includes("تایید"));
                    if (t) t.click();
                }''')
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # بستن پاپ‌آپ موفقیت
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('.sweet-alert .confirm');
                    if (btn) btn.click();
                }''')
                await asyncio.sleep(2)

            # بازگشت به فهرست
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnGotoMainPage');
                if (btn && !btn.disabled) btn.click();
            }''')
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۴. محاسبه و دریافت هزینه ────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const boxes = Array.from(document.querySelectorAll('.box'));
                const t = boxes.find(el => {
                    const h5 = el.querySelector('h5');
                    return h5 && h5.innerText && h5.innerText.includes("محاسبه و دريافت هزينه");
                });
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "محاسبه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            # استخراج هزینه‌ها
            cost_data = await _extract_cost_data(sana_page)
            final_total = cost_data.get("final_total", 0)

            # ── ۱۵. چاپ PDF ─────────────────────────────────────────────
            pdf_path = await _print_check(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۶. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result
            nat_ids = ", ".join([
                p.get("national_id", "") for p in plaintiffs if p.get("national_id")
            ])

            if pdf_path and os.path.exists(pdf_path):
                await send_lavayeh_result(
                    bot, user_id, pdf_path, final_total,
                    tracking_code=bill_no,
                    national_ids=nat_ids,
                    lavayeh_title=f"دادخواست چک — {request_title}",
                    lavayeh_province="",
                    lavayeh_row_number=1,
                    lavayeh_persons=plaintiffs,
                    skip_fee_calc=True,
                    is_ezhharnameh=False)
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [CHECK] ثبت دادخواست چک کاربر {user_id} موفق."
                    f" هزینه: {final_total:,} ریال"
                )
            else:
                await bot.send_message(
                    user_id,
                    f"📄 دادخواست چک با کد بایگانی `{bill_no}` ثبت شد "
                    f"اما خطا در چاپ PDF رخ داد."
                    f"با مدیریت تماس بگیرید.")

            return

        except Exception as e:
            logging.error(f"[CHECK] تلاش {attempt+1} ناموفق user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CHECK] تلاش {attempt+1} ناموفق. ریلود...\\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت دادخواست چک با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(ADMIN_ID, f"❌ [CHECK] کاربر {user_id} پس از {max_attempts} تلاش ناموفق.")
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="process_check_task", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int,
                            role: str = "", idx: int = 0):
    """پر کردن کدملی شخص حقیقی و استعلام"""
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
            break

    await asyncio.sleep(1)

    # کلیک استعلام
    await page.evaluate('''() => {
        const btn = document.querySelector('#btnCallNationalityCode');
        if (btn && !btn.disabled) btn.click();
    }''')
    await resilient_sleep(page, 5, bot, user_id)

    # بررسی خطای ثنا
    error_msg = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const p = popup.querySelector('p');
        return p ? p.innerText : null;
    }''')

    if error_msg:
        # بستن پاپ‌آپ
        await page.evaluate('''() => {
            const btn = document.querySelector('.sweet-alert .confirm');
            if (btn) btn.click();
        }''')
        await asyncio.sleep(1)
        logging.warning(f"[CHECK][{role}] خطای ثنا: {error_msg}")


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                            role: str = "", idx: int = 0):
    """پر کردن اطلاعات شخص حقوقی"""
    company_id = person.get("company_id", "")
    nat_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "")

    agent_value = "0091000010000008" if rep_type == "مدیرعامل" else "0091000010000010"

    # انتخاب نوع نماینده
    await page.evaluate(f'''() => {{
        const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
        if (sel && !sel.disabled) {{
            sel.value = "{agent_value}";
            sel.dispatchEvent(new Event("input", {{ bubbles: true }}));
            sel.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(2)

    # وارد کردن شناسه ملی شرکت
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtLegalNationalityCode');
        if (inp && inp.offsetParent !== null) {{
            inp.value = "{company_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # کلیک استعلام
    await page.evaluate('''() => {
        const btn = document.querySelector('#btnCallNationalityCode');
        if (btn && !btn.disabled) btn.click();
    }''')
    await resilient_sleep(page, 5, bot, user_id)

    # وارد کردن کدملی نماینده
    if nat_id:
        for _try in range(5):
            set_ok = await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtRealIrNationalityCode');
                if (inp && !inp.disabled) {{
                    inp.value = "{nat_id}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}''')
            if set_ok:
                break
            await asyncio.sleep(3)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnCallNationalityCode');
            if (btn && !btn.disabled) btn.click();
        }''')
        await resilient_sleep(page, 5, bot, user_id)


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int):
    """پر کردن کدملی وکیل"""
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
            break

    await asyncio.sleep(1)

    await page.evaluate('''() => {
        const btn = document.querySelector('#btnCallNationalityCode');
        if (btn && !btn.disabled) btn.click();
    }''')
    await resilient_sleep(page, 5, bot, user_id)


async def _download_check_images(bot: Bot, images: list, user_id: int) -> list:
    """دانلود تصاویر چک از بله"""
    from upload_helpers import download_images_from_bale
    file_ids = [img.get("file_id") for img in images if img.get("file_id")]
    paths = []
    if file_ids:
        paths = await download_images_from_bale(bot, file_ids, user_id)
    return paths


async def _upload_check_images(page, image_paths: list, bot: Bot, user_id: int):
    """آپلود تصاویر در بخش منضمات"""
    if not image_paths:
        return

    # کلیک editDocument
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('[ng-click*="editDocument"]') ||
                      Array.from(document.querySelectorAll('button, a')).find(b => b.innerText.includes("ویرایش"));
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        # try clicking by icon/text
        await page.evaluate('''() => {
            const icons = Array.from(document.querySelectorAll('.glyphicon-pencil, [class*="edit"]'));
            if (icons.length > 0) icons[0].click();
        }''')
    await asyncio.sleep(3)

    # آپلود فایل‌ها
    file_input = page.locator('#files_multipleFileUploader')
    try:
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(3)

        # کلیک آپلود همه
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnUploadAll');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if clicked:
            # صبر برای اتمام آپلود
            for _ in range(30):
                loading = await page.evaluate('''() => {
                    const bar = document.querySelector('.progress-bar-striped");
                    if (bar) {
                        const style = window.getComputedStyle(bar);
                        return style.display !== 'none';
                    }
                    return false;
                }''')
                if not loading:
                    break
                await asyncio.sleep(2)

            await resilient_sleep(page, 5, bot, user_id)

            # کلیک تایید همه
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnApplyAll');
                if (btn && !btn.disabled) btn.click();
            }''')
            await resilient_sleep(page, 5, bot, user_id)

            # بستن پاپ‌آپ‌ها
            for _ in range(5):
                popup = await page.evaluate('''() => {
                    const p = document.querySelector('.sweet-alert.showSweetAlert');
                    if (!p) return false;
                    const btn = p.querySelector('.confirm');
                    if (btn) { btn.click(); return true; }
                    return false;
                }''')
                if not popup:
                    break
                await asyncio.sleep(2)

    except Exception as e:
        logging.error(f"[CHECK] خطا در آپلود تصاویر: {e}")


async def _extract_cost_data(page) -> dict:
    """استخراج اطلاعات هزینه از جدول"""
    return await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        let costSum = 0;
        let extraSum = 0;
        const costDiv = document.querySelector('[ng-model="viewModel.costSum"]') ||
                         document.querySelector('.color-green');
        if (costDiv) {
            const text = costDiv.innerText || costDiv.textContent;
            costSum = parseInt(text.replace(/[^0-9]/g, '')) || 0;
        }
        // جمع ستون‌های خاص
        const amounts = Array.from(document.querySelectorAll('.color-red'));
        for (const el of amounts) {
            const text = el.innerText || el.textContent;
            const val = parseInt(text.replace(/[^0-9]/g, '')) || 0;
            if (val > 1000) {  // فیلتر کردن اعداد کوچک
                extraSum += val;
            }
        }
        extraSum += 55;
        // رند بالا تا 10000 ریال
        const rounded = Math.ceil((costSum + extraSum) / 10000) * 10000;
        return {
            costSum: costSum,
            extraSum: extraSum,
            final_total: rounded
        };
    }''')


async def _print_check(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    """چاپ PDF دادخواست"""
    pdf_path = ""
    try:
        # کلیک دکمه چاپ
        clicked = await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const t = btns.find(b => b.innerText.includes("چاپ"));
            if (t && !t.disabled) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "چاپ", bot, user_id)

        await asyncio.sleep(3)

        # باز کردن تب جدید و چاپ
        new_page = await browser_context.new_page()
        try:
            # پیدا کردن لینک چاپ
            print_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a'));
                const t = links.find(a => a.innerText && a.innerText.includes("چاپ"));
                return t ? t.href : null;
            }''')

            if print_url:
                await new_page.goto(print_url, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(5)

                # ذخیره PDF
                pdf_dir = "/home/z/my-project/online.judicial.services/public/uploads"
                os.makedirs(pdf_dir, exist_ok=True)
                pdf_filename = f"check_{bill_no}_{int(time.time())}.pdf"
                pdf_path = os.path.join(pdf_dir, pdf_filename)

                await new_page.pdf(path=pdf_path, format="A4")
                logging.info(f"[CHECK] PDF saved: {pdf_path}")
        finally:
            try:
                await new_page.close()
            except Exception:
                pass

    except Exception as e:
        logging.error(f"[CHECK] خطا در چاپ PDF: {e}")

    return pdf_path
