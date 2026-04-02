"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { 
  Plus, 
  Zap, 
  History, 
  BarChart3, 
  ChevronRight, 
  Search,
  MoreVertical,
  Activity,
  AlertCircle
} from "lucide-react";
import { cn } from "@/utils/cn";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, LineChart, Line } from "recharts";
import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function PipelinesPage() {
  const [search, setSearch] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedPipeline, setSelectedPipeline] = useState<any | null>(null);

  const { data: pipelines, isLoading } = useQuery({
    queryKey: ["pipelines"],
    queryFn: async () => {
      const resp = await axios.get("/api/pipelines");
      return resp.data;
    }
  });

  const filteredPipelines = pipelines?.filter((p: any) => 
    p.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2 uppercase tracking-widest">Pipeline Manager</h2>
          <p className="text-zinc-400">Configure, monitor and optimize your RAG architectures.</p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-5 h-5" />
          <span>Create Pipeline</span>
        </button>
      </div>

      {/* Filters & Search */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <input 
            type="text" 
            placeholder="Search pipelines..."
            className="w-full input-field pl-12"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <AnimatePresence>
          {filteredPipelines?.map((p: any) => (
            <PipelineCard 
              key={p.id} 
              pipeline={p} 
              onClick={() => setSelectedPipeline(p)} 
            />
          ))}
        </AnimatePresence>
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isModalOpen && (
          <CreatePipelineModal onClose={() => setIsModalOpen(false)} />
        )}
      </AnimatePresence>

      {/* Analytics Drawer */}
      <AnimatePresence>
        {selectedPipeline && (
          <AnalyticsDrawer 
            pipeline={selectedPipeline} 
            onClose={() => setSelectedPipeline(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function PipelineCard({ pipeline, onClick }: { pipeline: any, onClick: () => void }) {
  const statusColor = pipeline.avg_score > 0.8 ? "text-green-500" : pipeline.avg_score > 0.6 ? "text-yellow-500" : "text-red-500";
  const statusBg = pipeline.avg_score > 0.8 ? "bg-green-500/10" : pipeline.avg_score > 0.6 ? "bg-yellow-500/10" : "bg-red-500/10";

  return (
    <motion.div 
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -5 }}
      onClick={onClick}
      className="glass-card cursor-pointer group flex flex-col gap-6"
    >
      <div className="flex justify-between items-start">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h4 className="font-bold text-lg">{pipeline.name}</h4>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-zinc-500">v{pipeline.version}</span>
          </div>
          <p className="text-sm text-zinc-500 line-clamp-1">{pipeline.description || "Production RAG Pipeline"}</p>
        </div>
        <button className="p-2 rounded-lg hover:bg-white/5 text-zinc-500">
          <MoreVertical className="w-5 h-5" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <p className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider">Avg Score</p>
          <div className="flex items-center gap-2">
            <span className={cn("text-xl font-bold font-mono", statusColor)}>{pipeline.avg_score.toFixed(2)}</span>
            <div className={cn("w-2 h-2 rounded-full", statusColor.replace('text', 'bg'))} />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider">Queries (7d)</p>
          <span className="text-xl font-bold font-mono">{pipeline.run_count}</span>
        </div>
      </div>

      {/* Sparkline (Mocked) */}
      <div className="h-16 w-full opacity-50 group-hover:opacity-100 transition-opacity">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={[{v:10}, {v:15}, {v:12}, {v:20}, {v:18}, {v:25}, {v:22}]}>
            <Line type="monotone" dataKey="v" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center justify-between pt-4 border-t border-white/5">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <Activity className="w-4 h-4" />
          <span>Active</span>
        </div>
        <ChevronRight className="w-5 h-5 text-zinc-600 group-hover:text-blue-500 group-hover:translate-x-1 transition-all" />
      </div>
    </motion.div>
  );
}

function CreatePipelineModal({ onClose }: { onClose: () => void }) {
  const [config, setConfig] = useState(JSON.stringify({
    name: "new-pipeline",
    description: "Standard RAG pipeline",
    ingestion: {
      chunking_strategy: "hierarchical",
      chunk_size_tokens: 512,
      chunk_overlap_tokens: 64,
      extractors_enabled: ["pdf", "docx"]
    },
    retrieval: {
      dense_k: 20,
      sparse_k: 20,
      reranker: "cross-encoder",
      top_k_after_rerank: 5,
      query_expansion: true,
      metadata_filters_enabled: true
    },
    generation: {
      model_routing: { strategy: "cost_optimized" },
      max_context_tokens: 4096,
      temperature: 0.2,
      system_prompt_variant: "precise"
    },
    evaluation: {
      auto_evaluate: true,
      training_threshold: 0.8
    }
  }, null, 2));

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[200] flex items-center justify-center p-8">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-4xl h-[80vh] bg-[#0a0a0f] border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="p-6 border-b border-white/10 flex items-center justify-between">
          <h4 className="text-xl font-bold flex items-center gap-3">
            <Zap className="w-5 h-5 text-blue-500" />
            Config Editor
          </h4>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-zinc-500">
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-1 min-h-0 bg-black">
          <MonacoEditor
            height="100%"
            language="json"
            theme="vs-dark"
            value={config}
            onChange={(v) => setConfig(v || "")}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>

        <div className="p-6 border-t border-white/10 bg-white/5 flex justify-between items-center">
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <AlertCircle className="w-4 h-4" />
            <span>Validating against PipelineConfig schema...</span>
          </div>
          <div className="flex gap-4">
            <button onClick={onClose} className="px-6 py-2 rounded-xl text-zinc-400 hover:text-white transition-colors">Cancel</button>
            <button className="btn-primary px-8">Create Version</button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function AnalyticsDrawer({ pipeline, onClose }: { pipeline: any, onClose: () => void }) {
  const radarData = [
    { subject: 'Faithfulness', A: 85, fullMark: 100 },
    { subject: 'Relevance', A: 92, fullMark: 100 },
    { subject: 'Precision', A: 78, fullMark: 100 },
    { subject: 'Recall', A: 88, fullMark: 100 },
    { subject: 'Density', A: 65, fullMark: 100 },
  ];

  const latencyData = [
    { name: 'P50', ms: 1200 },
    { name: 'P95', ms: 2400 },
    { name: 'P99', ms: 3800 },
  ];

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
        className="fixed top-0 right-0 h-full w-[600px] bg-[#0a0a0f] border-l border-white/10 z-[201] shadow-2xl flex flex-col"
      >
        <div className="p-8 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-2xl bg-blue-500/10 text-blue-400">
              <Zap className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-2xl font-bold">{pipeline.name}</h4>
              <p className="text-sm text-zinc-500 uppercase tracking-widest font-semibold mt-1">Analytics Dashboard</p>
            </div>
          </div>
          <button onClick={onClose} className="p-3 rounded-xl hover:bg-white/5 text-zinc-500">
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-8 space-y-8">
          {/* Performance Radar */}
          <div className="glass-card bg-white/5 rounded-2xl">
            <h5 className="text-sm font-bold text-zinc-400 uppercase tracking-widest mb-6">Quality Radar</h5>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                  <PolarGrid stroke="#333" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#666', fontSize: 10 }} />
                  <Radar name="Pipeline" dataKey="A" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.6} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="glass-card bg-white/5">
              <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-4">Latency Distribution</h5>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={latencyData}>
                    <Bar dataKey="ms" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    <XAxis dataKey="name" tick={{ fill: '#666', fontSize: 10 }} axisLine={false} tickLine={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="glass-card bg-white/5">
              <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-4">Cost Trend (30d)</h5>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={[{v:10}, {v:12}, {v:11}, {v:14}, {v:13}]}>
                    <Line type="step" dataKey="v" stroke="#3b82f6" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <h5 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Recent Failures</h5>
            <div className="space-y-3">
              {[1, 2].map(i => (
                <div key={i} className="p-4 rounded-xl border border-red-500/20 bg-red-500/5 flex gap-4">
                  <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center text-red-500 shrink-0">
                    <AlertCircle className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-red-400">Context Overflow Error</p>
                    <p className="text-xs text-zinc-500 mt-1">Run ID: 4a2f-91b3 | 2 minutes ago</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </>
  );
}

import { X } from "lucide-react";
