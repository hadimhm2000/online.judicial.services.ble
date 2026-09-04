import { db } from '@/lib/db';
import { sendBaleMessage, sendBaleDocument, sendBaleInvoice } from '@/lib/bale';
import { getServiceOption } from '@/lib/service-types';
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';

/**
 * ارسال پیام مدیر به کاربر — با پشتیبانی هزینه (فاکتور کیف پول بله).
 *
 * منطق:
 *  ۱) اگر پیام «هزینه» دارد و هنوز پرداخت نشده:
 *     → به‌جای ارسال پیام، «فاکتور هزینه» برای کاربر ارسال می‌شود.
 *     → costStatus = AWAITING_PAYMENT و پیام PENDING می‌ماند.
 *     → پس از پرداخت، ربات POST /admin/bot-messages/{id}/paid را صدا می‌زند
 *       و همان‌جا متن/فایل پیام واقعاً برای کاربر ارسال می‌شود.
 *  ۲) اگر هزینه ندارد (costAmount=0) یا قبلاً پرداخت شده (PAID):
 *     → ارسال مستقیم متن (+ فایل) — مثل قبل.
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const message = await db.botMessage.findUnique({ where: { id } });
    if (!message) {
      return NextResponse.json({ error: 'پیام یافت نشد' }, { status: 404 });
    }

    if (!message.baleUserId) {
      return NextResponse.json(
        { error: 'شناسه بله برای این پیام ثبت نشده است' },
        { status: 400 }
      );
    }

    // ── حالت ۱: هزینه دارد و هنوز پرداخت نشده → ارسال فاکتور ──
    if (message.costAmount > 0 && message.costStatus !== 'PAID') {
      const toman = Math.floor(message.costAmount / 10);
      const amountRial = message.costAmount;
      const svcLabel = getServiceOption(message.serviceType)?.label;

      await sendBaleInvoice(
        message.baleUserId,
        svcLabel ? `هزینه ${svcLabel}` : 'هزینه پیام خدمات قضایی',
        `این فاکتور هزینهٔ ${svcLabel ? svcLabel : 'پیام/مدارکی'} است که پس از پرداخت برای شما ارسال می‌شود.${svcLabel && getServiceOption(message.serviceType)?.hasSignFlow ? '\nپس از پرداخت، مرحلهٔ درج امضای الکترونیک نیز آغاز خواهد شد.' : ''}\nمبلغ: ${toman.toLocaleString('fa-IR')} تومان (${amountRial.toLocaleString('fa-IR')} ریال)`,
        { type: 'panel_message', mid: message.id },
        amountRial
      );

      const updated = await db.botMessage.update({
        where: { id },
        data: {
          costStatus: 'AWAITING_PAYMENT',
          status: 'PENDING',
        },
      });

      await db.activityLog.create({
        data: {
          action: 'BOT_MESSAGE_INVOICE_SENT',
          details: `فاکتور هزینه ${toman.toLocaleString('fa-IR')} تومانی برای ${message.fullName || message.baleUserId} ارسال شد — پیام پس از پرداخت ارسال می‌شود`,
        },
      });

      // پاسخ متمایز تا UI پیام درست نشان دهد
      return NextResponse.json({
        ...updated,
        awaitingPayment: true,
        costAmount: message.costAmount,
      });
    }

    // ── حالت ۲: بدون هزینه یا هزینهٔ پرداخت‌شده → ارسال مستقیم ──
    // ارسال پیام متنی
    await sendBaleMessage(message.baleUserId, message.messageText);

    // ارسال فایل پیوست اگر وجود داشته باشد
    if (message.fileUrl && message.fileName) {
      const filePath = path.join(process.cwd(), 'public', message.fileUrl);
      await sendBaleDocument(
        message.baleUserId,
        filePath,
        message.fileName
      );
    }

    const updated = await db.botMessage.update({
      where: { id },
      data: {
        status: 'SENT',
        sentAt: new Date(),
      },
    });

    await db.activityLog.create({
      data: {
        action: 'BOT_MESSAGE_SENT',
        details: message.fileUrl
          ? `پیام و فایل «${message.fileName}» ارسال شد برای ${message.fullName || message.baleUserId}`
          : `پیام ارسال شد برای ${message.fullName || message.baleUserId}`,
      },
    });

    return NextResponse.json(updated);
  } catch (error: unknown) {
    console.error('Bot message send error:', error);

    const errorMessage =
      error instanceof Error ? error.message : 'خطا در ارسال پیام';

    try {
      const { id } = await params;
      await db.botMessage.update({
        where: { id },
        data: {
          status: 'FAILED',
          errorDetails: errorMessage,
        },
      });
    } catch {
      // نادیده بگیر
    }

    return NextResponse.json({ error: errorMessage }, { status: 500 });
  }
}
