"use client";

import { useState, useCallback, useMemo } from "react";
import { 
  ReactFlow, 
  MiniMap, 
  Controls, 
  Background, 
  useNodesState, 
  useEdgesState, 
  addEdge,
  MarkerType,
  Handle,
  Position
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Search, Zap, Filter, Layers, Database } from "lucide-react";
import { motion } from "framer-motion";

const CustomNode = ({ data, selected }: any) => (
  <div className={`px-4 py-3 rounded-xl border-2 transition-all duration-300 ${
    selected ? "border-blue-500 bg-blue-500/10 shadow-[0_0_20px_rgba(59,130,246,0.2)]" : "border-white/10 bg-[#0a0a0f]"
  }`}>
    <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-blue-500" />
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${data.color || "bg-blue-500/10 text-blue-400"}`}>
        <data.icon className="w-4 h-4" />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">{data.type}</p>
        <p className="text-sm font-bold text-white">{data.label}</p>
      </div>
    </div>
    {data.stats && (
      <div className="mt-2 pt-2 border-t border-white/5 flex gap-3">
        {Object.entries(data.stats).map(([k, v]: any) => (
          <div key={k}>
            <p className="text-[8px] uppercase text-zinc-600 font-bold">{k}</p>
            <p className="text-xs font-mono text-zinc-400">{v}</p>
          </div>
        ))}
      </div>
    )}
    <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-blue-500" />
  </div>
);

const nodeTypes = {
  custom: CustomNode,
};

export function RetrievalInspector({ onClose }: { onClose: () => void }) {
  const initialNodes = [
    { 
      id: "query", 
      type: "custom", 
      position: { x: 250, y: 0 }, 
      data: { label: "User Query", type: "Input", icon: Search, color: "bg-purple-500/10 text-purple-400" } 
    },
    { 
      id: "dense", 
      type: "custom", 
      position: { x: 0, y: 150 }, 
      data: { label: "Dense Retrieval", type: "Vector Search", icon: Zap, stats: { top_k: 50, score_min: 0.82 } } 
    },
    { 
      id: "sparse", 
      type: "custom", 
      position: { x: 250, y: 150 }, 
      data: { label: "Sparse Retrieval", type: "BM25 Search", icon: Filter, stats: { top_k: 50, avg_idf: 4.2 } } 
    },
    { 
      id: "hyde", 
      type: "custom", 
      position: { x: 500, y: 150 }, 
      data: { label: "HyDE Expansion", type: "Query Expansion", icon: Layers, stats: { variants: 3, strategy: "hypothetical" } } 
    },
    { 
      id: "fusion", 
      type: "custom", 
      position: { x: 250, y: 300 }, 
      data: { label: "RRF Fusion", type: "Rank Reciprocal Fusion", icon: Database, stats: { candidates: 150, k_constant: 60 } } 
    },
    { 
      id: "reranker", 
      type: "custom", 
      position: { x: 250, y: 450 }, 
      data: { label: "Cross-Encoder Rerank", type: "Reranker", icon: Zap, color: "bg-orange-500/10 text-orange-400", stats: { top_n: 10, avg_score: 0.94 } } 
    },
    { 
      id: "output", 
      type: "custom", 
      position: { x: 250, y: 600 }, 
      data: { label: "Final Context", type: "Output", icon: Layers, color: "bg-green-500/10 text-green-400", stats: { tokens: 1420, chunks: 5 } } 
    },
  ];

  const initialEdges = [
    { id: "e1", source: "query", target: "dense", animated: true },
    { id: "e2", source: "query", target: "sparse", animated: true },
    { id: "e3", source: "query", target: "hyde", animated: true },
    { id: "e4", source: "dense", target: "fusion" },
    { id: "e5", source: "sparse", target: "fusion" },
    { id: "e6", source: "hyde", target: "fusion" },
    { id: "e7", source: "fusion", target: "reranker", animated: true },
    { id: "e8", source: "reranker", target: "output" },
  ];

  const [nodes, , onNodesChange] = useNodesState(initialNodes as any);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  return (
    <div className="fixed inset-0 bg-[#0a0a0f]/95 backdrop-blur-xl z-[200] flex flex-col">
      <div className="p-6 border-b border-white/10 flex items-center justify-between bg-white/5">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl premium-gradient flex items-center justify-center">
            <Layout className="w-5 h-5 text-white" />
          </div>
          <div>
            <h4 className="text-xl font-bold">Retrieval Inspector</h4>
            <p className="text-xs text-zinc-500 uppercase tracking-widest mt-0.5">Real-time Pipeline Visualization</p>
          </div>
        </div>
        <button 
          onClick={onClose}
          className="p-3 rounded-xl hover:bg-white/5 text-zinc-500 hover:text-white transition-all border border-white/5 hover:border-white/20"
        >
          <X className="w-6 h-6" />
        </button>
      </div>

      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          colorMode="dark"
        >
          <Background color="#333" gap={20} />
          <Controls className="!bg-[#1a1a25] !border-white/10" />
          <MiniMap 
            className="!bg-[#0a0a0f] !border-white/10 shadow-2xl" 
            nodeColor="#3b82f6"
            maskColor="rgba(0,0,0,0.5)"
          />
        </ReactFlow>
      </div>

      <div className="p-6 border-t border-white/10 bg-white/5 flex gap-8">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-medium text-zinc-400">Live Trace Active</span>
        </div>
        <div className="text-sm text-zinc-500 flex items-center gap-2">
          <Zap className="w-4 h-4 text-orange-400" />
          <span>Optimization: Hybrid RRF enabled</span>
        </div>
      </div>
    </div>
  );
}
import { Layout } from "lucide-react";
