import { db } from '@/lib/db';
import { NextResponse } from 'next/server';
import { computeCaseProfit, NO_SYSTEM_COST_SERVICES, PAID_FEE_STATUSES } from '@/lib/profit';

// ⭐ v1.7 — محاسبهٔ سود با پیش‌پرداخت (منطق در src/lib/profit.ts)
//   سود پرونده = پیش‌پرداخت + (مابقی پرداخت شده؟ مابقی − هزینهٔ سامانه : ۰)
//
// درآمد (totalRevenue) = پیش‌پرداخت‌های دریافتی + مبالغ پرداخت‌شدهٔ fee.

const PAID_CONDITION = { feeStatus: { in: PAID_FEE_STATUSES } };

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

    // ─── ⭐ v1.7: محاسبهٔ سود (پیش‌پرداخت + مابقی − هزینهٔ سامانه) ───
    // پرونده‌هایی که یا مابقی را پرداخت کرده‌اند یا پیش‌پرداخت داشته‌اند
    const profitCases = await db.case.findMany({
      where: { OR: [PAID_CONDITION, { prepayAmount: { gt: 0 } }] },
      select: { serviceType: true, fee: true, feeStatus: true, systemCost: true, prepayAmount: true },
    });

    let totalProfit = 0;
    let inquiryProfit = 0; // سود استعلام‌ها و خدمات بدون هزینهٔ سامانه
    let serviceProfit = 0; // سود خدمات ثبت‌شده (لایحه/چک/...)
    let prepayProfit = 0; // سود حاصل از پیش‌پرداخت‌ها
    let remainingProfit = 0; // سود مرحلهٔ دوم (مابقی − هزینهٔ سامانه)
    let prepayTotal = 0;
    let systemCostTotal = 0;
    let estimatedCount = 0;
    let exactCount = 0;

    const profitByService: Record<string, { profit: number; revenue: number; systemCost: number; prepay: number; count: number }> = {};

    for (const c of profitCases) {
      const p = computeCaseProfit(c);

      totalProfit += p.profit;
      prepayProfit += p.prepayProfit;
      remainingProfit += p.remainingProfit;
      prepayTotal += p.prepayProfit;
      systemCostTotal += p.systemCost;
      if (p.remainingPaid) {
        if (p.exactSystemCost) exactCount += 1;
        else estimatedCount += 1;
      }

      if (NO_SYSTEM_COST_SERVICES.has(c.serviceType)) inquiryProfit += p.profit;
      else serviceProfit += p.profit;

      const bucket = profitByService[c.serviceType] || { profit: 0, revenue: 0, systemCost: 0, prepay: 0, count: 0 };
      bucket.profit += p.profit;
      bucket.revenue += p.revenue;
      bucket.systemCost += p.systemCost;
      bucket.prepay += p.prepayProfit;
      bucket.count += 1;
      profitByService[c.serviceType] = bucket;
    }

    // ─── ⭐ v1.7: خلاصهٔ دفتر مبالغ قابل بازگشت/کسر ───
    let openCredits: Array<{ kind: string; _sum: { amount: number | null }; _count: { id: number } }> = [];
    try {
      openCredits = await db.userCredit.groupBy({
        by: ['kind'],
        where: { status: 'OPEN' },
        _sum: { amount: true },
        _count: { id: true },
      });
    } catch {
      // جدول UserCredit هنوز ساخته نشده (prisma db push اجرا نشده)
    }
    const creditSum = (kind: string) => openCredits.find((r) => r.kind === kind)?._sum.amount ?? 0;
    const creditCount = openCredits.reduce((n, r) => n + r._count.id, 0);

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
      // ⭐ v1.7: درآمد = مبالغ پرداخت‌شدهٔ fee + پیش‌پرداخت‌های دریافتی
      totalRevenue: (totalRevenue._sum.fee || 0) + prepayTotal,
      paidFeeRevenue: totalRevenue._sum.fee || 0,
      prepayRevenue: prepayTotal,
      unpaidRevenue: unpaidRevenue._sum.fee || 0,
      // ⭐ v1.7 — سود
      totalProfit: Math.round(totalProfit),
      prepayProfit: Math.round(prepayProfit),
      remainingProfit: Math.round(remainingProfit),
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
      // ⭐ v1.7 — مبالغ باز در دفتر بازگشت/کسر
      openRefundTotal: creditSum('REFUND'),
      openDeductTotal: creditSum('DEDUCT_LATER'),
      openCreditCount: creditCount,
      serviceBreakdown,
      createdAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 });
  }
}
