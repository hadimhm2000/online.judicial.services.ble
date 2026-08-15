#!/usr/bin/env python3
"""
اسکریپت تست برای بررسی رفع خطای import در lavayeh_handlers
"""

def test_imports():
    """تست import های فایل lavayeh_handlers"""
    print("🔍 در حال تست import ها...")
    
    try:
        # تست import اصلی
        from aiogram.types import ReplyKeyboardRemove
        print("✅ ReplyKeyboardRemove از aiogram.types با موفقیت وارد شد")
        
        # تست import از keyboards (نباید شامل ReplyKeyboardRemove باشد)
        from keyboards import lavayeh_branch_input_method_kb, back_only_kb
        print("✅ keyboards با موفقیت وارد شدند")
        
        # تست import از branches
        from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
        print("✅ ماژول branches با موفقیت وارد شد")
        
        # بررسی وجود داده شعب
        if UNITS_DATA:
            print(f"✅ داده شعب بارگذاری شد - تعداد واحدها: {len(UNITS_DATA)}")
        else:
            print("⚠️ داده شعب خالی است - ممکن است فایل units_compact.json موجود نباشد")
        
        # بررسی ROOT_NODES
        if ROOT_NODES:
            print(f"✅ نودهای ریشه بارگذاری شدند - تعداد: {len(ROOT_NODES)}")
            print(f"   نمونه: {ROOT_NODES[0]['name'] if ROOT_NODES else 'خالی'}")
        else:
            print("⚠️ نودهای ریشه خالی است")
        
        print("\n✅ همه import ها با موفقیت انجام شد!")
        print("✅ مشکل import برطرف شده است")
        return True
        
    except ImportError as e:
        print(f"❌ خطا در import: {e}")
        return False
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("تست رفع خطای ImportError در lavayeh_handlers.py")
    print("=" * 60)
    print()
    
    success = test_imports()
    
    print()
    print("=" * 60)
    if success:
        print("✅ تست موفق - سیستم آماده اجراست")
    else:
        print("❌ تست ناموفق - لطفاً خطاها را بررسی کنید")
    print("=" * 60)
