"use client";

import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { 
  Activity, 
  Search, 
  Filter, 
  ChevronDown, 
  ChevronUp, 
  Clock, 
  CheckCircle2, 
  AlertTriangle,
  Zap,
  Layout,
  MessageSquare
} from "lucide-react";
import { cn } from "@/utils/cn";
import { motion, AnimatePresence } from "framer-motion";

export default function EvaluationsPage() {
  const [filterQuery, setFilterQuery] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [selectedPipeline, setSelectedPipeline] = useState("all");
  const [evaluations, setEvaluations] = useState<any[]>([]);

  // Fetch initial evaluations
  const { data: initialEvals } = useQuery({
    queryKey: ["initial-evaluations"],
    queryFn: async () => {
      const resp = await axios.get("/api/pipelines"); // Fallback or wait for evaluaitons endpoint
      return []; // Mock for now or fetch from a history endpoint
    }
  });

  // SSE setup for real-time feed
  useEffect(() => {
    const eventSource = new EventSource("/api/evaluations/stream");
    
    eventSource.onmessage = (event) => {
      const newEval = JSON.parse(event.data);
      setEvaluations(prev => [newEval, ...prev].slice(0, 50)); // Keep last 50
    };

    return () => eventSource.close();
  }, []);

  const filteredEvals = evaluations.filter(e => {
    const matchesPipeline = selectedPipeline === "all" || e.pipeline_name === selectedPipeline;
    const matchesScore = e.overall_score >= minScore;
    const matchesQuery = e.query.toLowerCase().includes(filterQuery.toLowerCase());
    return matchesPipeline && matchesScore && matchesQuery;
  });

  const { data: pipelines } = useQuery({ queryKey: ["pipelines"], queryFn: async () => (await axios.get("/api/pipelines")).data });

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2 uppercase tracking-widest">Evaluation Feed</h2>
          <p className="text-zinc-400">Real-time observability into model performance and alignment.</p>
        </div>
        <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-bold">Live Stream Active</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="glass-card flex flex-wrap gap-4 items-center">
        <div className="relative flex-1 min-w-[300px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input 
            type="text" 
            placeholder="Search by query..."
            className="w-full input-field pl-10"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
          />
        </div>
        
        <select 
          className="input-field bg-[#0a0a0f] min-w-[200px]"
          value={selectedPipeline}
          onChange={(e) => setSelectedPipeline(e.target.value)}
        >
          <option value="all">All Pipelines</option>
          {pipelines?.map((p: any) => (
            <option key={p.id} value={p.name}>{p.name}</option>
          ))}
        </select>

        <div className="flex items-center gap-3 px-4">
          <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Min Score</span>
          <input 
            type="range" 
            min="0" max="1" step="0.1" 
            value={minScore}
            onChange={(e) => setMinScore(parseFloat(e.target.value))}
            className="w-32 accent-blue-500"
          />
          <span className="text-sm font-mono text-blue-400">{minScore.toFixed(1)}</span>
        </div>
      </div>

      {/* Feed */}
      <div className="space-y-4">
        <AnimatePresence initial={false}>
          {filteredEvals.length === 0 ? (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center py-20 text-zinc-600 gap-4"
            >
              <Activity className="w-12 h-12 opacity-20" />
              <p>Waiting for incoming evaluations...</p>
            </motion.div>
          ) : (
            filteredEvals.map((evaluation, idx) => (
              <EvaluationCard key={evaluation.run_id || idx} evaluation={evaluation} />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function EvaluationCard({ evaluation }: { evaluation: any }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const score = evaluation.overall_score || 0;
  const color = score > 0.8 ? "text-green-500" : score > 0.6 ? "text-yellow-500" : "text-red-500";
  const bg = score > 0.8 ? "bg-green-500/10" : score > 0.6 ? "bg-yellow-500/10" : "bg-red-500/10";

  return (
    <motion.div 
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="glass-card hover:border-white/20 transition-all p-0 overflow-hidden"
    >
      <div 
        className="p-6 cursor-pointer flex items-center justify-between"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-6 flex-1">
          <div className={cn("px-4 py-2 rounded-xl font-bold font-mono text-lg border border-white/5", bg, color)}>
            {(score * 100).toFixed(0)}%
          </div>
          <div className="space-y-1 flex-1">
            <h4 className="font-bold text-zinc-200 line-clamp-1">{evaluation.query}</h4>
            <div className="flex items-center gap-4">
              <span className="text-xs text-zinc-500 flex items-center gap-1">
                <Zap className="w-3 h-3 text-blue-500" />
                {evaluation.pipeline_name}
              </span>
              <span className="text-xs text-zinc-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {evaluation.timestamp === "now" ? "Just now" : evaluation.timestamp}
              </span>
            </div>
          </div>
        </div>

        <div className="flex gap-4 px-8">
          <MetricMini label="F" value={evaluation.faithfulness} />
          <MetricMini label="R" value={evaluation.relevance} />
          <MetricMini label="P" value={evaluation.precision} />
          <MetricMini label="C" value={evaluation.recall} />
        </div>

        <button className="p-2 rounded-lg hover:bg-white/5 text-zinc-500">
          {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div 
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="border-t border-white/5 bg-white/[0.02]"
          >
            <div className="p-8 grid grid-cols-2 gap-8">
              <div className="space-y-4">
                <div>
                  <h5 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">User Query</h5>
                  <p className="text-sm leading-relaxed p-4 rounded-xl bg-white/5 border border-white/5">{evaluation.query}</p>
                </div>
                <div>
                  <h5 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Model Response</h5>
                  <p className="text-sm leading-relaxed p-4 rounded-xl bg-white/5 border border-white/5 text-zinc-400">
                    {evaluation.response || "Content placeholder for live trace..."}
                  </p>
                </div>
              </div>
              <div className="space-y-6">
                <h5 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Detailed Metrics</h5>
                <div className="space-y-4">
                  <MetricBar label="Faithfulness" value={evaluation.faithfulness} color="bg-blue-500" />
                  <MetricBar label="Answer Relevance" value={evaluation.relevance} color="bg-cyan-500" />
                  <MetricBar label="Context Precision" value={evaluation.precision} color="bg-indigo-500" />
                  <MetricBar label="Context Recall" value={evaluation.recall} color="bg-purple-500" />
                </div>
                <div className="pt-4 flex gap-4">
                  <button className="flex-1 py-3 rounded-xl bg-white/5 border border-white/10 text-xs font-bold hover:bg-white/10 transition-all flex items-center justify-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Open in Playground
                  </button>
                  <button className="flex-1 py-3 rounded-xl bg-white/5 border border-white/10 text-xs font-bold hover:bg-white/10 transition-all flex items-center justify-center gap-2">
                    <Layout className="w-4 h-4" />
                    View Retrieval Trace
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function MetricMini({ label, value }: { label: string, value: number }) {
  const color = value > 0.8 ? "text-blue-400" : value > 0.6 ? "text-zinc-400" : "text-red-400";
  return (
    <div className="flex flex-col items-center">
      <span className="text-[9px] font-bold text-zinc-600 mb-1">{label}</span>
      <span className={cn("text-xs font-mono font-bold", color)}>{(value || 0).toFixed(2)}</span>
    </div>
  );
}

function MetricBar({ label, value, color }: { label: string, value: number, color: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span className="font-mono text-zinc-200">{((value || 0) * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${(value || 0) * 100}%` }}
          className={cn("h-full rounded-full", color)}
        />
      </div>
    </div>
  );
}
