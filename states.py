"""حالت‌های مکالمه‌ی تلگرام (FSM) — تمام State های ربات فقط اینجا تعریف می‌شوند."""
from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    waiting_for_rule_acceptance = State()
    waiting_for_flow_type = State()
    main_menu = State()
    waiting_for_tracking_code = State()
    waiting_for_phone_number = State()
    waiting_for_national_id = State()
    waiting_for_doc_category = State()
    waiting_for_doc_subcategory = State()
    waiting_for_attachments_opt = State()
    confirm_opt = State()
    waiting_for_payment_receipt = State()

    # =========================================================
    # State های بخش استعلام دسته‌جمعی (فایل اکسل)
    # =========================================================
    bulk_inquiry_file_upload = State()       # منتظر آپلود فایل اکسل
    bulk_inquiry_confirm = State()           # نمایش فاکتور و انتظار تایید کاربر

    # =========================================================
    # State های بخش لایحه (ثبت لایحه)
    # =========================================================
    lavayeh_title = State()
    lavayeh_tracking_method = State()  # انتخاب روش: شماره پرونده یا شماره بایگانی
    lavayeh_tracking_code = State()
    lavayeh_archive_number = State()  # شماره بایگانی
    lavayeh_branch_input_method = State()  # انتخاب نحوه ورود نام شعبه
    lavayeh_branch_name = State()  # نام شعبه
    lavayeh_province = State()
    lavayeh_row_number = State()
    lavayeh_person_type = State()
    lavayeh_company_id = State()
    lavayeh_representative_type = State()
    lavayeh_national_id = State()
    lavayeh_more_persons = State()
    lavayeh_text = State()
    lavayeh_attachment_title = State()
    lavayeh_images = State()
    lavayeh_attachment_more = State()
    lavayeh_confirm = State()
    lavayeh_edit_choice = State()
    waiting_for_lavayeh_prepay = State()          # منتظر پرداخت خدمات قبل از ثبت در سامانه
    waiting_for_lavayeh_payment_receipt = State()
    lavayeh_payment_reminder_response = State()

    # =========================================================
    # State های بخش اخذ امضای الکترونیک لایحه
    # =========================================================
    lavayeh_sign_ready = State()               # آمادگی برای ارسال کد
    lavayeh_sign_person_select = State()       # انتخاب شخص برای ارسال کد
    lavayeh_sign_code_input = State()          # دریافت کد از کاربر
    lavayeh_sign_resend_prompt = State()       # سوال ارسال مجدد کد
    lavayeh_sign_later_prompt = State()        # سوال اقدام بعدی
    lavayeh_sign_wrong_code_wait = State()     # منتظر ۲۰ دقیقه بعد از کد اشتباه
    lavayeh_sign_no_action_timeout = State()   # ۶۰ دقیقه بدون اقدام

    # =========================================================
    # State های بخش اخذ امضای الکترونیک اظهارنامه
    # =========================================================
    ezhhar_sign_ready = State()               # آمادگی برای ارسال کد
    ezhhar_sign_person_select = State()       # انتخاب شخص برای ارسال کد
    ezhhar_sign_code_input = State()          # دریافت کد از کاربر
    ezhhar_sign_resend_prompt = State()       # سوال ارسال مجدد کد
    ezhhar_sign_later_prompt = State()        # سوال اقدام بعدی
    ezhhar_sign_wrong_code_wait = State()     # منتظر ۲۰ دقیقه بعد از کد اشتباه
    ezhhar_sign_no_action_timeout = State()  # ۶۰ دقیقه بدون اقدام

    # =========================================================
    # State های بخش اعلام وکالت
    # =========================================================
    ealam_vakalaht_national_id = State()
    ealam_vakalaht_more_lawyers = State()
    ealam_vakalaht_contract_number = State()
    ealam_vakalaht_more_contracts = State()
    ealam_vakalaht_stamp_amount = State()
    ealam_vakalaht_claim_type = State()
    ealam_vakalaht_claim_amount = State()
    ealam_vakalaht_stamp_type = State()
    ealam_vakalaht_text = State()
    ealam_vakalaht_attachment_title = State()
    ealam_vakalaht_images = State()
    ealam_vakalaht_attachment_more = State()
    ealam_vakalaht_confirm = State()
    ealam_vakalaht_edit_choice = State()
    waiting_for_ealam_payment_receipt = State()

    # =========================================================
    # State های بخش محاسبه تمبر مالیاتی (مستقل)
    # =========================================================
    stamp_calc_claim_type = State()
    stamp_calc_claim_amount = State()
    stamp_calc_waiting_payment = State()

    # =========================================================
    # State های بخش ثبت اظهارنامه
    # =========================================================
    # مرحله ۱: نوع شخصیت اظهارکننده
    ezhhar_declarant_person_type = State()
    ezhhar_declarant_company_id = State()
    ezhhar_declarant_representative_type = State()
    ezhhar_declarant_national_id = State()
    ezhhar_declarant_more_persons = State()

    # مرحله ۲: نوع شخصیت مخاطب
    ezhhar_addressee_person_type = State()
    ezhhar_addressee_company_id = State()
    ezhhar_addressee_company_id_no_rep = State()  # مخاطب حقوقی بدون پرسیدن کدملی نماینده
    ezhhar_addressee_representative_type = State()
    ezhhar_addressee_national_id = State()
    ezhhar_addressee_more_persons = State()

    # مرحله ۳: عنوان اظهارنامه
    ezhhar_subject = State()

    # مرحله ۴: شرح متن
    ezhhar_text = State()

    # مرحله ۵: مدارک (پیوست‌ها)
    ezhhar_attachment_title = State()
    ezhhar_images = State()
    ezhhar_attachment_images = State()
    ezhhar_attachment_more = State()

    # مرحله ۶: پیش‌نمایش و تایید
    ezhhar_confirm = State()
    ezhhar_edit_choice = State()
    waiting_for_ezhhar_prepay = State()          # منتظر پرداخت خدمات قبل از ثبت در سامانه

    # خطای استعلام ثنا در اظهارنامه — ویرایش شناسه ملی یا حذف درخواست
    ezhhar_sana_error_action = State()
    ezhhar_sana_error_new_national_id = State()

    # =========================================================
    # State های بخش ثبت دسته‌جمعی (بیش از ۵ مورد - لایحه و اظهارنامه)
    # =========================================================
    bulk_mode_select = State()      # انتخاب روش ثبت (تکی یا دسته‌جمعی سریع)
    bulk_input_method = State()     # انتخاب نوع فایل (اکسل، تصویر، متن)
    bulk_file_upload = State()      # دریافت فایل اکسل / تصویر / متن
    bulk_attachment_row = State()   # انتخاب پیوست برای هر ردیف اکسل
    bulk_attachment_title = State() # انتخاب عنوان پیوست برای ردیف جاری
    bulk_attachment_images = State() # دریافت تصاویر پیوست
    bulk_attachment_more = State()  # آیا پیوست بیشتری برای این ردیف هست؟
    bulk_attachment_all_confirm = State()  # تأیید پیوست مشابه برای همه ردیف‌ها
    bulk_attachment_all_title = State()    # انتخاب عنوان پیوست مشابه
    bulk_attachment_all_images = State()   # دریافت تصاویر پیوست مشابه
    bulk_attachment_all_more = State()     # آیا پیوست مشابه دیگری هم هست؟
    bulk_confirm = State()          # تایید نهایی و صدور کد رهگیری دسته‌جمعی
    bulk_admin_pending = State()    # در انتظار تایید مدیر
    bulk_prepay_wait = State()      # منتظر پرداخت پیش‌پرداخت دسته‌جمعی (مشترک لایحه/اظهارنامه)
    bulk_settlement_wait = State()  # منتظر پرداخت تسویهٔ باقیماندهٔ هزینه سامانه

    # =========================================================
    # State های بخش ابزار فایل (کاهش حجم عکس / تبدیل PDF به عکس)
    # =========================================================
    file_tools_menu = State()          # انتخاب نوع ابزار
    file_tools_waiting_image = State()  # منتظر دریافت عکس برای فشرده‌سازی
    file_tools_waiting_pdf = State()    # منتظر دریافت PDF برای تبدیل به عکس

    # =========================================================
    # State های بخش اشتراک ماهیانه
    # =========================================================
    subscription_main = State()                  # منوی اشتراک
    subscription_waiting_payment = State()       # منتظر دریافت رسید پرداخت اشتراک
    subscription_waiting_admin_review = State()   # منتظر تایید مدیر

    # =========================================================
    # State های بخش بازیابی پس از قطعی سامانه
    # =========================================================
    waiting_for_disrupted_retry = State()  # منتظر تصمیم کاربر برای تکرار بدون پرداخت

    # =========================================================
    # State های بخش اصلاح کدرهگیری نامعتبر (فرصت ۳۰ دقیقه‌ای رایگان)
    # =========================================================
    waiting_for_corrected_tracking_code = State()   # منتظر کدرهگیری اصلاح‌شده
    waiting_for_corrected_doc_category = State()    # منتظر نوع سند برای استعلام رایگان
    waiting_for_corrected_doc_subcategory = State()  # منتظر زیرشاخه‌ی نوع سند

    # =========================================================
    # State های بخش دعاوی اعتراضی
    # =========================================================
    tn_case_type = State()
    tn_judge_no = State()
    tn_file_no = State()
    # tn_file_no_row حذف شد
    tn_order_no = State()  # شماره قرار (فقط اعتراض به قرار دادسرا)
    tn_judge_date = State()
    tn_province = State()
    tn_doc_type = State()
    tn_amount_type = State()
    tn_amount = State()
    tn_insolvency = State()
    tn_appellant_person_type = State()
    tn_appellant_company_id = State()
    tn_appellant_representative_type = State()
    tn_appellant_national_id = State()
    tn_appellant_more = State()
    tn_appellee_person_type = State()
    tn_appellee_company_id = State()
    tn_appellee_national_id = State()
    tn_appellee_more = State()
    tn_witness_national_id = State()
    tn_more_witnesses = State()
    tn_text_choice = State()
    tn_text = State()
    tn_extra_text = State()
    tn_attachment_title = State()
    tn_images = State()
    tn_attachment_images = State()
    tn_attachment_more = State()
    tn_reason_select = State()
    tn_more_reasons = State()
    tn_confirm = State()
    tn_edit_choice = State()
    tn_sana_error_action = State()
    tn_sana_error_new_national_id = State()

    # =========================================================

    tn_appellant_vakalat_no = State()    # شماره قرارداد وکالت تجدیدنظرخواه
    tn_appellee_vakalat_no = State()     # شماره قرارداد وکالت تجدیدنظرخوانده
    check_plaintiff_vakalat_no = State() # شماره قرارداد وکالت خواهان چک
    check_defendant_vakalat_no = State() # شماره قرارداد وکالت خوانده چک

    # State های بخش اخذ امضای الکترونیک دعاوی اعتراضی
    tn_sign_ready = State()
    tn_sign_person_select = State()
    tn_sign_code_input = State()
    tn_sign_resend_prompt = State()
    tn_sign_later_prompt = State()
    tn_sign_wrong_code_wait = State()
    tn_sign_no_action_timeout = State()

    # State های بخش تست مدیر (منضمات / امضا / هزینه)
    # =========================================================
    test_mode_tracking_code = State()
    test_mode_doc_type = State()
    test_mode_section_select = State()
    test_mode_attachment_title = State()
    test_mode_attachment_images = State()
    test_mode_attachment_more = State()
    # تست اعلام وکالت — حلقه نماینده حقوقی در منضمات
    test_mode_ealam_representative_type = State()
    test_mode_ealam_contract_number = State()
    test_mode_ealam_stamp_amount = State()

    # =========================================================
    # State های بخش ثبت دعاوی چک
    # =========================================================
    check_request_type = State()          # انتخاب تکی یا دسته‌جمعی
    check_bulk_input_method = State()     # انتخاب نوع فایل (اکسل)
    check_bulk_file_upload = State()      # دریافت فایل اکسل
    check_request_title = State()         # انتخاب عنوان خواسته (صدور اجرائیه / مطالبه وجه)
    check_amount = State()                # مبلغ چک به ریال
    check_khasteh_title = State()         # عنوان خواسته (ویرایش متن پیشنهادی)
    check_tracking_no = State()           # کدرهگیری چک
    check_plaintiff_person_type = State() # نوع شخصیت خواهان
    check_plaintiff_company_id = State()  # شناسه ملی شرکت خواهان
    check_plaintiff_representative_type = State()  # سمت نماینده خواهان
    check_plaintiff_national_id = State() # کدملی خواهان
    check_plaintiff_more = State()        # افزودن خواهان دیگر
    check_defendant_person_type = State() # نوع شخصیت خوانده
    check_defendant_company_id = State()  # شناسه ملی شرکت خوانده
    check_defendant_representative_type = State()  # سمت نماینده خوانده
    check_defendant_national_id = State() # کدملی خوانده
    check_defendant_more = State()        # افزودن خوانده دیگر
    check_witness_national_id = State()   # کدملی مطلع/گواه
    check_more_witnesses = State()        # افزودن مطلع دیگر
    check_text = State()                  # شرح متن دادخواست
    check_text_input = State()       # دریافت متن تایپ‌شده یا فایل ورد
    check_extra_text = State()            # توضیحات جداگانه برای مقام قضائی
    check_images = State()                # دریافت تصاویر چک (حداکثر ۳)
    check_more_images = State()           # آیا تصویر یا مدرک دیگری دارید؟
    check_check_next_images = State()    # تصویر چک بعدی
    check_attachment_title = State()     # عنوان پیوست
    check_attachment_images = State()    # تصاویر پیوست
    check_attachment_more = State()      # آیا پیوست دیگری هست؟
    check_branch_code = State()           # انتخاب صلاحیت دادگاه (شعبه)
    check_confirm = State()               # پیش‌نمایش و تایید
    check_edit_choice = State()           # انتخاب بخش ویرایش

    # =========================================================
    # State های بخش استعلام ارزش منطقه‌ای
    # =========================================================
    rv_waiting_province = State()
    rv_waiting_address = State()
    rv_waiting_area = State()
    rv_waiting_land_use = State()
    rv_waiting_payment = State()
