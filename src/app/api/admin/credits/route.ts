import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { normalizeSearchText, searchTokens, matchesAllTokens } from '@/lib/search-normalize';
import { buildKnownNameMap } from '@/lib/user-names';

// ⭐ v1.7 — دفتر «مبالغ قابل بازگشت / قابل کسر» کاربران
//   GET  ?status=OPEN|SETTLED|CANCELLED&kind=REFUND|DEDUCT_LATER&baleUserId=&search=
//   POST { baleUserId, amount (تومان), reason, kind?, fullName?, caseId?, trackingCode?, source? }

const KINDS = new Set(['REFUND', 'DEDUCT_LATER']);
const STATUSES = new Set(['OPEN', 'SETTLED', 'CANCELLED']);

function toToman(value: unknown): number {
  const n = Math.round(Number(normalizeSearchText(value).replace(/[,\s]/g, '')));
  return Number.isFinite(n) ? n : NaN;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    const kind = searchParams.get('kind');
    const baleUserId = searchParams.get('baleUserId');
    const search = searchParams.get('search');

    const where: Record<string, unknown> = {};
    if (status && STATUSES.has(status)) where.status = status;
    if (kind && KINDS.has(kind)) where.kind = kind;
    if (baleUserId) where.baleUserId = normalizeSearchText(baleUserId);

    let records = await db.userCredit.findMany({ where, orderBy: { createdAt: 'desc' } });

    const nameMap = await buildKnownNameMap([...new Set(records.map((r) => r.baleUserId))]);
    records = records.map((r) => (r.fullName ? r : { ...r, fullName: nameMap.get(r.baleUserId) ?? null }));

    const tokens = search ? searchTokens(search) : [];
    if (tokens.length) {
      records = records.filter((r) =>
        matchesAllTokens(
          normalizeSearchText([r.baleUserId, r.fullName, r.reason, r.trackingCode, r.settleNote, r.amount].join(' | ')),
          tokens,
        ),
      );
    }

    const summary = { openRefund: 0, openDeduct: 0, openCount: 0 };
    for (const r of records) {
      if (r.status !== 'OPEN') continue;
      summary.openCount += 1;
      if (r.kind === 'REFUND') summary.openRefund += r.amount;
      else summary.openDeduct += r.amount;
    }

    return NextResponse.json({ records, summary });
  } catch (error) {
    console.error('Credits list error:', error);
    return NextResponse.json({ records: [], summary: { openRefund: 0, openDeduct: 0, openCount: 0 } });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const baleUserId = normalizeSearchText(body.baleUserId);
    const amount = toToman(body.amount);
    const reason = typeof body.reason === 'string' ? body.reason.trim() : '';
    const kind = KINDS.has(body.kind) ? body.kind : 'REFUND';

    if (!baleUserId) return NextResponse.json({ error: 'شناسه بله الزامی است' }, { status: 400 });
    if (!Number.isFinite(amount) || amount <= 0) {
      return NextResponse.json({ error: 'مبلغ باید عددی بزرگ‌تر از صفر باشد' }, { status: 400 });
    }
    if (!reason) return NextResponse.json({ error: 'دلیل ثبت مبلغ الزامی است' }, { status: 400 });

    const record = await db.userCredit.create({
      data: {
        baleUserId,
        amount,
        reason,
        kind,
        fullName: typeof body.fullName === 'string' && body.fullName.trim() ? body.fullName.trim() : null,
        caseId: typeof body.caseId === 'string' && body.caseId ? body.caseId : null,
        trackingCode: body.trackingCode ? normalizeSearchText(body.trackingCode) : null,
        source: body.source === 'BOT' ? 'BOT' : 'ADMIN',
      },
    });

    await db.activityLog.create({
      data: {
        caseId: record.caseId,
        action: kind === 'REFUND' ? 'CREDIT_REFUND_ADDED' : 'CREDIT_DEDUCT_ADDED',
        details: `${kind === 'REFUND' ? 'بازگشت به کاربر' : 'کسر در موارد بعدی'}: ${amount.toLocaleString('fa-IR')} تومان — کاربر ${baleUserId} — ${reason}`,
      },
    }).catch(() => {});

    return NextResponse.json({ record }, { status: 201 });
  } catch (error) {
    console.error('Credit create error:', error);
    return NextResponse.json({ error: 'خطا در ثبت مبلغ' }, { status: 500 });
  }
}
