# پچ check_handlers.py + keyboards.py — ۴ باگ تایید‌شده در «ثبت تکی چک»

هر ۴ مورد را با گرفتن کد واقعی از خود فایل شما بررسی کردم؛ همه تایید شدند
(نه فرضی). ترتیب مطابق ترتیب تصاویر شماست.

──────────────────────────────────────────────────────────────────────────
## باگ ۱ (تصویر ۱) — «بازگشت» در مرحلهٔ «عنوان خواسته» کار نمی‌کند

### ریشهٔ باگ
`check_request_title_handler` (مرحلهٔ ۱) هیچ شاخه‌ای برای متن «🔙 بازگشت»
ندارد؛ چون «بازگشت» داخل لیست `["صدور اجرائیه چک", "مطالبه وجه چک"]` نیست،
می‌افتد در شاخهٔ خطا («لطفاً یکی از گزینه‌های موجود را انتخاب کنید») و
همان کیبورد را دوباره نشان می‌دهد — دقیقاً همان چیزی که در تصویر دیدید.

### محل: تابع `check_request_title_handler`

جایگزین کنید:
```python
@check_router.message(Form.check_request_title)
async def check_request_title_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["صدور اجرائیه چک", "مطالبه وجه چک"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=check_request_title_kb
        )
        return
```
با:
```python
@check_router.message(Form.check_request_title)
async def check_request_title_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت":
        await message.answer(
            "🏦 *ثبت دعاوی چک*\n\n"
            "آیا قصد ثبت *یک مورد دادخواست چک* دارید یا *بیش از ۵ مورد (ثبت دسته‌جمعی)*؟",
            reply_markup=check_choice_kb)
        await state.set_state(Form.check_request_type)
        return

    if text not in ["صدور اجرائیه چک", "مطالبه وجه چک"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=check_request_title_kb
        )
        return
```
(بقیهٔ تابع دست‌نخورده می‌ماند.)

──────────────────────────────────────────────────────────────────────────
## باگ ۲ (تصویر ۲) — دکمهٔ «افزودن خوانده دیگر» در بخش مطلع/گواه

### ریشهٔ باگ (دو جزء)
۱) `check_addressee_add_more_kb` در keyboards.py متن دکمه‌اش هاردکد
   «➕ افزودن خوانده دیگر» است — همین کیبورد در ۷ جای بخش **مطلع/گواه** هم
   استفاده می‌شود (خطوط ۷۶۲، ۹۰۵، ۹۴۷، ۹۵۹، ۹۹۲، ۱۰۷۲، ۱۶۲۰ در check_handlers.py)
   بدون اینکه جایی برای «خوانده» واقعی استفاده شود — یعنی این کیبورد در عمل
   فقط برای مطلع/گواه ساخته شده ولی برچسبش کپی‌پیست از خوانده مانده.
۲) حتی اگر برچسب درست بود، `check_witness_national_id_handler` اصلاً شاخه‌ای
   برای این دکمه ندارد (فقط «اتمام و ادامه» و «بازگشت» را می‌شناسد)، پس با
   زدنش، متن دکمه به‌عنوان کدملی پارس می‌شود و خطای «کدملی باید ۱۰ رقمی
   باشد» می‌دهد — یعنی عملاً هیچ عملی (نه گرفتن نوع شخصیت، نه کدملی) انجام
   نمی‌شود، دقیقاً مطابق چیزی که گفتید.

### محل ۱: keyboards.py — تغییر برچسب (فقط همین یک کیبورد، جای دیگری برایش استفاده نمی‌شود)
```python
check_addressee_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن مطلع یا گواه دیگر")],   # ⬅️ قبلاً: "➕ افزودن خوانده دیگر"
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="📞 استعلام شماره تماس")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)
```

### محل ۲: check_handlers.py — تابع `check_witness_national_id_handler`
باید شاخه‌ای برای دکمهٔ جدید اضافه شود (چون در این مرحله لازم نیست کاری
بکند جز اینکه دوباره از کاربر کدملی بخواهد — تایپ مستقیم کدملی همان‌کاری
است که این دکمه «باید» انجام دهد):

```python
@check_router.message(Form.check_witness_national_id)
async def check_witness_national_id_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "✅ اتمام و ادامه":
        await _ask_check_text(message, state)
        return
    if text == "➕ افزودن مطلع یا گواه دیگر":
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* را ارسال فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=check_addressee_add_more_kb)
        return
    if "بازگشت" in text:
        ...  # ادامه طبق باگ ۳ زیر
```

──────────────────────────────────────────────────────────────────────────
## باگ ۳ (تصویر ۳) — «بازگشت» از مطلع/گواه، خواندهٔ قبلی را پاک نمی‌کند

### ریشهٔ باگ
در `check_defendant_more_handler` (وقتی از «آیا خواندهٔ دیگری دارید؟»
برمی‌گردید)، کد درست این کار را می‌کند: قبل از دوباره‌پرسیدن نوع شخصیت،
آخرین خوانده را با `defendants.pop()` حذف می‌کند. اما در
`check_witness_national_id_handler` (وقتی از مرحلهٔ مطلع/گواه به همان
مقصد برمی‌گردید) این خط `pop()` فراموش شده — یعنی خواندهٔ قبلی در لیست
می‌ماند، و وقتی کاربر دوباره همان کدملی را وارد می‌کند، به‌عنوان «تکراری»
رد می‌شود و اصلاً راهی برای ادامه نیست (دقیقاً چیزی که در تصویر ۳ دیدید).

### محل: شاخهٔ «بازگشت» در `check_witness_national_id_handler`

جایگزین کنید:
```python
    if "بازگشت" in text:
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
        return
```
با:
```python
    if "بازگشت" in text:
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        if defendants:
            defendants.pop()  # ⬅️ خط جاافتاده — دقیقاً مثل check_defendant_more_handler
            await state.update_data(check_defendants=defendants)
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
        return
```

──────────────────────────────────────────────────────────────────────────
## باگ ۴ (تصویر ۴) — «اتمام ارسال تصاویر» در بخش مدارک اضافی کار نمی‌کند

### ریشهٔ باگ (تایید‌شده با قطعیت بالا — نه حدس)
سه هندلر روی state یکسان (`Form.check_attachment_images`) ثبت شده‌اند، به
همین ترتیب در فایل:
```
خط ۱۳۱۶: @check_router.message(Form.check_attachment_images, F.photo)                          → دریافت عکس
خط ۱۳۴۶: @check_router.message(Form.check_attachment_images)                                    → fallback عمومی (بدون فیلتر متن!)
خط ۱۳۷۰: @check_router.message(Form.check_attachment_images, F.text == "✅ اتمام ارسال تصاویر")  → هندلر واقعیِ اتمام
```
در aiogram، هندلرها به‌ترتیب ثبت بررسی می‌شوند و اولین موردی که فیلترش
پاس شود اجرا و باقی نادیده گرفته می‌شوند. چون هندلر خط ۱۳۴۶ **هیچ فیلتر
متنی ندارد** (فقط state)، هر پیام متنی — از جمله دقیقاً همان دکمهٔ
«✅ اتمام ارسال تصاویر» — را زودتر از خط ۱۳۷۰ می‌قاپد. یعنی هندلر خط ۱۳۷۰
عملاً **کد مرده** است و هرگز اجرا نمی‌شود. برای همین با زدن آن دکمه فقط
پیام fallback («⚠️ لطفاً تصویر ارسال فرمایید...») را می‌بینید.

### راه‌حل: فقط جابه‌جایی ترتیب دو تابع (خط ۱۳۴۶ و ۱۳۷۰)
هیچ منطقی عوض نمی‌شود — فقط تابع «اتمام» باید **قبل از** fallback عمومی
در فایل تعریف شود:

```python
# ⬅️ این تابع را اول بیاورید (دقیقاً همان کد قبلی خط ۱۳۷۰، بدون تغییر)
@check_router.message(Form.check_attachment_images, F.text == "✅ اتمام ارسال تصاویر")
async def check_attachment_images_done_handler(message: Message, state: FSMContext):
    ...  # بدنهٔ فعلی‌اش را عیناً همین‌جا نگه دارید


# ⬅️ این fallback را بعد از آن بیاورید (دقیقاً همان کد قبلی خط ۱۳۴۶)
@check_router.message(Form.check_attachment_images)
async def check_attachment_images_text_fallback(message: Message, state: FSMContext):
    ...  # بدنهٔ فعلی‌اش را عیناً همین‌جا نگه دارید
```

یعنی صرفاً محل دو تابع در فایل را با هم عوض کنید (کد داخلشان دست‌نخورده).
`F.photo` (خط ۱۳۱۶) چون فیلتر اختصاصی خودش را دارد و از قبل هم اول همه
ثبت شده، مشکلی ندارد و لازم نیست جابه‌جا شود.

### دربارهٔ «تصاویر دریافت نمی‌شود» (بخش دوم تصویر ۴)
با بررسی کد، `check_receive_attachment_photo` (خط ۱۳۱۶) به‌خودی‌خود درست
است. اما ترتیب معکوسِ شمارش در اسکرین‌شات شما («تصویر شماره ۶» قبل از
«تصویر شماره ۵») نشانهٔ کلاسیک یک **race condition** است: اگر چند عکس را
پشت‌سرهم و سریع بفرستید، چند نمونه از این هندلر تقریباً هم‌زمان اجرا
می‌شوند، هرکدام لیست `_current_attachment_images` را جداگانه از FSM
می‌خوانند، یکی به آن اضافه می‌کند و ذخیره می‌کند، و دیگری — که با نسخهٔ
قدیمی‌تر لیست کار می‌کند — دوباره ذخیره می‌کند و نتیجهٔ اولی را بی‌صدا
پاک می‌کند. این *مستقل* از باگ بالا است و راه‌حلش قفل‌کردن (lock) به‌ازای
هر کاربر روی این بخش از FSM است. اگر بخواهید همین الان این را هم برایتان
پیاده کنم (با `asyncio.Lock` سراسری keyed به `user_id`)، بگویید تا در
پاسخ بعدی انجامش بدهم — چون نیاز به دیدن نحوهٔ راه‌اندازی دیسپچر
(`dp = Dispatcher(...)`) در فایل اصلی ربات (احتمالاً `bot.py` یا
`main.py`) دارد که در ریپازیتوری فعلی برایم در دسترس نبود.
