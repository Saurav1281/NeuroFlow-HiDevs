"use client";

import { motion } from "framer-motion";

export function EvaluationGauge({ label, value }: { label: string, value: number }) {
  const percentage = value * 100;
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-2 p-3 rounded-xl bg-white/5 border border-white/5 transition-colors hover:bg-white/10">
      <div className="relative w-16 h-16">
        {/* Background circle */}
        <svg className="w-full h-full transform -rotate-90">
          <circle
            cx="32"
            cy="32"
            r={radius}
            fill="transparent"
            stroke="currentColor"
            strokeWidth="4"
            className="text-white/10"
          />
          {/* Progress circle */}
          <motion.circle
            cx="32"
            cy="32"
            r={radius}
            fill="transparent"
            stroke="url(#blue-gradient)"
            strokeWidth="4"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.5, ease: "easeOut", delay: 0.2 }}
            strokeLinecap="round"
          />
          <defs>
            <linearGradient id="blue-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#06b6d4" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-bold text-blue-400">{Math.round(percentage)}%</span>
        </div>
      </div>
      <span className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">{label}</span>
    </div>
  );
}
