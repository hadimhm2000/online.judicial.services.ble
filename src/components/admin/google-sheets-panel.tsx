'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
  FileSpreadsheet, CheckCircle2, XCircle, Settings,
  ArrowLeftRight, Eye, Loader2, AlertTriangle, Zap, Clock,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ConfigStatus {
  email: boolean;
  key: boolean;
  sheetId: boolean;
  allConfigured: boolean;
}

interface SyncResult {
  success: boolean;
  message: string;
  syncedCount?: number;
  sheetTitle?: string;
}

interface GoogleSheetsPanelProps {
  open: boolean;
  onClose: () => void;
}

const ENV_VARS = [
  {
    key: 'GOOGLE_SERVICE_ACCOUNT_EMAIL',
    label: 'ایمیل Service Account',
    placeholder: 'my-service@project.iam.gserviceaccount.com',
    icon: '📧',
  },
  {
    key: 'GOOGLE_PRIVATE_KEY',
    label: 'Private Key',
    placeholder: '-----BEGIN PRIVATE KEY-----\n...',
    icon: '🔑',
    isSecret: true,
  },
  {
    key: 'GOOGLE_SHEET_ID',
    label: 'شناسه گوگل شیت',
    placeholder: '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms',
    icon: '📊',
    hint: 'از URL شیت: docs.google.com/spreadsheets/d/THIS_PART/edit',
  },
];

export default function GoogleSheetsPanel({ open, onClose }: GoogleSheetsPanelProps) {
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [initing, setIniting] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [testResult, setTestResult] = useState<SyncResult | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'config' | 'help'>('overview');

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/sheets/status');
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchStatus();
      const saved = localStorage.getItem('lastSheetSync');
      if (saved) setLastSyncTime(saved);
    }
  }, [open, fetchStatus]);

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await fetch('/api/admin/sheets/sync', { method: 'POST' });
      const data = await res.json();
      setSyncResult(data);
      if (data.success) {
        toast.success(data.message);
        const now = new Date().toLocaleString('fa-IR');
        setLastSyncTime(now);
        localStorage.setItem('lastSheetSync', now);
        fetchStatus();
      } else {
        toast.error(data.message);
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setSyncing(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/admin/sheets/test', { method: 'POST' });
      const data = await res.json();
      setTestResult(data);
      if (data.success) {
        toast.success(data.message);
      } else {
        toast.error(data.message);
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setTesting(false);
    }
  };

  const handleInit = async () => {
    setIniting(true);
    try {
      const res = await fetch('/api/admin/sheets/init', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.success(data.message);
      } else {
        toast.error(data.message);
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setIniting(false);
    }
  };

  const configuredCount = config ? [config.email, config.key, config.sheetId].filter(Boolean).length : 0;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" dir="rtl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5 text-lg">
            <div className="h-9 w-9 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <FileSpreadsheet className="h-4.5 w-4.5 text-emerald-600" />
            </div>
            <div className="flex flex-col">
              <span>همگام‌سازی گوگل شیت</span>
              <span className="text-xs text-muted-foreground font-normal">
                ثبت خودکار پرونده‌ها و پرداخت‌ها
              </span>
            </div>
          </DialogTitle>
          <DialogDescription className="sr-only">مدیریت اتصال به Google Sheets</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Config Status Banner */}
            <div className={cn(
              'rounded-xl border p-4',
              config?.allConfigured
                ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800'
                : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800'
            )}>
              <div className="flex items-start gap-3">
                {config?.allConfigured ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5 shrink-0" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold">
                    {config?.allConfigured ? 'اتصال برقرار است' : 'پیکربندی ناقص'}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {configuredCount === 3
                      ? 'تمام متغیرهای محیطی تنظیم شده‌اند — سیستم آماده همگام‌سازی است'
                      : `${configuredCount} از ۳ متغیر محیطی تنظیم شده — ${3 - configuredCount} مورد باقی‌مانده`}
                  </p>
                </div>
                <Badge variant={config?.allConfigured ? 'default' : 'outline'} className="shrink-0">
                  {configuredCount}/۳
                </Badge>
              </div>
            </div>

            {/* Config Items Table */}
            <div className="rounded-xl border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead className="text-xs">متغیر</TableHead>
                    <TableHead className="text-xs">وضعیت</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ENV_VARS.map((env) => {
                    const isSet = config?.[env.key === 'GOOGLE_PRIVATE_KEY' ? 'key' : env.key === 'GOOGLE_SERVICE_ACCOUNT_EMAIL' ? 'email' : 'sheetId' as keyof ConfigStatus] as boolean;
                    return (
                      <TableRow key={env.key}>
                        <TableCell className="text-xs font-medium">
                          <span className="ml-1.5">{env.icon}</span>
                          {env.label}
                        </TableCell>
                        <TableCell>
                          {isSet ? (
                            <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 hover:bg-emerald-100">
                              <CheckCircle2 className="h-3 w-3 ml-1" />
                              تنظیم شده
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-amber-600 border-amber-300">
                              <XCircle className="h-3 w-3 ml-1" />
                              تنظیم نشده
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* Last Sync Info */}
            {lastSyncTime && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
                <Clock className="h-3.5 w-3.5" />
                آخرین همگام‌سازی: {lastSyncTime}
              </div>
            )}

            {/* Action Buttons */}
            <div className="grid grid-cols-3 gap-2">
              <Button
                variant="outline"
                className="h-auto py-3 flex-col gap-1.5 text-xs"
                onClick={handleTest}
                disabled={testing || !config?.allConfigured}
              >
                {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                تست اتصال
              </Button>

              <Button
                className="h-auto py-3 flex-col gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700"
                onClick={handleSync}
                disabled={syncing || !config?.allConfigured}
              >
                {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowLeftRight className="h-4 w-4" />}
                همگام‌سازی
              </Button>

              <Button
                variant="outline"
                className="h-auto py-3 flex-col gap-1.5 text-xs"
                onClick={handleInit}
                disabled={initing || !config?.allConfigured}
              >
                {initing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                راه‌اندازی شیت
              </Button>
            </div>

            {/* Results */}
            {testResult && (
              <div className={cn(
                'rounded-lg border p-3 text-xs',
                testResult.success
                  ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800'
                  : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
              )}>
                <div className="flex items-start gap-2">
                  {testResult.success ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" /> : <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />}
                  <div className="min-w-0">
                    <p className="font-bold">{testResult.success ? 'موفق' : 'ناموفق'}</p>
                    <p className="text-muted-foreground mt-0.5 break-words">{testResult.message}</p>
                  </div>
                </div>
              </div>
            )}

            {syncResult && (
              <div className={cn(
                'rounded-lg border p-3 text-xs',
                syncResult.success
                  ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800'
                  : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
              )}>
                <div className="flex items-start gap-2">
                  {syncResult.success ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" /> : <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />}
                  <div className="min-w-0">
                    <p className="font-bold">{syncResult.success ? 'همگام‌سازی موفق' : 'خطا'}</p>
                    <p className="text-muted-foreground mt-0.5 break-words">{syncResult.message}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Help Section */}
            <div className="rounded-xl border bg-muted/30 p-4 space-y-3">
              <h4 className="text-sm font-bold flex items-center gap-2">
                <Settings className="h-4 w-4" />
                راهنمای تنظیم
              </h4>
              <ol className="text-xs text-muted-foreground space-y-2 list-decimal list-inside">
                <li>
                  به{' '}
                  <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-emerald-600 underline underline-offset-2">
                    Google Cloud Console
                  </a>{' '}
                  بروید و یک پروژه بسازید
                </li>
                <li>
                  <strong>Google Sheets API</strong> را فعال کنید
                </li>
                <li>
                  یک <strong>Service Account</strong> بسازید و کلید JSON را دانلود کنید
                </li>
                <li>
                  ایمیل Service Account را به ویرایشگرهای گوگل شیت اضافه کنید
                </li>
                <li>
                  سه متغیر محیطی زیر را در فایل <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono">.env</code> تنظیم کنید:
                </li>
              </ol>
              <div className="bg-background rounded-lg p-3 space-y-1.5 font-mono text-[11px] overflow-x-auto">
                <div className="text-amber-600">GOOGLE_SERVICE_ACCOUNT_EMAIL=your-email@project.iam.gserviceaccount.com</div>
                <div className="text-amber-600">GOOGLE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...</div>
                <div className="text-amber-600">GOOGLE_SHEET_ID=your-spreadsheet-id-from-url</div>
              </div>

              <div className="flex items-start gap-2 pt-1">
                <Zap className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                <p className="text-xs text-muted-foreground">
                  <strong>همگام‌سازی خودکار:</strong> هر پرونده جدید، تغییر وضعیت و پرداخت به‌صورت خودکار در گوگل شیت ثبت می‌شود
                </p>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
