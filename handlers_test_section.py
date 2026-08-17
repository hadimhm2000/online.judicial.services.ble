# ================= بخش تست مدیر (منضمات / امضا) =================

@router.message(Form.test_mode_tracking_code)
async def test_mode_receive_tracking_code(message: types.Message, state: FSMContext):
    """دریافت کدرهگیری از مدیر در حالت تست."""
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    clean_code = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()

    if not re.match(r'^[0-9]+$', clean_code) or not _is_valid_tracking_code(clean_code):
        await message.answer("⚠️ کدرهگیری نامعتبر است. لطفاً یک کدرهگیری ۱۶ رقمی معتبر ارسال فرمایید:")
        return

    await state.update_data(
        test_tracking_code=clean_code,
        test_attachments=[],
        test_images=[])
    await message.answer(
        f"✅ کدرهگیری `{clean_code}` دریافت شد.\n\n"
        f"🧪 *حالت تست* — تست بابت کدام مورد است؟",
        reply_markup=test_mode_doc_type_kb)
    await state.set_state(Form.test_mode_doc_type)


@router.message(Form.test_mode_doc_type)
async def test_mode_doc_type(message: types.Message, state: FSMContext):
    """انتخاب نوع سند: لایحه یا اظهارنامه."""
    if not message.text:
        return

    if "انصراف" in message.text:
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    if "لایحه" in message.text:
        doc_type = "لایحه"
    elif "اظهارنامه" in message.text:
        doc_type = "اظهارنامه"
    elif "اعتراضی" in message.text:
        doc_type = "دعاوی اعتراضی"
    elif "اعلام وکالت" in message.text:
        doc_type = "اعلام وکالت"
    else:
        await message.answer("لطفاً یکی از گزینه‌های بالا را انتخاب کنید:", reply_markup=test_mode_doc_type_kb)
        return

    await state.update_data(test_doc_type=doc_type)
    data = await state.get_data()
    tracking_code = data['test_tracking_code']

    await message.answer(
        f"🔖 کدرهگیری: `{tracking_code}`\n"
        f"📂 نوع: *{doc_type}*\n\n"
        f"آیا می‌خواهید کدام بخش را تست کنید؟",
        reply_markup=test_mode_section_kb)
    await state.set_state(Form.test_mode_section_select)


@router.message(Form.test_mode_section_select)
async def test_mode_section_select(message: types.Message, state: FSMContext):
    """انتخاب بخش تست: منضمات یا امضا."""
    if not message.text:
        return

    if "انصراف" in message.text:
        await message.answer("🧪 *حالت تست* — تست بابت کدام مورد است؟", reply_markup=test_mode_doc_type_kb)
        await state.set_state(Form.test_mode_doc_type)
        return

    data = await state.get_data()
    tracking_code = data['test_tracking_code']
    doc_type = data['test_doc_type']
    user_id = message.from_user.id

    if "منضمات" in message.text:
        # شروع حلقه جمع‌آوری منضمات
        await state.update_data(test_attachments=[], test_images=[])

        # اگر نوع اعلام وکالت باشد، ابتدا حلقه نماینده حقوقی طی شود
        if doc_type == "اعلام وکالت":
            await message.answer(
                "👔 *سمت نماینده حقوقی* در اعلام وکالت را انتخاب کنید:",
                reply_markup=test_mode_ealam_representative_kb)
            await state.set_state(Form.test_mode_ealam_representative_type)
        else:
            await message.answer(
                "📎 مدارک و نام عنوان را ارسال کنید:",
                reply_markup=test_mode_att_title_kb_first)
            await state.set_state(Form.test_mode_attachment_title)

    elif "ثبت کامل" in message.text and "اعتراضی" in message.text:
        # تست ثبت کامل دعوی اعتراضی — ورود به فلوی دعاوی اعتراضی
        from tajdid_nazar_handlers import tajdid_nazar_entry
        await tajdid_nazar_entry(message, state)

    elif "امضا" in message.text:
        await message.answer(
            f"🧪 *تست امضا شروع شد...*\n\n"
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"⏳ در حال ناوبری به بخش امضا...")

        if doc_type == "لایحه":
            sign_task_type = "LAVAYEH_SEND_SIGN_CODE"
            runtime_state.pending_lavayeh_sign[user_id] = {
                "tracking_code": tracking_code,
                "is_test": True,
            }
        elif doc_type == "اعلام وکالت":
            # اعلام وکالت امضای جداگانه ندارد — مستقیم به منضمات می‌رود
            await message.answer(
                "⚠️ اعلام وکالت بخش امضای جداگانه ندارد.\n"
                "لطفاً از گزینه *تست بخش منضمات* استفاده کنید.",
                reply_markup=test_mode_section_kb)
            return
        else:
            sign_task_type = "EZHHARNAMEH_SEND_SIGN_CODE"
            runtime_state.pending_ezhhar_sign[user_id] = {
                "tracking_code": tracking_code,
                "is_test": True,
                "is_ezhharnameh": True,
            }

        await runtime_state.job_queue.put({
            'user_id': user_id,
            'task_type': sign_task_type,
            'tracking_code': tracking_code,
            'phase': 'navigate',
            'doc_category': doc_type,
        })
        await state.clear()

    elif "هزینه" in message.text:
        # تست بخش هزینه — ارسال به صف مرورگر
        await message.answer(
            f"🧪 *تست هزینه شروع شد...*\n\n"
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"⏳ در حال ناوبری و محاسبه هزینه...")

        await runtime_state.job_queue.put({
            'user_id': user_id,
            'task_type': 'TEST_COST',
            'tracking_code': tracking_code,
            'doc_category': doc_type,
        })
        await state.clear()


# ── حلقه نماینده حقوقی در تست اعلام وکالت ──────────────

@router.message(Form.test_mode_ealam_representative_type)
async def test_mode_ealam_representative(message: types.Message, state: FSMContext):
    """دریافت سمت نماینده حقوقی در تست اعلام وکالت."""
    text = message.text or ""
    if not text:
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    # ثبت سمت نماینده حقوقی
    await state.update_data(test_ealam_representative_type=text)
    await message.answer(
        f"✅ سمت نماینده حقوقی «*{text}*» ثبت شد.\n\n"
        f"🔢 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n"
        f"_(۱۶ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.test_mode_ealam_contract_number)


@router.message(Form.test_mode_ealam_contract_number)
async def test_mode_ealam_contract(message: types.Message, state: FSMContext):
    """دریافت شماره قرارداد وکالت در تست اعلام وکالت."""
    text = (message.text or "").strip()
    if not text:
        return

    if text == "🔙 بازگشت":
        await message.answer(
            "👔 *سمت نماینده حقوقی* در اعلام وکالت را انتخاب کنید:",
            reply_markup=test_mode_ealam_representative_kb)
        await state.set_state(Form.test_mode_ealam_representative_type)
        return

    clean = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()

    if not clean.isdigit() or len(clean) != 16:
        await message.answer(
            "⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد.\n"
            f"شماره وارد شده *{len(clean)} رقمی* است. مجدداً وارد کنید:")
        return

    await state.update_data(test_ealam_contract_number=clean)
    await message.answer(
        f"✅ شماره قرارداد `{clean}` ثبت شد.\n\n"
        f"💰 *مقدار تمبر ابطالی:*\n\n"
        f"اگر مقدار تمبر را به ریال می‌دانید، عدد را وارد کنید.\n"
        f"در غیر این صورت از گزینه‌های زیر استفاده کنید:",
        reply_markup=test_mode_ealam_stamp_kb)
    await state.set_state(Form.test_mode_ealam_stamp_amount)


@router.message(Form.test_mode_ealam_stamp_amount)
async def test_mode_ealam_stamp(message: types.Message, state: FSMContext):
    """دریافت مقدار تمبر در تست اعلام وکالت."""
    text = (message.text or "").strip()
    if not text:
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    if "بدون تمبر" in text:
        await state.update_data(test_ealam_stamp_amount=0, test_ealam_stamp_type="بدون تمبر")
        await _test_mode_ealam_goto_attachments(message, state)
        return

    # کاربر عدد وارد کرده
    amount_str = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    if amount_str.isdigit() and int(amount_str) > 0:
        stamp_amount = int(amount_str)
        await state.update_data(test_ealam_stamp_amount=stamp_amount, test_ealam_stamp_type="مشخص")
        await message.answer(
            f"✅ مقدار تمبر *{stamp_amount:,} ریال* ثبت شد.")
        await _test_mode_ealam_goto_attachments(message, state)
        return

    await message.answer(
        "⚠️ لطفاً مقدار تمبر را به *ریال* وارد کنید یا از گزینه‌های زیر استفاده کنید:",
        reply_markup=test_mode_ealam_stamp_kb)


async def _test_mode_ealam_goto_attachments(message: types.Message, state: FSMContext):
    """پس از ثبت نماینده حقوقی و قرارداد، ورود به حلقه منضمات."""
    data = await state.get_data()
    representative_type = data.get('test_ealam_representative_type', '')
    contract_number = data.get('test_ealam_contract_number', '')
    stamp_amount = data.get('test_ealam_stamp_amount', 0)

    await message.answer(
        f"📋 *خلاصه اطلاعات اعلام وکالت:*\n\n"
        f"👔 سمت نماینده: *{representative_type}*\n"
        f"📑 شماره قرارداد: `{contract_number}`\n"
        f"💰 تمبر: *{stamp_amount:,} ریال*\n\n"
        f"📎 حالا مدارک و نام عنوان را ارسال کنید:",
        reply_markup=test_mode_att_title_kb_first)
    await state.set_state(Form.test_mode_attachment_title)


# ── حلقه جمع‌آوری منضمات (همان حلقه لایحه/اظهارنامه) ──────────────

@router.message(Form.test_mode_attachment_title)
async def test_mode_att_title(message: types.Message, state: FSMContext):
    """دریافت عنوان مدرک در حالت تست."""
    text = (message.text or "").strip()
    if not text:
        return

    data = await state.get_data()
    attachments = data.get('test_attachments', [])

    # رد کردن — بدون مدرک
    if "رد کردن" in text:
        if not attachments:
            # هیچ مدرکی جمع‌آوری نشده → مستقیم ارسال به صف
            await _test_mode_send_attachments_task(message, state)
            return
        # مدرکهایی وجود دارد → ادامه به مرحله بعد
        await _test_mode_send_attachments_task(message, state)
        return

    # انصراف
    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    # ثبت عنوان
    if "عنوان مهم نیست" in text:
        title = "مستندات"
    else:
        title = text

    await state.update_data(_test_current_att_title=title, test_images=[])
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        f"🖼 لطفاً تصاویر مربوط به این مدرک را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        f"پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.test_mode_attachment_images)


@router.message(Form.test_mode_attachment_images, F.photo)
async def test_mode_receive_image(message: types.Message, state: FSMContext):
    """دریافت تصاویر مدرک در حالت تست."""
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get('test_images', [])

    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.")
        return

    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(test_images=images)

    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")],
        ],
        resize_keyboard=True
    )
    remaining = MAX_IMAGES_PER_TITLE - len(images)
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n"
        f"مجموع تصاویر این مدرک: *{len(images)}* از {MAX_IMAGES_PER_TITLE}\n\n"
        f"می‌توانید تصاویر بیشتری ارسال کنید ({remaining} جای باقیمانده)\n"
        f"یا دکمه «اتمام ارسال تصاویر» را بزنید.",
        reply_markup=manage_kb)


@router.message(Form.test_mode_attachment_images, F.document)
async def test_mode_reject_document(message: types.Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت *عکس (Photo)* ارسال کنید، نه فایل.")


@router.message(Form.test_mode_attachment_images, F.text == "🗑 حذف تصویر")
async def test_mode_ask_delete_image(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get('test_images', [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    for i, fid in enumerate(images):
        await bot.send_photo(message.chat.id, photo=fid, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_test_deleting_image=True)


@router.message(Form.test_mode_attachment_images)
async def test_mode_images_text(message: types.Message, state: FSMContext):
    """هدلر متنی در حالت دریافت تصاویر — اتمام / حذف."""
    text = message.text or ""
    data = await state.get_data()
    images = data.get('test_images', [])
    deleting = data.get('_test_deleting_image', False)

    if deleting:
        num_str = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(test_images=images, _test_deleting_image=False)
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="🗑 حذف تصویر")],
                        ],
                        resize_keyboard=True
                    )
                else:
                    manage_kb = ReplyKeyboardRemove()
                await message.answer(
                    f"✅ تصویر شماره *{idx+1}* حذف شد.\n"
                    f"مجموع باقیمانده: *{len(images)} تصویر*",
                    reply_markup=manage_kb)
                return
        await state.update_data(_test_deleting_image=False)
        await message.answer("⚠️ شماره نامعتبر بود. لطفاً دوباره تلاش کنید.")
        return

    if "اتمام" in text:
        title = data.get('_test_current_att_title', 'مستندات')
        attachments = data.get('test_attachments', [])
        attachments.append({'title': title, 'images': list(images)})
        await state.update_data(test_attachments=attachments, test_images=[])

        await message.answer(
            f"✅ مدرک «*{title}*» با *{len(images)}* تصویر ثبت شد.\n\n"
            f"آیا مدرک دیگری هم دارید؟",
            reply_markup=test_mode_att_more_kb)
        await state.set_state(Form.test_mode_attachment_more)
        return

    await message.answer("لطفاً تصاویر را ارسال کنید یا دکمه «اتمام ارسال تصاویر» را بزنید.")


@router.message(Form.test_mode_attachment_more)
async def test_mode_attachment_more(message: types.Message, state: FSMContext):
    """آیا مدرک دیگری هست؟"""
    text = message.text or ""

    if "بله" in text and "مدرک" in text:
        await state.update_data(test_images=[])
        await message.answer(
            "📄 *عنوان مدرک بعدی:*\n\n"
            "در صورتی که تصویری برای ضمیمه دارید، عنوان آن را تایپ کنید\n"
            "یا یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=test_mode_att_title_kb)
        await state.set_state(Form.test_mode_attachment_title)
        return

    if "خیر" in text and "ادامه" in text:
        await _test_mode_send_attachments_task(message, state)
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=test_mode_att_more_kb)


async def _test_mode_send_attachments_task(message: types.Message, state: FSMContext):
    """ارسال تسک تست منضمات به صف مرورگر — از همان حلقه آپلود منضمات."""
    data = await state.get_data()
    tracking_code = data['test_tracking_code']
    doc_type = data['test_doc_type']
    attachments = data.get('test_attachments', [])
    user_id = message.from_user.id

    # نمایش خلاصه مدارک جمع‌آوری شده
    summary_lines = []
    total_images = 0
    for i, att in enumerate(attachments):
        img_count = len(att.get('images', []))
        total_images += img_count
        summary_lines.append(f"  {i+1}. *{att['title']}* — {img_count} تصویر")

    if not summary_lines:
        summary = "(بدون مدرک)"
    else:
        summary = "\n".join(summary_lines)

    # اطلاعات ویژه اعلام وکالت
    ealam_info = ""
    task_type = 'TEST_ATTACHMENTS'
    job_data = {
        'user_id': user_id,
        'task_type': task_type,
        'tracking_code': tracking_code,
        'doc_category': doc_type,
        'test_attachments': attachments,
    }

    if doc_type == "اعلام وکالت":
        representative_type = data.get('test_ealam_representative_type', '')
        contract_number = data.get('test_ealam_contract_number', '')
        stamp_amount = data.get('test_ealam_stamp_amount', 0)
        stamp_type = data.get('test_ealam_stamp_type', '')

        ealam_info = (
            f"\n👔 سمت نماینده: *{representative_type}*\n"
            f"📑 شماره قرارداد: `{contract_number}`\n"
            f"💰 تمبر: *{stamp_amount:,} ریال* ({stamp_type})\n"
        )
        job_data['test_ealam_representative_type'] = representative_type
        job_data['test_ealam_contract_number'] = contract_number
        job_data['test_ealam_stamp_amount'] = stamp_amount
        job_data['test_ealam_stamp_type'] = stamp_type

    await message.answer(
        f"🧪 *تست منضمات شروع شد...*\n\n"
        f"🔖 کدرهگیری: `{tracking_code}`\n"
        f"📂 نوع: *{doc_type}*\n"
        f"📎 تعداد مدارک: *{len(attachments)}* ({total_images} تصویر)\n"
        f"{ealam_info}\n"
        f"*لیست مدارک:*\n{summary}\n\n"
        f"⏳ در حال اجرای حلقه منضمات...")

    await runtime_state.job_queue.put(job_data)
    await state.clear()
