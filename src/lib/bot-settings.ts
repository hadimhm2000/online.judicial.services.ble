// ⭐ v1.9 — فهرست تنظیمات ربات که از پنل قابل ویرایش‌اند (bot_settings.py)
// پیش‌فرض‌ها همان مقادیر کد ربات‌اند (config.py / prepay_registration.py /
// sana_gate.py)؛ اگر کلیدی در پنل ذخیره نشده باشد ربات همان پیش‌فرض را استفاده می‌کند.

export type BotSettingKind = 'number' | 'boolean' | 'text';

export interface BotSettingDef {
  key: string;
  label: string;
  group: string;
  kind: BotSettingKind;
  defaultValue: string;
  hint?: string;
}

export const BOT_SETTING_DEFS: BotSettingDef[] = [
  { key: 'fee.inquiry.phone', group: 'تعرفهٔ استعلام (تومان)', label: 'استعلام با شماره تماس', kind: 'number', defaultValue: '65000' },
  { key: 'fee.inquiry.nid', group: 'تعرفهٔ استعلام (تومان)', label: 'استعلام با کد ملی', kind: 'number', defaultValue: '55000' },
  { key: 'fee.inquiry.tracking', group: 'تعرفهٔ استعلام (تومان)', label: 'استعلام کد رهگیری ساده', kind: 'number', defaultValue: '50000' },
  { key: 'fee.inquiry.tracking_attach', group: 'تعرفهٔ استعلام (تومان)', label: 'استعلام کد رهگیری با منضمات (پایه)', kind: 'number', defaultValue: '50000', hint: 'به‌علاوهٔ هزینهٔ هر صفحهٔ منضمات' },

  { key: 'prepay.lavayeh_ezhhar_toman', group: 'پیش‌پرداخت ثبت (تومان)', label: 'لایحه و اظهارنامه', kind: 'number', defaultValue: '1000', hint: 'حداقل ۱,۰۰۰ تومان (محدودیت فاکتور بله)' },
  { key: 'prepay.other_toman', group: 'پیش‌پرداخت ثبت (تومان)', label: 'سایر خدمات (دادخواست، دعاوی اعتراضی، اعلام وکالت و ...)', kind: 'number', defaultValue: '2000', hint: 'حداقل ۱,۰۰۰ تومان (محدودیت فاکتور بله)' },

  { key: 'rating.enabled', group: 'نظرسنجی و گزارش', label: 'نظرسنجی پس از تحویل فعال باشد', kind: 'boolean', defaultValue: 'true' },
  { key: 'report.hour', group: 'نظرسنجی و گزارش', label: 'ساعت ارسال گزارش شبانه به مدیر (۰ تا ۲۳)', kind: 'number', defaultValue: '23' },

  { key: 'gate.outage_queued', group: 'متن‌های صف سامانه', label: 'پیام به کاربر هنگام قطعی سامانه', kind: 'text', defaultValue: '' , hint: 'خالی = متن پیش‌فرض ربات' },
  { key: 'gate.offhours_queued', group: 'متن‌های صف سامانه', label: 'پیام به کاربر برای درخواست خارج از ساعت کاری', kind: 'text', defaultValue: '', hint: 'خالی = متن پیش‌فرض ربات. {start} = ساعت شروع کار' },
  { key: 'gate.released', group: 'متن‌های صف سامانه', label: 'پیام شروع ثبت پس از آزاد شدن صف', kind: 'text', defaultValue: '', hint: 'خالی = متن پیش‌فرض ربات' },
  { key: 'gate.inquiry_closed_offhours', group: 'متن‌های صف سامانه', label: 'پیام بسته بودن استعلام خارج از ساعت کاری', kind: 'text', defaultValue: '', hint: 'خالی = متن پیش‌فرض ربات. {start} و {end} = ساعت کاری' },
  { key: 'gate.inquiry_closed_outage', group: 'متن‌های صف سامانه', label: 'پیام بسته بودن استعلام هنگام قطعی سامانه', kind: 'text', defaultValue: '', hint: 'خالی = متن پیش‌فرض ربات' },
];

export const BOT_SETTING_KEYS = new Set(BOT_SETTING_DEFS.map((d) => d.key));

/** اعتبارسنجی مقدار؛ پیام خطا یا null */
export function validateBotSetting(def: BotSettingDef, value: string): string | null {
  if (value === '') return null; // خالی = حذف و بازگشت به پیش‌فرض
  if (def.kind === 'number') {
    if (!/^\d+$/.test(value)) return 'فقط عدد صحیح مثبت';
    const n = Number(value);
    if (def.key.startsWith('prepay.') && n < 1000) return 'حداقل ۱,۰۰۰ تومان';
    if (def.key === 'report.hour' && n > 23) return 'بین ۰ تا ۲۳';
  }
  if (def.kind === 'boolean' && value !== 'true' && value !== 'false') return 'true یا false';
  if (def.kind === 'text' && value.length > 1500) return 'حداکثر ۱۵۰۰ کاراکتر';
  return null;
}
