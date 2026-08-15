'use client';

import React, { useEffect, useCallback } from 'react';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command';
import {
  RefreshCw, Search, Filter, FileSpreadsheet, Printer,
  LayoutDashboard, FileCheck2, FileWarning, CreditCard, Send,
  AlertTriangle, XCircle, ListChecks, Activity, Sun, Moon,
} from 'lucide-react';

type CommandAction = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut?: string;
  group: string;
  onSelect: () => void;
};

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: CommandAction[];
}

export default function CommandPalette({ open, onOpenChange, actions }: CommandPaletteProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      onOpenChange(!open);
    }
    if (e.key === 'Escape' && open) {
      onOpenChange(false);
    }
  }, [open, onOpenChange]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const grouped = actions.reduce<Record<string, CommandAction[]>>((acc, action) => {
    if (!acc[action.group]) acc[action.group] = [];
    acc[action.group].push(action);
    return acc;
  }, {});

  const groupNames = Object.keys(grouped);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder='جستجوی دستور...'
        className="text-right focus-ring-premium"
      />
      <CommandList className="scrollbar-premium">
        <CommandEmpty>دستوری یافت نشد</CommandEmpty>
        {groupNames.map((group, gi) => (
          <React.Fragment key={group}>
            {gi > 0 && <CommandSeparator />}
            <CommandGroup heading={group}>
              {grouped[group].map((action) => {
                const Icon = action.icon;
                return (
                  <CommandItem
                    key={action.id}
                    onSelect={() => {
                      action.onSelect();
                      onOpenChange(false);
                    }}
                    className="gap-3 px-3 py-2.5"
                  >
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1">{action.label}</span>
                    {action.shortcut && (
                      <CommandShortcut className="kbd-shortcut px-1.5 py-0.5 rounded border bg-muted/50 text-[9px] font-mono">
                        {action.shortcut}
                      </CommandShortcut>
                    )}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </React.Fragment>
        ))}
      </CommandList>
    </CommandDialog>
  );
}

export type { CommandAction };
