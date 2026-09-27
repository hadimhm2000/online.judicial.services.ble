import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ v1.7 — تسویه / لغو / ویرایش یک ردیف دفتر بازگشت/کسر
//   PATCH { status?: 'OPEN'|'SETTLED'|'CANCELLED', settleNote?, reason?, amount? }
//   DELETE → حذف کامل ردیف

const STATUSES = new Set(['OPEN', 'SETTLED', 'CANCELLED']);

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const existing = await db.userCredit.findUnique({ where: { id } });
    if (!existing) return NextResponse.json({ error: 'ردیف یافت نشد' }, { status: 404 });

    const data: Record<string, unknown> = {};
    if (typeof body.status === 'string' && STATUSES.has(body.status)) {
      data.status = body.status;
      data.settledAt = body.status === 'OPEN' ? null : new Date();
    }
    if (typeof body.settleNote === 'string') data.settleNote = body.settleNote.trim() || null;
    if (typeof body.reason === 'string' && body.reason.trim()) data.reason = body.reason.trim();
    if (body.amount !== undefined) {
      const n = Math.round(Number(body.amount));
      if (!Number.isFinite(n) || n <= 0) {
        return NextResponse.json({ error: 'مبلغ نامعتبر است' }, { status: 400 });
      }
      data.amount = n;
    }

    const record = await db.userCredit.update({ where: { id }, data });

    if (data.status && data.status !== existing.status) {
      await db.activityLog.create({
        data: {
          caseId: record.caseId,
          action: 'CREDIT_STATUS_CHANGE',
          details: `مبلغ ${record.amount.toLocaleString('fa-IR')} تومان کاربر ${record.baleUserId}: ${existing.status} → ${record.status}${record.settleNote ? ` (${record.settleNote})` : ''}`,
        },
      }).catch(() => {});
    }

    return NextResponse.json({ record });
  } catch (error) {
    console.error('Credit update error:', error);
    return NextResponse.json({ error: 'خطا در به‌روزرسانی' }, { status: 500 });
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    await db.userCredit.delete({ where: { id } });
    return NextResponse.json({ message: 'حذف شد' });
  } catch (error) {
    console.error('Credit delete error:', error);
    return NextResponse.json({ error: 'خطا در حذف' }, { status: 500 });
  }
}
