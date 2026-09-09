'use client';

import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Trash2, Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

interface ResetDataDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}

// ⭐ ریست کامل داده‌ها — فقط پرونده‌ها (Case) و سوابق مستقیماً وابسته به آن‌ها
// (ActivityLog, AdminAction, CaseNote) پاک می‌شوند. ساعات کاری، کاربران معاف
// و پیام‌های ربات دست‌نخورده باقی می‌مانند. عملیات غیرقابل‌بازگشت است، پس
// کاربر باید عبارت «RESET» را تایپ کند تا دکمه فعال شود.
export default function ResetDataDialog({ open, onOpenChange, onDone }: ResetDataDialogProps) {
  const [confirmText, setConfirmText] = useState('');
  const [resetting, setResetting] = useState(false);

  const canReset = confirmText.trim().toUpperCase() === 'RESET';

  const handleReset = async () => {
    if (!canReset) return;
    setResetting(true);
    try {
      const res = await fetch('/api/admin/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: 'RESET' }),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(
          `تمام داده‌ها پاک شد — ${new Intl.NumberFormat('fa-IR').format(data.deleted?.cases ?? 0)} پرونده حذف شد`
        );
        setConfirmText('');
        onOpenChange(false);
        onDone?.();
      } else {
        toast.error(data.error || 'خطا در ریست داده‌ها');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setResetting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!resetting) { onOpenChange(v); if (!v) setConfirmText(''); } }}>
      <DialogContent className="max-w-sm p-0 dialog-premium" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center animate-float">
              <AlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">ریست کامل داده‌ها</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                این عمل تمام پرونده‌ها و سوابق مرتبط را برای همیشه پاک می‌کند و
                غیرقابل بازگشت است.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="p-5 space-y-3">
          <div className="bg-red-50/80 dark:bg-red-950/20 rounded-lg p-3 border border-red-200 dark:border-red-800 space-y-1">
            <p className="text-xs text-red-700 dark:text-red-400">
              پاک می‌شود: تمام پرونده‌ها، یادداشت‌ها، اقدامات ادمین و تاریخچه فعالیت.
            </p>
            <p className="text-xs text-muted-foreground">
              دست‌نخورده می‌ماند: ساعات کاری، کاربران معاف، پیام‌های ربات.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">
              برای تایید، عبارت <span className="font-mono font-bold" dir="ltr">RESET</span> را تایپ کنید
            </Label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="RESET"
              className="h-9 text-xs font-mono"
              dir="ltr"
              disabled={resetting}
            />
          </div>
        </div>
        <DialogFooter className="p-5 pt-0 gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={resetting}>انصراف</Button>
          <Button
            className="bg-red-600 hover:bg-red-700"
            onClick={handleReset}
            disabled={!canReset || resetting}
          >
            {resetting ? (
              <Loader2 className="h-4 w-4 ml-2 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4 ml-2" />
            )}
            پاک کردن همه چیز
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
