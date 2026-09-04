'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  User,
  FileText,
  CreditCard,
  MapPin,
  Clock,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Send,
  Hash,
  Building2,
  Copy,
  MessageSquare,
  Trash2,
  Pin,
  PinOff,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CaseItem } from './cases-table';

export interface AdminAction {
  id: string;
  caseId: string;
  actionType: string;
  adminNote: string | null;
  uploadedFileUrls: string | null;
  sentViaBot: boolean;
  createdAt: string;
}

interface CaseNote {
  id: string;
  caseId: string;
  text: string;
  isPinned: boolean;
  createdAt: string;
}

interface CaseDetailDialogProps {
  caseItem: CaseItem | null;
  open: boolean;
  onClose: () => void;
  onManualIntervention?: (c: CaseItem) => void;
  onConfirmSend?: (c: CaseItem) => void;
  onDeleteCase?: (c: CaseItem) => void;
  adminActions?: AdminAction[];
}

const serviceTypeLabels: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  CHECK: 'دادخواست چک',
  TAJDID_NAZAR: 'دعاوی اعتراضی',
  REGIONAL_VALUE: 'ارزش منطقه‌ای',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

const statusLabels: Record<string, string> = {
  COMPLETED: 'تکمیل شده',
  INCOMPLETE: 'ناقص',
  PENDING_PAYMENT: 'پرداخت نشده',
  PROCESSING: 'در حال پردازش',
  READY_TO_SEND: 'آماده ارسال',
  FAILED: 'شکست خورده',
  CANCELLED: 'لغو شده',
};

const statusColors: Record<string, string> = {
  COMPLETED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  INCOMPLETE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  PENDING_PAYMENT: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
  PROCESSING: 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300',
  READY_TO_SEND: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  FAILED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  CANCELLED: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

const statusDotColors: Record<string, string> = {
  COMPLETED: 'bg-emerald-500',
  INCOMPLETE: 'bg-amber-500',
  PENDING_PAYMENT: 'bg-rose-500',
  PROCESSING: 'bg-sky-500',
  READY_TO_SEND: 'bg-indigo-500',
  FAILED: 'bg-red-500',
  CANCELLED: 'bg-gray-500',
};

const statusBorderColors: Record<string, string> = {
  COMPLETED: 'border-l-emerald-500',
  INCOMPLETE: 'border-l-amber-500',
  PENDING_PAYMENT: 'border-l-rose-500',
  PROCESSING: 'border-l-sky-500',
  READY_TO_SEND: 'border-l-indigo-500',
  FAILED: 'border-l-red-500',
  CANCELLED: 'border-l-gray-400',
};

const actionTypeLabels: Record<string, string> = {
  MANUAL_INTERVENTION: 'مداخله دستی',
  PAYMENT_APPROVAL: 'تأیید پرداخت',
  PAYMENT_REJECTION: 'رد پرداخت',
  SEND_TO_USER: 'ارسال به کاربر',
  STATUS_CHANGE: 'تغییر وضعیت',
  MOVE_TO_READY: 'انتقال به آماده ارسال',
  CONFIRM_SEND: 'تأیید ارسال',
};

function formatToman(n: number): string {
  return `${new Intl.NumberFormat('fa-IR').format(n)} تومان`;
}

function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat('fa-IR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateStr));
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'همین الان';
  if (diffMin < 60) return `${new Intl.NumberFormat('fa-IR').format(diffMin)} دقیقه پیش`;
  if (diffHour < 24) return `${new Intl.NumberFormat('fa-IR').format(diffHour)} ساعت پیش`;
  if (diffDay < 7) return `${new Intl.NumberFormat('fa-IR').format(diffDay)} روز پیش`;
  return formatDate(dateStr);
}

export default function CaseDetailDialog({
  caseItem,
  open,
  onClose,
  onManualIntervention,
  onConfirmSend,
  onDeleteCase,
  adminActions = [],
}: CaseDetailDialogProps) {
  const [notes, setNotes] = useState<CaseNote[]>([]);
  const [newNoteText, setNewNoteText] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);

  const fetchNotes = async (caseId: string) => {
    try {
      setNotesLoading(true);
      const res = await fetch(`/api/admin/cases/${caseId}/notes`);
      if (res.ok) {
        const data = await res.json();
        setNotes(data);
      }
    } catch {
      // ignore
    } finally {
      setNotesLoading(false);
    }
  };

  useEffect(() => {
    if (open && caseItem) {
      fetchNotes(caseItem.id);
      setNewNoteText('');
    }
  }, [open, caseItem]);

  const handleAddNote = async () => {
    if (!caseItem || !newNoteText.trim()) return;
    try {
      const res = await fetch(`/api/admin/cases/${caseItem.id}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newNoteText.trim(), isPinned: false }),
      });
      if (res.ok) {
        setNewNoteText('');
        fetchNotes(caseItem.id);
      }
    } catch {
      // ignore
    }
  };

  const handleTogglePin = async (noteId: string, isPinned: boolean) => {
    if (!caseItem) return;
    try {
      await fetch(`/api/admin/cases/${caseItem.id}/notes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ noteId, isPinned: !isPinned }),
      });
      fetchNotes(caseItem.id);
    } catch {
      // ignore
    }
  };

  const handleDeleteNote = async (noteId: string) => {
    if (!caseItem) return;
    try {
      await fetch(`/api/admin/cases/${caseItem.id}/notes?noteId=${noteId}`, {
        method: 'DELETE',
      });
      fetchNotes(caseItem.id);
    } catch {
      // ignore
    }
  };

  const sortedNotes = [...notes].sort((a, b) => {
    if (a.isPinned && !b.isPinned) return -1;
    if (!a.isPinned && b.isPinned) return 1;
    return 0;
  });

  if (!caseItem) return null;

  const persons = caseItem.persons ? JSON.parse(caseItem.persons) : [];

  return (
    <Dialog open={open} onOpenChange={onClose} className="dialog-premium">
      <DialogContent className="max-w-2xl max-h-[90vh] p-0" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center justify-between -mx-5 -mt-5 mb-4 px-5 py-5 bg-gradient-to-l from-primary/5 via-primary/10 to-primary/5 dark:from-primary/10 dark:via-primary/15 dark:to-primary/10">
            <div className="flex items-center gap-3">
              <div className={cn(
                'h-11 w-11 rounded-xl flex items-center justify-center text-white font-bold text-sm shadow-md',
                caseItem.status === 'COMPLETED' ? 'bg-gradient-to-br from-emerald-500 to-emerald-600' :
                caseItem.status === 'FAILED' ? 'bg-gradient-to-br from-red-500 to-rose-600' :
                caseItem.status === 'READY_TO_SEND' ? 'bg-gradient-to-br from-indigo-500 to-violet-600' :
                'bg-gradient-to-br from-gray-500 to-gray-600'
              )}>
                {caseItem.fullName.charAt(0)}
              </div>
              <div>
                <DialogTitle className="text-lg font-bold">{caseItem.fullName}</DialogTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {serviceTypeLabels[caseItem.serviceType] || caseItem.serviceType}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn('h-2.5 w-2.5 rounded-full shrink-0 animate-pulse-dot', statusDotColors[caseItem.status])} />
              <Badge className={cn('text-sm shadow-sm', statusColors[caseItem.status])}>
                {caseItem.isInReadyToSend ? 'آماده ارسال' : statusLabels[caseItem.status]}
              </Badge>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[70vh] px-5 pb-5">
          <div className={cn('space-y-5 mt-2 border-l-4 rounded-r-xl pl-1', statusBorderColors[caseItem.status] || 'border-l-gray-300')}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <InfoCard icon={User} label="نام کاربر" value={caseItem.fullName} />
              <InfoCard icon={Hash} label="شناسه بله" value={caseItem.baleUserId} dir="ltr" />
            </div>

            <div className="divider-gradient" />

            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <div className="h-6 w-6 rounded-lg bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center">
                  <FileText className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" />
                </div>
                {"اطلاعات خدمت"}
              </h4>
              <div className="glass-v2 rounded-xl p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <InfoCard label="نوع خدمت" value={serviceTypeLabels[caseItem.serviceType] || caseItem.serviceType} />
                  <InfoCard label="دسته‌بندی" value={caseItem.documentCategory || '—'} />
                  <InfoCard label="عنوان" value={caseItem.title || '—'} />
                  {caseItem.trackingCode && (
                    <InfoCard label="کد رهگیری" value={caseItem.trackingCode} dir="ltr" />
                  )}
                  {caseItem.rowNumber && (
                    <InfoCard label="شماره ردیف" value={caseItem.rowNumber} />
                  )}
                </div>
              </div>
            </div>

            {caseItem.textContent && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
                      <MessageSquare className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
                    </div>
                    {"متن لایحه / اظهارنامه"}
                  </h4>
                  <div className="glass-v2 rounded-xl p-4 text-sm leading-7 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {caseItem.textContent}
                  </div>
                </div>
              </>
            )}

            {(caseItem.branchName || caseItem.province) && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
                      <MapPin className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
                    </div>
                    {"اطلاعات شعبه"}
                  </h4>
                  <div className="glass-v2 rounded-xl p-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <InfoCard icon={Building2} label="شعبه" value={caseItem.branchName || '—'} />
                      <InfoCard label="استان" value={caseItem.province || '—'} />
                      {caseItem.branchCode && (
                        <InfoCard label="کد شعبه" value={caseItem.branchCode} dir="ltr" />
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {persons.length > 0 && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center">
                      <User className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
                    </div>
                    {"اشخاص"} ({new Intl.NumberFormat('fa-IR').format(persons.length)} {"نفر"})
                  </h4>
                  <div className="space-y-2">
                    {persons.map((p: { type?: string; nationalId?: string }, i: number) => (
                      <div key={i} className="flex items-center gap-3 glass-v2 rounded-xl p-3 transition-all duration-200 hover:shadow-sm">
                        <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
                          {new Intl.NumberFormat('fa-IR').format(i + 1)}
                        </div>
                        <div>
                          <p className="text-sm font-medium">{p.type || 'حقیقی'}</p>
                          <p className="text-xs text-muted-foreground font-mono" dir="ltr">
                            {"کد ملی"}: {p.nationalId}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            <div className="divider-gradient" />

            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <div className="h-6 w-6 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                  <CreditCard className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                </div>
                {"اطلاعات مالی"}
              </h4>
              <div className="glass-v2 rounded-xl p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <InfoCard
                    label="هزینه"
                    value={formatToman(caseItem.fee)}
                    valueClassName={caseItem.feeStatus === 'UNPAID' ? 'text-red-600' : 'text-emerald-600'}
                  />
                  <InfoCard
                    label="وضعیت پرداخت"
                    value={
                      caseItem.feeStatus === 'PAID' ? 'پرداخت شده' :
                      caseItem.feeStatus === 'MANUAL_APPROVED' ? 'تأیید دستی' : 'پرداخت نشده'
                    }
                    valueClassName={
                      caseItem.feeStatus === 'UNPAID' ? 'text-red-600' : 'text-emerald-600'
                    }
                  />
                  {/* ⭐ v1.3 — شناسه پرداخت سامانه + هزینه سامانه + سود این پرونده */}
                  {caseItem.paymentId && (
                    <InfoCard
                      label="شناسه پرداخت سامانه"
                      value={caseItem.paymentId}
                      dir="ltr"
                      valueClassName="text-emerald-600 font-mono"
                    />
                  )}
                  {caseItem.systemCost !== null && caseItem.systemCost !== undefined && (
                    <InfoCard
                      label="هزینه سامانه"
                      value={formatToman(caseItem.systemCost)}
                      valueClassName="text-amber-600"
                    />
                  )}
                  {caseItem.systemCost !== null && caseItem.systemCost !== undefined && (
                    <InfoCard
                      label="سود این پرونده"
                      value={formatToman(Math.max(0, caseItem.fee) - caseItem.systemCost)}
                      valueClassName="text-emerald-600 font-bold"
                    />
                  )}
                </div>
              </div>
            </div>

            {caseItem.resultSummary && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    {"نتیجه"}
                  </h4>
                  <div className="bg-emerald-50/80 dark:bg-emerald-950/30 rounded-xl p-4 text-sm leading-7 border border-emerald-200/60 dark:border-emerald-800/40 backdrop-blur-sm">
                    {caseItem.resultSummary}
                  </div>
                </div>
              </>
            )}

            {caseItem.errorDetails && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-red-600">
                    <div className="h-6 w-6 rounded-lg bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                      <AlertCircle className="h-3.5 w-3.5" />
                    </div>
                    {"جزئیات خطا"}
                  </h4>
                  <div className="bg-red-50/80 dark:bg-red-950/30 rounded-xl p-4 text-sm leading-7 border border-red-200/60 dark:border-red-800/40 text-red-700 dark:text-red-300 backdrop-blur-sm">
                    {caseItem.errorDetails}
                  </div>
                </div>
              </>
            )}

            <div className="divider-gradient" />

            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <div className="h-6 w-6 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <Clock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                </div>
                {"تاریخچه"}
              </h4>
              <div className="relative">
                <div className="absolute right-[14px] top-6 bottom-6 w-px bg-gradient-to-b from-emerald-300 via-sky-300 to-transparent dark:from-emerald-600 dark:via-sky-600" />
                <div className="space-y-1">
                  <TimelineItem label="ثبت درخواست" time={caseItem.createdAt} icon={FileText} dotColor="bg-emerald-500" />
                  {caseItem.readyToSendAt && (
                    <TimelineItem label="آماده ارسال" time={caseItem.readyToSendAt} icon={Send} dotColor="bg-sky-500" />
                  )}
                  {caseItem.sentToUserAt && (
                    <TimelineItem
                      label={caseItem.sentViaBot ? 'ارسال از طریق ربات' : 'ارسال شده'}
                      time={caseItem.sentToUserAt}
                      icon={caseItem.sentViaBot ? CheckCircle2 : Send}
                      color="text-emerald-500"
                      dotColor="bg-emerald-500"
                    />
                  )}
                </div>
              </div>
            </div>

            {adminActions.length > 0 && (
              <>
                <div className="divider-gradient" />
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
                      <Copy className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" />
                    </div>
                    {"اقدامات ادمین"} ({new Intl.NumberFormat('fa-IR').format(adminActions.length)})
                  </h4>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {adminActions.map((action, idx) => (
                      <div
                        key={action.id}
                        className={cn(
                          'rounded-xl p-3 border-r-4 border-r-primary/40 transition-all duration-200 hover:shadow-sm',
                          idx % 2 === 0
                            ? 'bg-white/60 dark:bg-gray-800/40 backdrop-blur-sm'
                            : 'bg-muted/30 dark:bg-muted/20'
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <Badge variant="outline" className="text-[10px] shadow-sm">
                            {actionTypeLabels[action.actionType] || action.actionType}
                          </Badge>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {formatDate(action.createdAt)}
                          </span>
                        </div>
                        {action.adminNote && (
                          <p className="text-xs mt-1.5 text-muted-foreground leading-6">{action.adminNote}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {(caseItem.status === 'FAILED' || caseItem.status === 'INCOMPLETE') && onManualIntervention && (
              <>
                <div className="divider-gradient" />
                <div className="flex gap-2">
                  <Button
                    onClick={() => onManualIntervention(caseItem)}
                    className="flex-1 transition-all duration-200 scale-[1.02] active:scale-[0.98] hover-lift-sm"
                    variant="outline"
                  >
                    <Send className="h-4 w-4 ml-2" />
                    {"مداخله دستی و ارسال به کاربر"}
                  </Button>
                </div>
              </>
            )}

            {caseItem.isInReadyToSend && onConfirmSend && (
              <>
                <div className="divider-gradient" />
                <Button
                  onClick={() => onConfirmSend(caseItem)}
                  className="w-full bg-gradient-to-l from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white transition-all duration-200 scale-[1.02] active:scale-[0.98] shadow-md shadow-emerald-500/20 hover-lift-sm"
                >
                  <CheckCircle2 className="h-4 w-4 ml-2" />
                  {"تأیید نهایی و ارسال به کاربر"}
                </Button>
              </>
            )}

            {onDeleteCase && (
              <>
                <div className="divider-gradient" />
                <Button
                  variant="outline"
                  className="w-full text-red-600 border-red-200 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-950/20 transition-all duration-200 scale-[1.02] active:scale-[0.98] hover-lift-sm"
                  onClick={() => onDeleteCase(caseItem)}
                >
                  <Trash2 className="h-4 w-4 ml-2" />
                  {"حذف پرونده"}
                </Button>
              </>
            )}

            {/* Notes Section */}
            <div className="divider-gradient" />
            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <div className="h-6 w-6 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <MessageSquare className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                </div>
                {"یادداشت‌ها"}
                {notes.length > 0 && (
                  <Badge variant="secondary" className="text-[10px] h-5 px-1.5">{new Intl.NumberFormat('fa-IR').format(notes.length)}</Badge>
                )}
              </h4>

              {notesLoading ? (
                <div className="space-y-2">
                  <div className="h-14 rounded-xl bg-muted/40 animate-pulse" />
                  <div className="h-14 rounded-xl bg-muted/30 animate-pulse" />
                </div>
              ) : sortedNotes.length > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {sortedNotes.map((note) => (
                    <div
                      key={note.id}
                      className={cn(
                        'glass-v2 rounded-xl p-3 transition-all duration-200 group',
                        note.isPinned && 'border-r-[3px] border-r-amber-400'
                      )}
                    >
                      <div className="flex items-start gap-2">
                        {note.isPinned && (
                          <Pin className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                        )}
                        <p className="flex-1 text-sm leading-6">{note.text}</p>
                      </div>
                      <div className="flex items-center justify-between mt-1.5">
                        <span className="text-[10px] text-muted-foreground">{formatRelativeTime(note.createdAt)}</span>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => handleTogglePin(note.id, note.isPinned)}
                            className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/20 transition-colors"
                            title={note.isPinned ? 'بازکنی پین' : 'سنجاق'}
                          >
                            {note.isPinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
                          </button>
                          <button
                            onClick={() => handleDeleteNote(note.id)}
                            className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
                            title={"حذف"}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-xs text-muted-foreground">
                  {"هیچ یادداشتی ثبت نشده"}
                </div>
              )}

              <div className="flex items-center gap-2 mt-3">
                <input
                  type="text"
                  value={newNoteText}
                  onChange={(e) => setNewNoteText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAddNote(); } }}
                  placeholder={"یادداشت جدید..."}
                  className="flex-1 h-9 rounded-lg border border-border bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                />
                <Button
                  size="sm"
                  onClick={handleAddNote}
                  disabled={!newNoteText.trim()}
                  className="h-9 px-3"
                >
                  <Send className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function InfoCard({
  icon: Icon,
  label,
  value,
  dir,
  valueClassName,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  dir?: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-start gap-2 transition-all duration-200">
      {Icon && (
        <div className="h-5 w-5 rounded flex items-center justify-center bg-muted/50 shrink-0 mt-0.5">
          <Icon className="h-3 w-3 text-muted-foreground" />
        </div>
      )}
      <div className="min-w-0">
        <p className="text-[11px] text-muted-foreground">{label}</p>
        <p className={cn('text-sm font-medium truncate', valueClassName)} dir={dir}>
          {value}
        </p>
      </div>
    </div>
  );
}

function TimelineItem({
  label,
  time,
  icon: Icon,
  color = 'text-muted-foreground',
  dotColor = 'bg-muted-foreground',
}: {
  label: string;
  time: string;
  icon: React.ComponentType<{ className?: string }>;
  color?: string;
  dotColor?: string;
}) {
  return (
    <div className="flex items-center gap-3 relative">
      <div className="relative z-10 flex items-center justify-center">
        <span className={cn('h-3 w-3 rounded-full shrink-0', dotColor)} />
        <div className={cn('h-7 w-7 rounded-full bg-background border-2 border-border flex items-center justify-center shrink-0 absolute', dotColor, 'border-opacity-20')}>
          <Icon className={cn('h-3.5 w-3.5', color)} />
        </div>
      </div>
      <div className="flex-1">
        <p className="text-xs font-medium">{label}</p>
        <p className="text-[10px] text-muted-foreground font-mono">{formatDate(time)}</p>
      </div>
    </div>
  );
}
