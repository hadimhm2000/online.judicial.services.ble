import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ ریست کامل داده‌ها — فقط پرونده‌ها (Case) و رکوردهای وابسته به آن‌ها
// (ActivityLog, AdminAction, CaseNote) پاک می‌شوند. WorkingHour, BotMessage
// و ExemptUser دست‌نخورده باقی می‌مانند (طبق تصمیم صریح مالک پروژه).
//
// عملیات غیرقابل‌بازگشت است — برای جلوگیری از فراخوانی تصادفی، باید در
// بدنه‌ی درخواست دقیقاً { "confirm": "RESET" } ارسال شود.
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const { confirm } = body as { confirm?: string };

    if (confirm !== 'RESET') {
      return NextResponse.json(
        { error: 'برای تایید عملیات، مقدار confirm باید دقیقاً "RESET" باشد.' },
        { status: 400 }
      );
    }

    const [deletedActivityLogs, deletedAdminActions, deletedCaseNotes, deletedCases] =
      await db.$transaction([
        // ActivityLog با onDelete: SetNull به Case متصل است — با حذف Case
        // خودکار پاک نمی‌شود، پس باید صریحاً حذف شود.
        db.activityLog.deleteMany(),
        // AdminAction و CaseNote با onDelete: Cascade تعریف شده‌اند و با حذف
        // Case خودکار پاک می‌شوند؛ اینجا هم صریح حذف می‌شوند تا ترتیب و
        // شمارش دقیق در پاسخ مشخص باشد.
        db.adminAction.deleteMany(),
        db.caseNote.deleteMany(),
        db.case.deleteMany(),
      ]);

    return NextResponse.json({
      message: 'تمام پرونده‌ها و سوابق مرتبط با موفقیت پاک شدند.',
      deleted: {
        cases: deletedCases.count,
        activityLogs: deletedActivityLogs.count,
        adminActions: deletedAdminActions.count,
        caseNotes: deletedCaseNotes.count,
      },
    });
  } catch (error) {
    console.error('Reset data error:', error);
    return NextResponse.json({ error: 'خطا در ریست داده‌ها' }, { status: 500 });
  }
}
