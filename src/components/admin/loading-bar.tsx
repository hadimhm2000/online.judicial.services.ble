'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

interface LoadingBarProps {
  loading: boolean;
  delay?: number;
}

export default function LoadingBar({ loading, delay = 200 }: LoadingBarProps) {
  const [visible, setVisible] = useState(false);
  const [hiding, setHiding] = useState(false);
  const prevLoadingRef = useRef(loading);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  useEffect(() => {
    clearAllTimers();

    if (loading) {
      const t = setTimeout(() => {
        setVisible(true);
        setHiding(false);
      }, delay);
      timersRef.current.push(t);
    } else if (prevLoadingRef.current) {
      const t1 = setTimeout(() => {
        setHiding(true);
      }, 0);
      const t2 = setTimeout(() => {
        setVisible(false);
        setHiding(false);
      }, 400);
      timersRef.current.push(t1, t2);
    }

    prevLoadingRef.current = loading;
    return clearAllTimers;
  }, [loading, delay, clearAllTimers]);

  if (!visible && !hiding) return null;

  return (
    <div
      className={
        'loading-bar' +
        (hiding ? ' !opacity-0' : '')
      }
      style={{
        boxShadow: visible && !hiding ? '0 1px 4px oklch(0.65 0.22 155 / 30%)' : 'none',
        opacity: hiding ? 0 : 1,
        transition: 'opacity 400ms ease-out',
      }}
      aria-hidden="true"
    />
  );
}
