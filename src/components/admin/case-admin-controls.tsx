'use client';

// ⭐ v2.0 — کنترل‌های دستی مدیر در جزئیات پرونده:
// جابه‌جایی بین دسته‌ها، علامت امضا، وضعیت پرداخت و افزودن/کسر مبلغ.

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Loader2, Minus, Plus, Settings2 } from 'lucide-react';
import { toast } from 'sonner';
import type { CaseItem } from './cases-table';

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'PENDING_PAYMENT', label: 'پرداخت نشده' },
  { value: 'PROCESSING', label: 'در حال پردازش' },
  { value: 'INCOMPLETE', label: 'ناقص' },
  { value: 'COMPLETED', label: 'ثبت شده' },
  { value: 'READY_TO_SEND', label: 'آماده ارسال' },
  { value: 'FAILED', label: 'شکست خورده' },
  { value: 'CANCELLED', label: 'لغو شده' },
];

const PAID_STATUSES = new Set(['PAID', 'MANUAL_APPROVED']);

interface Props {
  caseItem: CaseItem;
  onUpdated: (updated: CaseItem) => void;
}

const fmt = (n: number) => new Intl.NumberFormat('fa-IR').format(n);

/** ارقام فارسی/عربی را به لاتین تبدیل و جداکننده‌ها را حذف می‌کند. */
function parseAmount(raw: string): number | null {
  const latin = raw
    .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
    .replace(/[,٬،\s]/g, '');
  if (!/^\d+$/.test(latin)) return null;
  return parseInt(latin, 10);
}

export default function CaseAdminControls({ caseItem, onUpdated }: Props) {
  const [saving, setSaving] = useState<string | null>(null);
  const [amount, setAmount] = useState('');

  useEffect(() => { setAmount(''); }, [caseItem.id]);

  const currentStatus = caseItem.isInReadyToSend ? 'READY_TO_SEND' : caseItem.status;
  const isPaid = PAID_STATUSES.has(caseItem.feeStatus);

  const update = async (key: string, payload: Record<string, unknown>, successMsg: string) => {
    setSaving(key);
    try {
      const res = await fetch(`/api/admin/cases/${caseItem.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'خطا در ذخیره');
      onUpdated({ ...caseItem, ...data });
      toast.success(successMsg);
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'خطا در ذخیره');
      return false;
    } finally {
      setSaving(null);
    }
  };

  const applyAmount = async (mode: 'add' | 'sub' | 'set') => {
    const n = parseAmount(amount);
    if (n === null) { toast.error('مبلغ معتبر وارد کنید'); return; }
    const payload = mode === 'set' ? { fee: n } : { feeDelta: mode === 'add' ? n : -n };
    const msg = mode === 'set' ? `مبلغ روی ${fmt(n)} تومان تنظیم شد`
      : mode === 'add' ? `${fmt(n)} تومان به مبلغ افزوده شد` : `${fmt(n)} تومان از مبلغ کسر شد`;
    if (await update('amount', payload, msg)) setAmount('');
  };

  return (
    <div>
      <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <div className="h-6 w-6 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
          <Settings2 className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
        </div>
        {'تنظیم دستی توسط مدیر'}
      </h4>
      <div className="glass-v2 rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Label className="text-xs text-muted-foreground shrink-0">{'دسته / وضعیت'}</Label>
          <div className="flex items-center gap-2">
            {saving === 'status' && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            <Select
              value={currentStatus}
              disabled={saving !== null}
              onValueChange={(v) => {
                const label = STATUS_OPTIONS.find((o) => o.value === v)?.label || v;
                update('status', { status: v }, `پرونده به «${label}» منتقل شد`);
              }}
            >
              <SelectTrigger className="w-40 h-9 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="admin-signature" className="text-xs text-muted-foreground">
            {'امضا درج شده'}
          </Label>
          <div className="flex items-center gap-2">
            {saving === 'signature' && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            <span className={caseItem.hasSignature ? 'text-xs text-emerald-600' : 'text-xs text-red-600'}>
              {caseItem.hasSignature ? 'بله' : 'خیر'}
            </span>
            <Switch
              id="admin-signature"
              checked={caseItem.hasSignature}
              disabled={saving !== null}
              onCheckedChange={(v) => update('signature', { hasSignature: v },
                v ? 'امضا «درج شده» ثبت شد' : 'امضا «درج نشده» ثبت شد')}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="admin-paid" className="text-xs text-muted-foreground">
            {'مبلغ پرداخت شده'}
          </Label>
          <div className="flex items-center gap-2">
            {saving === 'paid' && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            <span className={isPaid ? 'text-xs text-emerald-600' : 'text-xs text-red-600'}>
              {isPaid ? 'بله' : 'خیر'}
            </span>
            <Switch
              id="admin-paid"
              checked={isPaid}
              disabled={saving !== null}
              onCheckedChange={(v) => update('paid', { feeStatus: v ? 'PAID' : 'UNPAID' },
                v ? 'پرداخت «انجام شده» ثبت شد' : 'پرداخت «انجام نشده» ثبت شد')}
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="admin-amount" className="text-xs text-muted-foreground">{'مبلغ پرونده'}</Label>
            <span className="text-xs font-semibold nums-align">{fmt(caseItem.fee)} {'تومان'}</span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              id="admin-amount"
              inputMode="numeric"
              dir="ltr"
              placeholder="مبلغ (تومان)"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={saving !== null}
              className="h-9 text-xs flex-1"
            />
            <Button size="sm" variant="outline" className="h-9 text-emerald-700" disabled={saving !== null || !amount}
              onClick={() => applyAmount('add')} title="افزودن به مبلغ">
              <Plus className="h-3.5 w-3.5 ml-1" />{'افزودن'}
            </Button>
            <Button size="sm" variant="outline" className="h-9 text-red-600" disabled={saving !== null || !amount}
              onClick={() => applyAmount('sub')} title="کسر از مبلغ">
              <Minus className="h-3.5 w-3.5 ml-1" />{'کسر'}
            </Button>
            <Button size="sm" variant="outline" className="h-9" disabled={saving !== null || !amount}
              onClick={() => applyAmount('set')} title="جایگزینی مبلغ">
              {saving === 'amount' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'ثبت'}
            </Button>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground leading-5">
          {'این تغییرات فقط در پنل اعمال می‌شوند و در تاریخچهٔ پرونده ثبت می‌گردند؛ ربات را از مرحلهٔ فعلی کاربر جابه‌جا نمی‌کنند.'}
        </p>
      </div>
    </div>
  );
}
