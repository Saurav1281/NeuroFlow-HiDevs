"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import axios from "axios";
import { 
  Send, 
  Split, 
  MessageSquare, 
  Info, 
  CheckCircle2, 
  XCircle, 
  ThumbsUp, 
  ThumbsDown,
  ChevronRight,
  Database,
  Search,
  Zap,
  Layout
} from "lucide-react";
import { cn } from "@/utils/cn";
import { useSSEStream } from "@/hooks/useSSEStream";
import { motion, AnimatePresence } from "framer-motion";

// Components (will implement in separate files or inline for simplicity in this large block if needed)
import { EvaluationGauge } from "@/components/playground/EvaluationGauge";
import { CitationChip } from "@/components/playground/CitationChip";
import { RetrievalInspector } from "@/components/playground/RetrievalInspector";

export default function PlaygroundPage() {
  const [query, setQuery] = useState("");
  const [selectedPipelineA, setSelectedPipelineA] = useState<string>("");
  const [selectedPipelineB, setSelectedPipelineB] = useState<string>("");
  const [isCompareMode, setIsCompareMode] = useState(false);
  const [showInspector, setShowInspector] = useState(false);
  
  const streamA = useSSEStream();
  const streamB = useSSEStream();

  // Fetch pipelines
  const { data: pipelines } = useQuery({
    queryKey: ["pipelines"],
    queryFn: async () => {
      const resp = await axios.get("/api/pipelines");
      return resp.data;
    }
  });

  useEffect(() => {
    if (pipelines?.length > 0) {
      if (!selectedPipelineA) setSelectedPipelineA(pipelines[0].id);
      if (!selectedPipelineB) setSelectedPipelineB(pipelines[1]?.id || pipelines[0].id);
    }
  }, [pipelines]);

  const handleRun = async () => {
    if (!query || !selectedPipelineA) return;

    // Start Stream A
    const respA = await axios.post("/api/query", {
      query,
      pipeline_id: selectedPipelineA,
      stream: true
    });
    streamA.startStream(respA.data.run_id);

    if (isCompareMode && selectedPipelineB) {
      // Start Stream B
      const respB = await axios.post("/api/query", {
        query,
        pipeline_id: selectedPipelineB,
        stream: true
      });
      streamB.startStream(respB.data.run_id);
    }
  };

  const rateMutation = useMutation({
    mutationFn: async ({ runId, rating }: { runId: string, rating: number }) => {
      await axios.patch(`/api/runs/${runId}/rating`, { rating });
    }
  });

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold tracking-tight mb-2">Query Playground</h2>
          <p className="text-zinc-400">Test and compare retrieval-augmented generation pipelines in real-time.</p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={() => setIsCompareMode(!isCompareMode)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-all border",
              isCompareMode ? "bg-blue-500/10 border-blue-500/30 text-blue-400" : "bg-white/5 border-white/10 text-zinc-400"
            )}
          >
            <Split className="w-4 h-4" />
            <span>Compare Mode</span>
          </button>
        </div>
      </div>

      {/* Input Section */}
      <div className="glass-card flex flex-col gap-4">
        <div className="flex gap-4">
          <div className="flex-1 space-y-2">
            <label className="text-xs font-bold uppercase tracking-widest text-zinc-500 px-1">Pipeline {isCompareMode ? "A" : ""}</label>
            <select 
              value={selectedPipelineA} 
              onChange={(e) => setSelectedPipelineA(e.target.value)}
              className="w-full input-field bg-[#0a0a0f]"
            >
              {pipelines?.map((p: any) => (
                <option key={p.id} value={p.id}>{p.name} (v{p.version}) - {p.avg_score.toFixed(2)}</option>
              ))}
            </select>
          </div>
          {isCompareMode && (
            <div className="flex-1 space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-zinc-500 px-1">Pipeline B</label>
              <select 
                value={selectedPipelineB} 
                onChange={(e) => setSelectedPipelineB(e.target.value)}
                className="w-full input-field bg-[#0a0a0f]"
              >
                {pipelines?.map((p: any) => (
                  <option key={p.id} value={p.id}>{p.name} (v{p.version})</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="relative">
          <textarea 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything about the connected knowledge base..."
            className="w-full input-field min-h-[120px] pr-20 resize-none"
          />
          <div className="absolute bottom-4 right-4 flex items-center gap-3">
            <span className="text-xs text-zinc-500 font-mono">{query.length} chars</span>
            <button 
              onClick={handleRun}
              disabled={!query || streamA.isStreaming}
              className="btn-primary disabled:opacity-50 disabled:grayscale flex items-center justify-center p-3 rounded-xl"
            >
              <Send className="w-5 h-5 text-white" />
            </button>
          </div>
        </div>
      </div>

      {/* Results Section */}
      <div className={cn(
        "grid gap-6",
        isCompareMode ? "grid-cols-2" : "grid-cols-1"
      )}>
        <ResponsePanel 
          stream={streamA} 
          title={isCompareMode ? "Pipeline A Output" : "Response"} 
          onRate={(rating) => streamA.runId && rateMutation.mutate({ runId: streamA.runId, rating })}
          showInspector={() => setShowInspector(true)}
        />
        {isCompareMode && (
          <ResponsePanel 
            stream={streamB} 
            title="Pipeline B Output"
            onRate={(rating) => streamB.runId && rateMutation.mutate({ runId: streamB.runId, rating })}
            showInspector={() => setShowInspector(true)}
          />
        )}
      </div>

      {/* Retrieval Inspector Modal */}
      <AnimatePresence>
        {showInspector && (
          <RetrievalInspector onClose={() => setShowInspector(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}

function ResponsePanel({ stream, title, onRate, showInspector }: { 
  stream: ReturnType<typeof useSSEStream>, 
  title: string,
  onRate: (rating: number) => void,
  showInspector: () => void
}) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card flex flex-col min-h-[400px]"
    >
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-bold text-lg flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          {title}
        </h3>
        {stream.status === "complete" && (
          <button 
            onClick={showInspector}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
          >
            <Layout className="w-4 h-4" />
            Visualize Pipeline
          </button>
        )}
      </div>

      {/* Sources Bar */}
      <AnimatePresence>
        {stream.sources.length > 0 && (
          <motion.div 
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-wrap gap-2 mb-4"
          >
            {stream.sources.map((s, idx) => (
              <div key={idx} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-zinc-300">
                <Database className="w-3 h-3 text-blue-400" />
                {s}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Answer Content */}
      <div className="flex-1 bg-white/5 rounded-xl p-6 border border-white/5 relative group">
        {!stream.data && stream.status === "retrieving" && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-zinc-500">
            <div className="w-12 h-12 rounded-full border-2 border-t-blue-500 border-white/5 animate-spin" />
            <p className="animate-pulse">Retrieving relevant context...</p>
          </div>
        )}
        
        <div className="prose prose-invert max-w-none text-zinc-200 leading-relaxed font-inter">
          {stream.data}
          {stream.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-1 bg-blue-500 animate-pulse align-middle" />
          )}
        </div>

        {/* Citations */}
        {stream.citations.length > 0 && (
          <div className="mt-8 pt-6 border-t border-white/10">
            <p className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-3">Supporting Evidence</p>
            <div className="flex flex-wrap gap-2">
              {stream.citations.map((c, i) => (
                <CitationChip key={i} citation={c} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Feedback & Evaluations */}
      <AnimatePresence>
        {stream.status === "complete" && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-6 space-y-6 overflow-hidden"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm text-zinc-400">Helpful response?</span>
                <div className="flex gap-1">
                  <button 
                    onClick={() => onRate(5)}
                    className="p-2 rounded-lg hover:bg-green-500/10 text-zinc-500 hover:text-green-500 transition-colors"
                  >
                    <ThumbsUp className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={() => onRate(1)}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-zinc-500 hover:text-red-500 transition-colors"
                  >
                    <ThumbsDown className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Evaluation Gauges (Mocked/Simulated based on metrics if available) */}
            <div className="grid grid-cols-4 gap-4">
              <EvaluationGauge label="Faithfulness" value={0.88} />
              <EvaluationGauge label="Recall" value={0.92} />
              <EvaluationGauge label="Relevance" value={0.85} />
              <EvaluationGauge label="Precision" value={0.78} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
