import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

/**
 * GET /api/admin/bot-messages/sign-requests
 *
 * ⭐ v2.0 — درخواست‌های «فعال‌سازی روند امضا بدون فاکتور» که پیامشان برای
 * کاربر ارسال شده و ربات هنوز روند امضا را آغاز نکرده است. ربات
 * (admin_relay.free_sign_request_loop) این فهرست را دوره‌ای می‌خواند و هر مورد
 * را با POST /api/admin/bot-messages/{id}/sign-started تصاحب می‌کند.
 * موارد قدیمی‌تر از ۲۴ ساعت نادیده گرفته می‌شوند تا پس از قطعی طولانی
 * ربات، روند امضای کهنه ناگهان برای کاربر شروع نشود.
 */
export async function GET() {
  try {
    const since = new Date(Date.now() - 24 * 3600 * 1000);
    const requests = await db.botMessage.findMany({
      where: { costStatus: 'FREE_SIGN_PENDING', status: 'SENT', sentAt: { gte: since } },
      orderBy: { sentAt: 'asc' },
      take: 20,
      select: {
        id: true, baleUserId: true, fullName: true,
        serviceType: true, signMenuPath: true, trackingCode: true,
      },
    });
    return NextResponse.json({ requests });
  } catch (error) {
    console.error('Sign requests error:', error);
    return NextResponse.json({ error: 'خطا در دریافت درخواست‌های امضا' }, { status: 500 });
  }
}
