'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Percent, Plus, Loader2, XCircle, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface UserDiscountRecord {
  id: string;
  baleUserId: string;
  fullName: string | null;
  percent: number;
  reason: string | null;
  createdAt: string;
}

interface UserDiscountsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function UserDiscountsDialog({ open, onOpenChange }: UserDiscountsDialogProps) {
  const [records, setRecords] = useState<UserDiscountRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [baleUserId, setBaleUserId] = useState('');
  const [percent, setPercent] = useState('');
  const [fullName, setFullName] = useState('');
  const [reason, setReason] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/user-discounts');
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
      }
    } catch {
      toast.error('خطا در دریافت لیست تخفیف‌ها');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchRecords();
  }, [open, fetchRecords]);

  const handleAdd = useCallback(async () => {
    if (!baleUserId.trim()) {
      toast.error('شناسه بله الزامی است');
      return;
    }
    const pct = Number(percent);
    if (!Number.isInteger(pct) || pct < 1 || pct > 100) {
      toast.error('درصد تخفیف باید عددی صحیح بین ۱ تا ۱۰۰ باشد');
      return;
    }
    setAdding(true);
    try {
      const res = await fetch('/api/admin/user-discounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baleUserId: baleUserId.trim(),
          percent: pct,
          fullName: fullName.trim() || undefined,
          reason: reason.trim() || undefined,
        }),
      });
      if (res.ok) {
        toast.success('تخفیف کاربر ذخیره شد');
        setBaleUserId('');
        setPercent('');
        setFullName('');
        setReason('');
        fetchRecords();
      } else {
        const data = await res.json();
        toast.error(data.error || 'خطا در ذخیرهٔ تخفیف');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setAdding(false);
    }
  }, [baleUserId, percent, fullName, reason, fetchRecords]);

  const handleDelete = useCallback(async (id: string) => {
    setDeleting(id);
    try {
      const res = await fetch(`/api/admin/user-discounts/${id}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('تخفیف کاربر حذف شد');
        fetchRecords();
      } else {
        toast.error('خطا در حذف تخفیف');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setDeleting(null);
    }
  }, [fetchRecords]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center animate-float">
              <Percent className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">تخفیف اختصاصی کاربران</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                درصد تخفیف فقط از سود ربات کم می‌شود، نه از هزینهٔ سامانه و دفتر خدمات
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-3 p-3 rounded-xl bg-muted/30 border">
            <p className="text-xs font-medium text-muted-foreground">افزودن یا ویرایش تخفیف (شناسهٔ تکراری، درصد قبلی را جایگزین می‌کند)</p>
            <div className="space-y-2">
              <div className="space-y-1.5">
                <Label className="text-xs">شناسه بله *</Label>
                <Input
                  value={baleUserId}
                  onChange={(e) => setBaleUserId(e.target.value)}
                  placeholder="مثال: 123456789"
                  className="h-9 text-xs"
                  dir="ltr"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">درصد تخفیف از سود *</Label>
                <Input
                  value={percent}
                  onChange={(e) => setPercent(e.target.value.replace(/[^0-9۰-۹]/g, '').replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))))}
                  placeholder="مثال: 30"
                  inputMode="numeric"
                  className="h-9 text-xs"
                  dir="ltr"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">نام کامل</Label>
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="نام و نام خانوادگی"
                  className="h-9 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">توضیح</Label>
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="مثلاً همکار، مشتری ثابت"
                  className="h-9 text-xs"
                />
              </div>
            </div>
            <Button
              onClick={handleAdd}
              disabled={adding || !baleUserId.trim() || !percent}
              size="sm"
              className="w-full gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700"
            >
              {adding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              ذخیره
            </Button>
          </div>

          <div className="border-t pt-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-muted-foreground">
                کاربران دارای تخفیف ({new Intl.NumberFormat('fa-IR').format(records.length)} نفر)
              </p>
            </div>
            <ScrollArea className="max-h-[200px]">
              {loading ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-6">
                  <Percent className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
                  <p className="text-xs text-muted-foreground">تخفیفی ثبت نشده است</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {records.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-center justify-between gap-3 p-2.5 rounded-lg border bg-card hover:bg-muted/30 transition-colors"
                    >
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{record.fullName || '—'}</span>
                          <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded" dir="ltr">
                            {record.baleUserId}
                          </span>
                          <span className="text-[11px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-1.5 py-0.5 rounded">
                            {new Intl.NumberFormat('fa-IR').format(record.percent)}٪ از سود
                          </span>
                        </div>
                        {record.reason && (
                          <p className="text-[11px] text-muted-foreground truncate">{record.reason}</p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground shrink-0"
                        onClick={() => {
                          setBaleUserId(record.baleUserId);
                          setPercent(String(record.percent));
                          setFullName(record.fullName || '');
                          setReason(record.reason || '');
                        }}
                        title="ویرایش"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 shrink-0"
                        onClick={() => handleDelete(record.id)}
                        disabled={deleting === record.id}
                      >
                        {deleting === record.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>بستن</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
