"""همه‌ی کیبوردهای تلگرام (ReplyKeyboardMarkup) و منوی دسته‌بندی‌ها/زیردسته‌ها یک‌جا اینجا هستند."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

restart_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 ثبت درخواست جدید (شروع)")]], resize_keyboard=True)
new_lavayeh_request_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="ثبت درخواست جدید")]], resize_keyboard=True)
back_only_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 بازگشت")]], resize_keyboard=True)
accept_rules_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ قوانین و مقررات را تایید می‌نمایم")]], resize_keyboard=True)

# آیدی مدیر مجاز به مشاهده بخش تست
TEST_VISIBLE_USER_ID = 509108833

def get_flow_type_kb(user_id: int) -> ReplyKeyboardMarkup:
    """کیبورد منوی اصلی — دکمه تست فقط برای کاربر مجاز."""
    rows = [
        [KeyboardButton(text="🔍 استعلام"), KeyboardButton(text="📦 استعلام (چند مورد همزمان)")],
        [KeyboardButton(text="✍️ ثبت لایحه"), KeyboardButton(text="📄 ثبت اظهارنامه")],
        [KeyboardButton(text="⚖️ دعاوی اعتراضی"), KeyboardButton(text="🏦 ثبت دادخواست چک")],
        [KeyboardButton(text="💰 محاسبه تمبر"), KeyboardButton(text="🔧 ابزار فایل")],
    ]
    if user_id == TEST_VISIBLE_USER_ID:
        rows.append([KeyboardButton(text="🧪 تست")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

# کیبورد بدون تست (fallback)
flow_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 استعلام"), KeyboardButton(text="📦 استعلام (چند مورد همزمان)")],
        [KeyboardButton(text="✍️ ثبت لایحه"), KeyboardButton(text="📄 ثبت اظهارنامه")],
        [KeyboardButton(text="⚖️ دعاوی اعتراضی"), KeyboardButton(text="🏦 ثبت دادخواست چک")],
        [KeyboardButton(text="💰 محاسبه تمبر"), KeyboardButton(text="🔧 ابزار فایل")],
    ], resize_keyboard=True)

# =========================================================
# کیبوردهای بخش ابزار فایل
# =========================================================
file_tools_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🖼 کاهش حجم عکس")],
        [KeyboardButton(text="📄➡️🖼 تبدیل PDF به عکس")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
    ], resize_keyboard=True)

file_tools_back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 بازگشت")]], resize_keyboard=True)

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ استعلام لوایح، اظهارنامه، دادخواست و ...")],
        [KeyboardButton(text="2️⃣ استعلام براساس شماره تماس")],
        [KeyboardButton(text="3️⃣ استعلام براساس کدملی")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ], resize_keyboard=True)

doc_category_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="لایحه"), KeyboardButton(text="اظهارنامه")],
        [KeyboardButton(text="شکواییه"), KeyboardButton(text="دادخواست بدوی")],
        [KeyboardButton(text="دعاوی دادگاههای صلح")],
        [KeyboardButton(text="دعاوی اعتراضی"), KeyboardButton(text="دعاوی طاری")],
        [KeyboardButton(text="شورای حل اختلاف"), KeyboardButton(text="دیوان عدالت اداری")]
    ], resize_keyboard=True)

attachments_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 بله، پیوست‌ها هم ارسال شوند")],
        [KeyboardButton(text="📄 خیر، فقط چاپ اصلی کافی است")]
    ], resize_keyboard=True)

cart_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ثبت استعلام جدید (افزودن به سبد)")],
        [KeyboardButton(text="🛒 مشاهده سبد خرید و تسویه حساب")],
        [KeyboardButton(text="🧹 خالی کردن سبد استعلام")]
    ], resize_keyboard=True)

pay_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 پرداخت و تسویه حساب")],
        [KeyboardButton(text="🔙 بازگشت به سبد خرید")]
    ], resize_keyboard=True)

SUB_MENUS = {
    "دعاوی اعتراضی": [
        "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
        "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
        "اعتراض ثالث", "اعتراض به قرار دادسرا"
    ],
    "دعاوی طاری": [
        "دعوای تقابل", "دعوای ورود ثالث", "دعوای جلب ثالث"
    ],
    "شورای حل اختلاف": [
        "دعاوی حقوقی", "دعاوی کیفری",
        "تجدیدنظرخواهی شورا", "واخواهی شورا", "اعتراض ثالث شورا"
    ],
    "دیوان عدالت اداری": [
        "دادخواست بدوی دیوان عدالت اداری", "تجدیدنظرخواهی دیوان عدالت اداری",
        "ارایه و پیگیری لایحه", "جلب ثالث در بدوی دیوان عدالت اداری",
        "ورود ثالث در بدوی دیوان عدالت اداری", "جلب ثالث درتجدید نظر دیوان عدالت اداری",
        "ورود ثالث درتجدید نظر دیوان عدالت اداری", "دادخواست اعتراض ثالث دیوان عدالت اداری",
        "اعاده دادرسی دیوان عدالت اداری", "اعتراض به آراء و تصمیمات مراجع اختصاصی اداری",
        "درخواست اعمال ماده 79 قانون دیوان عدالت اداری"
    ]
}

confirm_single_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ تایید و دریافت فاکتور پرداخت"), KeyboardButton(text="❌ انصراف و اصلاح اطلاعات")]], resize_keyboard=True)
confirm_cart_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ افزودن به سبد خرید"), KeyboardButton(text="❌ انصراف و اصلاح اطلاعات")]], resize_keyboard=True)
payment_cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ انصراف")]], resize_keyboard=True)
admin_login_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ ورودم تکمیل شد")]], resize_keyboard=True)

def create_submenu_kb(category_name):
    items = SUB_MENUS.get(category_name, [])
    keyboard = []
    for i in range(0, len(items), 2):
        row = [KeyboardButton(text=items[i])]
        if i + 1 < len(items):
            row.append(KeyboardButton(text=items[i+1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🔙 بازگشت به منوی قبل")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# =========================================================
# کیبوردهای بخش لایحه
# =========================================================

LAVAYEH_TITLES = [
    "لایحه دفاعیه",
    "صدور اجرائیه",
    "اعتراض به نظر کارشناس",
    "اعتراض به قرار رد دفتر",
    "اعلام وکالت",
    "درخواست ممنوعیت از خروج کشور",
    "درخواست کپی از مدارک پرونده",
    "درخواست مطالعه پرونده",
    "سایر عناوین"
]

lavayeh_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="لایحه دفاعیه"), KeyboardButton(text="صدور اجرائیه")],
        [KeyboardButton(text="اعتراض به نظر کارشناس")],
        [KeyboardButton(text="اعتراض به قرار رد دفتر")],
        [KeyboardButton(text="اعلام وکالت")],
        [KeyboardButton(text="درخواست ممنوعیت از خروج کشور")],
        [KeyboardButton(text="درخواست کپی از مدارک پرونده")],
        [KeyboardButton(text="درخواست مطالعه پرونده")],
        [KeyboardButton(text="سایر عناوین")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

# کیبورد انتخاب روش ورود شماره پرونده
lavayeh_tracking_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ شماره پرونده و ردیف فرعی")],
        [KeyboardButton(text="2️⃣ شعبه رسیدگی کننده و شماره بایگانی")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

# کیبورد انتخاب نحوه ورود نام شعبه
# گزینه ورود دستی حذف شد - فقط انتخاب از لیست
lavayeh_branch_input_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 انتخاب شعبه از لیست")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

TEHRAN_CITY_LABEL = "واحدهای قضایی مستقر در شهر تهران"
TEHRAN_PROVINCE_EXCL_LABEL = "واحدهای قضایی مستقر در استان تهران به جز شهر تهران"

PROVINCES = [
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان",
    "البرز", "ایلام", "بوشهر",
    TEHRAN_CITY_LABEL, TEHRAN_PROVINCE_EXCL_LABEL,
    "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی",
    "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان",
    "فارس", "قزوین", "قم", "کردستان",
    "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد", "گلستان",
    "گیلان", "لرستان", "مازندران", "مرکزی",
    "هرمزگان", "همدان", "یزد"
]

def create_province_kb():
    keyboard = []
    i = 0
    while i < len(PROVINCES):
        item = PROVINCES[i]
        if item == TEHRAN_CITY_LABEL:
            keyboard.append([
                KeyboardButton(text=TEHRAN_CITY_LABEL),
                KeyboardButton(text=TEHRAN_PROVINCE_EXCL_LABEL),
            ])
            i += 2
            continue
        if i + 1 < len(PROVINCES):
            keyboard.append([KeyboardButton(text=item), KeyboardButton(text=PROVINCES[i + 1])])
            i += 2
        else:
            keyboard.append([KeyboardButton(text=item)])
            i += 1
    keyboard.append([KeyboardButton(text="🔙 بازگشت")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

PERSON_TYPES = ["شخص حقیقی", "شخص حقوقی", "وکیل"]

def create_person_type_kb(exclude: list = None):
    # باگ رفع شد: دیگر گزینه‌ها حذف نمی‌شوند — همه گزینه‌ها همیشه نمایش داده می‌شوند
    exclude = exclude or []
    available = PERSON_TYPES  # تمام گزینه‌ها بدون حذف
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    if exclude:
        keyboard.append([KeyboardButton(text="✅ خیر، ادامه مراحل")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

representative_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="مدیرعامل"), KeyboardButton(text="نماینده")]
    ],
    resize_keyboard=True
)

add_or_finish_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن کدملی دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="⏭ رد کردن (بدون مدرک)")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه بده")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

lavayeh_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

lavayeh_edit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 ویرایش عنوان لایحه")],
        [KeyboardButton(text="🔢 ویرایش شماره پرونده")],
        [KeyboardButton(text="🏙 ویرایش استان")],
        [KeyboardButton(text="🔢 ویرایش ردیف فرعی")],
        [KeyboardButton(text="👤 ویرایش اشخاص ارائه‌دهنده")],
        [KeyboardButton(text="📄 ویرایش شرح متن لایحه")],
        [KeyboardButton(text="🖼 ویرایش تصاویر مدارک")],
        [KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")]
    ],
    resize_keyboard=True
)

lavayeh_cancel_reminder_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

lavayeh_sign_ready_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ آماده‌ام، کد امضا ارسال شود")]
    ],
    resize_keyboard=True
)

lavayeh_sign_resend_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

lavayeh_sign_later_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

lavayeh_sign_try_again_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله، کد جدید ارسال شود"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)


# =========================================================
# کیبوردهای بخش اخذ امضای الکترونیک اظهارنامه
# =========================================================

ezhhar_sign_ready_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ آماده‌ام، کد امضا ارسال شود")]
    ],
    resize_keyboard=True
)

ezhhar_sign_resend_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

ezhhar_sign_later_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

ezhhar_sign_try_again_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله، کد جدید ارسال شود"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش اعلام وکالت
# =========================================================

ealam_more_lawyers_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، وکیل دیگری هم هست")],
        [KeyboardButton(text="✅ خیر، ادامه مراحل")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ealam_more_contracts_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن شماره قرارداد دیگر")],
        [KeyboardButton(text="✅ ادامه مراحل")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ealam_stamp_amount_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ نمیدانم، نیاز به محاسبه دارم")],
        [KeyboardButton(text="🚫 نیاز به ابطال تمبر ندارد")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ealam_claim_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ دعوی مالی است و مبلغ خواسته را می‌دانم")],
        [KeyboardButton(text="2️⃣ دعوی غیر مالی است")],
        [KeyboardButton(text="3️⃣ عدم نیاز به تمبر")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ealam_stamp_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📌 تمبر بدوی")],
        [KeyboardButton(text="📌 تمبر تجدیدنظر")],
        [KeyboardButton(text="📌 تمبر کلی")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

continue_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ ادامه مراحل")]
    ],
    resize_keyboard=True
)

ealam_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش محاسبه تمبر مستقل (منوی اصلی)
# =========================================================

stamp_calc_claim_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ دعوی مالی است و مبلغ خواسته را می‌دانم")],
        [KeyboardButton(text="2️⃣ دعوی غیر مالی است")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش اظهارنامه
# =========================================================

EZHHAR_PERSON_TYPES = ["شخص حقیقی", "شخص حقوقی", "وکیل"]

def create_ezhhar_declarant_person_type_kb(exclude: list = None):
    """کیبورد نوع شخص اظهارکننده - همیشه سه گزینه اول را نشان می‌دهد"""
    exclude = exclude or []
    available = [p for p in EZHHAR_PERSON_TYPES if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    # همیشه دکمه اتمام را نشان بده (حتی اگر exclude خالی باشد)
    keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def create_ezhhar_addressee_person_type_kb(exclude: list = None, show_finish: bool = None):
    """کیبورد نوع شخص مخاطب اظهارنامه"""
    exclude = exclude or []
    available = [p for p in ["شخص حقیقی", "شخص حقوقی"] if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    # گزینه استعلام شماره تماس
    keyboard.append([KeyboardButton(text="📞 استعلام شماره تماس")])
    show_finish = bool(exclude) if show_finish is None else show_finish
    if show_finish:
        keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

ezhhar_declarant_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن شخص اظهارکننده دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

# کیبورد «افزودن شخص دیگر» — نسخه اختصاصی بخش چک (خوانده به جای مخاطب)
check_addressee_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن خوانده دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="📞 استعلام شماره تماس")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_addressee_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن خوانده دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="📞 استعلام شماره تماس")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_subject_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (ادامه مراحل)")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="⏭ رد کردن (بدون مدرک)")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه بده")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

ezhhar_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

ezhhar_edit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 ویرایش اظهارکننده(ها)")],
        [KeyboardButton(text="👥 ویرایش مخاطب(ها)")],
        [KeyboardButton(text="📌 ویرایش عنوان اظهارنامه")],
        [KeyboardButton(text="📄 ویرایش شرح متن")],
        [KeyboardButton(text="🖼 ویرایش مدارک")],
        [KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای ثبت دسته‌جمعی (بیش از ۵ مورد)
# =========================================================

bulk_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚡️ ثبت دسته‌جمعی سریع (بدون معطلی - فایل اکسل)")],
        [KeyboardButton(text="1️⃣ ثبت تکی (روال عادی)")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

# کیبورد روش ورود برای ثبت دسته‌جمعی - فقط اکسل
bulk_input_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 دانلود نمونه اکسل و آپلود فایل")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

bulk_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و ارسال برای مدیر")],
        [KeyboardButton(text="🔄 ارسال مجدد فایل / اصلاح")],
        [KeyboardButton(text="❌ انصراف و بازگشت")]
    ],
    resize_keyboard=True
)

# کیبورد برای انتخاب پیوست هر ردیف در ثبت دسته‌جمعی
bulk_attachment_row_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 افزودن پیوست برای این ردیف")],
        [KeyboardButton(text="⏭ رد شدن از این ردیف (بدون پیوست)")],
        [KeyboardButton(text="✅ اتمام پیوست‌گذاری و ادامه")],
        [KeyboardButton(text="❌ انصراف")]
    ],
    resize_keyboard=True
)

# کیبورد برای ادامه پیوست‌گذاری ردیف
bulk_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن پیوست دیگر برای این ردیف")],
        [KeyboardButton(text="✅ اتمام پیوست این ردیف و رفتن به ردیف بعدی")],
        [KeyboardButton(text="❌ انصراف")]
    ],
    resize_keyboard=True
)

# کیبورد تایید مدیر برای ثبت دسته‌جمعی
admin_bulk_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع پردازش")],
        [KeyboardButton(text="❌ رد درخواست")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش اشتراک ماهیانه
# =========================================================

subscription_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 پرداخت آنلاین (کیف پول بله)")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش بازیابی پس از قطعی سامانه
# =========================================================

disrupted_retry_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 تلاش مجدد (بدون پرداخت هزینه)")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش تست مدیر (منضمات / امضا)
# =========================================================

test_mode_doc_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 لایحه"), KeyboardButton(text="📋 اظهارنامه")],
        [KeyboardButton(text="⚖️ دعاوی اعتراضی")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

test_mode_section_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 تست بخش منضمات")],
        [KeyboardButton(text="✍️ تست بخش امضا")],
        [KeyboardButton(text="⚖️ تست ثبت کامل دعوی اعتراضی")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

test_mode_att_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)"), KeyboardButton(text="⏭ رد کردن (بدون مدرک)")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

test_mode_att_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش دعاوی اعتراضی
# =========================================================

TN_CASE_TYPES = [
    "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
    "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
    "اعتراض ثالث", "اعتراض به قرار دادسرا"
]

tn_case_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="تجدیدنظرخواهی"), KeyboardButton(text="واخواهی")],
        [KeyboardButton(text="فرجام خواهی"), KeyboardButton(text="اعاده دادرسی مدنی")],
        [KeyboardButton(text="اعاده دادرسی کیفری"), KeyboardButton(text="اعتراض ثالث")],
        [KeyboardButton(text="اعتراض به قرار دادسرا")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
    ],
    resize_keyboard=True
)

tn_doc_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="حکم"), KeyboardButton(text="قرار")],
    ],
    resize_keyboard=True
)

tn_amount_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ مبلغ دقیق را نمی‌دانم")],
        [KeyboardButton(text="🚫 خواسته غیر مالی است")],
        [KeyboardButton(text="💰 مبلغ را می‌دانم و می‌خواهم وارد شود")],
    ],
    resize_keyboard=True
)

tn_insolvency_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")],
    ],
    resize_keyboard=True
)

tn_extra_text_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏭ رد شدن")],
    ],
    resize_keyboard=True
)

tn_more_witnesses_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، کدملی شخص دیگری را دارم")],
        [KeyboardButton(text="✅ خیر، ادامه مراحل")],
        [KeyboardButton(text="🔙 بازگشت")],
    ],
    resize_keyboard=True
)

tn_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")],
    ],
    resize_keyboard=True
)

def create_tn_edit_kb(labels: dict = None, has_reasons: bool = False, has_appellee: bool = True) -> ReplyKeyboardMarkup:
    """کیبورد داینامیک ویرایش - برچسب‌ها بر اساس نوع دعوی"""
    labels = labels or {}
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
    witness_label = labels.get("witness_step", "مطلع/گواه")

    keyboard = [
        [KeyboardButton(text="🔢 ویرایش اطلاعات دادنامه")],
        [KeyboardButton(text=f"👤 ویرایش {appellant_label}")],
    ]
    if has_appellee:
        keyboard.append([KeyboardButton(text=f"👥 ویرایش {appellee_label}")])
    keyboard.append([KeyboardButton(text=f"👁 ویرایش {witness_label}")])
    keyboard.extend([
        [KeyboardButton(text="📄 ویرایش شرح متن")],
        [KeyboardButton(text="📝 ویرایش توضیحات جداگانه")],
        [KeyboardButton(text="🖼 ویرایش مدارک")],
    ])
    if has_reasons:
        keyboard.append([KeyboardButton(text="⚖️ ویرایش جهات")])
    keyboard.append([KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# Legacy alias (backward compat)
tn_edit_kb = create_tn_edit_kb()

tn_reason_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، مورد دیگری هم هست")],
        [KeyboardButton(text="✅ خیر، ادامه مراحل")],
    ],
    resize_keyboard=True
)

tn_amount_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید")],
    ],
    resize_keyboard=True
)


def create_tn_appellant_person_type_kb(exclude: list = None):
    """کیبورد نوع شخص تجدیدنظرخواه — همان قوانین اظهارکننده اظهارنامه"""
    exclude = exclude or []
    available = [p for p in ["شخص حقیقی", "شخص حقوقی", "وکیل"] if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def create_tn_appellee_person_type_kb(exclude: list = None, show_finish: bool = None):
    """کیبورد نوع شخص تجدیدنظرخوانده — حقیقی و حقوقی"""
    exclude = exclude or []
    available = [p for p in ["شخص حقیقی", "شخص حقوقی"] if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    show_finish = bool(exclude) if show_finish is None else show_finish
    if show_finish:
        keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def create_tn_reasons_kb(remaining_reasons: list, selected: list = None):
    """کیبورد پویا برای انتخاب جهات اعاده دادرسی"""
    selected = selected or []
    keyboard = []
    for i in range(0, len(remaining_reasons), 2):
        row = [KeyboardButton(text=remaining_reasons[i])]
        if i + 1 < len(remaining_reasons):
            row.append(KeyboardButton(text=remaining_reasons[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="✅ خیر، ادامه مراحل")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ═══════════════════════════════════════════════════════════════
# کیبوردهای بخش امضای دعاوی اعتراضی
# ═══════════════════════════════════════════════════════════════
tn_sign_ready_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ آماده‌ام، کد امضا ارسال شود")]],
    resize_keyboard=True
)

tn_sign_resend_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 ارسال مجدد کد")],
        [KeyboardButton(text="⏳ فعلاً امضا نمی‌کنم")],
    ],
    resize_keyboard=True
)

tn_sign_later_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 ثبت امضا در حال حاضر")],
        [KeyboardButton(text="❌ انصراف و ادامه بدون امضا")],
    ],
    resize_keyboard=True
)

tn_sign_try_again_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔄 تلاش مجدد")]], resize_keyboard=True)

test_mode_att_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه بده")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش ثبت دعاوی چک
# =========================================================

check_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ ثبت تکی (روال عادی)")],
        [KeyboardButton(text="📊 دانلود فایل اکسل و ثبت دسته‌جمعی")],
        [KeyboardButton(text="🔙 بازگشت")],
    ],
    resize_keyboard=True
)

check_request_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="صدور اجرائیه چک"), KeyboardButton(text="مطالبه وجه چک")],
        [KeyboardButton(text="🔙 بازگشت")],
    ],
    resize_keyboard=True
)

check_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت"), KeyboardButton(text="✏️ ویرایش اطلاعات")],
        [KeyboardButton(text="❌ انصراف")],
    ],
    resize_keyboard=True
)

check_edit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 ویرایش عنوان خواسته"), KeyboardButton(text="💰 ویرایش مبلغ چک")],
        [KeyboardButton(text="📄 ویرایش عنوان خواسته (متن)"), KeyboardButton(text="🔢 ویرایش کدرهگیری")],
        [KeyboardButton(text="👤 ویرایش خواهان(ها)"), KeyboardButton(text="👥 ویرایش خوانده(ها)")],
        [KeyboardButton(text="🔍 ویرایش مطلع/گواه"), KeyboardButton(text="📋 ویرایش شرح متن")],
        [KeyboardButton(text="🖼 ویرایش تصاویر چک"), KeyboardButton(text="🏛 ویرایش صلاحیت دادگاه")],
        [KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")],
    ],
    resize_keyboard=True
)

check_extra_text_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ بله، توضیحات اضافی دارم")],
        [KeyboardButton(text="❌ خیر، ادامه بده")],
    ],
    resize_keyboard=True
)

check_more_images_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ تصویر چک بعدی")],
        [KeyboardButton(text="📎 تصویر یا مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه به انتخاب دادگاه")],
    ],
    resize_keyboard=True
)

def get_check_more_images_kb(image_count: int, max_images: int = 3) -> ReplyKeyboardMarkup:
    """کیبورد داینامیک — دکمه «تصویر چک بعدی» فقط وقتی هنوز جای هست نمایش داده شود."""
    rows = []
    if image_count < max_images:
        rows.append([KeyboardButton(text="➕ تصویر چک بعدی")])
    rows.append([KeyboardButton(text="📎 تصویر یا مدرک دیگر دارم")])
    rows.append([KeyboardButton(text="✅ خیر، ادامه به انتخاب دادگاه")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

check_attachment_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (سایر مستندات)"), KeyboardButton(text="⏭ رد کردن (بدون مدرک)")],
        [KeyboardButton(text="🔙 بازگشت")],
    ], resize_keyboard=True
)

check_attachment_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (سایر مستندات)")],
        [KeyboardButton(text="🔙 بازگشت")],
    ], resize_keyboard=True
)

check_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه به انتخاب دادگاه")],
        [KeyboardButton(text="🔙 بازگشت")],
    ], resize_keyboard=True
)

# کیبورد انتخاب روش ورود متن — عمومی (بازگشت دارد)
text_input_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⌨️ تایپ مستقیم متن"), KeyboardButton(text="📎 ارسال فایل ورد (.docx)")],
        [KeyboardButton(text="🔙 بازگشت")],
    ], resize_keyboard=True
)

check_docx_option_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 ارسال فایل ورد (.docx)")],
        [KeyboardButton(text="⌨️ تایپ مستقیم متن")],
    ],
    resize_keyboard=True
)


def create_check_person_type_kb(show_finish: bool = False):
    """کیبورد نوع شخصیت برای چک — همیشه حقیقی + حقوقی (بدون exclude)."""
    keyboard = [
        [KeyboardButton(text="شخص حقیقی"), KeyboardButton(text="شخص حقوقی")],
        [KeyboardButton(text="📞 استعلام شماره تماس")],
    ]
    if show_finish:
        keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
