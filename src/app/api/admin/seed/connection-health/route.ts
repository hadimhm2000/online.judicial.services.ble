import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

// ⭐ v1.3 — «وضعیت اتصال بخش‌های ربات به پنل»
//
// برای هر بخشِ ربات نشان می‌دهد:
//   - آخرین سینک (newest createdAt)
//   - تعداد کل و تعداد امروز
//   - وضعیت اتصال: active (۲۴ ساعت اخیر) / idle (۷ روز) / stale (بیشتر) / none (هیچ داده‌ای)
//
// بخش «محاسبه تمبر» ابزار رایگانِ بدون پرونده است و عمداً Case ثبت نمی‌کند.

interface ServiceStatus {
  key: string;
  label: string;
  kind: 'case' | 'message' | 'tool';
  status: 'active' | 'idle' | 'stale' | 'none' | 'tool';
  total: number;
  todayCount: number;
  lastSyncAt: string | null;
  note?: string;
}

const CASE_SERVICES: { key: string; label: string }[] = [
  { key: 'INQUIRY', label: 'استعلام پرونده' },
  { key: 'REGIONAL_VALUE', label: 'ارزش منطقه‌ای' },
  { key: 'LAVAYEH', label: 'ثبت لایحه' },
  { key: 'EZHHARNAMEH', label: 'ثبت اظهارنامه' },
  { key: 'TAJDID_NAZAR', label: 'دعاوی اعتراضی' },
  { key: 'CHECK', label: 'ثبت دادخواست چک' },
  { key: 'EALAM_VAKALAHT', label: 'اعلام وکالت' },
  { key: 'ADMIN_SEND', label: 'هزینهٔ پیام مدیریت' },
];

function classify(lastIso: string | null): 'active' | 'idle' | 'stale' | 'none' {
  if (!lastIso) return 'none';
  const age = Date.now() - new Date(lastIso).getTime();
  if (age <= 24 * 3600 * 1000) return 'active';
  if (age <= 7 * 24 * 3600 * 1000) return 'idle';
  return 'stale';
}

export async function GET() {
  try {
    const todayStart = new Date(new Date().setHours(0, 0, 0, 0));

    const results: ServiceStatus[] = await Promise.all(
      CASE_SERVICES.map(async (s) => {
        const [last, total, todayCount] = await Promise.all([
          db.case.findFirst({
            where: { serviceType: s.key },
            orderBy: { createdAt: 'desc' },
            select: { createdAt: true },
          }),
          db.case.count({ where: { serviceType: s.key } }),
          db.case.count({
            where: { serviceType: s.key, createdAt: { gte: todayStart } },
          }),
        ]);
        const lastSyncAt = last?.createdAt?.toISOString() ?? null;
        return {
          key: s.key,
          label: s.label,
          kind: 'case' as const,
          status: classify(lastSyncAt),
          total,
          todayCount,
          lastSyncAt,
        };
      })
    );

    // پیام‌های مدیر (BotMessage) — بخش جداگانهٔ پنل
    try {
      const [lastMsg, totalMsgs, todayMsgs] = await Promise.all([
        db.botMessage.findFirst({
          orderBy: { createdAt: 'desc' },
          select: { createdAt: true },
        }),
        db.botMessage.count(),
        db.botMessage.count({ where: { createdAt: { gte: todayStart } } }),
      ]);
      const lastSyncAt = lastMsg?.createdAt?.toISOString() ?? null;
      results.push({
        key: 'BOT_MESSAGES',
        label: 'پیام‌های مدیر به کاربر',
        kind: 'message',
        status: classify(lastSyncAt),
        total: totalMsgs,
        todayCount: todayMsgs,
        lastSyncAt,
      });
    } catch {
      // مدل BotMessage در دسترس نیست (مثلاً db push اجرا نشده) — بخش ناشناخته گزارش شود
      results.push({
        key: 'BOT_MESSAGES',
        label: 'پیام‌های مدیر به کاربر',
        kind: 'message',
        status: 'none',
        total: 0,
        todayCount: 0,
        lastSyncAt: null,
        note: 'مدل BotMessage در دیتابیس یافت نشد — prisma db push را اجرا کنید',
      });
    }

    results.push({
      key: 'STAMP_CALC',
      label: 'محاسبهٔ تمبر',
      kind: 'tool',
      status: 'tool',
      total: 0,
      todayCount: 0,
      lastSyncAt: null,
      note: 'ابزار رایگان — پرونده و پرداختی ندارد (ثبت در پنل لازم نیست)',
    });

    const connectedCount = results.filter(
      (r) => r.kind === 'case' && (r.total > 0 || r.status !== 'none')
    ).length;

    return NextResponse.json({
      services: results,
      summary: {
        totalSections: results.length,
        caseSections: CASE_SERVICES.length,
        withData: results.filter((r) => r.kind !== 'tool' && r.total > 0).length,
        activeToday: results.filter((r) => r.status === 'active').length,
      },
      generatedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Connection health error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch connection health' },
      { status: 500 }
    );
  }
}
