"""
تست سیستم انتخاب شعب
این اسکریپت برای بررسی صحت عملکرد سیستم انتخاب شعب استفاده می‌شود
"""
import json
from pathlib import Path

def test_units_data():
    """تست بارگذاری و ساختار داده شعب"""
    
    # بررسی وجود فایل
    units_file = Path("units_compact.json")
    if not units_file.exists():
        print("❌ فایل units_compact.json یافت نشد!")
        return False
    
    # بارگذاری داده
    with units_file.open("r", encoding="utf-8") as f:
        units = json.load(f)
    
    print(f"✅ تعداد واحدها: {len(units)}")
    
    # شمارش ریشه‌ها (سطح 0 یا بدون والد)
    roots = [u for u in units if u.get("Depth") == 0 or not u.get("ParentId")]
    print(f"✅ تعداد ریشه‌ها: {len(roots)}")
    for root in roots:
        print(f"   - {root.get('UnitName')}")
    
    # شمارش دادگستری‌های استانی (سطح 1)
    provinces = [u for u in units if u.get("Depth") == 1 and "دادگستری استان" in u.get("UnitName", "")]
    print(f"\n✅ تعداد دادگستری‌های استانی: {len(provinces)}")
    
    # شمارش سازمان‌های اصلی (سطح 1)
    organizations = [u for u in units if u.get("Depth") == 1 and "دادگستری استان" not in u.get("UnitName", "")]
    print(f"✅ تعداد سازمان‌های اصلی: {len(organizations)}")
    for org in organizations:
        print(f"   - {org.get('UnitName')}")
    
    # شمارش واحدهای قابل انتخاب (دارای کد)
    selectable = [u for u in units if u.get("Code") and u.get("Code").strip()]
    print(f"\n✅ تعداد واحدهای قابل انتخاب (دارای کد): {len(selectable)}")
    
    # نمایش نمونه واحدهای قابل انتخاب
    print("\n📋 نمونه واحدهای قابل انتخاب:")
    for unit in selectable[:5]:
        print(f"   - {unit.get('UnitName')} (کد: {unit.get('Code')})")
        print(f"     مسیر: {unit.get('Path')}")
    
    # بررسی یکتا بودن Id
    ids = [u.get("Id") for u in units]
    if len(ids) != len(set(ids)):
        print("\n⚠️ هشدار: برخی Id ها تکراری هستند!")
        return False
    print("\n✅ تمامی Id ها یکتا هستند")
    
    # بررسی روابط والد-فرزند
    id_set = set(ids)
    orphans = []
    for unit in units:
        parent_id = unit.get("ParentId") or unit.get("ParentUnitId")
        if parent_id and parent_id not in id_set:
            orphans.append(unit.get("UnitName"))
    
    if orphans:
        print(f"\n⚠️ تعداد واحدهای بدون والد معتبر: {len(orphans)}")
        for orphan in orphans[:5]:
            print(f"   - {orphan}")
    else:
        print("\n✅ تمامی روابط والد-فرزند معتبر هستند")
    
    # بررسی واحدهای نهایی بدون کد
    final_without_code = [
        u for u in units 
        if not u.get("HasChildUnit") and not (u.get("Code") and u.get("Code").strip())
    ]
    
    if final_without_code:
        print(f"\n⚠️ تعداد واحدهای نهایی بدون کد: {len(final_without_code)}")
        print("   این واحدها قابل انتخاب نیستند:")
        for unit in final_without_code[:5]:
            print(f"   - {unit.get('UnitName')}")
    
    # آمار نهایی
    print("\n" + "="*60)
    print("📊 خلاصه آمار:")
    print(f"   کل واحدها: {len(units)}")
    print(f"   واحدهای قابل انتخاب: {len(selectable)}")
    print(f"   واحدهای دارای زیرمجموعه: {len([u for u in units if u.get('HasChildUnit')])}")
    print(f"   عمق بیشینه درخت: {max(u.get('Depth', 0) for u in units)}")
    print("="*60)
    
    return True

def test_branches_module():
    """تست ماژول branches.py"""
    try:
        from branches import load_units_data, UNITS_DATA, ROOT_NODES
        
        print("\n🔄 تست بارگذاری ماژول branches...")
        
        if not UNITS_DATA:
            print("⚠️ داده‌ها بارگذاری نشدند. در حال بارگذاری مجدد...")
            load_units_data()
        
        if UNITS_DATA:
            print(f"✅ ماژول branches بارگذاری شد ({len(UNITS_DATA)} واحد)")
            print(f"✅ تعداد نودهای ریشه: {len(ROOT_NODES)}")
            return True
        else:
            print("❌ ماژول branches نتوانست داده‌ها را بارگذاری کند")
            return False
            
    except Exception as e:
        print(f"❌ خطا در بارگذاری ماژول branches: {e}")
        return False

if __name__ == "__main__":
    print("🧪 شروع تست سیستم انتخاب شعب\n")
    
    # تست 1: داده‌ها
    test1 = test_units_data()
    
    # تست 2: ماژول
    test2 = test_branches_module()
    
    # نتیجه نهایی
    print("\n" + "="*60)
    if test1 and test2:
        print("✅ تمامی تست‌ها موفق بودند!")
    else:
        print("⚠️ برخی تست‌ها ناموفق بودند. لطفاً خطاها را بررسی کنید.")
    print("="*60)
