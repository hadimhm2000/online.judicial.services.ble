import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

type BatchAction = 'APPROVE_PAYMENTS' | 'CHANGE_STATUS' | 'MOVE_TO_READY' | 'CONFIRM_SEND_ALL';

interface BatchRequestBody {
  ids: string[];
  action: BatchAction;
  newStatus?: string;
  adminNote?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: BatchRequestBody = await request.json();
    const { ids, action, newStatus, adminNote } = body;

    if (!Array.isArray(ids) || ids.length === 0) {
      return NextResponse.json(
        { error: 'ids must be a non-empty array of case IDs' },
        { status: 400 }
      );
    }

    if (!['APPROVE_PAYMENTS', 'CHANGE_STATUS', 'MOVE_TO_READY', 'CONFIRM_SEND_ALL'].includes(action)) {
      return NextResponse.json(
        { error: 'action must be one of: APPROVE_PAYMENTS, CHANGE_STATUS, MOVE_TO_READY, CONFIRM_SEND_ALL' },
        { status: 400 }
      );
    }

    if (action === 'CHANGE_STATUS' && !newStatus) {
      return NextResponse.json(
        { error: 'newStatus is required for CHANGE_STATUS action' },
        { status: 400 }
      );
    }

    // Fetch all cases that exist
    const cases = await db.case.findMany({
      where: { id: { in: ids } },
    });

    if (cases.length === 0) {
      return NextResponse.json(
        { error: 'No valid cases found for the provided IDs' },
        { status: 404 }
      );
    }

    let count = 0;

    for (const c of cases) {
      try {
        let updateData: Record<string, unknown> = {};
        let adminActionType: string = action;
        let activityAction: string = action;
        let activityDetails: string = '';

        switch (action) {
          case 'APPROVE_PAYMENTS':
            updateData = {
              feeStatus: 'PAID',
              paymentApprovedBy: 'admin',
              paymentApprovedAt: new Date(),
            };
            adminActionType = 'PAYMENT_APPROVAL';
            activityAction = 'BATCH_APPROVE_PAYMENT';
            activityDetails = adminNote || `تأیید دسته‌ای پرداخت - ${c.fullName}`;
            break;

          case 'CHANGE_STATUS':
            updateData = { status: newStatus! };
            // Clear error fields when resolving a failed case
            if (newStatus === 'COMPLETED' && c.status === 'FAILED') {
              updateData.errorDetails = null;
              updateData.errorStep = null;
            }
            adminActionType = 'STATUS_CHANGE';
            activityAction = 'BATCH_STATUS_CHANGE';
            activityDetails = adminNote || `تغییر دسته‌ای وضعیت از ${c.status} به ${newStatus} - ${c.fullName}`;
            break;

          case 'MOVE_TO_READY':
            updateData = {
              isInReadyToSend: true,
              readyToSendAt: new Date(),
              status: 'READY_TO_SEND',
            };
            adminActionType = 'MANUAL_INTERVENTION';
            activityAction = 'BATCH_MOVE_TO_READY';
            activityDetails = adminNote || `انتقال دسته‌ای به بخش آماده ارسال - ${c.fullName}`;
            break;

          case 'CONFIRM_SEND_ALL':
            updateData = {
              isInReadyToSend: false,
              sentToUserAt: new Date(),
              sentViaBot: true,
              status: 'COMPLETED',
              readyToSendAt: null,
            };
            adminActionType = 'SEND_TO_USER';
            activityAction = 'BATCH_CONFIRM_SEND';
            activityDetails = adminNote || `تأیید دسته‌ای ارسال به کاربر - ${c.fullName}`;
            break;
        }

        await db.case.update({
          where: { id: c.id },
          data: updateData as never,
        });

        await db.adminAction.create({
          data: {
            caseId: c.id,
            actionType: adminActionType,
            adminNote: adminNote || `عملیات دسته‌ای: ${action}`,
            sentViaBot: action === 'CONFIRM_SEND_ALL',
          },
        });

        await db.activityLog.create({
          data: {
            caseId: c.id,
            action: activityAction,
            details: activityDetails,
          },
        });

        count++;

        // Auto-sync to Google Sheets
        import('@/lib/google-sheets').then(m => m.appendNewCase(c.id)).catch(() => {});
      } catch (caseError) {
        console.error(`Batch operation failed for case ${c.id}:`, caseError);
        // Continue with remaining cases even if one fails
      }
    }

    const actionMessages: Record<string, string> = {
      APPROVE_PAYMENTS: `تأیید پرداخت برای ${count} پرونده انجام شد`,
      CHANGE_STATUS: `تغییر وضعیت ${count} پرونده انجام شد`,
      MOVE_TO_READY: `${count} پرونده به بخش آماده ارسال منتقل شدند`,
      CONFIRM_SEND_ALL: `${count} پرونده تأیید و ارسال شدند`,
    };

    return NextResponse.json({
      success: true,
      count,
      message: actionMessages[action],
    });
  } catch (error) {
    console.error('Batch operation error:', error);
    return NextResponse.json(
      { error: 'Failed to perform batch operation' },
      { status: 500 }
    );
  }
}
