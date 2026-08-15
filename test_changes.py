#!/usr/bin/env python3
"""
اسکریپت تست برای بررسی صحت تغییرات اعمال شده
"""

import re
import sys

def test_scenarios_alert_detection():
    """تست: بررسی اضافه شدن کد تشخیص alert در scenarios.py"""
    print("🧪 تست ۱: بررسی تشخیص پیام خطای ثنا...")
    
    with open('scenarios.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # چک کردن وجود کد تشخیص alert
    checks = [
        'alert-info',
        'alert-dismissable',
        'پایگاه داده ثنا',
        'ثبت نشده است',
        'alert_message'
    ]
    
    all_found = all(check in content for check in checks)
    
    if all_found:
        print("   ✅ تشخیص پیام خطای ثنا به درستی اضافه شده است")
        return True
    else:
        print("   ❌ کد تشخیص alert پیدا نشد!")
        missing = [check for check in checks if check not in content]
        print(f"   کلمات کلیدی یافت نشده: {missing}")
        return False


def test_ealam_nationality_field():
    """تست: بررسی اضافه شدن txtNationalityCode به سلکتورها"""
    print("🧪 تست ۲: بررسی فیلد کد ملی در اعلام وکالت...")
    
    with open('ealam_vakalaht_scenario.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # چک کردن وجود txtNationalityCode در اولویت اول
    pattern = r'candidate_selectors\s*=\s*\[[\s\S]*?["\']#txtNationalityCode["\']'
    
    if re.search(pattern, content):
        print("   ✅ فیلد txtNationalityCode به عنوان اولویت اول اضافه شده است")
        return True
    else:
        print("   ❌ فیلد txtNationalityCode در اولویت اول پیدا نشد!")
        return False


def test_ealam_sana_query_update():
    """تست: بررسی تغییر دکمه استعلام به getLawyerDataWithSana"""
    print("🧪 تست ۳: بررسی دکمه استعلام ثنا...")
    
    with open('ealam_vakalaht_scenario.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = [
        'getLawyerDataWithSana',
        'استعلام ثنا',
        'glyphicon-refresh'
    ]
    
    all_found = all(check in content for check in checks)
    
    if all_found:
        print("   ✅ دکمه استعلام ثنا به درستی تغییر یافته است")
        return True
    else:
        print("   ❌ تغییرات دکمه استعلام کامل نیست!")
        missing = [check for check in checks if check not in content]
        print(f"   کلمات کلیدی یافت نشده: {missing}")
        return False


def test_ealam_save_button():
    """تست: بررسی وجود تابع کلیک دکمه ثبت موقت"""
    print("🧪 تست ۴: بررسی تابع کلیک دکمه ثبت موقت...")
    
    with open('ealam_vakalaht_scenario.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # چک کردن وجود تابع _click_add_lawyer_save
    if 'async def _click_add_lawyer_save' in content:
        # چک کردن فراخوانی تابع
        if 'await _click_add_lawyer_save(page, bot, user_id)' in content:
            print("   ✅ تابع کلیک دکمه ثبت موقت اضافه و فراخوانی شده است")
            return True
        else:
            print("   ⚠️  تابع اضافه شده اما فراخوانی نشده است!")
            return False
    else:
        print("   ❌ تابع _click_add_lawyer_save پیدا نشد!")
        return False


def test_documentation():
    """تست: بررسی وجود مستندات"""
    print("🧪 تست ۵: بررسی مستندات...")
    
    files = ['README.md', 'CHANGES.md', '.env.example', '.gitignore']
    results = []
    
    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                if len(content) > 100:  # حداقل ۱۰۰ کاراکتر
                    print(f"   ✅ {file} موجود است")
                    results.append(True)
                else:
                    print(f"   ⚠️  {file} خیلی کوچک است")
                    results.append(False)
        except FileNotFoundError:
            print(f"   ❌ {file} یافت نشد!")
            results.append(False)
    
    return all(results)


def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║        🧪 تست خودکار تغییرات پروژه                       ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print()
    
    tests = [
        test_scenarios_alert_detection,
        test_ealam_nationality_field,
        test_ealam_sana_query_update,
        test_ealam_save_button,
        test_documentation
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"   ❌ خطا در اجرای تست: {e}")
            results.append(False)
        print()
    
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                      نتیجه نهایی                         ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 تعداد تست‌های موفق: {passed}/{total}")
    
    if all(results):
        print("\n✅ همه تست‌ها موفق بودند! پروژه آماده است.")
        return 0
    else:
        failed_indices = [i+1 for i, r in enumerate(results) if not r]
        print(f"\n❌ تست‌های شماره {failed_indices} ناموفق بودند.")
        print("   لطفاً مشکلات را رفع کنید.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
