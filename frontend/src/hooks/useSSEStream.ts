"use client";

import { useState, useCallback, useRef } from "react";

export type SSEEvent = {
  type: "retrieval_start" | "retrieval_complete" | "token" | "done" | "error";
  delta?: string;
  chunk_count?: number;
  sources?: string[];
  run_id?: string;
  citations?: any[];
  message?: string;
};

export function useSSEStream() {
  const [data, setData] = useState<string>("");
  const [sources, setSources] = useState<string[]>([]);
  const [citations, setCitations] = useState<any[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "retrieving" | "generating" | "complete">("idle");

  const eventSourceRef = useRef<EventSource | null>(null);

  const startStream = useCallback((run_id: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setData("");
    setSources([]);
    setCitations([]);
    setRunId(run_id);
    setIsStreaming(true);
    setError(null);
    setStatus("retrieving");

    const endpoint = `/api/proxy/query/${run_id}/stream`; // We'll set up a proxy to backend
    const eventSource = new EventSource(endpoint);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const payload: SSEEvent = JSON.parse(event.data);

        switch (payload.type) {
          case "retrieval_start":
            setStatus("retrieving");
            break;
          case "retrieval_complete":
            setStatus("generating");
            if (payload.sources) setSources(payload.sources);
            break;
          case "token":
            setData((prev) => prev + (payload.delta || ""));
            break;
          case "done":
            setStatus("complete");
            setIsStreaming(false);
            if (payload.citations) setCitations(payload.citations);
            eventSource.close();
            break;
          case "error":
            setError(payload.message || "An unknown error occurred");
            setIsStreaming(false);
            eventSource.close();
            break;
        }
      } catch (e) {
        console.error("Failed to parse SSE message", e);
      }
    };

    eventSource.onerror = (e) => {
      console.error("SSE error", e);
      setError("Connection to server lost.");
      setIsStreaming(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      setIsStreaming(false);
    }
  }, []);

  return {
    data,
    sources,
    citations,
    runId,
    isStreaming,
    error,
    status,
    startStream,
    stopStream
  };
}
