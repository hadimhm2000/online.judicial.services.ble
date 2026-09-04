'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Search, Filter, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  serviceFilter: string;
  onServiceFilterChange: (value: string) => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  searchRef?: React.RefObject<HTMLInputElement | null>;
  searchFocused?: boolean;
  onSearchFocus?: () => void;
  onSearchBlur?: () => void;
  onOpenCmdPalette?: () => void;
}

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

export default function FilterBar({
  search, onSearchChange, serviceFilter, onServiceFilterChange,
  showFilters, onToggleFilters,
  searchRef, searchFocused, onSearchFocus, onSearchBlur, onOpenCmdPalette,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative flex-1 min-w-0 sm:min-w-[200px] max-w-full sm:max-w-md">
        <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          ref={searchRef}
          placeholder="جستجو (نام، کد رهگیری، شناسه بله...)  /"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          onFocus={onSearchFocus}
          onBlur={onSearchBlur}
          className={cn(
            'pr-9 h-9 text-sm bg-background shadow-sm focus-ring-premium',
            searchFocused && 'animate-breathe-glow'
          )}
        />
        {onOpenCmdPalette && (
          <button
            onClick={onOpenCmdPalette}
            className="absolute left-2 top-1/2 -translate-y-1/2 kbd-shortcut px-1.5 py-0.5 text-[9px] font-mono cursor-pointer hover:bg-muted transition-colors"
            title="Ctrl+K"
          >
            Ctrl K
          </button>
        )}
      </div>
      <Select value={serviceFilter} onValueChange={onServiceFilterChange}>
        <SelectTrigger className="w-[140px] h-9 text-xs shadow-sm">
          <SelectValue placeholder="نوع خدمت" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">همه خدمات</SelectItem>
          {Object.entries(SERVICE_LABELS).map(([key, label]) => (
            <SelectItem key={key} value={key}>{label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant={showFilters ? 'default' : 'outline'}
        size="sm"
        className="h-9 gap-1.5 text-xs shadow-sm hover-lift-sm btn-press"
        onClick={onToggleFilters}
      >
        <Filter className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">فیلترها</span>
        <ChevronDown className={cn('h-3 w-3 transition-transform', showFilters && 'rotate-180')} />
      </Button>
    </div>
  );
}
