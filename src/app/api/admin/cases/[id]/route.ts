import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { appendNewCase } from '@/lib/google-sheets';
import {
  CASE_STATUSES, FEE_STATUSES, statusChangeData, effectiveStatus, statusLabel, feeStatusLabel,
} from '@/lib/admin-case-update';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const caseData = await db.case.findUnique({
      where: { id },
      include: {
        adminActions: {
          orderBy: { createdAt: 'desc' },
        },
        activityLogs: {
          orderBy: { createdAt: 'desc' },
        },
      },
    });

    if (!caseData) {
      return NextResponse.json({ error: 'Case not found' }, { status: 404 });
    }

    return NextResponse.json(caseData);
  } catch (error) {
    console.error('Case detail error:', error);
    return NextResponse.json({ error: 'Failed to fetch case' }, { status: 500 });
  }
}

// ⭐ v2.0 — تغییر دستی مدیر: دسته/وضعیت، امضا، وضعیت پرداخت و مبلغ.
// همهٔ فیلدها اختیاری‌اند؛ هر تغییر در AdminAction و ActivityLog ثبت می‌شود.
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { status, hasSignature, feeStatus, fee, feeDelta, adminNote } = body as {
      status?: string;
      hasSignature?: boolean;
      feeStatus?: string;
      fee?: number;
      feeDelta?: number;
      adminNote?: string;
    };

    if (status !== undefined && !(CASE_STATUSES as readonly string[]).includes(status)) {
      return NextResponse.json({ error: 'Invalid status value' }, { status: 400 });
    }
    if (feeStatus !== undefined && !(FEE_STATUSES as readonly string[]).includes(feeStatus)) {
      return NextResponse.json({ error: 'Invalid feeStatus value' }, { status: 400 });
    }
    if (hasSignature !== undefined && typeof hasSignature !== 'boolean') {
      return NextResponse.json({ error: 'hasSignature must be boolean' }, { status: 400 });
    }
    for (const [k, v] of [['fee', fee], ['feeDelta', feeDelta]] as const) {
      if (v !== undefined && (typeof v !== 'number' || !Number.isFinite(v))) {
        return NextResponse.json({ error: `${k} must be a number` }, { status: 400 });
      }
    }
    if (status === undefined && hasSignature === undefined && feeStatus === undefined
      && fee === undefined && feeDelta === undefined) {
      return NextResponse.json({ error: 'Nothing to update' }, { status: 400 });
    }

    const existing = await db.case.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json({ error: 'Case not found' }, { status: 404 });
    }

    const data: Record<string, unknown> = {};
    const changes: { actionType: string; activity: string; details: string }[] = [];
    const note = typeof adminNote === 'string' && adminNote.trim() ? adminNote.trim() : null;

    if (status !== undefined && status !== effectiveStatus(existing)) {
      Object.assign(data, statusChangeData(existing, status));
      changes.push({
        actionType: 'STATUS_CHANGE',
        activity: status === 'READY_TO_SEND' ? 'MOVE_TO_READY' : 'STATUS_CHANGE',
        details: `انتقال دستی از «${statusLabel(effectiveStatus(existing))}» به «${statusLabel(status)}»`,
      });
    }

    if (hasSignature !== undefined && hasSignature !== existing.hasSignature) {
      data.hasSignature = hasSignature;
      data.signedAt = hasSignature ? new Date() : null;
      changes.push({
        actionType: 'SIGNATURE_CHANGE',
        activity: hasSignature ? 'SIGNED' : 'UNSIGNED',
        details: hasSignature ? 'امضا توسط مدیر «درج شده» علامت خورد' : 'امضا توسط مدیر «درج نشده» علامت خورد',
      });
    }

    if (feeStatus !== undefined && feeStatus !== existing.feeStatus) {
      data.feeStatus = feeStatus;
      if (feeStatus === 'UNPAID') {
        data.paymentApprovedBy = null;
        data.paymentApprovedAt = null;
      } else {
        data.paymentApprovedBy = 'admin';
        data.paymentApprovedAt = new Date();
      }
      changes.push({
        actionType: feeStatus === 'UNPAID' ? 'PAYMENT_REJECTION' : 'PAYMENT_APPROVAL',
        activity: 'FEE_STATUS_CHANGE',
        details: `وضعیت پرداخت از «${feeStatusLabel(existing.feeStatus)}» به «${feeStatusLabel(feeStatus)}»`,
      });
    }

    // fee = مقدار جدید؛ feeDelta = افزودن (+) یا کسر (−) از مبلغ فعلی
    let newFee = existing.fee;
    if (fee !== undefined) newFee = Math.round(fee);
    if (feeDelta !== undefined) newFee += Math.round(feeDelta);
    if (newFee < 0) {
      return NextResponse.json({ error: 'مبلغ نمی‌تواند منفی شود' }, { status: 400 });
    }
    if (newFee !== existing.fee) {
      data.fee = newFee;
      const diff = newFee - existing.fee;
      const fmt = (n: number) => new Intl.NumberFormat('fa-IR').format(n);
      changes.push({
        actionType: 'FEE_ADJUSTMENT',
        activity: 'FEE_ADJUSTMENT',
        details: `مبلغ از ${fmt(existing.fee)} به ${fmt(newFee)} تومان (${diff > 0 ? 'افزودن' : 'کسر'} ${fmt(Math.abs(diff))})`,
      });
    }

    if (changes.length === 0) {
      return NextResponse.json(existing);
    }

    const updated = await db.case.update({ where: { id }, data: data as never });

    for (const ch of changes) {
      await db.adminAction.create({
        data: { caseId: id, actionType: ch.actionType, adminNote: note ? `${ch.details} — ${note}` : ch.details },
      });
      await db.activityLog.create({
        data: { caseId: id, action: ch.activity, details: ch.details },
      });
    }

    appendNewCase(id).catch(() => {});

    return NextResponse.json(updated);
  } catch (error) {
    console.error('Case update error:', error);
    return NextResponse.json({ error: 'Failed to update case' }, { status: 500 });
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    await db.case.delete({ where: { id } });
    return NextResponse.json({ message: 'Case deleted' });
  } catch (error) {
    console.error('Case delete error:', error);
    return NextResponse.json({ error: 'Failed to delete case' }, { status: 500 });
  }
}
