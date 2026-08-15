# ============================================================
# فایل اصلاحی برای lavayeh_scenario.py
# این کد را در بخش مربوطه جایگزین کنید
# ============================================================

# در تابع process_lavayeh_task، بعد از کلیک روی "اطلاعات پرونده"
# این قسمت را پیدا کنید و با کد زیر جایگزین کنید:

"""
await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
await resilient_sleep(sana_page, 3, bot, user_id)

# بررسی روش ثبت: شماره پرونده یا شماره بایگانی
if tracking_method == "archive_number":
    # ═══════════════════════════════════════════════════════════════
    # مسیر شماره بایگانی (اصلاح شده)
    # ═══════════════════════════════════════════════════════════════
    
    # مرحله 1: کلیک روی رادیو باتن شماره بایگانی (value="2")
    logging.info(f"[LAVAYEH] Archive method: clicking rdbCaseInfo2 radio button")
    await sana_page.evaluate('''() => {
        const rdb = document.querySelector('input[type="radio"][name="rdbCaseInfo"][id="rdbCaseInfo2"][value="2"]');
        if (rdb) {
            rdb.click();
            // Trigger Angular change event
            rdb.dispatchEvent(new Event('change', { bubbles: true }));
            try {
                const scope = angular.element(rdb).scope();
                if (scope) {
                    scope.$apply();
                }
            } catch(e) {}
            return true;
        }
        return false;
    }''')
    await resilient_sleep(sana_page, 2, bot, user_id)
    
    # مرحله 2: وارد کردن کد 5 رقمی واحد قضایی (شعبه)
    logging.info(f"[LAVAYEH] Archive method: filling txtCourtCode with branch_code={branch_code}")
    if branch_code:
        await _fill_input(sana_page, "#txtCourtCode", branch_code, bot, user_id)
        await resilient_sleep(sana_page, 2, bot, user_id)
        
        # منتظر بمانیم تا سامانه اطلاعات شعبه را بارگذاری کند
        await sana_page.evaluate('''(code) => {
            const inp = document.querySelector('#txtCourtCode');
            if (inp) {
                inp.value = code;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                inp.dispatchEvent(new Event('blur', { bubbles: true }));
                // Trigger ng-change
                try {
                    const scope = angular.element(inp).scope();
                    if (scope && scope.actions && scope.actions.getUnitByCodeWithBranch) {
                        scope.actions.getUnitByCodeWithBranch(code);
                        scope.$apply();
                    }
                } catch(e) {}
            }
        }''', branch_code)
        await resilient_sleep(sana_page, 3, bot, user_id)
    
    # مرحله 3: وارد کردن شماره بایگانی
    logging.info(f"[LAVAYEH] Archive method: filling txtCaseArchiveNo with archive_number={archive_number}")
    await _fill_input(sana_page, "#txtCaseArchiveNo", archive_number, bot, user_id)
    await resilient_sleep(sana_page, 1, bot, user_id)
    
    # مرحله 4: کلیک روی دکمه صحت‌سنجی (btnAddHst2)
    logging.info(f"[LAVAYEH] Archive method: clicking validate button (btnAddHst2)")
    await _click_validate_with_retry_archive(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 10, bot, user_id)
    
    # بررسی موفقیت
    table_ok = await _wait_for_case_table(sana_page, bot, user_id)
    if not table_ok:
        await bot.send_message(
            user_id,
            "⚠️ *استعلام پرونده با خطا مواجه شد.*\\n\\n"
            "لطفاً موارد زیر را بررسی و اصلاح نمایید:\\n"
            "🔢 شماره بایگانی\\n🏛 کد شعبه (5 رقمی)\\n\\n"
            "سپس مجدداً «ثبت لایحه» را شروع کنید.")
        await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی بایگانی کاربر {user_id} ناموفق. branch_code={branch_code}, archive_number={archive_number}")
        runtime_state.active_lavayeh_users.discard(user_id)
        await log_event(
            "خطای سامانه", "لایحه", str(user_id), user_id,
            tracking_code=archive_number, doc_name=title,
            note="صحت‌سنجی شماره بایگانی ناموفق"
        )
        return

else:
    # ═══════════════════════════════════════════════════════════════
    # مسیر شماره پرونده (کد قبلی - بدون تغییر)
    # ═══════════════════════════════════════════════════════════════
    
    logging.info(f"[LAVAYEH] Case number method: filling txtCaseNo with tracking_code={tracking_code}")
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
            "⚠️ *استعلام پرونده با خطا مواجه شد.*\\n\\n"
            "لطفاً موارد زیر را بررسی و اصلاح نمایید:\\n"
            "🔢 شماره پرونده\\n🔢 ردیف فرعی\\n🏙 استان\\n\\n"
            "سپس مجدداً «ثبت لایحه» را شروع کنید.")
        await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی پرونده کاربر {user_id} ناموفق.")
        runtime_state.active_lavayeh_users.discard(user_id)
        await log_event(
            "خطای سامانه", "لایحه", str(user_id), user_id,
            tracking_code=tracking_code, doc_name=title,
            note="صحت‌سنجی پرونده ناموفق"
        )
        return

# ادامه مراحل مشترک (ارائه‌کننده لایحه، متن، منضمات و ...)
# ...
"""


# ============================================================
# همچنین تابع _click_validate_with_retry_archive را اصلاح کنید:
# ============================================================

async def _click_validate_with_retry_archive(page, bot, user_id):
    """
    کلیک روی دکمه صحت‌سنجی اطلاعات برای شماره بایگانی.
    از دکمه btnAddHst2 استفاده می‌کند.
    """
    for attempt in range(5):
        logging.info(f"[LAVAYEH] _click_validate_with_retry_archive attempt {attempt + 1}")
        
        # اول سعی کن با ID کلیک کنی
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst2');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            // Fallback: پیدا کردن دکمه با متن
            const buttons = Array.from(document.querySelectorAll('button'));
            const targetBtn = buttons.find(b => 
                b.innerText && b.innerText.includes('صحت') && b.innerText.includes('سنجی')
            );
            if (targetBtn && !targetBtn.disabled) {
                targetBtn.click();
                return true;
            }
            return false;
        }''')
        
        if not clicked:
            logging.warning(f"[LAVAYEH] btnAddHst2 not found, trying text-based click")
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        
        await asyncio.sleep(12)
        
        # بررسی آیا popup خطا نمایش داده شده
        closed = await _close_error_popup(page)
        if closed:
            logging.warning(f"[LAVAYEH] Error popup closed, retrying...")
            await asyncio.sleep(5)
            continue
        
        # بررسی آیا جدول پرونده نمایش داده شده
        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        
        if has_table:
            logging.info(f"[LAVAYEH] Archive validation successful on attempt {attempt + 1}")
            return
        
        await asyncio.sleep(5)
    
    logging.warning(f"[LAVAYEH] Archive validation failed after 5 attempts")


# ============================================================
# مطمئن شوید که در lavayeh_handlers.py مقادیر درست ارسال می‌شوند:
# ============================================================

# در تابعی که data را برای process_lavayeh_task آماده می‌کند،
# مطمئن شوید که این فیلدها وجود دارند:

"""
data = {
    'user_id': message.from_user.id,
    'lavayeh_title': ...,
    'tracking_method': 'archive_number',  # یا 'case_number'
    
    # برای شماره بایگانی:
    'lavayeh_archive_number': archive_number,  # مثلا '9812345'
    'lavayeh_branch_code': branch_code,        # مثلا '12345' (5 رقمی)
    'lavayeh_branch_name': branch_name,        # نام شعبه (اختیاری)
    
    # برای شماره پرونده:
    'lavayeh_tracking_code': tracking_code,    # مثلا '140012345678901234'
    'lavayeh_province': province,              # مثلا 'تهران'
    'lavayeh_row_number': row_number,          # مثلا 1
    
    # سایر فیلدها:
    'lavayeh_persons': [...],
    'lavayeh_text': ...,
    'lavayeh_attachments': [...],
}
"""


# ============================================================
# در ابتدای تابع process_lavayeh_task، بررسی کنید که مقادیر درست هستند:
# ============================================================

"""
async def process_lavayeh_task(data: dict, bot: Bot):
    # ...
    
    tracking_method = data.get("tracking_method", "case_number")
    
    # برای شماره بایگانی
    archive_number = data.get("lavayeh_archive_number", "")
    branch_code = data.get("lavayeh_branch_code", "")
    branch_name = data.get("lavayeh_branch_name", "")
    
    # برای شماره پرونده
    tracking_code = data.get("lavayeh_tracking_code", "")
    province = data.get("lavayeh_province", "")
    row_number = data.get("lavayeh_row_number", 1)
    
    # لاگ برای دیباگ
    logging.info(
        f"[LAVAYEH] user={user_id} title={title} "
        f"tracking_method={tracking_method} "
        f"archive_number={archive_number} branch_code={branch_code} "
        f"tracking_code={tracking_code} province={province} row={row_number} "
        f"persons={len(persons)} attachment_groups={len(attachment_groups)}"
    )
    
    # اعتبارسنجی
    if tracking_method == "archive_number":
        if not archive_number or not branch_code:
            await bot.send_message(
                user_id,
                "⚠️ اطلاعات شماره بایگانی یا کد شعبه ناقص است. لطفاً مجدداً تلاش کنید.")
            runtime_state.active_lavayeh_users.discard(user_id)
            return
    else:
        if not tracking_code:
            await bot.send_message(
                user_id,
                "⚠️ شماره پرونده وارد نشده است. لطفاً مجدداً تلاش کنید.")
            runtime_state.active_lavayeh_users.discard(user_id)
            return
    
    # ادامه کد...
"""
