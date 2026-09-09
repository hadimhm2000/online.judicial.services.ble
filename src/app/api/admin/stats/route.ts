import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

// ⭐ v1.3 — محاسبهٔ سود
// ⭐ v1.5 — رفع باگ سود صفر برای اعلام وکالت + فرمول اختصاصی اظهارنامه
//
// قاعدهٔ کارفرما:
//   ۱) استعلام‌ها (INQUIRY / REGIONAL_VALUE) و خدمات بدون هزینهٔ سامانه
//      (ADMIN_SEND): کل مبلغ پرداختی مستقیماً سود است.
//   ۲) سایر خدمات: سود = مبلغ اعلام‌شده به کاربر (fee) − هزینهٔ سامانه (systemCost).
//      - systemCost برای پرونده‌های جدید دقیقاً از ربات (payment_id_capture) ثبت می‌شود.
//      - برای پرونده‌های قدیمی، از فرمول‌های قیمت‌گذاری ربات برمی‌گردیم:
//        * CHECK / TAJDID_NAZAR: کاربر دقیقاً هزینهٔ سامانه را می‌پردازد
//          (skip_fee_calc، بدون فرمول مارکاپ) → هزینهٔ سامانه = fee → سود ۰.
//        * LAVAYEH: fee = 2×roundUp1000(هزینهٔ سامانه) − کسرِ پلکانی
//          (۱۰۰ / ۲۸۰ / ۴۰۰ هزار ریال) → با وارون‌سازی فرمول، هزینهٔ سامانه
//          بازسازی می‌شود (خطای حداکثر <۱۰۰۰ ریال).
//        * EZHHARNAMEH: فرمول متفاوتی دارد (net = mainTotal − ۳ ردیف
//          کسرشونده؛ rounded = roundUp10k(net)؛ final = roundUp10k(rounded
//          + ۴۵۰,۰۰۰ + mainTotal)) — استفاده از فرمول لایحه برای این سرویس
//          نادرست است، بنابراین وارون‌سازی جداگانه‌ای دارد.
//        * EALAM_VAKALAHT: از v1.5 دیگر pass-through نیست — ربات از همان
//          فرمول کسرِ پلکانی لایحه (روی مبلغ خامِ سامانه) برای محاسبهٔ مبلغ
//          نهایی استفاده می‌کند، پس وارون‌سازی مشابه لایحه به‌کار می‌رود.
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
// ⭐ v1.5: EALAM_VAKALAHT از این لیست حذف شد — ربات از v1.5 مارکاپ واقعی
// روی این سرویس اعمال می‌کند (رجوع کنید به ealam_vakalaht_scenario.py)،
// بنابراین دیگر pass-through نیست.
const PASS_THROUGH_SERVICES = new Set([
  'CHECK',
  'TAJDID_NAZAR',
]);

// وارون‌سازی فرمول کسرِ پلکانی لایحه/اعلام وکالت (روی مبلغ به تومان):
//   fee_toman = 2×rounded_toman − ded_toman
//   کسرهای پلکانی: ۱۰,۰۰۰ / ۲۸,۰۰۰ / ۴۰,۰۰۰ تومان (۱۰۰/۲۸۰/۴۰۰ هزار ریال)
function invertLavayehStyleFormula(fee: number): number {
  const r1 = (fee + 10_000) / 2;
  if (r1 > 0 && r1 <= 200_000 && r1 % 100 === 0) return r1;
  const r2 = (fee + 28_000) / 2;
  if (r2 > 200_000 && r2 <= 300_000 && r2 % 100 === 0) return r2;
  const r3 = (fee + 40_000) / 2;
  if (r3 > 300_000 && r3 % 100 === 0) return r3;
  // حالت‌های خاص (معاف/دستی): تقریب نصف مبلغ
  return Math.round(fee / 2);
}

function estimateSystemCost(serviceType: string, fee: number, recordedCost: number | null): number {
  // ⭐ fee و systemCost از v1.4 به بعد هر دو به «تومان» هستند (مثل استعلام‌ها).
  //   - ربات همهٔ feeها را قبل از ارسال به پنل به تومان تبدیل می‌کند
  //     (court_total/final_fee ریال → fee = مبلغ // 10 تومان).
  //   - systemCost هم توسط payment_id_capture به تومان ثبت می‌شود.
  //   - پرونده‌های قدیمی (ریال) باید با اسکریپت migrate_fees_to_toman.js
  //     یکبار migrate شوند.

  // هزینهٔ سامانهٔ دقیق ثبت‌شده توسط ربات
  if (recordedCost !== null && recordedCost !== undefined) return recordedCost;

  // پروندهٔ بدون مبلغ (معاف / دستی): هزینهٔ سامانه‌ای وجود ندارد
  if (!fee || fee <= 0) return 0;

  if (NO_SYSTEM_COST_SERVICES.has(serviceType)) return 0;

  if (PASS_THROUGH_SERVICES.has(serviceType)) {
    // کاربر دقیقاً هزینهٔ سامانه را پرداخت کرده — سودی ندارد
    return fee;
  }

  // LAVAYEH و EALAM_VAKALAHT هر دو دقیقاً از فرمول کسرِ پلکانی
  // calculate_lavayeh_fee استفاده می‌کنند (رجوع کنید به config.py و
  // ealam_vakalaht_scenario.py::_calculate_cost_with_retry).
  if (serviceType === 'LAVAYEH' || serviceType === 'EALAM_VAKALAHT') {
    return invertLavayehStyleFormula(fee);
  }

  if (serviceType === 'EZHHARNAMEH') {
    // ⭐ فرمول اظهارنامه با لایحه فرق دارد.
    // رجوع کنید به ezhharnameh_scenario.py::_calculate_cost():
    //   net = mainTotal − excluded_sum (۳ ردیف کسرشونده)
    //   rounded = roundUp10k(net)
    //   final = roundUp10k(rounded + ۴۵۰,۰۰۰ + mainTotal)
    // چون excluded_sum برای پرونده‌های قدیمی در دسترس نیست، این یک
    // برآورد تقریبی است (با فرض excluded_sum ≈ ۰ و صرف‌نظر از رندها):
    //   final ≈ ۲×mainTotal + ۴۵۰,۰۰۰  (ریال)  ⟹  mainTotal ≈ (final − ۴۵۰,۰۰۰) / ۲
    // به تومان: mainTotal_toman ≈ (fee_toman − ۴۵,۰۰۰) / ۲
    // خطای این برآورد می‌تواند از وارون‌سازی لایحه بیشتر باشد — برای
    // پرونده‌های جدید systemCost همیشه دقیق از ربات ثبت می‌شود.
    const approx = (fee - 45_000) / 2;
    return approx > 0 ? Math.round(approx) : 0;
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
