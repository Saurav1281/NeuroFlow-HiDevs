"use client";

import { useState } from "react";
import { Info, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/utils/cn";

export function CitationChip({ citation }: { citation: any }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button 
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/5 border border-blue-500/20 text-xs text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/40 transition-all group"
      >
        <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
        <span className="font-semibold tracking-wide">[{citation.index}]</span>
        <span className="max-w-[120px] truncate opacity-80 group-hover:opacity-100">{citation.source || "Snippet"}</span>
        <Info className="w-3 h-3 ml-1 text-blue-500/50 group-hover:text-blue-500" />
      </button>

      {/* Side Drawer */}
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
            />
            <motion.div 
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 20, stiffness: 100 }}
              className="fixed top-0 right-0 h-full w-[450px] bg-[#0a0a0f] border-l border-white/10 z-[101] shadow-2xl flex flex-col"
            >
              <div className="p-6 border-b border-white/10 flex items-center justify-between bg-white/5">
                <div>
                  <h4 className="text-lg font-bold">Citation Context</h4>
                  <p className="text-xs text-zinc-500 uppercase tracking-widest mt-1">Found in {citation.source || "Unknown Document"}</p>
                </div>
                <button 
                  onClick={() => setIsOpen(false)}
                  className="p-2 rounded-xl hover:bg-white/5 text-zinc-500 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Content */}
                <div className="p-4 rounded-xl bg-blue-500/5 border border-blue-500/10">
                  <p className="text-zinc-200 leading-relaxed font-inter italic">
                    "{citation.content || "Full chunk content not available for this citation mock."}"
                  </p>
                </div>

                {/* Metadata */}
                <div className="space-y-4">
                  <h5 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Metadata</h5>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/5">
                      <span className="text-[10px] text-zinc-500 block mb-1">Relevance Score</span>
                      <span className="font-mono text-sm text-blue-400">{(citation.score || 0.94).toFixed(4)}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/5">
                      <span className="text-[10px] text-zinc-500 block mb-1">Source Index</span>
                      <span className="font-mono text-sm text-blue-400">#{citation.index || 1}</span>
                    </div>
                  </div>
                </div>

                {/* Raw Document Link */}
                <div className="p-4 rounded-xl bg-white/5 border border-white/5 flex items-center justify-between group cursor-pointer hover:border-blue-500/30 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400">
                      <Info className="w-5 h-5" />
                    </div>
                    <div className="text-sm">
                      <p className="font-bold text-zinc-200">View Source File</p>
                      <p className="text-xs text-zinc-500">{citation.source || "source_file.pdf"}</p>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
