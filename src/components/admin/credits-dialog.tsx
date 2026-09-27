'use client';

// ⭐ v1.7 — دفتر «مبالغ قابل بازگشت / قابل کسر» کاربران
// مبالغی از پیش‌پرداخت (یا هر پرداخت دیگر) که باید به کاربر بازگردد یا در
// موارد بعدی کاربر کسر شود، با شناسهٔ بله و دلیل ثبت و پیگیری می‌شوند.

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Wallet, Plus, Loader2, CheckCircle2, XCircle, RotateCcw, Trash2, Search, Undo2, MinusCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export interface UserCreditRecord {
  id: string;
  baleUserId: string;
  fullName: string | null;
  amount: number;
  kind: 'REFUND' | 'DEDUCT_LATER' | string;
  reason: string;
  status: 'OPEN' | 'SETTLED' | 'CANCELLED' | string;
  caseId: string | null;
  trackingCode: string | null;
  source: string;
  settledAt: string | null;
  settleNote: string | null;
  createdAt: string;
}

interface CreditsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** پیش‌پر کردن فرم از روی یک پرونده (اختیاری) */
  prefill?: { baleUserId?: string; fullName?: string; caseId?: string; trackingCode?: string | null } | null;
  onChanged?: () => void;
}

const KIND_LABEL: Record<string, string> = {
  REFUND: 'بازگشت به کاربر',
  DEDUCT_LATER: 'کسر در موارد بعدی',
};

const STATUS_LABEL: Record<string, string> = {
  OPEN: 'باز',
  SETTLED: 'تسویه‌شده',
  CANCELLED: 'لغو‌شده',
};

const fmt = (n: number) => new Intl.NumberFormat('fa-IR').format(n);
const fmtDate = (s: string) => new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: '2-digit', day: '2-digit' });

export default function CreditsDialog({ open, onOpenChange, prefill, onChanged }: CreditsDialogProps) {
  const [records, setRecords] = useState<UserCreditRecord[]>([]);
  const [summary, setSummary] = useState({ openRefund: 0, openDeduct: 0, openCount: 0 });
  const [loading, setLoading] = useState(false);
  const [statusTab, setStatusTab] = useState<'OPEN' | 'SETTLED' | 'ALL'>('OPEN');
  const [search, setSearch] = useState('');

  const [baleUserId, setBaleUserId] = useState('');
  const [fullName, setFullName] = useState('');
  const [amount, setAmount] = useState('');
  const [kind, setKind] = useState<'REFUND' | 'DEDUCT_LATER'>('REFUND');
  const [reason, setReason] = useState('');
  const [trackingCode, setTrackingCode] = useState('');
  const [caseId, setCaseId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [settlingId, setSettlingId] = useState<string | null>(null);
  const [settleNote, setSettleNote] = useState('');

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusTab !== 'ALL') params.set('status', statusTab);
      const res = await fetch(`/api/admin/credits?${params}`);
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
        if (statusTab === 'OPEN') setSummary(data.summary);
      }
    } catch {
      toast.error('خطا در دریافت دفتر مبالغ');
    } finally {
      setLoading(false);
    }
  }, [statusTab]);

  useEffect(() => {
    if (open) fetchRecords();
  }, [open, fetchRecords]);

  useEffect(() => {
    if (open && prefill) {
      setBaleUserId(prefill.baleUserId ?? '');
      setFullName(prefill.fullName && !/^\d+$/.test(prefill.fullName) ? prefill.fullName : '');
      setTrackingCode(prefill.trackingCode ?? '');
      setCaseId(prefill.caseId ?? null);
      if (prefill.baleUserId) setSearch(prefill.baleUserId);
    }
  }, [open, prefill]);

  // جستجوی سمت کاربر (شناسه، نام، دلیل، کد رهگیری) — ارقام فارسی هم پذیرفته می‌شود
  const filtered = useMemo(() => {
    const q = search.trim().replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)));
    if (!q) return records;
    return records.filter((r) =>
      [r.baleUserId, r.fullName, r.reason, r.trackingCode, r.settleNote]
        .filter(Boolean)
        .some((v) => String(v).includes(q)),
    );
  }, [records, search]);

  const resetForm = () => {
    setBaleUserId(''); setFullName(''); setAmount(''); setReason('');
    setTrackingCode(''); setCaseId(null); setKind('REFUND');
  };

  const handleAdd = useCallback(async () => {
    if (!baleUserId.trim() || !amount.trim() || !reason.trim()) {
      toast.error('شناسه بله، مبلغ و دلیل الزامی است');
      return;
    }
    setAdding(true);
    try {
      const res = await fetch('/api/admin/credits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baleUserId: baleUserId.trim(),
          fullName: fullName.trim() || undefined,
          amount: amount.trim(),
          kind,
          reason: reason.trim(),
          trackingCode: trackingCode.trim() || undefined,
          caseId: caseId || undefined,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success('مبلغ در دفتر ثبت شد');
        resetForm();
        fetchRecords();
        onChanged?.();
      } else {
        toast.error(data.error || 'خطا در ثبت');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setAdding(false);
    }
  }, [baleUserId, fullName, amount, kind, reason, trackingCode, caseId, fetchRecords, onChanged]);

  const patch = useCallback(async (id: string, body: Record<string, unknown>, okMsg: string) => {
    setBusyId(id);
    try {
      const res = await fetch(`/api/admin/credits/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        toast.success(okMsg);
        setSettlingId(null);
        setSettleNote('');
        fetchRecords();
        onChanged?.();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.error || 'خطا در به‌روزرسانی');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setBusyId(null);
    }
  }, [fetchRecords, onChanged]);

  const handleDelete = useCallback(async (id: string) => {
    if (!window.confirm('این ردیف برای همیشه حذف شود؟')) return;
    setBusyId(id);
    try {
      const res = await fetch(`/api/admin/credits/${id}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('ردیف حذف شد');
        fetchRecords();
        onChanged?.();
      } else {
        toast.error('خطا در حذف');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setBusyId(null);
    }
  }, [fetchRecords, onChanged]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center animate-float">
              <Wallet className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">مبالغ قابل بازگشت / کسر</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                مبالغی که باید به کاربر برگردد یا در موارد بعدی او کسر شود، همراه با دلیل
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-170px)] -mx-1 px-1">
          <div className="space-y-4">
            {/* خلاصه */}
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-xl border bg-rose-50/60 dark:bg-rose-950/20 p-2.5 text-center">
                <p className="text-[10px] text-muted-foreground">بازگشت‌های باز</p>
                <p className="text-sm font-bold text-rose-600 nums-align">{fmt(summary.openRefund)}</p>
              </div>
              <div className="rounded-xl border bg-sky-50/60 dark:bg-sky-950/20 p-2.5 text-center">
                <p className="text-[10px] text-muted-foreground">کسرهای باز</p>
                <p className="text-sm font-bold text-sky-600 nums-align">{fmt(summary.openDeduct)}</p>
              </div>
              <div className="rounded-xl border bg-muted/30 p-2.5 text-center">
                <p className="text-[10px] text-muted-foreground">ردیف باز</p>
                <p className="text-sm font-bold nums-align">{fmt(summary.openCount)}</p>
              </div>
            </div>

            {/* فرم افزودن */}
            <div className="space-y-3 p-3 rounded-xl bg-muted/30 border">
              <p className="text-xs font-medium text-muted-foreground">ثبت مبلغ جدید (تومان)</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">شناسه بله *</Label>
                  <Input value={baleUserId} onChange={(e) => setBaleUserId(e.target.value)}
                    placeholder="مثال: 123456789" className="h-9 text-xs" dir="ltr" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">نام کاربر</Label>
                  <Input value={fullName} onChange={(e) => setFullName(e.target.value)}
                    placeholder="اختیاری" className="h-9 text-xs" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">مبلغ (تومان) *</Label>
                  <Input value={amount} onChange={(e) => setAmount(e.target.value)}
                    placeholder="مثال: 2000" className="h-9 text-xs" dir="ltr" inputMode="numeric" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">نوع *</Label>
                  <Select value={kind} onValueChange={(v) => setKind(v as 'REFUND' | 'DEDUCT_LATER')}>
                    <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="REFUND">بازگشت به کاربر</SelectItem>
                      <SelectItem value="DEDUCT_LATER">کسر در موارد بعدی</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs">دلیل *</Label>
                  <Textarea value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="مثلاً: ثبت به‌دلیل خطای سامانه انجام نشد؛ پیش‌پرداخت باید برگردد"
                    className="text-xs min-h-[60px]" />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs">کد رهگیری مرتبط</Label>
                  <Input value={trackingCode} onChange={(e) => setTrackingCode(e.target.value)}
                    placeholder="اختیاری" className="h-9 text-xs" dir="ltr" />
                </div>
              </div>
              <Button onClick={handleAdd}
                disabled={adding || !baleUserId.trim() || !amount.trim() || !reason.trim()}
                size="sm" className="w-full gap-1.5 text-xs bg-amber-600 hover:bg-amber-700">
                {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                ثبت در دفتر
              </Button>
            </div>

            {/* فیلتر و جستجو */}
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
              <Tabs value={statusTab} onValueChange={(v) => setStatusTab(v as 'OPEN' | 'SETTLED' | 'ALL')}>
                <TabsList className="h-8">
                  <TabsTrigger value="OPEN" className="text-xs">باز</TabsTrigger>
                  <TabsTrigger value="SETTLED" className="text-xs">تسویه‌شده</TabsTrigger>
                  <TabsTrigger value="ALL" className="text-xs">همه</TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="relative flex-1 min-w-[160px]">
                <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="جستجو: شناسه، نام، دلیل..." className="h-8 pr-8 text-xs" />
              </div>
            </div>

            {/* لیست */}
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-8">
                <Wallet className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
                <p className="text-xs text-muted-foreground">موردی ثبت نشده است</p>
              </div>
            ) : (
              <div className="space-y-2">
                {filtered.map((r) => (
                  <div key={r.id} className={cn(
                    'p-3 rounded-lg border bg-card space-y-2 transition-colors',
                    r.status !== 'OPEN' && 'opacity-70',
                  )}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-medium truncate">{r.fullName || '—'}</span>
                          <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded" dir="ltr">
                            {r.baleUserId}
                          </span>
                          <Badge className={cn('text-[10px] gap-1',
                            r.kind === 'REFUND'
                              ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300'
                              : 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300')}>
                            {r.kind === 'REFUND' ? <Undo2 className="h-3 w-3" /> : <MinusCircle className="h-3 w-3" />}
                            {KIND_LABEL[r.kind] ?? r.kind}
                          </Badge>
                          <Badge variant="outline" className="text-[10px]">{STATUS_LABEL[r.status] ?? r.status}</Badge>
                          {r.source === 'BOT' && <Badge variant="secondary" className="text-[10px]">ربات</Badge>}
                        </div>
                        <p className="text-xs text-foreground/80 whitespace-pre-wrap break-words">{r.reason}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {fmtDate(r.createdAt)}
                          {r.trackingCode && <> · رهگیری: <span dir="ltr" className="font-mono">{r.trackingCode}</span></>}
                          {r.settledAt && <> · {r.status === 'SETTLED' ? 'تسویه' : 'لغو'}: {fmtDate(r.settledAt)}</>}
                          {r.settleNote && <> · {r.settleNote}</>}
                        </p>
                      </div>
                      <p className="text-sm font-bold nums-align shrink-0">{fmt(r.amount)} <span className="text-[10px] font-normal text-muted-foreground">تومان</span></p>
                    </div>

                    {settlingId === r.id ? (
                      <div className="flex items-center gap-2">
                        <Input value={settleNote} onChange={(e) => setSettleNote(e.target.value)}
                          placeholder={r.kind === 'REFUND' ? 'توضیح (مثلاً: به کارت کاربر واریز شد)' : 'توضیح (مثلاً: در پرونده X کسر شد)'}
                          className="h-8 text-xs" autoFocus />
                        <Button size="sm" className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700"
                          disabled={busyId === r.id}
                          onClick={() => patch(r.id, { status: 'SETTLED', settleNote }, 'تسویه ثبت شد')}>
                          {busyId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'ثبت'}
                        </Button>
                        <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setSettlingId(null)}>انصراف</Button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {r.status === 'OPEN' ? (
                          <>
                            <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1 text-emerald-700"
                              onClick={() => { setSettlingId(r.id); setSettleNote(''); }}>
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              {r.kind === 'REFUND' ? 'بازگردانده شد' : 'کسر شد'}
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1"
                              disabled={busyId === r.id}
                              onClick={() => patch(r.id, { status: 'CANCELLED' }, 'لغو شد')}>
                              <XCircle className="h-3.5 w-3.5" />
                              لغو
                            </Button>
                          </>
                        ) : (
                          <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1"
                            disabled={busyId === r.id}
                            onClick={() => patch(r.id, { status: 'OPEN' }, 'دوباره باز شد')}>
                            <RotateCcw className="h-3.5 w-3.5" />
                            بازگشایی
                          </Button>
                        )}
                        <Button size="sm" variant="ghost"
                          className="h-7 w-7 p-0 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 mr-auto"
                          disabled={busyId === r.id} onClick={() => handleDelete(r.id)}>
                          {busyId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>بستن</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
