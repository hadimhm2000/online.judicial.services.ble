// ⭐ v1.7 — محاسبهٔ سود (مشترک بین API آمار و رابط کاربری)
//
// قاعدهٔ کارفرما (۱۴۰۵/۰۷):
//   ۱) اگر کاربر «پیش‌پرداخت» را پرداخت کرده باشد، کل مبلغ پیش‌پرداخت
//      مستقیماً سود است (فارغ از اینکه مابقی پرداخت شده یا نه).
//   ۲) اگر پس از چاپ و اعلام مبلغ، کاربر «مابقی» را هم پرداخت کند:
//      سودِ این مرحله = مابقیِ پرداخت‌شده − هزینهٔ سامانه.
//
//   سود پرونده = پیش‌پرداخت + (مابقی پرداخت شده؟ مابقی − هزینهٔ سامانه : ۰)
//
// نکته: از v1.7 وقتی پیش‌پرداخت وجود دارد، فیلد fee همان «مابقی» است
// (ربات پس از کسر پیش‌پرداخت، مبلغ مابقی را در fee ثبت می‌کند).
// برای پرونده‌های بدون پیش‌پرداخت (prepayAmount = 0) فرمول به همان
// «fee − هزینهٔ سامانه» قبلی برمی‌گردد.
//
// همهٔ مبالغ به «تومان» هستند.

export const PAID_FEE_STATUSES = ['PAID', 'MANUAL_APPROVED'];

// سرویس‌هایی که هزینهٔ سامانه ندارند — کل مبلغ، سود است
export const NO_SYSTEM_COST_SERVICES = new Set([
  'INQUIRY',
  'REGIONAL_VALUE',
  'ADMIN_SEND',
  'STAMP_CALC',
  'UNKNOWN',
]);

// سرویس‌هایی که کاربر دقیقاً هزینهٔ سامانه را می‌پردازد (بدون مارکاپ)
const PASS_THROUGH_SERVICES = new Set(['CHECK', 'TAJDID_NAZAR']);

// وارون‌سازی فرمول کسرِ پلکانی لایحه/اعلام وکالت (تومان):
//   total = 2×rounded − ded   (ded: ۱۰,۰۰۰ / ۲۸,۰۰۰ / ۴۰,۰۰۰ تومان)
function invertLavayehStyleFormula(total: number): number {
  const r1 = (total + 10_000) / 2;
  if (r1 > 0 && r1 <= 200_000 && r1 % 100 === 0) return r1;
  const r2 = (total + 28_000) / 2;
  if (r2 > 200_000 && r2 <= 300_000 && r2 % 100 === 0) return r2;
  const r3 = (total + 40_000) / 2;
  if (r3 > 300_000 && r3 % 100 === 0) return r3;
  return Math.round(total / 2);
}

/**
 * هزینهٔ سامانه — مقدار دقیق ثبت‌شده توسط ربات، در غیر این صورت برآورد
 * از روی «مبلغ کل» (= مابقی + پیش‌پرداخت) برای پرونده‌های قدیمی.
 */
export function estimateSystemCost(
  serviceType: string,
  totalFee: number,
  recordedCost: number | null | undefined,
): { cost: number; exact: boolean } {
  if (recordedCost !== null && recordedCost !== undefined) {
    return { cost: recordedCost, exact: true };
  }
  if (!totalFee || totalFee <= 0) return { cost: 0, exact: false };
  if (NO_SYSTEM_COST_SERVICES.has(serviceType)) return { cost: 0, exact: true };
  if (PASS_THROUGH_SERVICES.has(serviceType)) return { cost: totalFee, exact: false };
  if (serviceType === 'LAVAYEH' || serviceType === 'EALAM_VAKALAHT') {
    return { cost: invertLavayehStyleFormula(totalFee), exact: false };
  }
  if (serviceType === 'EZHHARNAMEH') {
    const approx = (totalFee - 45_000) / 2;
    return { cost: approx > 0 ? Math.round(approx) : 0, exact: false };
  }
  return { cost: 0, exact: false };
}

export interface ProfitInput {
  serviceType: string;
  fee: number | null | undefined;
  feeStatus: string;
  systemCost: number | null | undefined;
  prepayAmount?: number | null;
}

export interface ProfitBreakdown {
  /** سود حاصل از پیش‌پرداخت (کل مبلغ پیش‌پرداخت) */
  prepayProfit: number;
  /** سود مرحلهٔ دوم: مابقی − هزینهٔ سامانه (فقط اگر مابقی پرداخت شده) */
  remainingProfit: number;
  /** جمع سود پرونده */
  profit: number;
  /** هزینهٔ سامانهٔ لحاظ‌شده (۰ اگر مابقی هنوز پرداخت نشده) */
  systemCost: number;
  /** درآمد واقعی دریافت‌شده (پیش‌پرداخت + مابقیِ پرداخت‌شده) */
  revenue: number;
  remainingPaid: boolean;
  exactSystemCost: boolean;
}

export function computeCaseProfit(c: ProfitInput): ProfitBreakdown {
  const prepay = Math.max(0, c.prepayAmount ?? 0);
  const remaining = Math.max(0, c.fee ?? 0);
  const remainingPaid = PAID_FEE_STATUSES.includes(c.feeStatus);

  let remainingProfit = 0;
  let systemCost = 0;
  let exact = true;

  if (remainingPaid) {
    const est = estimateSystemCost(c.serviceType, remaining + prepay, c.systemCost);
    systemCost = est.cost;
    exact = est.exact;
    // سود مرحلهٔ دوم = مابقیِ پرداخت‌شده − هزینهٔ سامانه
    // (ممکن است منفی شود اگر مابقی کمتر از هزینهٔ سامانه باشد — زیان واقعی)
    remainingProfit = remaining - systemCost;
  }

  return {
    prepayProfit: prepay,
    remainingProfit,
    profit: prepay + remainingProfit,
    systemCost,
    revenue: prepay + (remainingPaid ? remaining : 0),
    remainingPaid,
    exactSystemCost: exact,
  };
}

// ─────────────────────────────────────────────────────────────────────
// ⭐ v1.8 — سود یک پرداخت کارت‌به‌کارت (CardPayment)
//   PREPAY  → کل مبلغ سود است (قاعدهٔ پیش‌پرداخت)
//   DIRECT  → سرویس بدون هزینهٔ سامانه — کل مبلغ سود است
//   FINAL   → مبلغ − هزینهٔ سامانهٔ پروندهٔ مرتبط (در نبود پرونده، برآورد)
// همهٔ مبالغ به تومان.
// ─────────────────────────────────────────────────────────────────────
export interface CardPaymentProfitInput {
  amount: number;
  paymentKind: string;
  serviceType: string;
}

export function computeCardPaymentProfit(
  cp: CardPaymentProfitInput,
  linkedCase?: { serviceType: string; fee: number | null; prepayAmount?: number | null; systemCost: number | null } | null,
): { profit: number; systemCost: number; exact: boolean } {
  const amount = Math.max(0, cp.amount || 0);
  if (cp.paymentKind !== 'FINAL') {
    return { profit: amount, systemCost: 0, exact: true };
  }
  const est = linkedCase
    ? estimateSystemCost(
        linkedCase.serviceType,
        (linkedCase.fee ?? 0) + (linkedCase.prepayAmount ?? 0),
        linkedCase.systemCost,
      )
    : estimateSystemCost(cp.serviceType, amount, null);
  return { profit: amount - est.cost, systemCost: est.cost, exact: est.exact && !!linkedCase };
}
