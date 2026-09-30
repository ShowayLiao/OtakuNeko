"use client";

import { CheckCircle2, Loader2, Clock, BrainCircuit } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';

export interface ProgressStep {
  name: string;
  done: boolean;
  durationMs: number;
}

interface ProgressPanelProps {
  plan: string;
  steps: ProgressStep[];
}

export default function ProgressPanel({ plan, steps }: ProgressPanelProps) {
  const { isDarkMode } = useAppTheme();

  return (
    <div
      style={{
        marginBottom: 12,
        padding: 12,
        borderRadius: 10,
        background: isDarkMode ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)',
        border: `1px solid ${isDarkMode ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.12)'}`,
      }}
    >
      {plan && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            marginBottom: steps.length > 0 ? 10 : 0,
            fontSize: 13,
            fontWeight: 500,
            color: isDarkMode ? '#93c5fd' : '#3b82f6',
          }}
        >
          <BrainCircuit size={16} style={{ marginTop: 1, flexShrink: 0 }} />
          <span>{plan.length > 120 ? plan.slice(0, 120) + '...' : plan}</span>
        </div>
      )}

      {steps.map((step, i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '4px 0',
            fontSize: 13,
            color: step.done
              ? isDarkMode ? '#86efac' : '#15803d'
              : isDarkMode ? '#fbbf24' : '#d97706',
          }}
        >
          {step.done ? (
            <CheckCircle2 size={16} />
          ) : (
            <Loader2 size={16} className="animate-spin" />
          )}
          <span style={{ flex: 1 }}>{step.name}</span>
          {step.durationMs > 0 && (
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                fontSize: 11,
                color: isDarkMode ? '#9ca3af' : '#6b7280',
              }}
            >
              <Clock size={11} />
              {(step.durationMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      ))}

      {steps.length === 0 && !plan && null}
    </div>
  );
}
