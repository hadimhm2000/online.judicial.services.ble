/**
 * انواع سند/سرویس برای «پیام مدیر به کاربر» وقتی هزینه دارد.
 *
 * وقتی مدیر برای پیام هزینه وارد می‌کند و نوع سندی انتخاب می‌کند، پس از
 * پرداخت موفق کاربر (فاکتور کیف پول بله)، ربات به‌صورت خودکار «روند درج
 * امضا» (کد موقت سامانهٔ ثنا) را برای همان نوع سند آغاز می‌کند.
 *
 * signMenuPath = مسیر منوی سامانهٔ ثنا که به‌ترتیب کلیک می‌شود تا به صفحهٔ
 * امضای همان نوع سند رسید (مطابق lavayeh_sign_scenario.navigate_to_sign_page).
 * null یعنی مسیر پیش‌فرض لایحه («ارایه و پیگیری لایحه») یا فلوی اختصاصی
 * اظهارنامه — و hasSignFlow=false یعنی اصلاً امضا ندارد.
 */

export interface PanelServiceOption {
  /** مقدار ذخیره‌شده در DB و پاس داده‌شده به ربات */
  value: string;
  /** برچسب فارسی برای UI */
  label: string;
  /** مسیر منوی سامانه برای ناوبری امضا — null = پیش‌فرض لایحه */
  signMenuPath: string[] | null;
  /** آیا پس از پرداخت، فلوی امضا شروع می‌شود؟ */
  hasSignFlow: boolean;
}

export const PANEL_SERVICE_OPTIONS: PanelServiceOption[] = [
  {
    value: 'NONE',
    label: 'بدون امضا — فقط ارسال پیام',
    signMenuPath: null,
    hasSignFlow: false,
  },
  {
    value: 'LAVAYEH',
    label: 'لایحه',
    signMenuPath: null, // مسیر پیش‌فرض: «ارایه و پیگیری لایحه»
    hasSignFlow: true,
  },
  {
    value: 'EZHHARNAMEH',
    label: 'اظهارنامه',
    signMenuPath: null, // فلوی اختصاصی امضای اظهارنامه
    hasSignFlow: true,
  },
  {
    value: 'TAJDID_NAZAR',
    label: 'تجدیدنظرخواهی',
    signMenuPath: ['تجدیدنظرخواهی'],
    hasSignFlow: true,
  },
  {
    value: 'VAKHAVI',
    label: 'واخواهی',
    signMenuPath: ['واخواهی'],
    hasSignFlow: true,
  },
  {
    value: 'FARQAM',
    label: 'فرجام‌خواهی',
    signMenuPath: ['فرجام خواهی'],
    hasSignFlow: true,
  },
  {
    value: 'DADKHAST_BEDAVI',
    label: 'دادخواست بدوی',
    signMenuPath: ['ارایه و پیگیری دادخواست', 'دادخواست بدوی'],
    hasSignFlow: true,
  },
  {
    value: 'SOHL',
    label: 'دعاوی صلح',
    signMenuPath: ['دعاوی دادگاههای صلح', 'دعاوی حقوقی'],
    hasSignFlow: true,
  },
  {
    value: 'CHECK_BEDAVI',
    label: 'چک — دادخواست بدوی',
    signMenuPath: ['ارایه و پیگیری دادخواست', 'دادخواست بدوی'],
    hasSignFlow: true,
  },
  {
    value: 'CHECK_SOHL',
    label: 'چک — دعاوی صلح',
    signMenuPath: ['دعاوی دادگاههای صلح', 'دعاوی حقوقی'],
    hasSignFlow: true,
  },
  {
    value: 'INQUIRY',
    label: 'استعلام — بدون امضا',
    signMenuPath: null,
    hasSignFlow: false,
  },
];

/** گزینهٔ مربوط به یک مقدار serviceType را برمی‌گرداند (اگر معتبر باشد). */
export function getServiceOption(value: string | null | undefined): PanelServiceOption | undefined {
  if (!value) return undefined;
  return PANEL_SERVICE_OPTIONS.find((o) => o.value === value);
}
