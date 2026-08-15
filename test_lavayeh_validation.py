#!/usr/bin/env python3
"""
تست‌های واحد برای توابع validation شماره پرونده و شماره بایگانی
"""

import sys
sys.path.insert(0, '.')

from lavayeh_handlers import validate_tracking_code, validate_archive_number


def test_tracking_code_validation():
    """تست اعتبارسنجی شماره پرونده"""
    print("🧪 تست اعتبارسنجی شماره پرونده...")
    
    # تست شماره‌های معتبر
    # سال ۱۴۰۰-۱۴۰۷ (۱۸ رقمی)
    valid, msg = validate_tracking_code("140012345678901234")
    assert valid, f"شماره پرونده ۱۸ رقمی باید معتبر باشد: {msg}"
    print("  ✅ شماره پرونده ۱۸ رقمی (۱۴۰۰-۱۴۰۷): معتبر")
    
    # سال ۱۳۹۹ و قبل‌تر (۱۶ رقمی)
    valid, msg = validate_tracking_code("1399123456789012")
    assert valid, f"شماره پرونده ۱۶ رقمی باید معتبر باشد: {msg}"
    print("  ✅ شماره پرونده ۱۶ رقمی (۱۳۹۹ و قبل): معتبر")
    
    # تست شماره‌های نامعتبر
    # سال ۱۴۰۰ با ۱۶ رقم (باید ۱۸ باشد)
    valid, msg = validate_tracking_code("1400123456789012")
    assert not valid, "شماره پرونده ۱۶ رقمی برای سال ۱۴۰۰ نباید معتبر باشد"
    print("  ✅ شماره پرونده ۱۶ رقمی برای سال ۱۴۰۰: نامعتبر (انتظار داشتیم)")
    
    # سال ۱۳۹۹ با ۱۸ رقم (باید ۱۶ باشد)
    valid, msg = validate_tracking_code("139912345678901234")
    assert not valid, "شماره پرونده ۱۸ رقمی برای سال ۱۳۹۹ نباید معتبر باشد"
    print("  ✅ شماره پرونده ۱۸ رقمی برای سال ۱۳۹۹: نامعتبر (انتظار داشتیم)")
    
    # شماره غیر عددی
    valid, msg = validate_tracking_code("14001234abc")
    assert not valid, "شماره پرونده غیرعددی نباید معتبر باشد"
    print("  ✅ شماره پرونده غیرعددی: نامعتبر (انتظار داشتیم)")
    
    print("✅ تمام تست‌های شماره پرونده موفق بودند!\n")


def test_archive_number_validation():
    """تست اعتبارسنجی شماره بایگانی"""
    print("🧪 تست اعتبارسنجی شماره بایگانی...")
    
    # تست شماره‌های معتبر
    # دو رقم اول ۰۰-۰۷ (۷ رقمی)
    test_cases_7_digit = [
        "0012345",  # شروع با ۰۰
        "0312345",  # شروع با ۰۳
        "0712345",  # شروع با ۰۷
    ]
    
    for archive in test_cases_7_digit:
        valid, msg = validate_archive_number(archive)
        assert valid, f"شماره بایگانی {archive} باید معتبر باشد: {msg}"
        print(f"  ✅ شماره بایگانی {archive} (۷ رقمی): معتبر")
    
    # دو رقم اول ۹۳-۹۹ (۶ رقمی)
    test_cases_6_digit = [
        "931234",  # شروع با ۹۳
        "961234",  # شروع با ۹۶
        "991234",  # شروع با ۹۹
    ]
    
    for archive in test_cases_6_digit:
        valid, msg = validate_archive_number(archive)
        assert valid, f"شماره بایگانی {archive} باید معتبر باشد: {msg}"
        print(f"  ✅ شماره بایگانی {archive} (۶ رقمی): معتبر")
    
    # تست شماره‌های نامعتبر
    # دو رقم اول ۰۰-۰۷ با ۶ رقم (باید ۷ باشد)
    valid, msg = validate_archive_number("001234")
    assert not valid, "شماره بایگانی ۶ رقمی با شروع ۰۰ نباید معتبر باشد"
    print("  ✅ شماره بایگانی ۶ رقمی با شروع ۰۰-۰۷: نامعتبر (انتظار داشتیم)")
    
    # دو رقم اول ۰۰-۰۷ با ۸ رقم (باید ۷ باشد)
    valid, msg = validate_archive_number("00123456")
    assert not valid, "شماره بایگانی ۸ رقمی با شروع ۰۰ نباید معتبر باشد"
    print("  ✅ شماره بایگانی ۸ رقمی با شروع ۰۰-۰۷: نامعتبر (انتظار داشتیم)")
    
    # دو رقم اول ۹۳-۹۹ با ۷ رقم (باید ۶ باشد)
    valid, msg = validate_archive_number("9312345")
    assert not valid, "شماره بایگانی ۷ رقمی با شروع ۹۳ نباید معتبر باشد"
    print("  ✅ شماره بایگانی ۷ رقمی با شروع ۹۳-۹۹: نامعتبر (انتظار داشتیم)")
    
    # دو رقم اول ۹۳-۹۹ با ۵ رقم (باید ۶ باشد)
    valid, msg = validate_archive_number("93123")
    assert not valid, "شماره بایگانی ۵ رقمی با شروع ۹۳ نباید معتبر باشد"
    print("  ✅ شماره بایگانی ۵ رقمی با شروع ۹۳-۹۹: نامعتبر (انتظار داشتیم)")
    
    # دو رقم اول نامعتبر (مثلا ۰۸ یا ۵۰)
    valid, msg = validate_archive_number("0812345")
    assert not valid, "شماره بایگانی با شروع ۰۸ نباید معتبر باشد"
    print("  ✅ شماره بایگانی با دو رقم اول نامعتبر (۰۸): نامعتبر (انتظار داشتیم)")
    
    valid, msg = validate_archive_number("5012345")
    assert not valid, "شماره بایگانی با شروع ۵۰ نباید معتبر باشد"
    print("  ✅ شماره بایگانی با دو رقم اول نامعتبر (۵۰): نامعتبر (انتظار داشتیم)")
    
    # شماره غیر عددی
    valid, msg = validate_archive_number("93abc1")
    assert not valid, "شماره بایگانی غیرعددی نباید معتبر باشد"
    print("  ✅ شماره بایگانی غیرعددی: نامعتبر (انتظار داشتیم)")
    
    # شماره کمتر از ۲ رقم
    valid, msg = validate_archive_number("9")
    assert not valid, "شماره بایگانی کمتر از ۲ رقم نباید معتبر باشد"
    print("  ✅ شماره بایگانی کمتر از ۲ رقم: نامعتبر (انتظار داشتیم)")
    
    print("✅ تمام تست‌های شماره بایگانی موفق بودند!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("🔬 شروع تست‌های واحد")
    print("=" * 60 + "\n")
    
    try:
        test_tracking_code_validation()
        test_archive_number_validation()
        
        print("=" * 60)
        print("🎉 تمام تست‌ها با موفقیت انجام شدند!")
        print("=" * 60)
        sys.exit(0)
        
    except AssertionError as e:
        print(f"\n❌ خطا در تست: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
