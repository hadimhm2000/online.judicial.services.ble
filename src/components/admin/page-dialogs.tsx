'use client';

import React from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Send, Trash2, Keyboard } from 'lucide-react';
import type { CaseItem } from '@/components/admin/cases-table';

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
};

interface ConfirmSendDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  caseItem: CaseItem | null;
  onConfirm: () => void;
}

export function ConfirmSendDialog({ open, onOpenChange, caseItem, onConfirm }: ConfirmSendDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm p-0 dialog-premium" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center animate-float">
              <Send className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">تأیید ارسال</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                آیا از ارسال نتیجه پرونده مطمئن هستید؟
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="p-5">
          {caseItem && (
            <div className="bg-gradient-to-br from-emerald-50/80 to-teal-50/50 dark:from-emerald-950/20 dark:to-teal-950/10 rounded-lg p-3 space-y-1.5 border border-emerald-100 dark:border-emerald-900/30">
              <p className="text-sm font-medium">{caseItem.fullName}</p>
              <p className="text-xs text-muted-foreground">{SERVICE_LABELS[caseItem.serviceType] || caseItem.serviceType}</p>
              {caseItem.trackingCode && (
                <p className="text-[11px] text-muted-foreground font-mono" dir="ltr">کد: {caseItem.trackingCode}</p>
              )}
            </div>
          )}
        </div>
        <DialogFooter className="p-5 pt-0 gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>انصراف</Button>
          <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={onConfirm}>
            <Send className="h-4 w-4 ml-2" />
            تأیید و ارسال
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  caseItem: CaseItem | null;
  onConfirm: () => void;
}

export function DeleteDialog({ open, onOpenChange, caseItem, onConfirm }: DeleteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm p-0 dialog-premium" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center animate-float">
              <Trash2 className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">حذف پرونده</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                این عمل غیرقابل بازگشت است
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="p-5">
          {caseItem && (
            <div className="bg-gradient-to-br from-red-50/80 to-rose-50/50 dark:from-red-950/20 dark:to-rose-950/10 rounded-lg p-3 space-y-1.5 border border-red-200 dark:border-red-800">
              <p className="text-sm font-medium">{caseItem.fullName}</p>
              <p className="text-xs text-muted-foreground">{SERVICE_LABELS[caseItem.serviceType] || caseItem.serviceType}</p>
            </div>
          )}
        </div>
        <DialogFooter className="p-5 pt-0 gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>انصراف</Button>
          <Button className="bg-red-600 hover:bg-red-700" onClick={onConfirm}>
            <Trash2 className="h-4 w-4 ml-2" />
            حذف نهایی
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts: { key: string; label: string }[];
}

export function KeyboardShortcutsDialog({ open, onOpenChange, shortcuts }: KeyboardShortcutsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md p-0 dialog-premium" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center animate-float">
              <Keyboard className="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">میانبر کلیدی</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                دسترسی سریع به ابزارهای پنل
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="p-5">
          <div className="grid grid-cols-2 gap-2.5">
            {shortcuts.map((s) => (
              <div
                key={s.key}
                className="flex items-center gap-3 p-2.5 rounded-lg bg-muted/40 border border-border/50"
              >
                <kbd className="kbd-shortcut shrink-0 text-[10px]">{s.key}</kbd>
                <span className="text-xs text-muted-foreground">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface PageDialogsProps {
  confirmSendOpen: boolean;
  onConfirmSendOpenChange: (open: boolean) => void;
  confirmSendCase: CaseItem | null;
  onConfirmSend: () => void;
  deleteOpen: boolean;
  onDeleteOpenChange: (open: boolean) => void;
  deleteCase: CaseItem | null;
  onDelete: () => void;
  showShortcuts: boolean;
  onShortcutsOpenChange: (open: boolean) => void;
  shortcuts: { key: string; label: string }[];
}

export default function PageDialogs({
  confirmSendOpen, onConfirmSendOpenChange, confirmSendCase, onConfirmSend,
  deleteOpen, onDeleteOpenChange, deleteCase, onDelete,
  showShortcuts, onShortcutsOpenChange, shortcuts,
}: PageDialogsProps) {
  return (
    <>
      <ConfirmSendDialog
        open={confirmSendOpen}
        onOpenChange={onConfirmSendOpenChange}
        caseItem={confirmSendCase}
        onConfirm={onConfirmSend}
      />
      <DeleteDialog
        open={deleteOpen}
        onOpenChange={onDeleteOpenChange}
        caseItem={deleteCase}
        onConfirm={onDelete}
      />
      <KeyboardShortcutsDialog
        open={showShortcuts}
        onOpenChange={onShortcutsOpenChange}
        shortcuts={shortcuts}
      />
    </>
  );
}
