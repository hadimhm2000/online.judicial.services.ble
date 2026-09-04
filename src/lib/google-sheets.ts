import { google } from 'googleapis';
import { db } from './db';

// Service Account auth
function getAuth() {
  const email = process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
  const key = process.env.GOOGLE_PRIVATE_KEY?.replace(/\\n/g, '\n');

  if (!email || !key) {
    throw new Error('اطلاعات Service Account تنظیم نشده است');
  }

  const auth = new google.auth.JWT({
    email,
    key,
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
  });
  return auth;
}

function getSheetId(): string {
  const id = process.env.GOOGLE_SHEET_ID;
  if (!id) throw new Error('شناسه گوگل شیت تنظیم نشده است');
  return id;
}

export const SHEET_HEADERS = [
  'ردیف',
  'نام',
  'شناسه بله',
  'نوع خدمت',
  'وضعیت',
  'وضعیت پرداخت',
  'هزینه (تومان)',
  'کد پیگیری',
  'شعبه',
  'استان',
  'شماره پرونده',
  'شماره بایگانی',
  'تاریخ ایجاد',
  'آخرین بروزرسانی',
  'آماده ارسال',
  'ارسال به کاربر',
  'جزئیات خطا',
];

const STATUS_LABELS: Record<string, string> = {
  PENDING_PAYMENT: 'در انتظار پرداخت',
  INCOMPLETE: 'ناقص',
  PROCESSING: 'در حال پردازش',
  READY_TO_SEND: 'آماده ارسال',
  COMPLETED: 'تکمیل شده',
  FAILED: 'شکست خورده',
  CANCELLED: 'لغو شده',
};

const FEE_STATUS_LABELS: Record<string, string> = {
  UNPAID: 'پرداخت نشده',
  PAID: 'پرداخت شده',
  MANUAL_APPROVED: 'تایید دستی',
};

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

export async function testConnection(): Promise<{ success: boolean; message: string; sheetTitle?: string }> {
  try {
    const auth = getAuth();
    const sheets = google.sheets({ version: 'v4', auth });
    const spreadsheetId = getSheetId();

    const response = await sheets.spreadsheets.get({
      spreadsheetId,
      fields: 'properties.title,sheets.properties.title',
    });

    return {
      success: true,
      message: `اتصال موفق — فایل: ${response.data.properties?.title}`,
      sheetTitle: response.data.properties?.title,
    };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'خطای ناشناخته';
    return { success: false, message: msg };
  }
}

export async function initSheet(): Promise<{ success: boolean; message: string }> {
  try {
    const auth = getAuth();
    const sheets = google.sheets({ version: 'v4', auth });
    const spreadsheetId = getSheetId();

    // Check if sheet exists, if not create it
    const existing = await sheets.spreadsheets.get({
      spreadsheetId,
      fields: 'sheets.properties.title,sheets.properties.sheetId',
    });

    const sheetName = 'پرونده‌ها';
    const hasSheet = existing.data.sheets?.some(
      (s) => s.properties?.title === sheetName
    );

    if (!hasSheet) {
      await sheets.spreadsheets.batchUpdate({
        spreadsheetId,
        requestBody: {
          requests: [{
            addSheet: {
              properties: { title: sheetName },
            },
          }],
        },
      });
    }

    // Write headers with formatting
    await sheets.spreadsheets.values.update({
      spreadsheetId,
      range: `${sheetName}!A1:Q1`,
      valueInputOption: 'USER_ENTERED',
      requestBody: {
        values: [SHEET_HEADERS],
      },
    });

    // Format header row
    await sheets.spreadsheets.batchUpdate({
      spreadsheetId,
      requestBody: {
        requests: [
          {
            repeatCell: {
              range: {
                sheetId: 0,
                startRowIndex: 0,
                endRowIndex: 1,
                startColumnIndex: 0,
                endColumnIndex: SHEET_HEADERS.length,
              },
              cell: {
                userEnteredFormat: {
                  backgroundColor: { red: 0.02, green: 0.59, blue: 0.41 },
                  textFormat: {
                    foregroundColor: { red: 1, green: 1, blue: 1 },
                    bold: true,
                    fontSize: 11,
                    fontFamily: 'Vazirmatn',
                  },
                  horizontalAlignment: 'CENTER',
                },
              },
              fields: 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)',
            },
          },
          {
            updateSheetProperties: {
              properties: {
                rightToLeft: true,
              },
              fields: 'rightToLeft',
            },
          },
        ],
      },
    });

    return { success: true, message: 'شیت با موفقیت مقداردهی شد' };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'خطای ناشناخته';
    return { success: false, message: msg };
  }
}

export async function syncAllCases(): Promise<{
  success: boolean;
  message: string;
  syncedCount: number;
}> {
  try {
    const auth = getAuth();
    const sheets = google.sheets({ version: 'v4', auth });
    const spreadsheetId = getSheetId();
    const sheetName = 'پرونده‌ها';

    // Get all cases
    const cases = await db.case.findMany({
      orderBy: { createdAt: 'desc' },
    });

    if (cases.length === 0) {
      return { success: true, message: 'پرونده‌ای برای همگام‌سازی وجود ندارد', syncedCount: 0 };
    }

    // Build rows
    const rows = cases.map((c, i) => [
      i + 1,
      c.fullName,
      c.baleUserId,
      SERVICE_LABELS[c.serviceType] || c.serviceType,
      STATUS_LABELS[c.status] || c.status,
      FEE_STATUS_LABELS[c.feeStatus] || c.feeStatus,
      c.fee.toLocaleString('fa-IR'),
      c.trackingCode || '—',
      c.branchName || '—',
      c.province || '—',
      c.rowNumber || '—',
      c.archiveNumber || '—',
      new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(c.createdAt)),
      new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(c.updatedAt)),
      c.isInReadyToSend ? '✅ بله' : '❌ خیر',
      c.sentViaBot ? '✅ ارسال شد' : '⏳ نشده',
      c.errorDetails || '—',
    ]);

    // Clear existing data (keep header)
    const clearResponse = await sheets.spreadsheets.values.clear({
      spreadsheetId,
      range: `${sheetName}!A2:Q`,
    });

    // Write new data
    const writeResponse = await sheets.spreadsheets.values.update({
      spreadsheetId,
      range: `${sheetName}!A2:Q${cases.length + 1}`,
      valueInputOption: 'USER_ENTERED',
      requestBody: {
        values: rows,
      },
    });

    return {
      success: true,
      message: `${cases.length} پرونده با موفقیت همگام‌سازی شد`,
      syncedCount: cases.length,
    };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'خطای ناشناخته';
    return { success: false, message: `خطا در همگام‌سازی: ${msg}`, syncedCount: 0 };
  }
}

export async function syncSingleCase(caseId: string): Promise<{
  success: boolean;
  message: string;
}> {
  try {
    const auth = getAuth();
    const sheets = google.sheets({ version: 'v4', auth });
    const spreadsheetId = getSheetId();
    const sheetName = 'پرونده‌ها';

    const c = await db.case.findUnique({ where: { id: caseId } });
    if (!c) {
      return { success: false, message: 'پرونده یافت نشد' };
    }

    const rowData = [
      0, // placeholder for row number
      c.fullName,
      c.baleUserId,
      SERVICE_LABELS[c.serviceType] || c.serviceType,
      STATUS_LABELS[c.status] || c.status,
      FEE_STATUS_LABELS[c.feeStatus] || c.feeStatus,
      c.fee.toLocaleString('fa-IR'),
      c.trackingCode || '—',
      c.branchName || '—',
      c.province || '—',
      c.rowNumber || '—',
      c.archiveNumber || '—',
      new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(c.createdAt)),
      new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(c.updatedAt)),
      c.isInReadyToSend ? '✅ بله' : '❌ خیر',
      c.sentViaBot ? '✅ ارسال شد' : '⏳ نشده',
      c.errorDetails || '—',
    ];

    // Check if case already exists in sheet (find by baleUserId + date match in col B and col M)
    const existingData = await sheets.spreadsheets.values.get({
      spreadsheetId,
      range: `${sheetName}!A2:Q`,
    });

    const existingRows = existingData.data.values || [];
    let foundRow = -1;

    for (let i = 0; i < existingRows.length; i++) {
      const row = existingRows[i];
      // Match by baleUserId (col C = index 2)
      if (row[2] === c.baleUserId && row[13] === new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(c.createdAt))) {
        foundRow = i + 2; // +2 because sheet starts at row 2, array is 0-indexed
        break;
      }
    }

    if (foundRow > 0) {
      // Update existing row
      rowData[0] = foundRow - 1; // row number
      await sheets.spreadsheets.values.update({
        spreadsheetId,
        range: `${sheetName}!A${foundRow}:Q${foundRow}`,
        valueInputOption: 'USER_ENTERED',
        requestBody: { values: [rowData] },
      });
      return { success: true, message: `پرونده ${c.fullName} بروزرسانی شد` };
    } else {
      // Append new row
      const nextRow = existingRows.length + 2;
      rowData[0] = existingRows.length + 1;
      await sheets.spreadsheets.values.append({
        spreadsheetId,
        range: `${sheetName}!A:Q`,
        valueInputOption: 'USER_ENTERED',
        insertDataOption: 'INSERT_ROWS',
        requestBody: { values: [rowData] },
      });
      return { success: true, message: `پرونده ${c.fullName} اضافه شد` };
    }
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'خطای ناشناخته';
    return { success: false, message: `خطا: ${msg}` };
  }
}

export async function appendNewCase(caseId: string): Promise<void> {
  try {
    const email = process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
    const key = process.env.GOOGLE_PRIVATE_KEY;
    const sheetId = process.env.GOOGLE_SHEET_ID;

    // Only sync if configured
    if (!email || !key || !sheetId) return;

    await syncSingleCase(caseId);
  } catch {
    // Silent fail - don't block main flow for sheet sync
  }
}

export function isGoogleSheetsConfigured(): boolean {
  return !!(
    process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL &&
    process.env.GOOGLE_PRIVATE_KEY &&
    process.env.GOOGLE_SHEET_ID
  );
}

export function getGoogleSheetsConfigStatus(): {
  email: boolean;
  key: boolean;
  sheetId: boolean;
  allConfigured: boolean;
} {
  const email = !!process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
  const key = !!process.env.GOOGLE_PRIVATE_KEY;
  const sheetId = !!process.env.GOOGLE_SHEET_ID;
  return { email, key, sheetId, allConfigured: email && key && sheetId };
}
