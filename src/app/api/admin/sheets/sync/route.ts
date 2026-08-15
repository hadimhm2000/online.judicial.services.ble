import { NextResponse } from 'next/server';
import { syncAllCases, isGoogleSheetsConfigured } from '@/lib/google-sheets';

export async function POST() {
  try {
    if (!isGoogleSheetsConfigured()) {
      return NextResponse.json(
        { success: false, message: 'گوگل شیت پیکربندی نشده است. متغیرهای محیطی را تنظیم کنید.' },
        { status: 400 }
      );
    }

    const result = await syncAllCases();
    return NextResponse.json(result);
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'خطای ناشناخته';
    return NextResponse.json({ success: false, message: msg }, { status: 500 });
  }
}
