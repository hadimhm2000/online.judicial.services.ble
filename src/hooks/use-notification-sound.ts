'use client';

import { useEffect, useRef, useCallback, useState } from 'react';

type SoundType = 'success' | 'error' | 'warning' | 'info';

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || (window as unknown as Record<string, unknown>).webkitAudioContext) as AudioContext;
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

export function playNotificationSound(type: SoundType): void {
  const muted = typeof window !== 'undefined' && localStorage.getItem('admin-notification-muted') === 'true';
  if (muted) return;

  try {
    const ctx = getAudioContext();
    const vol = 0.15;
    const now = ctx.currentTime;

    if (type === 'success') {
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.value = 523.25;
      gain1.gain.setValueAtTime(vol, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc1.connect(gain1).connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.2);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.value = 659.25;
      gain2.gain.setValueAtTime(vol, now + 0.2);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
      osc2.connect(gain2).connect(ctx.destination);
      osc2.start(now + 0.2);
      osc2.stop(now + 0.4);
    } else if (type === 'error') {
      const softVol = 0.1;
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sawtooth';
      osc1.frequency.value = 659.25;
      gain1.gain.setValueAtTime(softVol, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc1.connect(gain1).connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.3);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sawtooth';
      osc2.frequency.value = 261.63;
      gain2.gain.setValueAtTime(softVol, now + 0.3);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
      osc2.connect(gain2).connect(ctx.destination);
      osc2.start(now + 0.3);
      osc2.stop(now + 0.6);
    } else if (type === 'warning') {
      for (let i = 0; i < 2; i++) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.value = 440;
        const start = now + i * 0.2;
        gain.gain.setValueAtTime(vol, start);
        gain.gain.exponentialRampToValueAtTime(0.001, start + 0.15);
        osc.connect(gain).connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 0.15);
      }
    } else {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 523.25;
      gain.gain.setValueAtTime(vol, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.1);
    }
  } catch {
    // Audio not supported
  }
}

export function useNotificationListener(
  failedCount: number,
  prevFailedCountRef: React.MutableRefObject<number>,
  readyToSendCount?: number,
  prevReadyToSendRef?: React.MutableRefObject<number>,
): void {
  useEffect(() => {
    if (failedCount > prevFailedCountRef.current) {
      playNotificationSound('error');
    }
    prevFailedCountRef.current = failedCount;
  }, [failedCount, prevFailedCountRef]);

  useEffect(() => {
    if (prevReadyToSendRef && readyToSendCount !== undefined) {
      if (readyToSendCount > prevReadyToSendRef.current) {
        playNotificationSound('warning');
      }
      prevReadyToSendRef.current = readyToSendCount;
    }
  }, [readyToSendCount, prevReadyToSendRef]);
}

export function useNotificationMuted(): [boolean, (v: boolean) => void] {
  const getStored = useCallback(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem('admin-notification-muted') === 'true';
  }, []);

  const [muted, setMutedState] = useState(false);

  useEffect(() => {
    setMutedState(getStored());
  }, [getStored]);

  const setMuted = useCallback((v: boolean) => {
    localStorage.setItem('admin-notification-muted', v ? 'true' : 'false');
    setMutedState(v);
  }, []);

  return [muted, setMuted];
}
