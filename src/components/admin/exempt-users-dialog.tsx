'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Users, Plus, Trash2, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface ExemptUserRecord {
  id: string;
  baleUserId: string;
  fullName: string | null;
  reason: string | null;
  createdAt: string;
}

interface ExemptUsersDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ExemptUsersDialog({ open, onOpenChange }: ExemptUsersDialogProps) {
  const [records, setRecords] = useState<ExemptUserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [baleUserId, setBaleUserId] = useState('');
  const [fullName, setFullName] = useState('');
  const [reason, setReason] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/exempt-users');
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
      }
    } catch {
      toast.error('خطا در دریافت لیست کاربران معاف');
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
    setAdding(true);
    try {
      const res = await fetch('/api/admin/exempt-users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baleUserId: baleUserId.trim(),
          fullName: fullName.trim() || undefined,
          reason: reason.trim() || undefined,
        }),
      });
      if (res.ok) {
        toast.success('کاربر معاف با موفقیت اضافه شد');
        setBaleUserId('');
        setFullName('');
        setReason('');
        fetchRecords();
      } else {
        const data = await res.json();
        toast.error(data.error || 'خطا در افزودن کاربر');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setAdding(false);
    }
  }, [baleUserId, fullName, reason, fetchRecords]);

  const handleDelete = useCallback(async (id: string) => {
    setDeleting(id);
    try {
      const res = await fetch(`/api/admin/exempt-users/${id}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('کاربر معاف حذف شد');
        fetchRecords();
      } else {
        toast.error('خطا در حذف کاربر');
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
            <div className="h-10 w-10 rounded-full bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center animate-float">
              <Users className="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">کاربران معاف</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                مدیریت کاربرانی از محدودیت ساعات کاری معاف هستند
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-3 p-3 rounded-xl bg-muted/30 border">
            <p className="text-xs font-medium text-muted-foreground">افزودن کاربر جدید</p>
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
                <Label className="text-xs">نام کامل</Label>
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="نام و نام خانوادگی"
                  className="h-9 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">دلیل معافیت</Label>
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="دلیل معافیت از محدودیت"
                  className="h-9 text-xs"
                />
              </div>
            </div>
            <Button
              onClick={handleAdd}
              disabled={adding || !baleUserId.trim()}
              size="sm"
              className="w-full gap-1.5 text-xs bg-violet-600 hover:bg-violet-700"
            >
              {adding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              افزودن
            </Button>
          </div>

          <div className="border-t pt-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-muted-foreground">
                لیست کاربران معاف ({new Intl.NumberFormat('fa-IR').format(records.length)} نفر)
              </p>
            </div>
            <ScrollArea className="max-h-[200px]">
              {loading ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-6">
                  <Users className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
                  <p className="text-xs text-muted-foreground">کاربر معافی ثبت نشده است</p>
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
                        </div>
                        {record.reason && (
                          <p className="text-[11px] text-muted-foreground truncate">{record.reason}</p>
                        )}
                      </div>
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
