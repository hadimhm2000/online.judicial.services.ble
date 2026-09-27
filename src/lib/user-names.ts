import { db } from '@/lib/db';
import { isPlaceholderName } from '@/lib/search-normalize';

// ⭐ v1.7 — نام واقعی کاربر بر اساس شناسهٔ بله
// ربات در بیشتر مسیرها fullName پرونده را همان شناسهٔ بله ثبت می‌کند؛
// نام واقعی معمولاً در پرونده‌های دیگر همان کاربر (مثل استعلام‌ها)،
// پیام‌های پنل یا لیست کاربران معاف وجود دارد. این نقشه برای نمایش و
// جستجو استفاده می‌شود.
export async function buildKnownNameMap(baleUserIds?: string[]): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  const idFilter = baleUserIds ? { baleUserId: { in: baleUserIds } } : {};
  if (baleUserIds && baleUserIds.length === 0) return map;

  const [caseNames, msgNames, exemptNames] = await Promise.all([
    db.case.findMany({
      where: idFilter,
      select: { baleUserId: true, fullName: true },
      orderBy: { createdAt: 'desc' },
      distinct: ['baleUserId', 'fullName'],
    }),
    db.botMessage.findMany({
      where: { ...idFilter, fullName: { not: null } },
      select: { baleUserId: true, fullName: true },
      orderBy: { createdAt: 'desc' },
      distinct: ['baleUserId', 'fullName'],
    }).catch(() => []),
    db.exemptUser.findMany({
      where: { ...idFilter, fullName: { not: null } },
      select: { baleUserId: true, fullName: true },
    }).catch(() => []),
  ]);

  // اولویت: کاربران معاف (ثبت دستی مدیر) > پرونده‌ها (جدیدترین) > پیام‌ها
  for (const src of [exemptNames, caseNames, msgNames]) {
    for (const r of src) {
      if (!r.fullName || map.has(r.baleUserId)) continue;
      if (isPlaceholderName(r.fullName, r.baleUserId)) continue;
      map.set(r.baleUserId, r.fullName);
    }
  }
  return map;
}

/** جایگزینی fullNameهای ساختگی (شناسهٔ عددی) با نام واقعی شناخته‌شده. */
export function applyKnownNames<T extends { baleUserId: string; fullName: string }>(
  rows: T[],
  names: Map<string, string>,
): T[] {
  return rows.map((r) => {
    if (!isPlaceholderName(r.fullName, r.baleUserId)) return r;
    const known = names.get(r.baleUserId);
    return known ? { ...r, fullName: known } : r;
  });
}
