import { db } from '@/lib/db';
import { getServiceOption } from '@/lib/service-types';
import { NextRequest, NextResponse } from 'next/server';
import { Prisma } from '@prisma/client';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1');
    const limit = parseInt(searchParams.get('limit') || '20');
    const status = searchParams.get('status') || '';
    const search = searchParams.get('search') || '';

    const where: Prisma.BotMessageWhereInput = {};
    if (status) where.status = status;
    if (search) {
      where.OR = [
        { fullName: { contains: search } },
        { baleUserId: { contains: search } },
        { messageText: { contains: search } },
      ];
    }

    const [messages, total] = await Promise.all([
      db.botMessage.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * limit,
        take: limit,
      }),
      db.botMessage.count({ where }),
    ]);

    return NextResponse.json({
      messages,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Bot messages list error:', error);
    return NextResponse.json({ error: 'خطا در دریافت پیام‌ها' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { baleUserId, fullName, messageText, fileUrl, fileName, costToman, serviceType, trackingCode } = body;

    if (!baleUserId || !messageText) {
      return NextResponse.json(
        { error: 'شناسه بله و متن پیام الزامی است' },
        { status: 400 }
      );
    }

    // ⭐ هزینهٔ پیام — ورودی UI به «تومان» است؛ ذخیره به «ریال» (فیلد
    // costAmount جداول BotMessage برای ارسال فاکتور IRR؛ فیلد جدا از
    // Case.fee که از v1.4 به بعد به «تومان» است)
    let costAmountRial = 0;
    if (costToman !== undefined && costToman !== null && costToman !== '') {
      const toman = parseInt(String(costToman), 10);
      if (Number.isFinite(toman)) {
        if (toman < 0) {
          return NextResponse.json(
            { error: 'مبلغ هزینه نمی‌تواند منفی باشد' },
            { status: 400 }
          );
        }
        if (toman > 0) {
          costAmountRial = toman * 10;
        }
      }
    }

    // ⭐ نوع سند — فقط وقتی «هزینه» دارد معنا دارد (امضا پس از پرداخت آغاز می‌شود)
    let serviceTypeClean: string | null = null;
    let signMenuPathJson: string | null = null;
    if (costAmountRial > 0 && serviceType && String(serviceType).trim() !== '' && String(serviceType) !== 'NONE') {
      const opt = getServiceOption(String(serviceType).trim());
      if (!opt) {
        return NextResponse.json(
          { error: 'نوع سند انتخاب‌شده معتبر نیست' },
          { status: 400 }
        );
      }
      serviceTypeClean = opt.value;
      if (opt.hasSignFlow && opt.signMenuPath) {
        signMenuPathJson = JSON.stringify(opt.signMenuPath);
      }
    }

    const message = await db.botMessage.create({
      data: {
        baleUserId,
        fullName: fullName || '',
        messageText,
        fileUrl: fileUrl || null,
        fileName: fileName || null,
        status: 'PENDING',
        costAmount: costAmountRial,
        costStatus: costAmountRial > 0 ? 'AWAITING_PAYMENT' : 'NONE',
        serviceType: serviceTypeClean,
        signMenuPath: signMenuPathJson,
        trackingCode:
          typeof trackingCode === 'string' && trackingCode.trim() !== ''
            ? trackingCode.trim()
            : null,
      },
    });

    await db.activityLog.create({
      data: {
        action: 'BOT_MESSAGE_CREATED',
        details:
          costAmountRial > 0
            ? `پیام جدید برای ${fullName || baleUserId} - با هزینه ${costAmountRial / 10} تومان${serviceTypeClean ? ` (${getServiceOption(serviceTypeClean)?.label || serviceTypeClean} - امضای خودکار پس از پرداخت)` : ' - بدون امضا'} - در انتظار ارسال`
            : `پیام جدید برای ${fullName || baleUserId} - در انتظار ارسال`,
      },
    });

    return NextResponse.json(message, { status: 201 });
  } catch (error) {
    console.error('Bot message create error:', error);
    return NextResponse.json({ error: 'خطا در ایجاد پیام' }, { status: 500 });
  }
}
