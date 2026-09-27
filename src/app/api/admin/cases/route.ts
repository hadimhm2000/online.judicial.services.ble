import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { appendNewCase } from '@/lib/google-sheets';
import { sanitizeCaseData } from '@/lib/case-fields';
import { normalizeSearchText, searchTokens, matchesAllTokens, flattenJsonForSearch } from '@/lib/search-normalize';
import { buildKnownNameMap, applyKnownNames } from '@/lib/user-names';

// ⭐ v1.7 — فیلدهایی که جستجو روی آن‌ها انجام می‌شود
const SEARCH_SELECT = {
  id: true, baleUserId: true, fullName: true, trackingCode: true,
  branchName: true, branchCode: true, title: true, province: true,
  documentCategory: true, subCategory: true, paymentId: true,
  archiveNumber: true, rowNumber: true, persons: true,
} as const;

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

    const orderBy: Record<string, string> = {};
    orderBy[sortBy] = sortOrder;

    // ─── ⭐ v1.7: جستجوی نرمال‌شده (ارقام فارسی/لاتین، ی/ي، ک/ك، نیم‌فاصله) ───
    // جستجو دیگر با LIKE خام SQLite انجام نمی‌شود؛ کاندیداها (با سایر فیلترها)
    // خوانده و در حافظه با متن نرمال‌شده تطبیق داده می‌شوند. نام واقعی کاربر
    // (از پرونده‌های دیگرش) و اشخاص پرونده (کد ملی/نام) هم جستجو می‌شوند.
    const tokens = search ? searchTokens(search) : [];
    if (tokens.length > 0) {
      const [candidates, nameMap] = await Promise.all([
        db.case.findMany({ where, orderBy, select: SEARCH_SELECT }),
        buildKnownNameMap(),
      ]);
      const matchedIds: string[] = [];
      for (const c of candidates) {
        const hay = normalizeSearchText([
          c.fullName, nameMap.get(c.baleUserId), c.baleUserId, c.trackingCode,
          c.branchName, c.branchCode, c.title, c.province, c.documentCategory,
          c.subCategory, c.paymentId, c.archiveNumber, c.rowNumber, flattenJsonForSearch(c.persons), c.id,
        ].filter(Boolean).join(' | '));
        if (matchesAllTokens(hay, tokens)) matchedIds.push(c.id);
      }
      const pageIds = matchedIds.slice((page - 1) * limit, page * limit);
      const pageRows = pageIds.length
        ? await db.case.findMany({ where: { id: { in: pageIds } } })
        : [];
      const byId = new Map(pageRows.map((r) => [r.id, r]));
      const ordered = pageIds.map((id) => byId.get(id)).filter((r): r is NonNullable<typeof r> => !!r);
      return NextResponse.json({
        cases: applyKnownNames(ordered, nameMap),
        pagination: { page, limit, total: matchedIds.length, totalPages: Math.ceil(matchedIds.length / limit) },
      });
    }

    const shouldDedup = !status && serviceType !== 'INQUIRY';

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
    let pagination = { page, limit, total, totalPages: Math.ceil(total / limit) };
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
      pagination = { page, limit, total: dedupTotal, totalPages: Math.ceil(dedupTotal / limit) };
    }

    const nameMap = await buildKnownNameMap([...new Set(cases.map((c) => c.baleUserId))]);
    return NextResponse.json({ cases: applyKnownNames(cases, nameMap), pagination });
  } catch (error) {
    console.error('Cases list error:', error);
    return NextResponse.json({ error: 'Failed to fetch cases' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...rawUpdate } = body;

    if (!id) {
      return NextResponse.json({ error: 'Case ID is required' }, { status: 400 });
    }

    // ⭐ v1.7 — تبدیل تاریخ‌ها (مثل signedAt بدون offset) و حذف فیلدهای ناشناخته
    const { data: updateData, dropped } = sanitizeCaseData(rawUpdate);
    if (dropped.length) console.warn(`[cases PUT] فیلدهای نامعتبر نادیده گرفته شد: ${dropped.join(', ')}`);

    const updatedCase = await db.case.update({
      where: { id },
      data: { ...updateData, updatedAt: new Date() },
    });

    if (updateData.hasSignature === true) {
      await db.activityLog.create({
        data: { caseId: id, action: 'SIGNED', details: 'امضای الکترونیک با موفقیت درج شد' },
      }).catch(() => {});
    }

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
    const dupWhere: Record<string, unknown> = {
      baleUserId: body.baleUserId,
      serviceType: body.serviceType,
    };
    if (body.trackingCode) {
      dupWhere.trackingCode = body.trackingCode;
    }
    if (body.documentCategory) {
      dupWhere.documentCategory = body.documentCategory;
    }

    const existingCase = await db.case.findFirst({
      where: dupWhere,
      orderBy: { createdAt: 'desc' },
    });

    if (existingCase) {
      return NextResponse.json({
        ...existingCase,
        _duplicate: true,
        _message: 'رکورد تکراری - مورد مشابه قبلا ثبت شده',
      }, { status: 200 });
    }

    const { data: createData } = sanitizeCaseData(body);
    const newCase = await db.case.create({
      data: {
        ...(createData as { baleUserId: string; fullName: string; serviceType: string }),
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
