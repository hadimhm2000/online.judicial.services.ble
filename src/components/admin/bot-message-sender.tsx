'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Send, MessageSquare, Search, Check, XCircle, Clock, Trash2, User, ChevronDown,
  Paperclip, X, Upload,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface BotMessageItem {
  id: string;
  baleUserId: string;
  fullName: string | null;
  messageText: string;
  fileUrl: string | null;
  fileName: string | null;
  status: string;
  sentAt: string | null;
  errorDetails: string | null;
  createdAt: string;
}

interface UserSuggestion {
  baleUserId: string;
  fullName: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onRefresh?: () => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  PENDING: { label: 'در انتظار', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: Clock },
  SENT: { label: 'ارسال شده', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: Check },
  FAILED: { label: 'شکست خورده', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', icon: XCircle },
};

export default function BotMessageSender({ open, onClose, onRefresh }: Props) {
  const [messages, setMessages] = useState<BotMessageItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'compose' | 'history'>('compose');
  const [baleUserId, setBaleUserId] = useState('');
  const [fullName, setFullName] = useState('');
  const [messageText, setMessageText] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [userSuggestions, setUserSuggestions] = useState<UserSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [sendingAll, setSendingAll] = useState(false);
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<Set<string>>(new Set());
  const [attachedFile, setAttachedFile] = useState<{ url: string; name: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchMessages = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/bot-messages?limit=50');
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && activeTab === 'history') {
      fetchMessages();
    }
  }, [open, activeTab, fetchMessages]);

  const searchUsers = useCallback(async (query: string) => {
    if (!query || query.length < 2) {
      setUserSuggestions([]);
      return;
    }
    try {
      const res = await fetch(`/api/admin/users?search=${encodeURIComponent(query)}`);
      if (res.ok) {
        const data = await res.json();
        setUserSuggestions(data.users || []);
        setShowSuggestions(true);
      }
    } catch {
      // silent
    }
  }, []);

  const handleUserSearchChange = (value: string) => {
    setUserSearch(value);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      searchUsers(value);
    }, 300);
  };

  const selectUser = (user: UserSuggestion) => {
    setBaleUserId(user.baleUserId);
    setFullName(user.fullName);
    setUserSearch(user.fullName);
    setShowSuggestions(false);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 20 * 1024 * 1024) {
      toast.error('حجم فایل نباید بیشتر از ۲۰ مگابایت باشد');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('files', file);
      const res = await fetch('/api/admin/upload', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.files?.length) {
          setAttachedFile({ url: data.files[0].url, name: data.files[0].name });
          toast.success(`فایل «${file.name}» آپلود شد`);
        }
      } else {
        toast.error('خطا در آپلود فایل');
      }
    } catch {
      toast.error('خطا در آپلود فایل');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeFile = () => {
    setAttachedFile(null);
  };

  const handleSend = async () => {
    if (!baleUserId.trim() || !messageText.trim()) {
      toast.error('شناسه بله و متن پیام الزامی است');
      return;
    }

    try {
      const res = await fetch('/api/admin/bot-messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baleUserId: baleUserId.trim(),
          fullName: fullName.trim(),
          messageText: messageText.trim(),
          fileUrl: attachedFile?.url || null,
          fileName: attachedFile?.name || null,
        }),
      });

      if (res.ok) {
        const msg = await res.json();
        toast.success('پیام ثبت شد');

        setSending(msg.id);
        const sendRes = await fetch(`/api/admin/bot-messages/${msg.id}/send`, { method: 'POST' });
        setSending(null);

        if (sendRes.ok) {
          toast.success(`پیام برای ${fullName || baleUserId} ارسال شد`);
          setMessageText('');
          setAttachedFile(null);
          fetchMessages();
          onRefresh?.();
        } else {
          const errData = await sendRes.json().catch(() => null);
          toast.error(errData?.error || 'خطا در ارسال پیام');
          fetchMessages();
        }
      } else {
        const errData = await res.json().catch(() => null);
        toast.error(errData?.error || 'خطا در ثبت پیام');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    }
  };

  const handleResend = async (id: string) => {
    setSending(id);
    try {
      const res = await fetch(`/api/admin/bot-messages/${id}/send`, { method: 'POST' });
      if (res.ok) {
        toast.success('پیام مجدداً ارسال شد');
        fetchMessages();
      } else {
        const errData = await res.json().catch(() => null);
        toast.error(errData?.error || 'خطا در ارسال');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setSending(null);
    }
  };

  const handleSendSelected = async () => {
    if (selectedHistoryIds.size === 0) return;
    setSendingAll(true);
    let sent = 0;
    for (const id of selectedHistoryIds) {
      try {
        const res = await fetch(`/api/admin/bot-messages/${id}/send`, { method: 'POST' });
        if (res.ok) sent++;
      } catch {
        // continue
      }
    }
    setSendingAll(false);
    setSelectedHistoryIds(new Set());
    toast.success(`${new Intl.NumberFormat('fa-IR').format(sent)} پیام ارسال شد`);
    fetchMessages();
  };

  const pendingCount = messages.filter(m => m.status === 'PENDING').length;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg p-0 dialog-premium max-h-[85vh] flex flex-col" dir="rtl">
        <DialogHeader className="p-5 pb-0 shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center animate-float">
              <MessageSquare className="h-5 w-5 text-sky-600" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-base font-bold">{'ارسال پیام به کاربر'}</DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                {'ارسال پیام سفارشی برای کاربر از طریق ربات'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex items-center gap-1 px-5 pt-3 shrink-0">
          <button
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'compose'
                ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            )}
            onClick={() => setActiveTab('compose')}
          >
            <Send className="h-3.5 w-3.5" />
            {'ارسال پیام'}
          </button>
          <button
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'history'
                ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            )}
            onClick={() => setActiveTab('history')}
          >
            <Clock className="h-3.5 w-3.5" />
            {'تاریخچه پیام‌ها'}
            {pendingCount > 0 && (
              <Badge className="h-4 min-w-4 px-1 text-[9px] bg-amber-500 rounded-full">{pendingCount}</Badge>
            )}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {activeTab === 'compose' ? (
            <div className="p-5 space-y-4">
              {/* User Search */}
              <div className="space-y-1.5 relative">
                <label className="text-[11px] font-medium text-muted-foreground">{'جستجوی کاربر'}</label>
                <div className="relative">
                  <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="نام یا شناسه بله..."
                    value={userSearch}
                    onChange={(e) => handleUserSearchChange(e.target.value)}
                    className="pr-8 h-10 text-sm"
                  />
                  {showSuggestions && userSuggestions.length > 0 && (
                    <div className="absolute top-full mt-1 left-0 right-0 z-50 bg-popover border rounded-lg shadow-lg max-h-48 overflow-y-auto">
                      {userSuggestions.map((user) => (
                        <button
                          key={user.baleUserId}
                          className="w-full flex items-center gap-2 px-3 py-2.5 text-sm hover:bg-muted/50 transition-colors text-right"
                          onClick={() => selectUser(user)}
                        >
                          <User className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="font-medium">{user.fullName}</span>
                          <span className="text-xs text-muted-foreground font-mono" dir="ltr">{user.baleUserId}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* شناسه بله (دستی) */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-muted-foreground">{'شناسه بله'}</label>
                <Input
                  placeholder="مثال: 123456789"
                  value={baleUserId}
                  onChange={(e) => setBaleUserId(e.target.value)}
                  className="h-10 text-sm font-mono"
                  dir="ltr"
                />
              </div>

              {/* Message Text */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-muted-foreground">{'متن پیام'}</label>
                <textarea
                  ref={textareaRef}
                  placeholder="متن پیام خود را وارد کنید..."
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  rows={4}
                  className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-sky-500/50 transition-shadow"
                />
                <p className="text-[10px] text-muted-foreground text-left" dir="ltr">
                  {messageText.length} / 4096
                </p>
              </div>

              {/* File Attachment */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-muted-foreground">{'فایل پیوست (اختیاری)'}</label>
                {attachedFile ? (
                  <div className="flex items-center gap-2 p-2.5 rounded-lg border bg-muted/30">
                    <Paperclip className="h-4 w-4 text-sky-600 shrink-0" />
                    <span className="flex-1 text-xs font-medium truncate" dir="ltr">{attachedFile.name}</span>
                    <button
                      onClick={removeFile}
                      className="h-6 w-6 rounded-full flex items-center justify-center hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-colors"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="w-full flex items-center justify-center gap-2 p-3 rounded-lg border border-dashed text-sm text-muted-foreground hover:text-foreground hover:border-sky-300 hover:bg-sky-50/50 dark:hover:bg-sky-900/10 transition-all disabled:opacity-50"
                  >
                    {uploading ? (
                      <div className="h-4 w-4 border-2 border-sky-300 border-t-sky-600 rounded-full animate-spin" />
                    ) : (
                      <Upload className="h-4 w-4" />
                    )}
                    {uploading ? 'در حال آپلود...' : 'انتخاب فایل'}
                  </button>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <p className="text-[10px] text-muted-foreground">حداکثر ۲۰ مگابایت</p>
              </div>

              {/* Send Button */}
              <Button
                className="w-full h-11 bg-sky-600 hover:bg-sky-700 gap-2 text-sm font-medium"
                onClick={handleSend}
                disabled={!baleUserId.trim() || !messageText.trim() || sending !== null || uploading}
              >
                {sending ? (
                  <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Send className="h-4 w-4 ml-1" />
                )}
                {'ارسال پیام از طریق ربات'}
              </Button>
            </div>
          ) : (
            <div className="p-5">
              {selectedHistoryIds.size > 0 && (
                <div className="flex items-center justify-between mb-3 p-2.5 rounded-lg bg-sky-50 dark:bg-sky-900/20 border border-sky-200 dark:border-sky-800">
                  <span className="text-xs font-medium text-sky-700 dark:text-sky-300">
                    {new Intl.NumberFormat('fa-IR').format(selectedHistoryIds.size)} پیام انتخاب شده
                  </span>
                  <Button
                    size="sm"
                    className="h-8 text-xs bg-sky-600 hover:bg-sky-700"
                    onClick={handleSendSelected}
                    disabled={sendingAll}
                  >
                    {sendingAll ? (
                      <div className="h-3.5 w-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5 ml-1" />
                    )}
                    {'ارسال دسته‌ای'}
                  </Button>
                </div>
              )}

              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="animate-shimmer h-20 rounded-lg bg-muted" />
                  ))}
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <MessageSquare className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">{'پیامی ثبت نشده است'}</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {messages.map((msg) => {
                    const cfg = STATUS_CONFIG[msg.status] || STATUS_CONFIG.PENDING;
                    const StatusIcon = cfg.icon;
                    const isSelected = selectedHistoryIds.has(msg.id);
                    return (
                      <div
                        key={msg.id}
                        className={cn(
                          'rounded-lg border p-3 transition-all',
                          isSelected ? 'border-sky-300 bg-sky-50/50 dark:border-sky-700 dark:bg-sky-900/10' : 'border-border hover:border-border/80'
                        )}
                      >
                        <div className="flex items-start gap-2.5">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {
                              setSelectedHistoryIds(prev => {
                                const next = new Set(prev);
                                if (next.has(msg.id)) next.delete(msg.id);
                                else next.add(msg.id);
                                return next;
                              });
                            }}
                            className="mt-1 h-4 w-4 rounded border-muted-foreground/30 text-sky-600 focus:ring-sky-500 shrink-0"
                          />
                          <div className="flex-1 min-w-0 space-y-1.5">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="text-sm font-medium truncate">{msg.fullName || msg.baleUserId}</span>
                                <Badge className={cn('text-[9px] px-1.5 py-0 rounded-full', cfg.color)}>
                                  <StatusIcon className="h-2.5 w-2.5 ml-0.5" />
                                  {cfg.label}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-1 shrink-0">
                                {(msg.status === 'FAILED' || msg.status === 'PENDING') && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 w-7 p-0 text-sky-600 hover:text-sky-700 hover:bg-sky-50"
                                    onClick={() => handleResend(msg.id)}
                                    disabled={sending === msg.id}
                                  >
                                    {sending === msg.id ? (
                                      <div className="h-3.5 w-3.5 border-2 border-sky-300 border-t-sky-600 rounded-full animate-spin" />
                                    ) : (
                                      <Send className="h-3.5 w-3.5" />
                                    )}
                                  </Button>
                                )}
                              </div>
                            </div>
                            <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{msg.messageText}</p>
                            {msg.fileName && (
                              <div className="flex items-center gap-1.5 text-xs text-sky-600 dark:text-sky-400">
                                <Paperclip className="h-3 w-3" />
                                <span className="truncate" dir="ltr">{msg.fileName}</span>
                              </div>
                            )}
                            <p className="text-[10px] text-muted-foreground/60" dir="ltr">
                              {new Date(msg.createdAt).toLocaleString('fa-IR')}
                            </p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
