# پچ check_handlers.py — جایگزینی درخت انتخاب دادگاه چک

هدف: در بخش چک، دیگر از branches.py/units_compact.json (که زیرشعبه‌های
«اجرای احکام» را هم نشان می‌دهد) استفاده نشود؛ به‌جایش از
check_branches_tree.py (ساخته‌شده از units_output.csv شما) استفاده شود.
مسیر لایحه (branches.py) دست‌نخورده می‌ماند.

## ۱) ایمپورت (بالای فایل، خط ۵۴)

جایگزین کنید:
```python
from branches import create_branches_keyboard, ROOT_NODES, ID_TO_INDEX
```
با:
```python
from branches import create_branches_keyboard, ROOT_NODES, ID_TO_INDEX  # همچنان برای لایحه لازم است، دست نزنید
from check_branches_tree import (
    create_check_branch_keyboard, ROOT_NODES as CHECK_ROOT_NODES,
    get_children as check_get_children, has_children as check_has_children,
    PATH_TO_ROW as CHECK_PATH_TO_ROW, PATH_TO_INDEX as CHECK_PATH_TO_INDEX,
    INDEX_TO_PATH as CHECK_INDEX_TO_PATH, _normalize as check_normalize,
)
```

## ۲) تابع `_ask_check_branch` (خط ۱۴۱۸)

جایگزین کنید:
```python
async def _ask_check_branch(message: Message, state: FSMContext):
    await message.answer(
        "🏛 *مرحله ۱۱:* لطفاً از طریق جدول زیر، *صلاحیت دادگاه* خود را انتخاب کنید:",
        reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
    await state.set_state(Form.check_branch_code)
```
با:
```python
async def _ask_check_branch(message: Message, state: FSMContext):
    await message.answer(
        "🏛 *مرحله ۱۱:* لطفاً از طریق جدول زیر، *صلاحیت دادگاه* خود را انتخاب کنید:",
        reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
    await state.set_state(Form.check_branch_code)
```

## ۳) کل تابع `check_branch_callback` (خط ۱۶۴۶ تا ۱۷۴۱)

فیلتر callback را از `F.data.startswith("br:")` به `F.data.startswith("cbr:")`
تغییر دهید و کل بدنه را با نسخهٔ مبتنی بر path جایگزین کنید:

```python
@check_router.callback_query(F.data.startswith("cbr:"))
async def check_branch_callback(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Form.check_branch_code:
        return

    await callback.answer()

    data_parts = callback.data.split(":")
    action = data_parts[1]

    if action == "root":
        await callback.message.edit_text(
            "🏛 *انتخاب صلاحیت دادگاه*\n\n"
            "لطفاً از لیست زیر انتخاب کنید:",
            reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
        return

    idx = int(data_parts[2])
    norm_path = CHECK_INDEX_TO_PATH.get(idx)

    if not norm_path or norm_path not in CHECK_PATH_TO_ROW:
        await callback.message.edit_text("❌ خطا: واحد مورد نظر یافت نشد.")
        return

    node = CHECK_PATH_TO_ROW[norm_path]

    if action == "open":
        children = check_get_children(norm_path)
        if not children:
            await callback.message.edit_text(f"ℹ️ واحد «{node['name']}» فرزندی ندارد.")
            return
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"📁 *{node['name']}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=node["path"]))

    elif action == "page":
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        children = check_get_children(norm_path)
        await callback.message.edit_reply_markup(
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=node["path"])
        )

    elif action == "back":
        parent_norm_path = CHECK_INDEX_TO_PATH.get(idx)
        if not parent_norm_path or parent_norm_path not in CHECK_PATH_TO_ROW:
            await callback.message.edit_text(
                "🏛 *انتخاب صلاحیت دادگاه*\n\n"
                "لطفاً از لیست زیر انتخاب کنید:",
                reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
            return
        parent_node = CHECK_PATH_TO_ROW[parent_norm_path]
        children = check_get_children(parent_norm_path)
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"📁 *{parent_node['name']}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=parent_node["path"]))

    elif action == "sel":
        branch_code = node["code"]
        if not branch_code:
            await callback.answer("⚠️ این واحد فاقد کد است و قابل انتخاب نیست.", show_alert=True)
            return

        branch_name = node["name"]
        branch_path = node["path"]

        await callback.message.edit_text(
            f"📋 *اطلاعات واحد*\n\n"
            f"📌 نام: *{branch_name}*\n"
            f"🔢 کد: `{branch_code}`\n"
            f"🗂 مسیر:\n`{branch_path}`\n"
        )

        await state.update_data(
            check_branch_name=branch_name,
            check_branch_code=branch_code,
            check_branch_path=branch_path,
        )

        await callback.message.answer(
            f"✅ *دادگاه انتخاب شد:*\n\n"
            f"📋 نام: *{branch_name}*\n"
            f"🔢 کد: `{branch_code}`")

        from check_handlers import _go_to_check_preview
        await _go_to_check_preview(callback.message, state)
```

## چرا کد callback (`idx`) هنوز کار می‌کند؟

در نسخهٔ قدیم `idx` معادل شمارهٔ index در آرایهٔ units_compact.json بود و
از طریق `INDEX_TO_ID` به Id واقعی نود map می‌شد. در نسخهٔ جدید همان الگو را
با `CHECK_INDEX_TO_PATH` (index → مسیر نرمال‌شده) و `CHECK_PATH_TO_ROW`
(مسیر نرمال‌شده → ردیف کامل) پیاده کرده‌ام — یعنی هیچ تغییری در طول/فرمت
callback_data لازم نبود، فقط منبع داده عوض شد.

## نکتهٔ دیگر — دو راه‌حل قبلی من

فایل‌های `check_branches_lookup.py` (برای اکسل دسته‌جمعی — تطبیق متنی نام)
و این `check_branches_tree.py` (برای منوی تعاملی تک‌ثبتی) هر دو از همان
units_output.csv می‌خوانند ولی برای دو مصرف متفاوت‌اند؛ لازم نیست ادغام
شوند — هرکدام برای همان مسیرش (اکسل / دکمه‌های تلگرام) باقی می‌ماند.
