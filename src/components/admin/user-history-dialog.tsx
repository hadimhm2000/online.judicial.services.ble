'use client';

import { useState, useEffect } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  User, CheckCircle2, XCircle, CreditCard, Loader2, Clock, Inbox, FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CaseItem } from './cases-table';

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

const statusBorderColors: Record<string, string> = {
  COMPLETED: 'border-l-emerald-500',
  INCOMPLETE: 'border-l-amber-500',
  PENDING_PAYMENT: 'border-l-rose-500',
  PROCESSING: 'border-l-sky-500',
  READY_TO_SEND: 'border-l-indigo-500',
  FAILED: 'border-l-red-500',
  CANCELLED: 'border-l-gray-400',
};

const serviceTypeLabels: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
};

interface UserHistoryProps {
  baleUserId: string;
  fullName: string;
  open: boolean;
  onClose: () => void;
}

export default function UserHistoryDialog({ baleUserId, fullName, open, onClose }: UserHistoryProps) {
  const [data, setData] = useState<{ summary: Record<string, unknown>; cases: CaseItem[] } | null>(null);
  const [fetchedFor, setFetchedFor] = useState('');

  const loading = open && fetchedFor !== baleUserId && data === null;

  useEffect(() => {
    if (!open || !baleUserId || fetchedFor === baleUserId) return;
    let cancelled = false;
    fetch(`/api/admin/users?baleUserId=${baleUserId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled) { setData(d); setFetchedFor(baleUserId); } })
      .catch(() => { if (!cancelled) { setData(null); setFetchedFor(baleUserId); } });
    return () => { cancelled = true; };
  }, [open, baleUserId, fetchedFor]);

  const initials = fullName
    .split(' ')
    .map((w) => w.charAt(0))
    .slice(0, 2)
    .join('');

  return (
    <Dialog open={open} onOpenChange={onClose} className="dialog-premium">
      <DialogContent className="max-w-lg p-0" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="bg-gradient-to-l from-primary/5 via-primary/10 to-primary/5 dark:from-primary/10 dark:via-primary/15 dark:to-primary/10 -mx-5 -mt-5 mb-4 px-5 py-5 rounded-t-2xl">
            <div className="flex items-center gap-3.5">
              <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center text-white font-bold text-lg shadow-md">
                {initials}
              </div>
              <div className="flex-1">
                <DialogTitle className="text-base font-bold">{fullName}</DialogTitle>
                <div className="flex items-center gap-1.5 mt-1">
                  <div className="h-5 w-5 rounded-md bg-muted/60 flex items-center justify-center">
                    <User className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <p className="text-[11px] text-muted-foreground font-mono" dir="ltr">
                    ID: {baleUserId}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </DialogHeader>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-xs text-muted-foreground">{"در حال بارگذاری..."}</p>
          </div>
        ) : data ? (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-xl p-3 text-center border border-border/50 transition-all duration-200">
                  <div className="h-7 w-7 rounded-lg bg-muted/50 mx-auto mb-1.5 flex items-center justify-center">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                  <p className="text-lg font-bold">{new Intl.NumberFormat('fa-IR').format(data.summary.total as number)}</p>
                  <p className="text-[10px] text-muted-foreground">{"کل پرونده"}</p>
                </div>
                <div className="bg-emerald-50/80 dark:bg-emerald-900/20 rounded-xl p-3 text-center border border-emerald-200/40 dark:border-emerald-800/30 transition-all duration-200">
                  <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-900/40 mx-auto mb-1.5 flex items-center justify-center">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{new Intl.NumberFormat('fa-IR').format(data.summary.completed as number)}</p>
                  <p className="text-[10px] text-muted-foreground">{"موفق"}</p>
                </div>
                <div className="bg-red-50/80 dark:bg-red-900/20 rounded-xl p-3 text-center border border-red-200/40 dark:border-red-800/30 transition-all duration-200">
                  <div className="h-7 w-7 rounded-lg bg-red-100 dark:bg-red-900/40 mx-auto mb-1.5 flex items-center justify-center">
                    <XCircle className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
                  </div>
                  <p className="text-lg font-bold text-red-600 dark:text-red-400">{new Intl.NumberFormat('fa-IR').format(data.summary.failed as number)}</p>
                  <p className="text-[10px] text-muted-foreground">{"شکست خورده"}</p>
                </div>
              </div>

              {data.cases.length > 0 && (
                <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-xl p-3 border border-border/50">
                  <div className="flex items-center gap-2 mb-2">
                    <CreditCard className="h-3.5 w-3.5 text-muted-foreground" />
                    <p className="text-[11px] text-muted-foreground">{"مجموع هزینه پرداخت شده:"}</p>
                    <span className="text-sm font-bold tabular-nums">{new Intl.NumberFormat('fa-IR').format(data.summary.totalSpent as number)} {"تومان"}</span>
                  </div>
                  {(data.summary.serviceTypes as string[]).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {(data.summary.serviceTypes as string[]).map((s: string) => (
                        <Badge key={s} variant="outline" className="text-[11px] shadow-sm">{serviceTypeLabels[s] || s}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {data.cases.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <svg width="100" height="100" viewBox="0 0 100 100" fill="none" className="mb-3 opacity-25">
                    <rect x="15" y="20" width="70" height="60" rx="6" stroke="currentColor" strokeWidth="2" fill="none" />
                    <line x1="28" y1="38" x2="72" y2="38" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <line x1="28" y1="48" x2="62" y2="48" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <line x1="28" y1="58" x2="55" y2="58" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <line x1="28" y1="68" x2="68" y2="68" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <div className="flex items-center gap-2">
                    <Inbox className="h-5 w-5" />
                    <p className="text-sm font-medium">{"پرونده‌ای یافت نشد"}</p>
                  </div>
                </div>
              ) : (
                <ScrollArea className="h-[300px]">
                  <div className="space-y-2">
                    {data.cases.map((c: CaseItem) => (
                      <div
                        key={c.id}
                        className={cn(
                          'rounded-xl p-3 cursor-pointer transition-all duration-200 hover:shadow-sm hover:bg-muted/30 border-l-[3px] bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm',
                          statusBorderColors[c.status] || 'border-l-gray-300'
                        )}
                        onClick={() => { onClose(); }}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <Badge variant="outline" className="text-[10px] shrink-0 shadow-sm">
                                {serviceTypeLabels[c.serviceType] || c.serviceType}
                              </Badge>
                              {c.documentCategory && (
                                <span className="text-[11px] text-muted-foreground truncate">
                                  {c.documentCategory}
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-muted-foreground font-mono">
                              {new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric' }).format(new Date(c.createdAt))}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-1.5 shrink-0">
                            <Badge variant="secondary" className={cn('text-[10px] shadow-sm', statusColors[c.status])}>
                              {statusLabels[c.status] || c.status}
                            </Badge>
                            <span className="text-[10px] text-muted-foreground tabular-nums">
                              {new Intl.NumberFormat('fa-IR').format(c.fee)} {"ت"}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
