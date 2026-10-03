import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

// ⭐ فهرست شناسهٔ همهٔ کاربرانی که تاکنون با ربات کار کرده‌اند
//   GET → { users: string[], count }
// ربات (guide_handlers.py) برای ارسال همگانی PDF راهنما از این فهرست استفاده
// می‌کند؛ از همهٔ جدول‌هایی که شناسهٔ بله دارند، شناسه‌های یکتا جمع می‌شود.
export async function GET() {
  try {
    const groups = await Promise.all([
      db.case.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.botMessage.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.funnelEvent.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.feedback.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.userCredit.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.cardPayment.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
      db.exemptUser.findMany({ select: { baleUserId: true }, distinct: ['baleUserId'] }),
    ]);
    const ids = new Set<string>();
    for (const rows of groups) {
      for (const r of rows) {
        if (r.baleUserId && /^\d+$/.test(r.baleUserId)) ids.add(r.baleUserId);
      }
    }
    const users = [...ids];
    return NextResponse.json({ users, count: users.length });
  } catch (error) {
    console.error('[bot-users] GET error:', error);
    return NextResponse.json({ error: 'خطا در دریافت فهرست کاربران' }, { status: 500 });
  }
}
