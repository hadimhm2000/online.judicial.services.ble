'use client';

import { useEffect, useMemo, useState } from 'react';

interface Props {
  active: boolean;
  onComplete: () => void;
}

const COLORS = ['#10b981', '#0ea5e9', '#f59e0b', '#f43f5e', '#8b5cf6'];

interface Particle {
  id: number;
  color: string;
  size: number;
  x: number;
  y: number;
  rotation: number;
  dx: number;
  dy: number;
  delay: number;
}

export default function ConfettiAnimation({ active, onComplete }: Props) {
  const [visible, setVisible] = useState(false);

  const particles = useMemo<Particle[]>(() => {
    const arr: Particle[] = [];
    for (let i = 0; i < 40; i++) {
      const angle = (Math.random() * Math.PI * 2);
      const velocity = 80 + Math.random() * 180;
      arr.push({
        id: i,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        size: 4 + Math.random() * 4,
        x: 50,
        y: 8,
        rotation: Math.random() * 360,
        dx: Math.cos(angle) * velocity,
        dy: Math.sin(angle) * velocity - 60,
        delay: Math.random() * 0.15,
      });
    }
    return arr;
  }, []);

  useEffect(() => {
    if (!active) return;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
      onComplete();
    }, 1500);
    return () => clearTimeout(timer);
  }, [active, onComplete]);

  if (!visible) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-[9998] overflow-hidden">
      {particles.map((p) => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: `${p.size}px`,
            height: `${p.size}px`,
            borderRadius: p.id % 3 === 0 ? '50%' : '2px',
            backgroundColor: p.color,
            opacity: 1,
            transform: `rotate(${p.rotation}deg)`,
            animation: `confetti-burst ${1 + p.delay * 2}s ease-out ${p.delay}s forwards`,
            '--confetti-dx': `${p.dx}px`,
            '--confetti-dy': `${p.dy}px`,
          } as React.CSSProperties}
        />
      ))}
      <style>{`
        @keyframes confetti-burst {
          0% {
            opacity: 1;
            transform: rotate(0deg) translate(0, 0) scale(1);
          }
          40% {
            opacity: 1;
            transform: rotate(180deg) translate(var(--confetti-dx), var(--confetti-dy)) scale(1);
          }
          100% {
            opacity: 0;
            transform: rotate(540deg) translate(var(--confetti-dx), calc(var(--confetti-dy) + 120px)) scale(0.3);
          }
        }
      `}</style>
    </div>
  );
}
