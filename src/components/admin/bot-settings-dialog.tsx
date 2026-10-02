'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Settings2, Save, Loader2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { BOT_SETTING_DEFS, validateBotSetting, type BotSettingDef } from '@/lib/bot-settings';

// ⭐ v1.9 — تعرفه‌ها و متن‌های ربات بدون دیپلوی (bot_settings.py هر ۶۰ ثانیه می‌خواند)

interface BotSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function BotSettingsDialog({ open, onOpenChange }: BotSettingsDialogProps) {
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch('/api/admin/bot-settings')
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => {
        const map: Record<string, string> = {};
        for (const s of data.settings || []) map[s.key] = s.value;
        setSaved(map);
        setDraft(map);
      })
      .catch(() => toast.error('خطا در خواندن تنظیمات ربات'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const groups = useMemo(() => {
    const out = new Map<string, BotSettingDef[]>();
    for (const def of BOT_SETTING_DEFS) {
      if (!out.has(def.group)) out.set(def.group, []);
      out.get(def.group)!.push(def);
    }
    return [...out.entries()];
  }, []);

  const errors = useMemo(() => {
    const out: Record<string, string> = {};
    for (const def of BOT_SETTING_DEFS) {
      const err = validateBotSetting(def, (draft[def.key] ?? '').trim());
      if (err) out[def.key] = err;
    }
    return out;
  }, [draft]);

  const changedKeys = BOT_SETTING_DEFS
    .map((d) => d.key)
    .filter((k) => (draft[k] ?? '').trim() !== (saved[k] ?? ''));

  const handleSave = useCallback(async () => {
    if (Object.keys(errors).length > 0) {
      toast.error('برخی مقادیر نامعتبرند');
      return;
    }
    const values: Record<string, string> = {};
    for (const k of changedKeys) values[k] = (draft[k] ?? '').trim();
    setSaving(true);
    try {
      const res = await fetch('/api/admin/bot-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const map: Record<string, string> = {};
      for (const s of data.settings || []) map[s.key] = s.value;
      setSaved(map);
      setDraft(map);
      toast.success('ذخیره شد — حداکثر ظرف یک دقیقه در ربات اعمال می‌شود');
    } catch {
      toast.error('خطا در ذخیرهٔ تنظیمات');
    } finally {
      setSaving(false);
    }
  }, [changedKeys, draft, errors]);

  const setValue = (key: string, value: string) => setDraft((d) => ({ ...d, [key]: value }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center">
              <Settings2 className="h-5 w-5 text-sky-600" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">تنظیمات ربات</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                تعرفه‌ها و متن‌های ربات بدون نیاز به دیپلوی؛ خالی گذاشتن هر مورد یعنی مقدار پیش‌فرض ربات
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-5 max-h-[55vh] overflow-y-auto scrollbar-premium py-2 px-1">
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin" /></div>
          ) : groups.map(([group, defs]) => (
            <section key={group} className="space-y-2">
              <h3 className="text-xs font-bold text-muted-foreground">{group}</h3>
              {defs.map((def) => {
                const value = draft[def.key] ?? '';
                const isOverridden = (saved[def.key] ?? '') !== '';
                return (
                  <div key={def.key} className="p-3 rounded-xl border bg-card space-y-1.5">
                    <div className="flex items-center gap-2">
                      <Label className="text-sm flex-1">{def.label}</Label>
                      {isOverridden && (
                        <Button
                          variant="ghost" size="sm" className="h-7 gap-1 text-xs"
                          onClick={() => setValue(def.key, '')}
                          title="بازگشت به پیش‌فرض ربات"
                        >
                          <RotateCcw className="h-3 w-3" /> پیش‌فرض
                        </Button>
                      )}
                    </div>
                    {def.kind === 'boolean' ? (
                      <Switch
                        checked={(value || def.defaultValue) === 'true'}
                        onCheckedChange={(checked) => setValue(def.key, checked ? 'true' : 'false')}
                      />
                    ) : def.kind === 'text' ? (
                      <Textarea
                        value={value}
                        onChange={(e) => setValue(def.key, e.target.value)}
                        placeholder="متن پیش‌فرض ربات"
                        className="text-sm min-h-20"
                      />
                    ) : (
                      <Input
                        value={value}
                        onChange={(e) => setValue(def.key, e.target.value)}
                        placeholder={`پیش‌فرض: ${new Intl.NumberFormat('fa-IR').format(Number(def.defaultValue))}`}
                        inputMode="numeric"
                        dir="ltr"
                        className="h-9 text-sm"
                      />
                    )}
                    {(errors[def.key] || def.hint) && (
                      <p className={errors[def.key] ? 'text-xs text-red-600' : 'text-xs text-muted-foreground'}>
                        {errors[def.key] || def.hint}
                      </p>
                    )}
                  </div>
                );
              })}
            </section>
          ))}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>بستن</Button>
          <Button
            onClick={handleSave}
            disabled={saving || changedKeys.length === 0}
            className="bg-sky-600 hover:bg-sky-700 gap-1.5"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            ذخیره{changedKeys.length > 0 ? ` (${new Intl.NumberFormat('fa-IR').format(changedKeys.length)})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
