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
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertTriangle,
  Upload,
  Send,
  FileCheck2,
  Loader2,
  X,
  CheckCircle2,
  Info,
  FileUp,
  Bot,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CaseItem } from './cases-table';

interface ManualInterventionDialogProps {
  caseItem: CaseItem | null;
  open: boolean;
  onClose: () => void;
  onSubmit: (data: {
    caseId: string;
    adminNote: string;
    actionType: string;
    newStatus: string;
    uploadedFileUrls: string[];
    sentViaBot: boolean;
  }) => Promise<void>;
}

export default function ManualInterventionDialog({
  caseItem,
  open,
  onClose,
  onSubmit,
}: ManualInterventionDialogProps) {
  const [adminNote, setAdminNote] = useState('');
  const [actionType, setActionType] = useState('MANUAL_INTERVENTION');
  const [newStatus, setNewStatus] = useState('COMPLETED');
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [botSend, setBotSend] = useState(true);

  if (!caseItem) return null;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploadError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      Array.from(files).forEach((f) => formData.append('files', f));

      const res = await fetch('/api/admin/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'آپلود فایل ناموفق بود');
      }

      const newUrls = (data.files as { url: string; name: string }[]).map((f) => f.url);
      const newNames = (data.files as { url: string; name: string }[]).map((f) => f.name);

      setUploadedFiles((prev) => [...prev, ...newUrls]);
      setFileNames((prev) => [...prev, ...newNames]);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'آپلود فایل ناموفق بود');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const removeFile = (index: number) => {
    setFileNames(fileNames.filter((_, i) => i !== index));
    setUploadedFiles(uploadedFiles.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!adminNote.trim() && actionType === 'MANUAL_INTERVENTION') return;
    setSending(true);
    try {
      await onSubmit({
        caseId: caseItem.id,
        adminNote,
        actionType,
        newStatus: actionType === 'SEND_TO_USER' ? 'COMPLETED' : newStatus,
        uploadedFileUrls: uploadedFiles,
        sentViaBot: actionType === 'SEND_TO_USER' ? botSend : false,
      });
      setSuccess(true);
      setTimeout(() => {
        handleClose();
      }, 2000);
    } catch (err) {
      console.error(err);
    } finally {
      setSending(false);
    }
  };

  const handleClose = () => {
    setAdminNote('');
    setActionType('MANUAL_INTERVENTION');
    setNewStatus('COMPLETED');
    setUploadedFiles([]);
    setFileNames([]);
    setSending(false);
    setUploading(false);
    setUploadError(null);
    setSuccess(false);
    setBotSend(true);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={handleClose} className="dialog-premium">
      <DialogContent className="max-w-lg p-0" dir="rtl">
        <DialogHeader className="p-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-md shadow-amber-500/25">
              <AlertTriangle className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold">
                {"مداخله دستی ادمین"}
              </DialogTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                {caseItem.fullName} {"—"} {caseItem.serviceType === 'INQUIRY' ? 'استعلام' :
                  caseItem.serviceType === 'LAVAYEH' ? 'ثبت لایحه' :
                  caseItem.serviceType === 'EZHHARNAMEH' ? 'اظهارنامه' :
                  caseItem.serviceType === 'EALAM_VAKALAHT' ? 'اعلام وکالت' : caseItem.serviceType}
              </p>
            </div>
          </div>
        </DialogHeader>

        {success ? (
          <div className="p-8 flex flex-col items-center justify-center gap-3 animate-scale-in">
            <div className="h-16 w-16 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg shadow-emerald-500/30">
              <CheckCircle2 className="h-8 w-8 text-white" />
            </div>
            <p className="font-bold text-emerald-700 dark:text-emerald-300">{"عملیات با موفقیت انجام شد"}</p>
            <p className="text-sm text-muted-foreground">
              {actionType === 'SEND_TO_USER'
                ? `نتیجه برای ${caseItem.fullName} از طریق ربات ارسال شد`
                : 'اقدام ادمین ثبت شد'}
            </p>
          </div>
        ) : (
          <div className="p-5 space-y-4 glass-v2 rounded-b-2xl">
            <div className="bg-gradient-to-l from-amber-50 to-orange-50 dark:from-amber-950/20 dark:to-orange-950/20 rounded-xl p-3.5 border border-amber-200/60 dark:border-amber-800/40">
              <div className="flex items-start gap-2.5">
                <div className="h-6 w-6 rounded-lg bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center shrink-0 mt-0.5">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                </div>
                <div className="text-xs text-amber-700 dark:text-amber-300 leading-6">
                  {"توجه: این عملیات مستقیماً در پرونده ثبت می‌شود. لطفاً دقیق باشید."}
                </div>
              </div>
            </div>

            {caseItem.errorDetails && (
              <div className="bg-red-50/80 dark:bg-red-950/30 border border-red-200/60 dark:border-red-800/40 rounded-xl p-3.5 transition-all duration-200">
                <p className="text-xs font-semibold text-red-600 mb-1 flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {"دلیل شکست:"}
                </p>
                <p className="text-xs text-red-700 dark:text-red-300 leading-6">
                  {caseItem.errorDetails}
                </p>
              </div>
            )}

            {caseItem.lastCompletedStep && (
              <div className="bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/40 rounded-xl p-3.5 transition-all duration-200">
                <p className="text-xs text-amber-700 dark:text-amber-300 leading-6">
                  {"آخرین مرحله تکمیل شده:"} <strong>{caseItem.lastCompletedStep}</strong>
                </p>
              </div>
            )}

            <div className="space-y-2">
              <Label className="text-sm font-medium transition-all duration-200">{"نوع اقدام"}</Label>
              <Select value={actionType} onValueChange={setActionType}>
                <SelectTrigger className="w-full transition-all duration-200 focus-ring-premium">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MANUAL_INTERVENTION">{"ثبت یادداشت و ادامه"}</SelectItem>
                  <SelectItem value="SEND_TO_USER">
                    {"تکمیل و ارسال مستقیم به کاربر"}
                  </SelectItem>
                  <SelectItem value="STATUS_CHANGE">{"تغییر وضعیت"}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {actionType === 'STATUS_CHANGE' && (
              <div className="space-y-2">
                <Label className="text-sm font-medium transition-all duration-200">{"وضعیت جدید"}</Label>
                <Select value={newStatus} onValueChange={setNewStatus}>
                  <SelectTrigger className="w-full transition-all duration-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="COMPLETED">{"تکمیل شده"}</SelectItem>
                    <SelectItem value="PROCESSING">{"در حال پردازش"}</SelectItem>
                    <SelectItem value="INCOMPLETE">{"ناقص"}</SelectItem>
                    <SelectItem value="CANCELLED">{"لغو شده"}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label className="text-sm font-medium">{"بارگذاری فایل"}</Label>
              <div className="border-2 border-dashed border-border rounded-xl p-6 text-center hover:border-primary/50 hover:bg-primary/5 transition-all duration-200 cursor-pointer group">
                <input
                  type="file"
                  multiple
                  onChange={handleFileChange}
                  className="hidden"
                  id="file-upload"
                  accept="image/*,.pdf,.doc,.docx"
                  disabled={uploading}
                />
                <label
                  htmlFor="file-upload"
                  className={cn(
                    'flex flex-col items-center gap-2.5',
                    uploading ? 'cursor-wait opacity-70' : 'cursor-pointer'
                  )}
                >
                  <div className="h-10 w-10 rounded-xl bg-muted/50 group-hover:bg-primary/10 flex items-center justify-center transition-all duration-200 group-hover:scale-110">
                    {uploading ? (
                      <Loader2 className="h-5 w-5 text-primary animate-spin" />
                    ) : (
                      <FileUp className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground group-hover:text-foreground transition-colors">
                      {uploading ? 'در حال آپلود...' : 'کلیک کنید یا فایل بکشید'}
                    </p>
                    <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                      {"تصاویر، PDF، Word — حداکثر ۲۰ مگابایت"}
                    </p>
                  </div>
                </label>
              </div>

              {uploadError && (
                <p className="text-xs text-red-600 dark:text-red-400">{uploadError}</p>
              )}

              {fileNames.length > 0 && (
                <div className="space-y-1.5">
                  {fileNames.map((name, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-lg p-2.5 border border-border/50 transition-all duration-200 hover:shadow-sm"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FileCheck2 className="h-4 w-4 text-primary shrink-0" />
                        <span className="text-xs truncate">{name}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 shrink-0 transition-all duration-200"
                        onClick={() => removeFile(i)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">{"توضیحات ادمین"}</Label>
              <Textarea
                value={adminNote}
                onChange={(e) => setAdminNote(e.target.value)}
                placeholder={"توضیحات خود را بنویسید..."}
                className="min-h-[100px] text-sm resize-none transition-all duration-200 focus:ring-2 focus:ring-primary/20 focus-ring-premium"
              />
            </div>

            {actionType === 'SEND_TO_USER' && (
              <div className="bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-xl p-3.5 border border-sky-200/60 dark:border-sky-800/40 transition-all duration-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-start gap-2.5 flex-1">
                    <div className="h-6 w-6 rounded-lg bg-sky-100 dark:bg-sky-900/40 flex items-center justify-center shrink-0 mt-0.5">
                      <Bot className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" />
                    </div>
                    <p className="text-xs text-sky-700 dark:text-sky-300 leading-6">
                      {"ارسال از طریق ربات به"} <strong>{caseItem.fullName}</strong>
                    </p>
                  </div>
                  <Switch
                    checked={botSend}
                    onCheckedChange={setBotSend}
                    className="transition-all duration-200"
                  />
                </div>
              </div>
            )}

            <div className="bg-muted/30 dark:bg-muted/20 rounded-xl p-3 border border-border/50">
              <div className="flex items-start gap-2.5">
                <Info className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-[11px] text-muted-foreground leading-6">
                  {"مداخله دستی به ادمین اجازه می‌دهد تا بدون مرجعه به سامانه های خارجی، نتیجه را ثبت کرده و برای کاربر ارسال کند."}
                </p>
              </div>
            </div>

            <DialogFooter className="gap-2 sm:gap-0">
              <Button variant="outline" onClick={handleClose} className="transition-all duration-200">
                {"انصراف"}
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={sending || uploading || (!adminNote.trim() && actionType !== 'SEND_TO_USER')}
                className={cn(
                  'transition-all duration-200 scale-[1.02] active:scale-[0.98] shadow-md',
                  actionType === 'SEND_TO_USER'
                    ? 'bg-gradient-to-l from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white shadow-emerald-500/20'
                    : ''
                )}
              >
                {sending ? (
                  <>
                    <Loader2 className="h-4 w-4 ml-2 animate-spin" />
                    {"در حال ارسال..."}
                  </>
                ) : actionType === 'SEND_TO_USER' ? (
                  <>
                    <Send className="h-4 w-4 ml-2" />
                    {"ارسال از طریق ربات"}
                  </>
                ) : (
                  'ثبت اقدام'
                )}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
