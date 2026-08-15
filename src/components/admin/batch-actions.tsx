'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  Send,
  ArrowLeftRight,
  FileCheck2,
  Loader2,
  Zap,
  Check,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface BatchActionsDialogProps {
  selectedIds: string[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}

const ACTIONS = [
  {
    value: 'APPROVE_PAYMENTS',
    label: 'تأیید پرداخت',
    description: 'تغییر وضعیت پرداخت انتخاب‌شده به «پرداخت شده»',
    icon: CheckCircle2,
    color: 'text-emerald-600',
    borderColor: 'border-emerald-300 dark:border-emerald-700',
    bgColor: 'bg-emerald-50 dark:bg-emerald-950/20',
    iconBg: 'bg-emerald-100 dark:bg-emerald-900/40',
    needsStatus: false,
  },
  {
    value: 'MOVE_TO_READY',
    label: 'انتقال به آماده ارسال',
    description: 'انتخاب‌شده‌ها را به بخش آماده ارسال منتقل کن',
    icon: FileCheck2,
    color: 'text-sky-600',
    borderColor: 'border-sky-300 dark:border-sky-700',
    bgColor: 'bg-sky-50 dark:bg-sky-950/20',
    iconBg: 'bg-sky-100 dark:bg-sky-900/40',
    needsStatus: false,
  },
  {
    value: 'CONFIRM_SEND_ALL',
    label: 'تأیید و ارسال همه',
    description: 'همه را از طریق ربات برای کاربران ارسال کن',
    icon: Send,
    color: 'text-teal-600',
    borderColor: 'border-teal-300 dark:border-teal-700',
    bgColor: 'bg-teal-50 dark:bg-teal-950/20',
    iconBg: 'bg-teal-100 dark:bg-teal-900/40',
    needsStatus: false,
  },
  {
    value: 'CHANGE_STATUS',
    label: 'تغییر وضعیت دسته‌ای',
    description: 'تغییر وضعیت به یک مقدار مشخص',
    icon: ArrowLeftRight,
    color: 'text-violet-600',
    borderColor: 'border-violet-300 dark:border-violet-700',
    bgColor: 'bg-violet-50 dark:bg-violet-950/20',
    iconBg: 'bg-violet-100 dark:bg-violet-900/40',
    needsStatus: true,
  },
];

export default function BatchActionsDialog({
  selectedIds,
  open,
  onClose,
  onDone,
}: BatchActionsDialogProps) {
  const [action, setAction] = useState('');
  const [newStatus, setNewStatus] = useState('');
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);

  const selectedAction = ACTIONS.find((a) => a.value === action);
  const needsStatus = selectedAction?.needsStatus;

  const handleSubmit = async () => {
    if (!action) return;
    setSending(true);
    try {
      const body: Record<string, unknown> = {
        ids: selectedIds,
        action,
        adminNote: note || undefined,
      };
      if (needsStatus && newStatus) body.newStatus = newStatus;

      const res = await fetch('/api/admin/cases/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message);
        onDone();
        handleClose();
      } else {
        const data = await res.json();
        toast.error(data.error || 'خطا در انجام عملیات');
      }
    } catch (e) {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setSending(false);
    }
  };

  const handleClose = () => {
    setAction('');
    setNewStatus('');
    setNote('');
    setSending(false);
    onClose();
  };

  const isValid = action && (!needsStatus || newStatus);

  const currentStep = needsStatus && newStatus ? 3 : action ? 2 : 1;

  return (
    <Dialog open={open} onOpenChange={handleClose} className="dialog-premium">
      <DialogContent className="max-w-md p-0" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-md shadow-violet-500/25">
                <Zap className="h-5 w-5 text-white" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold">
                  {"عملیات دسته‌ای"}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge className={cn('text-[10px] animate-badge-pulse shadow-sm',
                    selectedIds.length > 10 ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300' :
                    'bg-primary/10 text-primary'
                  )}>
                    {new Intl.NumberFormat('fa-IR').format(selectedIds.length)} {"مورد انتخاب شده"}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 mt-4">
            {[1, 2, 3].map((step) => (
              <div key={step} className="flex items-center gap-1.5 flex-1">
                <div className={cn(
                  'h-7 w-7 rounded-full flex items-center justify-center text-[11px] font-bold transition-all duration-300',
                  currentStep >= step
                    ? 'bg-gradient-to-br from-primary to-primary/80 text-primary-foreground shadow-sm'
                    : 'bg-muted/50 text-muted-foreground'
                )}>
                  {currentStep > step ? <Check className="h-3.5 w-3.5" /> : step}
                </div>
                {step < 3 && (
                  <div className={cn(
                    'flex-1 h-0.5 rounded-full transition-all duration-300',
                    currentStep > step ? 'bg-primary/60' : 'bg-muted/30'
                  )} />
                )}
              </div>
            ))}
          </div>
        </DialogHeader>

        <div className="p-5 space-y-4">
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">{"نوع عملیات"}</Label>
            <Select value={action} onValueChange={(v) => { setAction(v); setNewStatus(''); }}>
              <SelectTrigger className="w-full transition-all duration-200">
                <SelectValue placeholder={"انتخاب کنید..."} />
              </SelectTrigger>
              <SelectContent>
                {ACTIONS.map((a) => {
                  const Icon = a.icon;
                  return (
                    <SelectItem key={a.value} value={a.value}>
                      <span className="flex items-center gap-2">
                        <Icon className={cn('h-4 w-4', a.color)} />
                        {a.label}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>

          {selectedAction && (
            <div className={cn(
              'rounded-xl p-3.5 border transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md',
              selectedAction.bgColor,
              selectedAction.borderColor
            )}>
              <div className="flex items-center gap-2.5">
                <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center', selectedAction.iconBg)}>
                  <selectedAction.icon className={cn('h-4 w-4', selectedAction.color)} />
                </div>
                <div>
                  <p className={cn('text-sm font-semibold', selectedAction.color)}>{selectedAction.label}</p>
                  <p className="text-[11px] text-muted-foreground leading-5">{selectedAction.description}</p>
                </div>
              </div>
            </div>
          )}

          {needsStatus && (
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">{"وضعیت جدید"}</Label>
              <Select value={newStatus} onValueChange={setNewStatus}>
                <SelectTrigger className="w-full transition-all duration-200">
                  <SelectValue placeholder={"انتخاب وضعیت..."} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="COMPLETED">{"تکمیل شده"}</SelectItem>
                  <SelectItem value="INCOMPLETE">{"ناقص"}</SelectItem>
                  <SelectItem value="CANCELLED">{"لغو شده"}</SelectItem>
                  <SelectItem value="PROCESSING">{"در حال پردازش"}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-sm font-medium">{"یادداشت"}</Label>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={"توضیحات ادمین..."}
              className="min-h-[70px] text-sm resize-none transition-all duration-200 focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={handleClose} className="transition-all duration-200">
              {"انصراف"}
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!isValid || sending}
              className={cn(
                'transition-all duration-200 scale-[1.02] active:scale-[0.98] shadow-md',
                action === 'CONFIRM_SEND_ALL'
                  ? 'bg-gradient-to-l from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white shadow-emerald-500/20'
                  : ''
              )}
            >
              {sending ? (
                <>
                  <Loader2 className="h-4 w-4 ml-2 animate-spin" />
                  {"در حال انجام..."}
                </>
              ) : (
                <>
                  {selectedAction && (
                    <selectedAction.icon className="h-4 w-4 ml-2" />
                  )}
                  {"اجرا"}
                </>
              )}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
