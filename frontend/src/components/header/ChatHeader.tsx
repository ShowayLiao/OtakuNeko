"use client";

import { Header } from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';

export default function ChatHeader() {
  const { primaryColor } = useAppTheme();

  return (
    <Header
      leftArea={
        <div className="flex items-center gap-3">
          <img 
            src="/Icon.png" 
            alt="OtakuNeko Logo" 
            className="h-8 w-8 object-contain" 
          />
          <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
            OtakuNeko
          </span>
        </div>
      }
    />
  );
}
