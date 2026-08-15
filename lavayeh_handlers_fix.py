# ============================================================
# اصلاحات لازم برای lavayeh_handlers.py
# ============================================================

# مطمئن شوید که در هندلر نهایی (وقتی کاربر تایید می‌کند)،
# داده‌ها به درستی به process_lavayeh_task ارسال می‌شوند:

# پیدا کنید تابعی که job را به صف اضافه می‌کند و این‌طور تغییر دهید:

"""
# در هندلر تایید نهایی لایحه (مثلاً lavayeh_confirm_handler)

@lavayeh_router.message(Form.lavayeh_confirm, F.text == "✅ تایید و دریافت فاکتور پرداخت")
async def lavayeh_confirm_yes_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    
    tracking_method = data.get("tracking_method", "case_number")
    
    # ساخت دیکشنری job با تمام اطلاعات لازم
    job_data = {
        'user_id': message.from_user.id,
        'lavayeh_title': data.get("lavayeh_title", "لایحه دفاعیه"),
        'lavayeh_system_title': data.get("lavayeh_system_title", data.get("lavayeh_title", "لایحه دفاعیه")),
        'tracking_method': tracking_method,
        'lavayeh_persons': data.get("lavayeh_persons", []),
        'lavayeh_text': data.get("lavayeh_text", ""),
        'lavayeh_attachments': data.get("lavayeh_attachments", []),
    }
    
    # اضافه کردن فیلدهای مخصوص هر روش
    if tracking_method == "archive_number":
        # روش شماره بایگانی
        job_data['lavayeh_archive_number'] = data.get("lavayeh_archive_number", "")
        job_data['lavayeh_branch_code'] = data.get("lavayeh_branch_code", "")
        job_data['lavayeh_branch_name'] = data.get("lavayeh_branch_name", "")
        
        # مقادیر شماره پرونده را None یا خالی بگذارید
        job_data['lavayeh_tracking_code'] = None
        job_data['lavayeh_province'] = None
        job_data['lavayeh_row_number'] = None
        
    else:
        # روش شماره پرونده
        job_data['lavayeh_tracking_code'] = data.get("lavayeh_tracking_code", "")
        job_data['lavayeh_province'] = data.get("lavayeh_province", "")
        job_data['lavayeh_row_number'] = data.get("lavayeh_row_number", 1)
        
        # مقادیر بایگانی را None یا خالی بگذارید
        job_data['lavayeh_archive_number'] = None
        job_data['lavayeh_branch_code'] = None
        job_data['lavayeh_branch_name'] = None
    
    # اضافه کردن به صف
    await runtime_state.lavayeh_queue.put(job_data)
    
    # ...
"""


# ============================================================
# همچنین در هندلر دریافت شماره بایگانی:
# ============================================================

"""
@lavayeh_router.message(Form.lavayeh_archive_number)
async def lavayeh_archive_number_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    
    if message.text == "🔙 بازگشت":
        # برگشت به مرحله قبل
        await message.answer("🏛 لطفاً شعبه را انتخاب فرمایید:", reply_markup=lavayeh_branch_input_method_kb)
        await state.set_state(Form.lavayeh_branch_input_method)
        return
    
    archive_num = _to_en(message.text)
    
    # اعتبارسنجی شماره بایگانی
    is_valid, result = validate_archive_number(archive_num)
    if not is_valid:
        await message.answer(result)
        return
    
    # ذخیره شماره بایگانی
    await state.update_data(
        lavayeh_archive_number=archive_num,
        tracking_method="archive_number"  # مهم: این را حتماً ست کنید
    )
    
    # رفتن به مرحله بعد (نوع شخص)
    await message.answer(
        "✅ شماره بایگانی ثبت شد.\\n\\n"
        "👤 لطفاً نوع شخصیت ارائه‌دهنده لایحه را انتخاب فرمایید:",
        reply_markup=create_person_type_kb())
    await state.set_state(Form.lavayeh_person_type)
"""


# ============================================================
# در هندلر انتخاب شعبه (بعد از انتخاب از درخت شعب):
# ============================================================

"""
# وقتی کاربر شعبه را از لیست انتخاب می‌کند:

async def save_selected_branch(message: Message, state: FSMContext, branch_code: str, branch_name: str):
    # ذخیره کد شعبه (5 رقمی)
    await state.update_data(
        lavayeh_branch_code=branch_code,  # مثلاً "12345"
        lavayeh_branch_name=branch_name,   # مثلاً "شعبه اول حقوقی تهران"
        tracking_method="archive_number"   # مهم!
    )
    
    await message.answer(
        f"✅ شعبه انتخاب شد:\\n"
        f"🏛 *{branch_name}*\\n"
        f"🔢 کد: `{branch_code}`\\n\\n"
        f"🔢 لطفاً شماره بایگانی پرونده را وارد کنید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.lavayeh_archive_number)
"""


# ============================================================
# در هندلر انتخاب روش ورود اطلاعات:
# ============================================================

"""
@lavayeh_router.message(Form.lavayeh_tracking_method)
async def lavayeh_tracking_method_handler(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer("📝 لطفاً عنوان لایحه را انتخاب فرمایید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return
    
    if "شماره پرونده" in text or "1️⃣" in text:
        # روش شماره پرونده
        await state.update_data(tracking_method="case_number")
        await message.answer(
            "🔢 لطفاً *شماره پرونده* را وارد کنید:\\n"
            "_(۱۶ یا ۱۸ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_tracking_code)
        
    elif "بایگانی" in text or "2️⃣" in text:
        # روش شماره بایگانی
        await state.update_data(tracking_method="archive_number")
        await message.answer(
            "🏛 لطفاً شعبه رسیدگی‌کننده را انتخاب فرمایید:",
            reply_markup=lavayeh_branch_input_method_kb)
        await state.set_state(Form.lavayeh_branch_input_method)
    
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:")
"""


# ============================================================
# دیباگ: اضافه کردن لاگ در build_preview
# ============================================================

"""
def build_preview(data: dict) -> str:
    tracking_method = data.get("tracking_method", "case_number")
    
    # لاگ برای دیباگ
    import logging
    logging.info(f"[PREVIEW] tracking_method={tracking_method}")
    logging.info(f"[PREVIEW] archive_number={data.get('lavayeh_archive_number')}")
    logging.info(f"[PREVIEW] branch_code={data.get('lavayeh_branch_code')}")
    logging.info(f"[PREVIEW] tracking_code={data.get('lavayeh_tracking_code')}")
    
    # ...
"""
