import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

// ⭐ v1.3 — محاسبهٔ سود
//
// قاعدهٔ کارفرما:
//   ۱) استعلام‌ها (INQUIRY / REGIONAL_VALUE) و خدمات بدون هزینهٔ سامانه
//      (ADMIN_SEND): کل مبلغ پرداختی مستقیماً سود است.
//   ۲) سایر خدمات: سود = مبلغ اعلام‌شده به کاربر (fee) − هزینهٔ سامانه (systemCost).
//      - systemCost برای پرونده‌های جدید دقیقاً از ربات (payment_id_capture) ثبت می‌شود.
//      - برای پرونده‌های قدیمی، از فرمول‌های قیمت‌گذاری ربات برمی‌گردیم:
//        * CHECK / TAJDID_NAZAR / EALAM_VAKALAHT: کاربر دقیقاً هزینهٔ سامانه را می‌پردازد
//          (skip_fee_calc) → هزینهٔ سامانه = fee → سود ۰.
//        * LAVAYEH / EZHHARNAMEH: fee = 2×roundUp(هزینهٔ سامانه) − کسرِ پلکانی
//          (۱۰۰ / ۲۸۰ / ۴۰۰ هزار ریال) → با وارون‌سازی فرمول، هزینهٔ سامانه
//          بازسازی می‌شود (خطای حداکثر <۱۰۰۰ ریال).
//
// شرایط شمارش: مثل «درآمد» فقط پرونده‌های PAID / MANUAL_APPROVED.

const PAID_CONDITION = { feeStatus: { in: ['PAID', 'MANUAL_APPROVED'] } };

// سرویس‌هایی که هزینهٔ سامانه ندارند — کل مبلغ، سود است
const NO_SYSTEM_COST_SERVICES = new Set([
  'INQUIRY',
  'REGIONAL_VALUE',
  'ADMIN_SEND',
  'STAMP_CALC',
  'UNKNOWN',
]);

// سرویس‌هایی که کاربر دقیقاً هزینهٔ سامانه را می‌پردازد — سود ۰
const PASS_THROUGH_SERVICES = new Set([
  'CHECK',
  'TAJDID_NAZAR',
  'EALAM_VAKALAHT',
]);

function estimateSystemCost(serviceType: string, fee: number, recordedCost: number | null): number {
  // هزینهٔ سامانهٔ دقیق ثبت‌شده توسط ربات
  if (recordedCost !== null && recordedCost !== undefined) return recordedCost;

  // پروندهٔ بدون مبلغ (معاف / دستی): هزینهٔ سامانه‌ای وجود ندارد
  if (!fee || fee <= 0) return 0;

  if (NO_SYSTEM_COST_SERVICES.has(serviceType)) return 0;

  if (PASS_THROUGH_SERVICES.has(serviceType)) {
    // کاربر دقیقاً هزینهٔ سامانه را پرداخت کرده — سودی ندارد
    return fee;
  }

  if (serviceType === 'LAVAYEH' || serviceType === 'EZHHARNAMEH') {
    // وارون‌سازی فرمول: fee = 2×rounded − ded  ⟹  rounded = (fee + ded) / 2
    const r1 = (fee + 100_000) / 2;
    if (r1 > 0 && r1 <= 2_000_000 && r1 % 1000 === 0) return r1;
    const r2 = (fee + 280_000) / 2;
    if (r2 > 2_000_000 && r2 <= 3_000_000 && r2 % 1000 === 0) return r2;
    const r3 = (fee + 400_000) / 2;
    if (r3 > 3_000_000 && r3 % 1000 === 0) return r3;
    // حالت‌های خاص (معاف/دستی): تقریب نصف مبلغ
    return Math.round(fee / 2);
  }

  return 0;
}

export async function GET() {
  try {
    const [
      total,
      completed,
      incomplete,
      unpaid,
      readyToSend,
      failed,
      cancelled,
      processing,
      todayCases,
      totalRevenue,
      unpaidRevenue,
    ] = await Promise.all([
      db.case.count(),
      db.case.count({ where: { status: 'COMPLETED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'INCOMPLETE', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { feeStatus: 'UNPAID', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { isInReadyToSend: true, serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'FAILED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'CANCELLED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'PROCESSING', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({
        where: {
          createdAt: {
            gte: new Date(new Date().setHours(0, 0, 0, 0)),
          },
        },
      }),
      db.case.aggregate({
        _sum: { fee: true },
        where: PAID_CONDITION,
      }),
      db.case.aggregate({
        _sum: { fee: true },
        where: { feeStatus: 'UNPAID' },
      }),
    ]);

    // ─── ⭐ v1.3: محاسبهٔ سود ───
    const paidCases = await db.case.findMany({
      where: PAID_CONDITION,
      select: { serviceType: true, fee: true, systemCost: true },
    });

    let totalProfit = 0;
    let inquiryProfit = 0; // سود استعلام‌ها و خدمات بدون هزینهٔ سامانه
    let serviceProfit = 0; // سود خدمات ثبت‌شده (لایحه/چک/...)
    let systemCostTotal = 0; // مجموع هزینهٔ سامانه (ریال)
    let estimatedCount = 0; // چند پرونده بدون systemCost دقیق محاسبه شد
    let exactCount = 0;

    const profitByService: Record<string, { profit: number; revenue: number; systemCost: number; count: number }> = {};

    for (const c of paidCases) {
      const fee = c.fee ?? 0;
      const hasExact = c.systemCost !== null && c.systemCost !== undefined;
      const systemCost = estimateSystemCost(c.serviceType, fee, c.systemCost ?? null);
      const profit = Math.max(0, fee) - systemCost;

      totalProfit += profit;
      systemCostTotal += systemCost;
      if (hasExact) exactCount += 1;
      else estimatedCount += 1;

      if (NO_SYSTEM_COST_SERVICES.has(c.serviceType)) {
        inquiryProfit += profit;
      } else {
        serviceProfit += profit;
      }

      const bucket = profitByService[c.serviceType] || { profit: 0, revenue: 0, systemCost: 0, count: 0 };
      bucket.profit += profit;
      bucket.revenue += fee;
      bucket.systemCost += systemCost;
      bucket.count += 1;
      profitByService[c.serviceType] = bucket;
    }

    const serviceBreakdown = await db.case.groupBy({
      by: ['serviceType'],
      _count: { id: true },
    });

    const sevenDaysAgo = new Date(Date.now() - 7 * 86400000);
    const dailyCases = await db.case.groupBy({
      by: ['createdAt'],
      where: { createdAt: { gte: sevenDaysAgo } },
      _count: { id: true },
    });

    return NextResponse.json({
      total,
      completed,
      incomplete,
      unpaid,
      readyToSend,
      failed,
      cancelled,
      processing,
      todayCases,
      totalRevenue: totalRevenue._sum.fee || 0,
      unpaidRevenue: unpaidRevenue._sum.fee || 0,
      // ⭐ v1.3 — سود
      totalProfit: Math.round(totalProfit),
      inquiryProfit: Math.round(inquiryProfit),
      serviceProfit: Math.round(serviceProfit),
      systemCostTotal: Math.round(systemCostTotal),
      profitExactCount: exactCount,
      profitEstimatedCount: estimatedCount,
      profitByService: Object.entries(profitByService).map(([serviceType, v]) => ({
        serviceType,
        ...v,
        profit: Math.round(v.profit),
        systemCost: Math.round(v.systemCost),
      })),
      serviceBreakdown,
      createdAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 });
  }
}
