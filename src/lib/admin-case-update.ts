// ⭐ v2.0 — تغییرات دستی مدیر روی پرونده (دسته/وضعیت، امضا، پرداخت، مبلغ)
//
// باگ «آماده ارسال نمی‌شود»: تب «آماده ارسال» و شمارندهٔ آن بر اساس فلگ
// isInReadyToSend فیلتر می‌شوند، نه status. منوی تغییر وضعیت جدول فقط
// status را READY_TO_SEND می‌کرد و فلگ دست نمی‌خورد؛ پس برچسب عوض می‌شد
// ولی پرونده هرگز وارد بخش «آماده ارسال» نمی‌شد. این تابع فیلدهای وابسته
// را همراه وضعیت هم‌گام می‌کند تا هر دسته واقعاً همان تب را نشان دهد.

export const CASE_STATUSES = [
  'PENDING_PAYMENT',
  'INCOMPLETE',
  'PROCESSING',
  'READY_TO_SEND',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
] as const;

export const FEE_STATUSES = ['UNPAID', 'PAID', 'MANUAL_APPROVED', 'ADMIN_MANUAL'] as const;

const STATUS_LABELS: Record<string, string> = {
  PENDING_PAYMENT: 'پرداخت نشده',
  INCOMPLETE: 'ناقص',
  PROCESSING: 'در حال پردازش',
  READY_TO_SEND: 'آماده ارسال',
  COMPLETED: 'ثبت شده',
  FAILED: 'شکست خورده',
  CANCELLED: 'لغو شده',
};

const FEE_STATUS_LABELS: Record<string, string> = {
  UNPAID: 'پرداخت نشده',
  PAID: 'پرداخت شده',
  MANUAL_APPROVED: 'تأیید دستی',
  ADMIN_MANUAL: 'ثبت توسط مدیر',
};

export const statusLabel = (s: string) => STATUS_LABELS[s] || s;
export const feeStatusLabel = (s: string) => FEE_STATUS_LABELS[s] || s;

interface ExistingCase {
  status: string;
  isInReadyToSend: boolean;
}

/** فیلدهای لازم برای اینکه پرونده واقعاً به دستهٔ newStatus برود. */
export function statusChangeData(existing: ExistingCase, newStatus: string): Record<string, unknown> {
  const data: Record<string, unknown> = { status: newStatus };
  if (newStatus === 'READY_TO_SEND') {
    data.isInReadyToSend = true;
    if (!existing.isInReadyToSend) data.readyToSendAt = new Date();
  } else if (existing.isInReadyToSend) {
    data.isInReadyToSend = false;
    data.readyToSendAt = null;
  }
  if (newStatus === 'COMPLETED' && existing.status === 'FAILED') {
    data.errorDetails = null;
    data.errorStep = null;
  }
  return data;
}

/** دستهٔ نمایشی فعلی پرونده (همان منطقی که جدول برای برچسب استفاده می‌کند). */
export function effectiveStatus(c: ExistingCase): string {
  return c.isInReadyToSend ? 'READY_TO_SEND' : c.status;
}
