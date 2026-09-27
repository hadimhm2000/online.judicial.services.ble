// ⭐ v1.7 — پاک‌سازی ورودی‌های ثبت/آپدیت پرونده (POST/PUT /api/admin/cases)
//
// باگ «همیشه بدون امضا»: ربات signedAt را به‌صورت
// datetime.now().isoformat() (بدون offset، مثل 2026-09-27T05:54:00.123456)
// می‌فرستاد. Prisma برای DateTime رشتهٔ RFC-3339 همراه offset می‌خواهد و
// کل آپدیت با خطا رد می‌شد؛ در نتیجه hasSignature هیچ‌وقت true نمی‌شد.
// اینجا همهٔ فیلدهای تاریخ به Date تبدیل می‌شوند و فیلدهای ناشناخته
// (که Prisma با خطا رد می‌کند) حذف می‌شوند.

const CASE_WRITABLE_FIELDS = new Set([
  'baleUserId', 'fullName', 'serviceType', 'status',
  'trackingCode', 'documentCategory', 'subCategory', 'branchCode', 'branchName',
  'province', 'rowNumber', 'archiveNumber', 'persons', 'title', 'textContent',
  'fee', 'feeStatus', 'paymentReceiptUrl', 'paymentApprovedBy', 'paymentApprovedAt',
  'resultSummary', 'resultData', 'resultAttachmentUrls',
  'errorDetails', 'errorStep', 'lastCompletedStep',
  'isInReadyToSend', 'readyToSendAt', 'sentToUserAt', 'sentViaBot',
  'hasSignature', 'signedAt',
  'paymentId', 'systemCost',
  'prepayAmount', 'prepaidAt',
]);

const DATE_FIELDS = new Set([
  'paymentApprovedAt', 'readyToSendAt', 'sentToUserAt', 'signedAt', 'prepaidAt',
]);

const INT_FIELDS = new Set(['fee', 'systemCost', 'prepayAmount']);

function toDate(value: unknown): Date | null | undefined {
  if (value === null) return null;
  if (value === undefined || value === '') return undefined;
  const d = value instanceof Date ? value : new Date(String(value));
  return Number.isNaN(d.getTime()) ? undefined : d;
}

export function sanitizeCaseData(input: Record<string, unknown>): {
  data: Record<string, unknown>;
  dropped: string[];
} {
  const data: Record<string, unknown> = {};
  const dropped: string[] = [];
  for (const [key, value] of Object.entries(input)) {
    if (!CASE_WRITABLE_FIELDS.has(key)) {
      dropped.push(key);
      continue;
    }
    if (DATE_FIELDS.has(key)) {
      const d = toDate(value);
      if (d === undefined) { dropped.push(key); continue; }
      data[key] = d;
      continue;
    }
    if (INT_FIELDS.has(key) && value !== null && value !== undefined) {
      const n = Math.round(Number(value));
      if (Number.isNaN(n)) { dropped.push(key); continue; }
      data[key] = n;
      continue;
    }
    if ((key === 'persons' || key === 'resultData' || key === 'resultAttachmentUrls')
      && value !== null && value !== undefined && typeof value !== 'string') {
      data[key] = JSON.stringify(value);
      continue;
    }
    data[key] = value;
  }
  return { data, dropped };
}
