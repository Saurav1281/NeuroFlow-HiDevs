"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { 
  FileText, 
  Upload, 
  Search, 
  MoreVertical, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  FileCode,
  Globe,
  Database,
  Info,
  ChevronRight,
  ShieldCheck,
  Zap,
  Layers,
  Sparkle
} from "lucide-react";
import { cn } from "@/utils/cn";
import { motion, AnimatePresence } from "framer-motion";

export default function DocumentsPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const queryClient = useQueryClient();

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: async () => (await axios.get("/api/documents")).data
  });

  const uploadMutation = useMutation({
    mutationFn: async (files: FileList) => {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
      }
      return await axios.post("/api/documents", formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  });

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      uploadMutation.mutate(e.dataTransfer.files);
    }
  }, []);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2 uppercase tracking-widest">Knowledge Base</h2>
          <p className="text-zinc-400">Manage and ingest documents into your RAG vector space.</p>
        </div>
        <div className="flex gap-4">
          <div className="glass-card py-2 px-4 flex items-center gap-3 bg-blue-500/5">
            <Database className="w-5 h-5 text-blue-500" />
            <div className="text-xs">
              <p className="font-bold text-zinc-300">{documents?.length || 0} Documents</p>
              <p className="text-zinc-500 font-mono">1.4M Tokens Total</p>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Zone */}
      <div 
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={cn(
          "relative group cursor-pointer transition-all duration-500",
          "border-2 border-dashed rounded-3xl p-12 flex flex-col items-center justify-center gap-4 bg-[#0a0a0f]",
          isDragging ? "border-blue-500 bg-blue-500/5 scale-[0.99]" : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
        )}
      >
        <div className={cn(
          "w-20 h-20 rounded-2xl premium-gradient flex items-center justify-center shadow-2xl transition-transform duration-500",
          isDragging ? "scale-110 rotate-12" : "group-hover:scale-105"
        )}>
          <Upload className="w-8 h-8 text-white" />
        </div>
        <div className="text-center space-y-2">
          <h4 className="text-xl font-bold">Drag and drop files here</h4>
          <p className="text-zinc-500">Support for PDF, DOCX, CSV, TXT up to 50MB</p>
        </div>
        
        {uploadMutation.isPending && (
          <div className="absolute inset-0 bg-[#0a0a0f]/80 backdrop-blur-sm flex flex-col items-center justify-center gap-6 z-10 rounded-3xl">
            <div className="w-64 h-2 bg-white/10 rounded-full overflow-hidden">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: "100%" }}
                transition={{ duration: 2, repeat: Infinity }}
                className="h-full premium-gradient"
              />
            </div>
            <p className="text-blue-400 font-bold animate-pulse">Ingesting and chunking documents...</p>
          </div>
        )}
      </div>

      {/* Document Table */}
      <div className="glass-card p-0 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-white/5 text-[10px] uppercase tracking-widest font-bold text-zinc-500 border-b border-white/5">
            <tr>
              <th className="px-6 py-4">Filename</th>
              <th className="px-6 py-4">Status</th>
              <th className="px-6 py-4">Type</th>
              <th className="px-6 py-4">Chunks</th>
              <th className="px-6 py-4">Timestamp</th>
              <th className="px-6 py-4"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {documents?.map((doc: any) => (
              <tr 
                key={doc.id} 
                onClick={() => setSelectedDoc(doc)}
                className="group hover:bg-white/[0.02] cursor-pointer transition-colors"
              >
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <FileIcon type={doc.type} />
                    <span className="font-bold text-sm text-zinc-200 group-hover:text-white transition-colors">{doc.filename}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <StatusBadge status={doc.status} />
                </td>
                <td className="px-6 py-4 text-xs text-zinc-500 uppercase font-mono">{doc.type}</td>
                <td className="px-6 py-4 text-sm font-mono text-zinc-400">{doc.chunk_count || 0}</td>
                <td className="px-6 py-4 text-xs text-zinc-600 font-mono">
                  {new Date(doc.created_at).toLocaleDateString()}
                </td>
                <td className="px-6 py-4 text-right">
                  <button className="p-2 rounded-lg hover:bg-white/5 text-zinc-600 group-hover:text-zinc-400 transition-colors">
                    <MoreVertical className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Doc Detail Drawer */}
      <AnimatePresence>
        {selectedDoc && (
          <DocumentDetailDrawer 
            doc={selectedDoc} 
            onClose={() => setSelectedDoc(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function FileIcon({ type }: { type: string }) {
  const iconProps = "w-5 h-5";
  if (type === 'pdf') return <FileText className={cn(iconProps, "text-red-400")} />;
  if (type === 'url') return <Globe className={cn(iconProps, "text-blue-400")} />;
  if (type === 'code') return <FileCode className={cn(iconProps, "text-green-400")} />;
  return <FileText className={cn(iconProps, "text-zinc-400")} />;
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'processing') return (
    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/5 border border-blue-500/20 text-[10px] font-bold text-blue-400 uppercase tracking-widest">
      <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse-blue" />
      Ingesting
    </div>
  );
  return (
    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/5 border border-green-500/20 text-[10px] font-bold text-green-500 uppercase tracking-widest">
      <CheckCircle2 className="w-3 h-3" />
      Indexed
    </div>
  );
}

function DocumentDetailDrawer({ doc, onClose }: { doc: any, onClose: () => void }) {
  const { data: chunks, isLoading } = useQuery({
    queryKey: ["chunks", doc.id],
    queryFn: async () => (await axios.get(`/api/documents/${doc.id}/chunks`)).data
  });

  const [highlightedChunks, setHighlightedChunks] = useState<string[]>([]);
  
  const searchSimilar = useMutation({
    mutationFn: async (chunkId: string) => (await axios.get(`/api/documents/chunks/search?chunk_id=${chunkId}&limit=5`)).data,
    onSuccess: (data) => {
      setHighlightedChunks(data.map((c: any) => c.id));
      // Scroll to first highlighted? Or just visual feedback
    }
  });

  return (
    <>
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[200]"
      />
      <motion.div 
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 120 }}
        className="fixed top-0 right-0 h-full w-[800px] bg-[#0a0a0f] border-l border-white/10 z-[201] shadow-2xl flex flex-col"
      >
        <div className="p-8 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-2xl bg-white/5 text-zinc-400">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-2xl font-bold">{doc.filename}</h4>
              <p className="text-xs text-zinc-500 uppercase tracking-widest font-bold mt-1">
                {doc.chunk_count || 0} Chunks · {doc.type} Source
              </p>
            </div>
          </div>
          <div className="flex gap-4">
            <button className="text-xs font-bold text-blue-400 hover:text-blue-300 transition-colors uppercase tracking-widest">Full Re-index</button>
            <button onClick={onClose} className="p-2 rounded-xl hover:bg-white/5 text-zinc-500"><X className="w-6 h-6" /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-40 gap-4 text-zinc-500 animate-pulse">
              <Layers className="w-8 h-8 animate-spin" />
              <span>Loading document shards...</span>
            </div>
          ) : (
            chunks?.map((chunk: any) => (
              <div 
                key={chunk.id}
                className={cn(
                  "p-6 rounded-2xl border transition-all duration-300 relative group",
                  highlightedChunks.includes(chunk.id) 
                    ? "bg-blue-500/10 border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)] ring-1 ring-blue-500/50" 
                    : "bg-white/5 border-white/5 hover:border-white/10"
                )}
              >
                {highlightedChunks.includes(chunk.id) && (
                  <div className="absolute -top-3 left-6 px-3 py-1 rounded-full bg-blue-500 text-white text-[10px] font-bold uppercase tracking-widest shadow-lg flex items-center gap-2">
                    <Sparkle className="w-3 h-3" />
                    Highly Similar
                  </div>
                )}
                <div className="flex justify-between items-start mb-3">
                  <span className="text-[10px] font-bold text-zinc-500 font-mono uppercase tracking-widest">Chunk #{chunk.index} · {chunk.tokens} Tokens</span>
                  <button 
                    onClick={() => searchSimilar.mutate(chunk.id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-bold text-white shadow-xl"
                  >
                    <Search className="w-3.5 h-3.5" />
                    Find Similar
                  </button>
                </div>
                <p className="text-sm leading-relaxed text-zinc-300 font-inter font-light">
                  {chunk.content}
                </p>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </>
  );
}

import { X } from "lucide-react";
