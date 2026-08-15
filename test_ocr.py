#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت تست OCR
این اسکریپت برای تست عملکرد سیستم OCR استفاده می‌شود.
"""

import sys
import logging
from ocr import verify_payment_receipt, HAS_OCR, HAS_OPENCV

# تنظیم logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def print_banner():
    """نمایش بنر شروع"""
    print("\n" + "=" * 70)
    print("🔍 تست سیستم OCR فیش پرداخت")
    print("=" * 70 + "\n")

def check_dependencies():
    """بررسی وابستگی‌ها"""
    print("📦 بررسی وابستگی‌ها:")
    print("-" * 70)
    
    status = []
    
    # Tesseract & PIL
    if HAS_OCR:
        print("✅ Tesseract OCR و PIL نصب شده است")
        status.append(True)
        
        try:
            import pytesseract
            version = pytesseract.get_tesseract_version()
            print(f"   📌 نسخه Tesseract: {version}")
            
            # بررسی زبان‌ها
            try:
                from PIL import Image
                import pytesseract
                import subprocess
                result = subprocess.run(
                    ['tesseract', '--list-langs'],
                    capture_output=True,
                    text=True
                )
                langs = result.stdout
                
                if 'fas' in langs or 'persian' in langs.lower():
                    print("   ✅ زبان فارسی (fas) نصب شده است")
                else:
                    print("   ⚠️  زبان فارسی (fas) نصب نشده است!")
                    print("   💡 راهنما: INSTALL_OCR.md را بخوانید")
                    status.append(False)
                    
                if 'eng' in langs:
                    print("   ✅ زبان انگلیسی (eng) نصب شده است")
                    
            except Exception as e:
                print(f"   ⚠️  خطا در بررسی زبان‌ها: {e}")
                
        except Exception as e:
            print(f"   ⚠️  خطا در دریافت نسخه: {e}")
    else:
        print("❌ Tesseract OCR یا PIL نصب نشده است")
        print("   💡 راهنما: INSTALL_OCR.md را بخوانید")
        status.append(False)
    
    # OpenCV
    if HAS_OPENCV:
        print("✅ OpenCV نصب شده است (پیش‌پردازش پیشرفته فعال)")
        try:
            import cv2
            print(f"   📌 نسخه OpenCV: {cv2.__version__}")
        except:
            pass
        status.append(True)
    else:
        print("⚠️  OpenCV نصب نشده است (پیش‌پردازش ساده استفاده می‌شود)")
        print("   💡 نصب: pip install opencv-python")
    
    print("-" * 70 + "\n")
    
    return all(status)

def test_sample_receipt():
    """تست با فیش نمونه"""
    print("🧪 تست با داده نمونه:")
    print("-" * 70)
    
    # داده‌های تست
    test_cases = [
        {
            'name': 'تست 1: فیش موجود در پروژه',
            'photo_path': 'lavayeh_img_509108833_0.jpg',
            'amount': 50000,
            'card': '6037991234567890'
        },
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n📝 {test['name']}")
        print(f"   مبلغ: {test['amount']:,} تومان")
        print(f"   کارت: {test['card'][-4:]}")
        print(f"   تصویر: {test['photo_path']}")
        
        import os
        if not os.path.exists(test['photo_path']):
            print(f"   ⚠️  فایل تصویر یافت نشد: {test['photo_path']}")
            print(f"   💡 برای تست، یک فیش واقعی را در این مسیر قرار دهید")
            continue
        
        try:
            result, message = verify_payment_receipt(
                test['photo_path'],
                test['amount'],
                test['card']
            )
            
            print(f"\n   {'='*66}")
            if result:
                print(f"   ✅ نتیجه: تایید شد")
            else:
                print(f"   ❌ نتیجه: رد شد")
            print(f"   {'='*66}")
            
            # نمایش پیام با تورفتگی
            for line in message.split('\n'):
                print(f"   {line}")
            print(f"   {'='*66}")
            
        except Exception as e:
            print(f"   ❌ خطا در تست: {e}")
            import traceback
            traceback.print_exc()
    
    print("-" * 70 + "\n")

def interactive_test():
    """تست تعاملی"""
    print("🎮 تست تعاملی:")
    print("-" * 70)
    
    try:
        photo_path = input("مسیر فایل تصویر: ").strip()
        if not photo_path:
            print("❌ مسیر خالی است!")
            return
        
        import os
        if not os.path.exists(photo_path):
            print(f"❌ فایل یافت نشد: {photo_path}")
            return
        
        amount = int(input("مبلغ مورد انتظار (تومان): ").strip())
        card = input("شماره کارت مقصد: ").strip()
        
        print("\n⏳ در حال پردازش...")
        
        result, message = verify_payment_receipt(photo_path, amount, card)
        
        print("\n" + "=" * 70)
        if result:
            print("✅ نتیجه: تایید شد")
        else:
            print("❌ نتیجه: رد شد")
        print("=" * 70)
        print(message)
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  لغو شد توسط کاربر")
    except ValueError:
        print("❌ مبلغ باید یک عدد صحیح باشد!")
    except Exception as e:
        print(f"❌ خطا: {e}")
        import traceback
        traceback.print_exc()
    
    print("-" * 70 + "\n")

def main():
    """تابع اصلی"""
    print_banner()
    
    # بررسی وابستگی‌ها
    deps_ok = check_dependencies()
    
    if not deps_ok:
        print("⚠️  برخی وابستگی‌ها نصب نیستند!")
        print("📖 لطفا فایل INSTALL_OCR.md را مطالعه کنید\n")
    
    # انتخاب نوع تست
    print("انتخاب نوع تست:")
    print("  1. تست خودکار (با فیش نمونه)")
    print("  2. تست تعاملی (وارد کردن مسیر فایل)")
    print("  3. نمایش راهنما")
    print("  4. خروج")
    
    try:
        choice = input("\nانتخاب شما (1-4): ").strip()
        
        if choice == '1':
            test_sample_receipt()
        elif choice == '2':
            interactive_test()
        elif choice == '3':
            print("\n📖 راهنمای نصب و تنظیم OCR در فایل INSTALL_OCR.md موجود است")
            print("برای مشاهده:")
            print("  - ویندوز: notepad INSTALL_OCR.md")
            print("  - لینوکس/مک: cat INSTALL_OCR.md\n")
        elif choice == '4':
            print("\n👋 خروج...\n")
        else:
            print("\n❌ انتخاب نامعتبر!\n")
            
    except KeyboardInterrupt:
        print("\n\n👋 خروج...\n")
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}\n")

if __name__ == '__main__':
    main()
