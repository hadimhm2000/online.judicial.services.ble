// ⭐ v1.7 — نرمال‌سازی متن برای جستجوی پنل
//
// چرا جستجو «هیچ نتیجه‌ای» نمی‌داد:
//   • اعداد با کیبورد فارسی (۱۲۳) تایپ می‌شوند ولی کد رهگیری/شناسه بله/کد ملی
//     در پایگاه داده با ارقام لاتین (123) ذخیره شده‌اند و LIKE آن‌ها را برابر نمی‌داند.
//   • متن‌های سامانهٔ قضایی اغلب «ي/ك» عربی دارند ولی کیبورد فارسی «ی/ک» می‌زند.
//   • نیم‌فاصله، اعراب و کشیده هم باعث عدم تطابق می‌شوند.
// این تابع هر دو طرف (عبارت جستجو و داده) را به یک شکل واحد می‌برد.

const CHAR_MAP: Record<string, string> = {
  'ي': 'ی', 'ى': 'ی', 'ئ': 'ی',
  'ك': 'ک',
  'ة': 'ه', 'ۀ': 'ه',
  'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
  'ؤ': 'و',
};

export function normalizeSearchText(input: unknown): string {
  if (input === null || input === undefined) return '';
  let s = String(input);
  // ارقام فارسی و عربی → لاتین
  s = s.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0));
  s = s.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
  // حروف عربی → فارسی
  s = s.replace(/[يىئكةۀأإآٱؤ]/g, (c) => CHAR_MAP[c] ?? c);
  // اعراب، کشیده و کاراکترهای کنترلی جهت‌نما
  s = s.replace(/[ً-ٰٟـ‎‏‪-‮]/g, '');
  // نیم‌فاصله و فاصله‌های خاص → فاصله
  s = s.replace(/[‌‍   ]/g, ' ');
  return s.toLowerCase().replace(/\s+/g, ' ').trim();
}

/** توکن‌های عبارت جستجو (همه باید در متن پیدا شوند). */
export function searchTokens(query: string): string[] {
  return normalizeSearchText(query).split(' ').filter(Boolean);
}

/** آیا همهٔ توکن‌ها در متن (نرمال‌شده) هستند؟ */
export function matchesAllTokens(haystack: string, tokens: string[]): boolean {
  if (tokens.length === 0) return true;
  const compactHay = haystack.replace(/[\s-]/g, '');
  return tokens.every((t) => haystack.includes(t) || compactHay.includes(t.replace(/-/g, '')));
}

/** «نام ساختگی» — ربات در بسیاری از مسیرها به‌جای نام، شناسهٔ بله را می‌فرستد. */
export function isPlaceholderName(name: string | null | undefined, baleUserId?: string | null): boolean {
  if (!name) return true;
  const n = normalizeSearchText(name);
  if (!n) return true;
  if (baleUserId && n === normalizeSearchText(baleUserId)) return true;
  return /^\d+$/.test(n);
}

/**
 * متن قابل‌جستجو از یک رشتهٔ JSON (مثل persons). پایتون با ensure_ascii
 * پیش‌فرض، حروف فارسی را به‌صورت \u06cc ذخیره می‌کند؛ با parse کردن،
 * مقادیر واقعی (نام، کد ملی و ...) برای جستجو استخراج می‌شوند.
 */
export function flattenJsonForSearch(raw: string | null | undefined): string {
  if (!raw) return '';
  const trimmed = raw.trim();
  if (!trimmed.startsWith('[') && !trimmed.startsWith('{')) return raw;
  try {
    const out: string[] = [];
    const walk = (v: unknown) => {
      if (v === null || v === undefined) return;
      if (Array.isArray(v)) { v.forEach(walk); return; }
      if (typeof v === 'object') { Object.values(v as Record<string, unknown>).forEach(walk); return; }
      out.push(String(v));
    };
    walk(JSON.parse(trimmed));
    return out.join(' ');
  } catch {
    return raw;
  }
}
