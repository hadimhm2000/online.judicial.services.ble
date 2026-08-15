import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

// Seed test data for development
export async function POST() {
  try {
    // Check if we already have data
    const existingCount = await db.case.count();
    if (existingCount > 0) {
      return NextResponse.json({ message: 'Data already exists', count: existingCount });
    }

    const serviceTypes = ['INQUIRY', 'LAVAYEH', 'EZHHARNAMEH', 'EALAM_VAKALAHT'];
    const statuses = ['COMPLETED', 'INCOMPLETE', 'PENDING_PAYMENT', 'FAILED', 'CANCELLED'];
    const feeStatuses = ['PAID', 'UNPAID', 'MANUAL_APPROVED'];
    const documentCategories = [
      'لایحه دفاعیه', 'اظهارنامه', 'شکواییه', 'دادخواست بدوی',
      'تجدیدنظرخواهی', 'واخواهی', 'اعاده دادرسی', 'اعتراض ثالث'
    ];
    const provinces = [
      'تهران', 'اصفهان', 'فارس', 'خراسان رضوی', 'آذربایجان شرقی',
      'مازندران', 'گیلان', 'کرمان', 'همدان', 'خوزستان'
    ];
    const names = [
      'علی محمدی', 'فاطمه احمدی', 'محمد حسینی', 'زهرا رضایی',
      'حسین کریمی', 'مریم موسوی', 'رضا جعفری', 'سارا نوری',
      'امیر صادقی', 'نازنین قاسمی', 'مهدی عباسی', 'الهام طاهری',
      'پویا شفیعی', 'شیما رحمانی', 'دانیال بهرامی'
    ];

    const cases = [];

    // Create 50 test cases with realistic distribution
    for (let i = 0; i < 50; i++) {
      const serviceType = serviceTypes[Math.floor(Math.random() * serviceTypes.length)];
      let status: string;
      const rand = Math.random();

      if (rand < 0.3) status = 'COMPLETED';
      else if (rand < 0.5) status = 'INCOMPLETE';
      else if (rand < 0.65) status = 'PENDING_PAYMENT';
      else if (rand < 0.8) status = 'FAILED';
      else status = 'CANCELLED';

      const feeStatus = status === 'COMPLETED' ? 'PAID'
        : status === 'PENDING_PAYMENT' ? 'UNPAID'
        : feeStatuses[Math.floor(Math.random() * feeStatuses.length)];

      const fee = serviceType === 'INQUIRY'
        ? [50000, 55000, 65000][Math.floor(Math.random() * 3)]
        : Math.floor(Math.random() * 500000) + 100000;

      const trackingCode = String(Math.floor(Math.random() * 9000000000000000) + 1000000000000000);
      const baleUserId = String(Math.floor(Math.random() * 900000000) + 100000000);
      const fullName = names[Math.floor(Math.random() * names.length)];
      const category = documentCategories[Math.floor(Math.random() * documentCategories.length)];
      const province = provinces[Math.floor(Math.random() * provinces.length)];

      // Generate random date in the last 30 days
      const daysAgo = Math.floor(Math.random() * 30);
      const createdAt = new Date(Date.now() - daysAgo * 86400000);

      // Error details for failed cases
      const errorSteps = ['SESSION_EXPIRED', 'UPLOAD_FAILED', 'SUBMIT_FAILED', 'SIGN_CODE_TIMEOUT', 'PAYMENT_VERIFICATION_FAILED', 'NETWORK_ERROR'];
      const errorDetails = status === 'FAILED'
        ? `خطا در مرحله: ${errorSteps[Math.floor(Math.random() * errorSteps.length)]} - جزئیات خطا در سامانه ثنا`
        : null;

      // Last completed step for incomplete cases
      const completedSteps = ['PERSON_INFO', 'TEXT_CONTENT', 'ATTACHMENTS', 'PREVIEW', 'PAYMENT', 'SIGNATURE'];
      const lastCompletedStep = status === 'INCOMPLETE'
        ? completedSteps[Math.floor(Math.random() * (completedSteps.length - 1))]
        : null;

      const caseData: Record<string, unknown> = {
        baleUserId,
        fullName,
        serviceType,
        status,
        trackingCode: serviceType !== 'INQUIRY' || Math.random() > 0.3 ? trackingCode : null,
        documentCategory: category,
        subCategory: Math.random() > 0.5 ? 'زیر دسته ' + Math.floor(Math.random() * 5 + 1) : null,
        branchCode: String(Math.floor(Math.random() * 9000) + 1000),
        branchName: `شعبه ${Math.floor(Math.random() * 50) + 1} ${province}`,
        province,
        rowNumber: Math.random() > 0.5 ? String(Math.floor(Math.random() * 100) + 1) : null,
        persons: JSON.stringify([
          {
            type: ['حقیقی', 'حقوقی', 'وکیل'][Math.floor(Math.random() * 3)],
            nationalId: String(Math.floor(Math.random() * 9000000000) + 1000000000),
          }
        ]),
        title: `${category} - ${trackingCode.slice(-6)}`,
        textContent: `محتوای ${category.toLowerCase()} مربوط به پرونده شماره ${trackingCode.slice(-8)}`,
        fee,
        feeStatus,
        errorDetails,
        errorStep: status === 'FAILED' ? 'BROWSER_AUTOMATION' : null,
        lastCompletedStep,
        createdAt,
        updatedAt: new Date(createdAt.getTime() + Math.random() * 86400000),
      };

      // Mark some completed cases as ready to send
      if (status === 'COMPLETED' && Math.random() > 0.5) {
        caseData.isInReadyToSend = true;
        caseData.readyToSendAt = new Date(createdAt.getTime() + 86400000);
      }

      // Result for completed cases
      if (status === 'COMPLETED') {
        caseData.resultSummary = `نتیجه ${category}: پرونده با کد رهگیری ${trackingCode} با موفقیت ثبت شد. وضعیت: در دست بررسی`;
        caseData.sentToUserAt = Math.random() > 0.3 ? new Date(createdAt.getTime() + 172800000) : null;
        caseData.sentViaBot = Math.random() > 0.5;
      }

      cases.push(caseData);
    }

    // Insert all cases
    for (const c of cases) {
      await db.case.create({ data: c as never });
    }

    return NextResponse.json({
      message: 'Seed data created successfully',
      count: cases.length,
    });
  } catch (error) {
    console.error('Seed error:', error);
    return NextResponse.json({ error: 'Failed to seed data' }, { status: 500 });
  }
}
