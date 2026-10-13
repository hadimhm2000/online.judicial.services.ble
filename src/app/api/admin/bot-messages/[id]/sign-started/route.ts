import { db } from '@/lib/db';
import { getServiceOption } from '@/lib/service-types';
import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/admin/bot-messages/{id}/sign-started
 *
 * ⭐ v2.0 — ربات قبل از آغاز «روند امضا بدون فاکتور» این مسیر را صدا می‌زند.
 * تغییر وضعیت اتمیک است (FREE_SIGN_PENDING → FREE_SIGN_STARTED)؛ فقط اولین
 * فراخوانی claimed=true می‌گیرد تا روند امضا دوبار برای کاربر شروع نشود.
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { count } = await db.botMessage.updateMany({
      where: { id, costStatus: 'FREE_SIGN_PENDING' },
      data: { costStatus: 'FREE_SIGN_STARTED' },
    });
    if (count === 1) {
      const msg = await db.botMessage.findUnique({ where: { id } });
      await db.activityLog.create({
        data: {
          action: 'FREE_SIGN_STARTED',
          details: `روند امضای ${getServiceOption(msg?.serviceType)?.label || msg?.serviceType || ''} بدون فاکتور برای ${msg?.fullName || msg?.baleUserId} توسط ربات آغاز شد`,
        },
      });
    }
    return NextResponse.json({ claimed: count === 1 });
  } catch (error) {
    console.error('Sign started error:', error);
    return NextResponse.json({ error: 'خطا در ثبت شروع روند امضا' }, { status: 500 });
  }
}
