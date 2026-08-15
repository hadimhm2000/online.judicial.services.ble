import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    const serviceType = searchParams.get('serviceType');
    const search = searchParams.get('search');
    const feeStatus = searchParams.get('feeStatus');
    const readyToSend = searchParams.get('readyToSend');
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
    if (readyToSend === 'true') where.isInReadyToSend = true;
    if (branchName) where.branchName = { contains: branchName };
    if (province) where.province = province;
    if (errorStep) where.errorStep = errorStep;
    if (hasError === 'true') where.errorDetails = { not: null };

    // Date range filter
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

    const [cases, total] = await Promise.all([
      db.case.findMany({
        where,
        orderBy,
        skip: (page - 1) * limit,
        take: limit,
      }),
      db.case.count({ where }),
    ]);

    return NextResponse.json({
      cases,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
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
      data: {
        ...updateData,
        updatedAt: new Date(),
      },
    });

    // Log the action
    if (updateData.status) {
      await db.activityLog.create({
        data: {
          caseId: id,
          action: 'STATUS_CHANGE',
          details: `تغییر وضعیت به: ${updateData.status}`,
        },
      });
    }

    // Auto-sync to Google Sheets on status/payment change
    if (updateData.status || updateData.feeStatus) {
      import('@/lib/google-sheets').then(m => m.appendNewCase(id)).catch(() => {});
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

    const newCase = await db.case.create({
      data: {
        ...body,
        status: body.status || 'PENDING_PAYMENT',
        feeStatus: body.feeStatus || 'UNPAID',
      },
    });

    // Auto-sync to Google Sheets
    import('@/lib/google-sheets').then(m => m.appendNewCase(newCase.id)).catch(() => {});

    return NextResponse.json(newCase, { status: 201 });
  } catch (error) {
    console.error('Case create error:', error);
    return NextResponse.json({ error: 'Failed to create case' }, { status: 500 });
  }
}
