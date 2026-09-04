import { db } from '@/lib/db';
import { sendBaleMessage, sendBaleDocument } from '@/lib/bale';
import { getServiceOption } from '@/lib/service-types';
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';

/**
 * POST /api/admin/bot-messages/{id}/paid
 *
 * این مسیر را «ربات بله» بعد از successful_payment فاکتور هزینهٔ پیام صدا می‌زند:
 *   payload فاکتور: {"type": "panel_message", "mid": "<messageId>"}
 *
 * کارها:
 *  ۱) ثبت پرداخت (costStatus=PAID + paymentId + paidAt)
 *  ۲) ارسال واقعی پیام (متن + فایل پیوست) به کاربر
 *  ۳) آپدیت status=SENT + لاگ فعالیت
 *  ۴) پاسخ شامل serviceType / signMenuPath / trackingCode است تا ربات
 *     در صورت نیاز «روند درج امضا» را برای همان نوع سند آغاز کند.
 *
 * idempotent است: اگر قبلاً PAID/SENT شده باشد، فقط ok + پیام برمی‌گرداند
 * (تا ربات در تلاش مجدد هم به اطلاعات نوع سند دسترسی داشته باشد).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    let paymentId: string | undefined;
    try {
      const body = await request.json();
      paymentId = body?.paymentId || undefined;
    } catch {
      // بدنه خالی/نامعتبر — مهم نیست
    }

    const message = await db.botMessage.findUnique({ where: { id } });
    if (!message) {
      return NextResponse.json({ error: 'پیام یافت نشد' }, { status: 404 });
    }

    // idempotency — پرداخت/ارسال تکراری مشکلی ایجاد نکند
    // ⭐ پیام کامل برگردانده می‌شود تا ربات حتی در تلاش مجدد، بتواند فلوی
    // امضا را با serviceType/signMenuPath/trackingCode درست آغاز کند.
    if (message.costStatus === 'PAID' && message.status === 'SENT') {
      return NextResponse.json({ ok: true, alreadyProcessed: true, message });
    }

    // ── ۱) ثبت پرداخت ──
    await db.botMessage.update({
      where: { id },
      data: {
        costStatus: 'PAID',
        paidAt: new Date(),
        paymentId: paymentId || message.paymentId,
      },
    });

    // ── ۲) ارسال پیام به کاربر ──
    await sendBaleMessage(message.baleUserId, message.messageText);

    if (message.fileUrl && message.fileName) {
      const filePath = path.join(process.cwd(), 'public', message.fileUrl);
      await sendBaleDocument(message.baleUserId, filePath, message.fileName);
    }

    // ── ۳) آپدیت وضعیت + لاگ ──
    const updated = await db.botMessage.update({
      where: { id },
      data: {
        status: 'SENT',
        sentAt: new Date(),
        errorDetails: null,
      },
    });

    await db.activityLog.create({
      data: {
        action: 'BOT_MESSAGE_PAID_AND_SENT',
        details: `هزینه پیام ${message.fullName || message.baleUserId} پرداخت شد (${Math.floor(message.costAmount / 10).toLocaleString('fa-IR')} تومان) و پیام ارسال گردید${
          message.serviceType
            ? ` — نوع سند: ${getServiceOption(message.serviceType)?.label || message.serviceType} (ربات روند درج امضا را آغاز می‌کند)`
            : ''
        }${paymentId ? ` — payment_id: ${paymentId}` : ''}`,
      },
    });

    return NextResponse.json({ ok: true, message: updated });
  } catch (error: unknown) {
    console.error('Bot message paid error:', error);
    const errorMessage =
      error instanceof Error ? error.message : 'خطا در پردازش پرداخت پیام';

    try {
      const { id } = await params;
      await db.botMessage.update({
        where: { id },
        data: {
          status: 'FAILED',
          errorDetails: `پس از پرداخت: ${errorMessage}`,
        },
      });
    } catch {
      // نادیده بگیر
    }

    return NextResponse.json({ error: errorMessage }, { status: 500 });
  }
}
