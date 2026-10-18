'use client';

// ⭐ پرونده‌های در انتظار امضا و پرداخت — همان فهرست بخش «🖊 پرونده‌های در انتظار
// امضا و پرداخت» ربات (pending_cases.py): لایحه و اعلام وکالت ۴ روز، سایر موارد ۳۰ روز.

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PenLine, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export interface PendingSignatureCase {
  id: string;
  baleUserId: string;
  fullName: string;
  serviceType: string;
  status: string;
  trackingCode: string | null;
  title: string | null;
  documentCategory: string | null;
  fee: number;
  feeStatus: string;
  createdAt: string;
  paid: boolean;
  expiresAt: string;
}

interface Summary {
  total: number;
  paidCount: number;
  unpaidCount: number;
  unpaidAmount: number;
}

interface PendingSignaturesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SERVICE_LABEL: Record<string, string> = {
  LAVAYEH: 'لایحه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  EZHHARNAMEH: 'اظهارنامه',
  TAJDID_NAZAR: 'دعاوی اعتراضی',
  CHECK: 'دادخواست',
};

const fa = new Intl.NumberFormat('fa-IR');
const toman = (n: number) => `${fa.format(n)} تومان`;
const faDate = (iso: string) =>
  new Date(iso).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' });

type Filter = 'ALL' | 'UNPAID' | 'PAID';

export default function PendingSignaturesDialog({ open, onOpenChange }: PendingSignaturesDialogProps) {
  const [cases, setCases] = useState<PendingSignatureCase[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<Filter>('ALL');

  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/pending-signatures');
      if (res.ok) {
        const data = await res.json();
        setCases(data.cases || []);
        setSummary(data.summary || null);
      }
    } catch {
      toast.error('خطا در دریافت پرونده‌های در انتظار امضا');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(fetchCases, 0);
    return () => clearTimeout(t);
  }, [open, fetchCases]);

  const visible = useMemo(() => {
    if (filter === 'PAID') return cases.filter((c) => c.paid);
    if (filter === 'UNPAID') return cases.filter((c) => !c.paid);
    return cases;
  }, [cases, filter]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[88vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center animate-float">
              <PenLine className="h-5 w-5 text-violet-600" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-base font-bold">پرونده‌های در انتظار امضا و پرداخت</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                همان فهرستی که کاربر در ربات می‌بیند: لایحه و اعلام وکالت ۴ روز، سایر موارد ۳۰ روز. درج امضا فقط پس از پرداخت فعال است.
              </DialogDescription>
            </div>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={fetchCases} disabled={loading} title="بارگذاری مجدد">
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </Button>
          </div>
        </DialogHeader>

        {summary && (
          <div className="grid grid-cols-3 gap-2">
            <SummaryTile label="کل پرونده‌ها" value={fa.format(summary.total)} tone="slate" />
            <SummaryTile label="پرداخت نشده" value={fa.format(summary.unpaidCount)} sub={toman(summary.unpaidAmount)} tone="amber" />
            <SummaryTile label="پرداخت شده، بدون امضا" value={fa.format(summary.paidCount)} tone="violet" />
          </div>
        )}

        <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
          <TabsList className="grid grid-cols-3 w-full h-9">
            <TabsTrigger value="ALL" className="text-xs">همه</TabsTrigger>
            <TabsTrigger value="UNPAID" className="text-xs">پرداخت نشده</TabsTrigger>
            <TabsTrigger value="PAID" className="text-xs">در انتظار امضا</TabsTrigger>
          </TabsList>
        </Tabs>

        <ScrollArea className="max-h-[48vh] -mx-1 px-1">
          {loading && !cases.length ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : visible.length === 0 ? (
            <div className="text-center py-10">
              <PenLine className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-xs text-muted-foreground">پرونده‌ای در انتظار امضا یا پرداخت نیست</p>
            </div>
          ) : (
            <div className="space-y-2">
              {visible.map((c) => (
                <PendingRow key={c.id} item={c} />
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

function SummaryTile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: 'amber' | 'slate' | 'violet' }) {
  const tones: Record<string, string> = {
    amber: 'border-amber-200 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-900/10',
    slate: 'bg-muted/30',
    violet: 'border-violet-200 dark:border-violet-900/50 bg-violet-50/60 dark:bg-violet-900/10',
  };
  return (
    <div className={cn('rounded-xl border p-2.5 space-y-0.5', tones[tone])}>
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="text-sm font-bold tabular-nums">{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground tabular-nums">{sub}</p>}
    </div>
  );
}

function PendingRow({ item: c }: { item: PendingSignatureCase }) {
  return (
    <div className="flex gap-3 p-2.5 rounded-lg border bg-card hover:bg-muted/30 transition-colors">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium truncate">{SERVICE_LABEL[c.serviceType] ?? c.serviceType}</span>
          <Badge
            variant="secondary"
            className={cn(
              'text-[10px] px-1.5 py-0 h-5 border-0',
              c.paid
                ? 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
            )}
          >
            {c.paid ? 'پرداخت شده، در انتظار امضا' : 'پرداخت نشده'}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground flex-wrap">
          <span>{c.fullName || '—'}</span>
          <span className="font-mono bg-muted px-1.5 py-0.5 rounded" dir="ltr">{c.baleUserId}</span>
          {c.trackingCode && <span className="font-mono" dir="ltr">#{c.trackingCode}</span>}
          <span>ثبت: {faDate(c.createdAt)}</span>
          <span>مهلت: {faDate(c.expiresAt)}</span>
        </div>
        {(c.documentCategory || c.title) && (
          <p className="text-[11px] text-muted-foreground truncate">{c.documentCategory || c.title}</p>
        )}
      </div>
      {!c.paid && c.fee > 0 && (
        <div className="shrink-0 text-left">
          <p className="text-sm font-bold tabular-nums">{toman(c.fee)}</p>
        </div>
      )}
    </div>
  );
}
