'use client';

import React from 'react';
import { cn } from '@/lib/utils';

interface TabConfig {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface MobileNavProps {
  tabs: TabConfig[];
  activeTab: string;
  onTabChange: (key: string) => void;
}

export default function MobileNav({ tabs, activeTab, onTabChange }: MobileNavProps) {
  if (tabs.length === 0) return null;

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 sm:hidden mobile-nav-premium print:hidden safe-bottom">
      <div className="flex items-center justify-around py-1.5 px-1">
        {tabs.slice(0, 5).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => onTabChange(tab.key)}
              className={cn(
                'flex flex-col items-center gap-0.5 py-1 px-2 rounded-lg transition-all min-w-[48px] relative',
                isActive
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="text-[9px] font-medium leading-tight">{tab.label}</span>
              {isActive && (
                <div className="absolute -top-1 inset-x-2 h-0.5 rounded-full bg-gradient-to-l from-primary/80 via-primary to-primary/80" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
