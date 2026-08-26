import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { appendNewCase } from '@/lib/google-sheets';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    const serviceType = searchParams.get('serviceType');
    const search = searchParams.get('search');
    const feeStatus = searchParams.get('feeStatus');
    const readyToSend = searchParams.get('readyToSend');
    const excludeInquiry = searchParams.get('excludeInquiry');
    const page = parseInt(searchParams.get('page') || '1');
    const limit = parseInt(searchParams.get('limit') || '20');
    const sortBy = searchParams.get('sortBy') || 'createdAt';
    const sortOrder = searchParams.get('sortOrder') || 'desc';

    const dateFrom = searchParams.get('dateFrom');
    const dateTo = searchParams.get('dateTo');
    const branchName = searchParams.get('branchName');
    const province = searchParams.get('province');
    const errorStep = searchParams.get('errorStep');
    const hasError = searchParams.get('hasError');

    const where: Record<string, unknown> = {};

    if (status) where.status = status;
    if (serviceType) where.serviceType = serviceType;
    if (feeStatus) where.feeStatus = feeStatus;
    if (readyToSend === 'true') {
      where.isInReadyToSend = true;
      where.serviceType = { not: 'INQUIRY' };
    }
    if (excludeInquiry === 'true' && !serviceType) {
      where.serviceType = { not: 'INQUIRY' };
    }
    if (branchName) where.branchName = { contains: branchName };
    if (province) where.province = province;
    if (errorStep) where.errorStep = errorStep;
    if (hasError === 'true') where.errorDetails = { not: null };

    if (dateFrom || dateTo) {
      where.createdAt = {} as Record<string, unknown>;
      if (dateFrom) (where.createdAt as Record<string, unknown>).gte = new Date(dateFrom);
      if (dateTo) (where.createdAt as Record<string, unknown>).lte = new Date(dateTo + 'T23:59:59.999Z');
    }

    if (search) {
      where.OR = [
        { fullName: { contains: search } },
        { trackingCode: { contains: search } },
        { baleUserId: { contains: search } },
        { branchName: { contains: search } },
        { title: { contains: search } },
        { province: { contains: search } },
      ];
    }

    const orderBy: Record<string, string> = {};
    orderBy[sortBy] = sortOrder;

    const shouldDedup = !search && !status && serviceType !== 'INQUIRY';

    const [rawCases, total] = await Promise.all([
      db.case.findMany({
        where,
        orderBy,
        skip: shouldDedup ? 0 : (page - 1) * limit,
        take: shouldDedup ? 10000 : limit,
      }),
      db.case.count({ where }),
    ]);

    let cases = rawCases;
    if (shouldDedup) {
      const seen = new Map<string, typeof rawCases[0]>();
      for (const c of rawCases) {
        if (!c.trackingCode) { seen.set(c.id, c); continue; }
        const existing = seen.get(c.trackingCode);
        if (!existing || new Date(c.createdAt) > new Date(existing.createdAt)) {
          if (existing) seen.delete(existing.id);
          seen.set(c.trackingCode, c);
        }
      }
      cases = Array.from(seen.values());
      const dedupTotal = cases.length;
      cases = cases.slice((page - 1) * limit, page * limit);
      return NextResponse.json({
        cases,
        pagination: { page, limit, total: dedupTotal, totalPages: Math.ceil(dedupTotal / limit) },
      });
    }

    return NextResponse.json({
      cases,
      pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
    });
  } catch (error) {
    console.error('Cases list error:', error);
    return NextResponse.json({ error: 'Failed to fetch cases' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...updateData } = body;

    if (!id) {
      return NextResponse.json({ error: 'Case ID is required' }, { status: 400 });
    }

    const updatedCase = await db.case.update({
      where: { id },
      data: { ...updateData, updatedAt: new Date() },
    });

    if (updateData.status) {
      await db.activityLog.create({
        data: { caseId: id, action: 'STATUS_CHANGE', details: `تغییر وضعیت به: ${updateData.status}` },
      });
    }

    if (updateData.status || updateData.feeStatus) {
      appendNewCase(id).catch(() => {});
    }

    return NextResponse.json(updatedCase);
  } catch (error) {
    console.error('Case update error:', error);
    return NextResponse.json({ error: 'Failed to update case' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // ── Duplicate Prevention ──
    // قبلاً اگر trackingCode/documentCategory در بدنه نبود، تشخیص تکراری فقط
    // با baleUserId+serviceType انجام می‌شد؛ یعنی هر درخواست دومِ همون کاربر
    // از همون نوع سرویس (که هنوز trackingCode نداره، مثلا لحظه‌ی شروعِ فلو
    // قبل از پرداخت) به‌اشتباه «تکراری» شناسایی و به‌جای رکورد جدید،
    // رکورد قدیمی برگردانده می‌شد و هیچ Case جدیدی ساخته نمی‌شد.
    // اصلاح: وقتی trackingCode مشخصه، تکراری فقط با تطابق دقیق trackingCode
    // بررسی می‌شه. وقتی trackingCode نداریم (شروع فلو)، فقط جلوی
    // دابل-کلیک/ری‌ترای رو با یه پنجره‌ی زمانی کوتاه (۲ دقیقه) می‌گیریم،
    // نه اینکه همه‌ی درخواست‌های بعدی کاربر رو یکی حساب کنیم.
    let existingCase = null as Awaited<ReturnType<typeof db.case.findFirst>>;

    if (body.trackingCode) {
      const dupWhere: Record<string, unknown> = {
        baleUserId: body.baleUserId,
        serviceType: body.serviceType,
        trackingCode: body.trackingCode,
      };
      if (body.documentCategory) dupWhere.documentCategory = body.documentCategory;
      existingCase = await db.case.findFirst({ where: dupWhere, orderBy: { createdAt: 'desc' } });
    } else {
      const twoMinutesAgo = new Date(Date.now() - 2 * 60 * 1000);
      const dupWhere: Record<string, unknown> = {
        baleUserId: body.baleUserId,
        serviceType: body.serviceType,
        trackingCode: null,
        createdAt: { gte: twoMinutesAgo },
      };
      if (body.documentCategory) dupWhere.documentCategory = body.documentCategory;
      existingCase = await db.case.findFirst({ where: dupWhere, orderBy: { createdAt: 'desc' } });
    }

    if (existingCase) {
      return NextResponse.json({
        ...existingCase,
        _duplicate: true,
        _message: 'رکورد تکراری - مورد مشابه قبلا ثبت شده',
      }, { status: 200 });
    }

    const newCase = await db.case.create({
      data: {
        ...body,
        status: body.status || 'PENDING_PAYMENT',
        feeStatus: body.feeStatus || 'UNPAID',
      },
    });

    appendNewCase(newCase.id).catch(() => {});

    return NextResponse.json(newCase, { status: 201 });
  } catch (error) {
    console.error('Case create error:', error);
    return NextResponse.json({ error: 'Failed to create case' }, { status: 500 });
  }
}
