'use client';

// ⭐ v1.8 — پرداخت‌های کارت‌به‌کارت
// رسیدهایی که کاربران پس از ۲۰ دقیقه عدم پرداخت فاکتور بله ارسال کرده‌اند.
// تایید/رد در خود ربات (پیام مدیر) انجام می‌شود؛ این پنل سابقه، تصویر رسید،
// درآمد و سود هر پرداخت و پروندهٔ پیوندشده را نشان می‌دهد.

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CreditCard, Loader2, RefreshCw, ImageIcon, Link2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export interface CardPaymentRecord {
  id: string;
  externalId: string;
  baleUserId: string;
  fullName: string | null;
  serviceType: string;
  serviceLabel: string | null;
  invoiceTitle: string | null;
  trackingCode: string | null;
  amount: number;
  paymentKind: string;
  status: string;
  receiptUrl: string | null;
  rejectReason: string | null;
  caseId: string | null;
  caseTrackingCode: string | null;
  approvedAt: string | null;
  createdAt: string;
  profit: number | null;
  systemCost: number | null;
  profitExact: boolean;
}

interface Summary {
  pendingCount: number;
  pendingAmount: number;
  approvedCount: number;
  approvedRevenue: number;
  approvedProfit: number;
  rejectedCount: number;
}

interface CardPaymentsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const STATUS_META: Record<string, { label: string; className: string }> = {
  PENDING_REVIEW: { label: 'در انتظار بررسی', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
  APPROVED: { label: 'تایید شده', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
  REJECTED: { label: 'رد شده', className: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300' },
  PAID_VIA_GATEWAY: { label: 'پرداخت از درگاه', className: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300' },
  EXPIRED: { label: 'منقضی', className: 'bg-muted text-muted-foreground' },
  AWAITING_RECEIPT: { label: 'منتظر رسید', className: 'bg-muted text-muted-foreground' },
};

const KIND_LABEL: Record<string, string> = {
  PREPAY: 'پیش‌پرداخت',
  FINAL: 'مابقی / هزینه نهایی',
  DIRECT: 'پرداخت مستقیم',
};

const fa = new Intl.NumberFormat('fa-IR');
const toman = (n: number) => `${fa.format(n)} تومان`;
const faDate = (iso: string) =>
  new Date(iso).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' });

type Filter = 'ALL' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED';

export default function CardPaymentsDialog({ open, onOpenChange }: CardPaymentsDialogProps) {
  const [records, setRecords] = useState<CardPaymentRecord[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<Filter>('ALL');

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/card-payments');
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
        setSummary(data.summary || null);
      }
    } catch {
      toast.error('خطا در دریافت پرداخت‌های کارت‌به‌کارت');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchRecords();
  }, [open, fetchRecords]);

  const visible = useMemo(
    () => (filter === 'ALL' ? records : records.filter((r) => r.status === filter)),
    [records, filter],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[88vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center animate-float">
              <CreditCard className="h-5 w-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-base font-bold">پرداخت‌های کارت به کارت</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                تایید یا رد رسید از داخل ربات انجام می‌شود؛ پس از تایید، پرونده مثل پرداخت درگاه ثبت و در درآمد و سود لحاظ می‌شود.
              </DialogDescription>
            </div>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={fetchRecords} disabled={loading} title="بارگذاری مجدد">
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </Button>
          </div>
        </DialogHeader>

        {summary && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <SummaryTile label="در انتظار بررسی" value={fa.format(summary.pendingCount)} sub={toman(summary.pendingAmount)} tone="amber" />
            <SummaryTile label="تایید شده" value={fa.format(summary.approvedCount)} sub={`${fa.format(summary.rejectedCount)} رد شده`} tone="slate" />
            <SummaryTile label="درآمد کارت به کارت" value={toman(summary.approvedRevenue)} tone="indigo" />
            <SummaryTile label="سود کارت به کارت" value={toman(summary.approvedProfit)} tone="emerald" />
          </div>
        )}

        <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
          <TabsList className="grid grid-cols-4 w-full h-9">
            <TabsTrigger value="ALL" className="text-xs">همه</TabsTrigger>
            <TabsTrigger value="PENDING_REVIEW" className="text-xs">در انتظار</TabsTrigger>
            <TabsTrigger value="APPROVED" className="text-xs">تایید شده</TabsTrigger>
            <TabsTrigger value="REJECTED" className="text-xs">رد شده</TabsTrigger>
          </TabsList>
        </Tabs>

        <ScrollArea className="max-h-[48vh] -mx-1 px-1">
          {loading && !records.length ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : visible.length === 0 ? (
            <div className="text-center py-10">
              <CreditCard className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-xs text-muted-foreground">پرداخت کارت به کارتی ثبت نشده است</p>
            </div>
          ) : (
            <div className="space-y-2">
              {visible.map((r) => (
                <CardPaymentRow key={r.id} record={r} />
              ))}
            </div>
          )}
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>بستن</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryTile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: 'amber' | 'slate' | 'indigo' | 'emerald' }) {
  const tones: Record<string, string> = {
    amber: 'border-amber-200 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-900/10',
    slate: 'bg-muted/30',
    indigo: 'border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-900/10',
    emerald: 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-900/10',
  };
  return (
    <div className={cn('rounded-xl border p-2.5 space-y-0.5', tones[tone])}>
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="text-sm font-bold tabular-nums">{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground tabular-nums">{sub}</p>}
    </div>
  );
}

function CardPaymentRow({ record: r }: { record: CardPaymentRecord }) {
  const meta = STATUS_META[r.status] ?? { label: r.status, className: 'bg-muted text-muted-foreground' };
  const tracking = r.trackingCode || r.caseTrackingCode;
  return (
    <div className="flex gap-3 p-2.5 rounded-lg border bg-card hover:bg-muted/30 transition-colors">
      {r.receiptUrl ? (
        <a
          href={r.receiptUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 h-16 w-16 rounded-md overflow-hidden border bg-muted"
          title="مشاهدهٔ رسید"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={r.receiptUrl} alt="رسید پرداخت" className="h-full w-full object-cover" />
        </a>
      ) : (
        <div className="shrink-0 h-16 w-16 rounded-md border bg-muted/50 flex items-center justify-center" title="تصویر رسید در پنل ذخیره نشده">
          <ImageIcon className="h-5 w-5 text-muted-foreground/40" />
        </div>
      )}

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium truncate">{r.serviceLabel || r.serviceType}</span>
          <Badge variant="secondary" className={cn('text-[10px] px-1.5 py-0 h-5 border-0', meta.className)}>{meta.label}</Badge>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5">{KIND_LABEL[r.paymentKind] ?? r.paymentKind}</Badge>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground flex-wrap">
          <span>{r.fullName || '—'}</span>
          <span className="font-mono bg-muted px-1.5 py-0.5 rounded" dir="ltr">{r.baleUserId}</span>
          {tracking && <span className="font-mono" dir="ltr">#{tracking}</span>}
          <span>{faDate(r.createdAt)}</span>
          {r.caseId && (
            <span className="inline-flex items-center gap-0.5 text-indigo-600 dark:text-indigo-400">
              <Link2 className="h-3 w-3" /> پرونده پیوند شد
            </span>
          )}
        </div>
        {r.invoiceTitle && <p className="text-[11px] text-muted-foreground truncate">{r.invoiceTitle}</p>}
        {r.rejectReason && r.status === 'REJECTED' && (
          <p className="text-[11px] text-rose-600 dark:text-rose-400">علت رد: {r.rejectReason}</p>
        )}
      </div>

      <div className="shrink-0 text-left space-y-0.5">
        <p className="text-sm font-bold tabular-nums">{toman(r.amount)}</p>
        {r.profit !== null && (
          <p
            className={cn('text-[11px] tabular-nums', r.profit >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600')}
            title={r.systemCost ? `هزینهٔ سامانه: ${toman(r.systemCost)}${r.profitExact ? '' : ' (برآورد)'}` : undefined}
          >
            سود: {toman(r.profit)}{!r.profitExact && ' *'}
          </p>
        )}
      </div>
    </div>
  );
}
