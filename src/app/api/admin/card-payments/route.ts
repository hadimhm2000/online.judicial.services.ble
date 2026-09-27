import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { computeCardPaymentProfit } from '@/lib/profit';

// ⭐ v1.8 — پرداخت‌های کارت‌به‌کارت (ربات: card_payment.py)
//   GET  ?status=PENDING_REVIEW|APPROVED|REJECTED|PAID_VIA_GATEWAY|EXPIRED
//        → { records (با سود هر پرداخت), summary }
//   POST (از ربات) upsert بر اساس externalId:
//        { externalId, baleUserId, fullName?, serviceType, serviceLabel?, invoiceTitle?,
//          trackingCode?, amount (تومان), paymentKind?, status, receiptUrl?, rejectReason?, approvedAt? }
//
// درآمد و سود پرونده‌ها همان مسیر همیشگی را دارند: پس از تایید مدیر، ربات
// رویداد پرداخت را بازپخش می‌کند و پرونده مثل پرداخت درگاه PAID/پیش‌پرداخت
// می‌شود. این روت فقط سابقهٔ رسیدها را نگه می‌دارد، پرونده را به پرداخت
// کارتی پیوند می‌دهد (paymentMethod = CARD) و جمع درآمد/سود کارتی را می‌دهد.

const STATUSES = new Set(['PENDING_REVIEW', 'APPROVED', 'REJECTED', 'PAID_VIA_GATEWAY', 'EXPIRED', 'AWAITING_RECEIPT']);
const KINDS = new Set(['PREPAY', 'FINAL', 'DIRECT']);
// سرویس‌هایی که پرونده (Case) در پنل دارند
const CASE_SERVICES = new Set([
  'INQUIRY', 'LAVAYEH', 'EZHHARNAMEH', 'EALAM_VAKALAHT', 'TAJDID_NAZAR', 'CHECK', 'REGIONAL_VALUE',
]);
// پنجرهٔ زمانی پیوند: پرونده‌ای که حداکثر ۳۰ دقیقه قبل تا ۶ ساعت بعد از تایید به‌روز شده
const LINK_BEFORE_MS = 30 * 60 * 1000;
const LINK_AFTER_MS = 6 * 60 * 60 * 1000;

type CardPaymentRow = Awaited<ReturnType<typeof db.cardPayment.findMany>>[number];

/** پیدا کردن و پیوند پروندهٔ مرتبط با یک پرداخت کارتی تاییدشده (بهترین تلاش). */
async function linkCase(cp: CardPaymentRow): Promise<CardPaymentRow> {
  if (cp.status !== 'APPROVED' || cp.caseId || !CASE_SERVICES.has(cp.serviceType)) return cp;
  const at = (cp.approvedAt ?? cp.updatedAt).getTime();
  const where: Record<string, unknown> = {
    baleUserId: cp.baleUserId,
    serviceType: cp.serviceType,
    updatedAt: { gte: new Date(at - LINK_BEFORE_MS), lte: new Date(at + LINK_AFTER_MS) },
  };
  if (cp.trackingCode) where.trackingCode = cp.trackingCode;

  const found = await db.case.findFirst({ where, orderBy: { updatedAt: 'desc' } });
  if (!found) return cp;

  await db.case.update({
    where: { id: found.id },
    data: {
      paymentMethod: 'CARD',
      paymentReceiptUrl: cp.receiptUrl ?? found.paymentReceiptUrl,
      paymentApprovedBy: found.paymentApprovedBy ?? 'ADMIN (کارت به کارت)',
      paymentApprovedAt: found.paymentApprovedAt ?? cp.approvedAt ?? new Date(),
    },
  });
  await db.activityLog.create({
    data: {
      caseId: found.id,
      action: 'CARD_PAYMENT_LINKED',
      details: `پرداخت کارت‌به‌کارت ${cp.externalId} — ${cp.amount.toLocaleString('fa-IR')} تومان`,
    },
  });
  return db.cardPayment.update({ where: { id: cp.id }, data: { caseId: found.id } });
}

export async function GET(request: NextRequest) {
  try {
    const status = new URL(request.url).searchParams.get('status');
    const where = status && STATUSES.has(status) ? { status } : {};

    let records = await db.cardPayment.findMany({ where, orderBy: { createdAt: 'desc' }, take: 300 });
    // پیوند تنبل: پرونده ممکن است چند ثانیه پس از تایید در پنل ثبت شود
    records = await Promise.all(records.map((r) => linkCase(r).catch(() => r)));

    const caseIds = [...new Set(records.map((r) => r.caseId).filter((x): x is string => !!x))];
    const cases = caseIds.length
      ? await db.case.findMany({
          where: { id: { in: caseIds } },
          select: { id: true, serviceType: true, fee: true, prepayAmount: true, systemCost: true, trackingCode: true },
        })
      : [];
    const caseMap = new Map(cases.map((c) => [c.id, c]));

    const summary = {
      pendingCount: 0,
      pendingAmount: 0,
      approvedCount: 0,
      approvedRevenue: 0, // درآمد کارت‌به‌کارت (تومان)
      approvedProfit: 0, // سود کارت‌به‌کارت (تومان)
      rejectedCount: 0,
    };

    const enriched = records.map((r) => {
      const linked = r.caseId ? caseMap.get(r.caseId) ?? null : null;
      const p = computeCardPaymentProfit(r, linked);
      if (r.status === 'PENDING_REVIEW') {
        summary.pendingCount += 1;
        summary.pendingAmount += r.amount;
      } else if (r.status === 'APPROVED') {
        summary.approvedCount += 1;
        summary.approvedRevenue += r.amount;
        summary.approvedProfit += p.profit;
      } else if (r.status === 'REJECTED') {
        summary.rejectedCount += 1;
      }
      return {
        ...r,
        profit: r.status === 'APPROVED' ? Math.round(p.profit) : null,
        systemCost: r.status === 'APPROVED' ? p.systemCost : null,
        profitExact: p.exact,
        caseTrackingCode: linked?.trackingCode ?? null,
      };
    });

    summary.approvedProfit = Math.round(summary.approvedProfit);
    return NextResponse.json({ records: enriched, summary });
  } catch (error) {
    console.error('Card payments list error:', error);
    return NextResponse.json({
      records: [],
      summary: { pendingCount: 0, pendingAmount: 0, approvedCount: 0, approvedRevenue: 0, approvedProfit: 0, rejectedCount: 0 },
    });
  }
}

export async function POST(request: NextRequest) {
  try {
    const b = await request.json();
    const externalId = typeof b.externalId === 'string' ? b.externalId.trim() : '';
    const baleUserId = b.baleUserId != null ? String(b.baleUserId).trim() : '';
    const amount = Math.round(Number(b.amount));
    const status = STATUSES.has(b.status) ? b.status : 'PENDING_REVIEW';

    if (!externalId || !baleUserId) {
      return NextResponse.json({ error: 'externalId و baleUserId الزامی است' }, { status: 400 });
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      return NextResponse.json({ error: 'مبلغ نامعتبر است' }, { status: 400 });
    }

    const data = {
      baleUserId,
      fullName: b.fullName || null,
      serviceType: typeof b.serviceType === 'string' && b.serviceType ? b.serviceType : 'UNKNOWN',
      serviceLabel: b.serviceLabel || null,
      invoiceTitle: b.invoiceTitle || null,
      trackingCode: b.trackingCode || null,
      amount,
      paymentKind: KINDS.has(b.paymentKind) ? b.paymentKind : 'DIRECT',
      status,
      // تصویر رسید را با مقدار خالی بازنویسی نکن
      ...(b.receiptUrl ? { receiptUrl: String(b.receiptUrl) } : {}),
      rejectReason: status === 'REJECTED' ? b.rejectReason || null : null,
      approvedAt: b.approvedAt ? new Date(b.approvedAt) : null,
    };

    const prev = await db.cardPayment.findUnique({ where: { externalId } });
    let record = await db.cardPayment.upsert({
      where: { externalId },
      create: { externalId, ...data },
      update: data,
    });

    if (!prev || prev.status !== status) {
      await db.activityLog.create({
        data: {
          action: `CARD_PAYMENT_${status}`,
          details: `کارت‌به‌کارت ${externalId} — ${data.serviceLabel ?? data.serviceType} — ` +
            `${amount.toLocaleString('fa-IR')} تومان — کاربر ${baleUserId}` +
            (data.rejectReason ? ` — علت رد: ${data.rejectReason}` : ''),
        },
      });
    }

    record = await linkCase(record).catch(() => record);
    return NextResponse.json({ record }, { status: prev ? 200 : 201 });
  } catch (error) {
    console.error('Card payment upsert error:', error);
    return NextResponse.json({ error: 'خطا در ثبت پرداخت کارت‌به‌کارت' }, { status: 500 });
  }
}
