'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Clock, Copy, Save, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface WorkingHourItem {
  dayOfWeek: number;
  startHour: number;
  startMin: number;
  endHour: number;
  endMin: number;
  enabled: boolean;
}

const DEFAULT_SCHEDULE: WorkingHourItem[] = [
  { dayOfWeek: 0, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 1, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 2, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 3, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 4, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 5, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 6, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
];

const DAY_NAMES = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];

interface WorkingHoursDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function WorkingHoursDialog({ open, onOpenChange }: WorkingHoursDialogProps) {
  const [schedule, setSchedule] = useState<WorkingHourItem[]>([...DEFAULT_SCHEDULE]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const fetchSchedule = async () => {
      try {
        const res = await fetch('/api/admin/working-hours');
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.schedule) && data.schedule.length === 7) {
            setSchedule(data.schedule);
            return;
          }
        }
      } catch {
        // fall through to defaults
      }
      setSchedule([...DEFAULT_SCHEDULE]);
    };
    fetchSchedule();
  }, [open]);

  const updateDay = useCallback((index: number, updates: Partial<WorkingHourItem>) => {
    setSchedule((prev) =>
      prev.map((d, i) => (i === index ? { ...d, ...updates } : d))
    );
  }, []);

  const applyToAll = useCallback(() => {
    const firstEnabled = schedule.find((d) => d.enabled);
    if (!firstEnabled) {
      toast.error('حداقل یک روز فعال لازم است');
      return;
    }
    setSchedule((prev) =>
      prev.map((d) =>
        d.enabled
          ? { ...d, startHour: firstEnabled.startHour, startMin: firstEnabled.startMin, endHour: firstEnabled.endHour, endMin: firstEnabled.endMin }
          : d
      )
    );
    toast.success('ساعات کاری برای همه روزهای فعال اعمال شد');
  }, [schedule]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/admin/working-hours', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schedule }),
      });
      if (res.ok) {
        toast.success('ساعات کاری با موفقیت ذخیره شد');
        onOpenChange(false);
      } else {
        toast.error('خطا در ذخیره ساعات کاری');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setSaving(false);
    }
  }, [schedule, onOpenChange]);

  const hourOptions = Array.from({ length: 24 }, (_, i) => i);
  const minOptions = [0, 15, 30, 45];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center animate-float">
              <Clock className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">ساعات کاری سیستم</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                تنظیم ساعات کاری برای هر روز هفته
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-2 max-h-[50vh] overflow-y-auto scrollbar-premium py-2">
          {schedule.map((day, index) => (
            <div
              key={day.dayOfWeek}
              className={cn(
                'flex items-center gap-3 p-3 rounded-xl border transition-all duration-200',
                day.enabled
                  ? 'bg-card border-border'
                  : 'bg-muted/30 border-border/50 opacity-60'
              )}
            >
              <div className="flex items-center gap-2 min-w-[90px]">
                <Switch
                  checked={day.enabled}
                  onCheckedChange={(checked) => updateDay(index, { enabled: checked })}
                />
                <Label className="text-sm font-medium">{DAY_NAMES[index]}</Label>
              </div>

              {day.enabled && (
                <div className="flex items-center gap-2 flex-1">
                  <Select
                    value={String(day.startHour)}
                    onValueChange={(v) => updateDay(index, { startHour: Number(v) })}
                  >
                    <SelectTrigger className="w-20 h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {hourOptions.map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {new Intl.NumberFormat('fa-IR').format(h).padStart(2, '۰')}:{new Intl.NumberFormat('fa-IR').format(day.startMin).padStart(2, '۰')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={String(day.startMin)}
                    onValueChange={(v) => updateDay(index, { startMin: Number(v) })}
                  >
                    <SelectTrigger className="w-20 h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {minOptions.map((m) => (
                        <SelectItem key={m} value={String(m)}>
                          :{new Intl.NumberFormat('fa-IR').format(m).padStart(2, '۰')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <span className="text-xs text-muted-foreground mx-1">تا</span>

                  <Select
                    value={String(day.endHour)}
                    onValueChange={(v) => updateDay(index, { endHour: Number(v) })}
                  >
                    <SelectTrigger className="w-20 h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {hourOptions.map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {new Intl.NumberFormat('fa-IR').format(h).padStart(2, '۰')}:{new Intl.NumberFormat('fa-IR').format(day.endMin).padStart(2, '۰')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={String(day.endMin)}
                    onValueChange={(v) => updateDay(index, { endMin: Number(v) })}
                  >
                    <SelectTrigger className="w-20 h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {minOptions.map((m) => (
                        <SelectItem key={m} value={String(m)}>
                          :{new Intl.NumberFormat('fa-IR').format(m).padStart(2, '۰')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          ))}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={applyToAll}
            className="gap-1.5 text-xs"
          >
            <Copy className="h-3.5 w-3.5" />
            اعمال به همه
          </Button>
          <div className="flex-1" />
          <Button variant="outline" onClick={() => onOpenChange(false)}>انصراف</Button>
          <Button
            onClick={handleSave}
            disabled={saving}
            className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
