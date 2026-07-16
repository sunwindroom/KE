import { useState, useCallback, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { createSSEConnection, type SSEMessage } from "../lib/sse-client";
import { apiClient } from "../lib/api-client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export function useQA() {
  const [streamingText, setStreamingText] = useState("");
  const [citations, setCitations] = useState<SSEMessage["citations"]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [lastMessageId, setLastMessageId] = useState<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  const askStream = useCallback(
    (question: string, domain?: string) => {
      setStreamingText("");
      setCitations([]);
      setIsStreaming(true);

      const controller = createSSEConnection(
        `${API_BASE_URL}/qa/ask-stream`,
        { question, domain, session_id: sessionId },
        (msg: SSEMessage) => {
          if (msg.content) {
            setStreamingText((prev) => prev + msg.content);
          }
          if (msg.citations) {
            setCitations(msg.citations);
          }
          if (msg.sessionId) {
            setSessionId(msg.sessionId);
          }
          if (msg.messageId) {
            setLastMessageId(msg.messageId);
          }
          if (msg.done) {
            setIsStreaming(false);
          }
        },
        () => {
          setIsStreaming(false);
        },
        () => {
          setIsStreaming(false);
        },
      );
      abortRef.current = controller;
    },
    [sessionId],
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  const resetSession = useCallback(() => {
    setSessionId(undefined);
    setLastMessageId(undefined);
    setStreamingText("");
    setCitations([]);
  }, []);

  return {
    streamingText,
    citations,
    isStreaming,
    sessionId,
    lastMessageId,
    askStream,
    stopStream,
    resetSession,
  };
}

export function useQAFeedback() {
  return useMutation({
    mutationFn: (req: {
      session_id: string;
      message_id: string;
      helpful: boolean;
      comment?: string;
    }) => apiClient.post("/qa/feedback", req),
  });
}

export function useQASessions() {
  return useMutation({
    mutationFn: () =>
      apiClient.get<
        Array<{ sessionId: string; title: string; domain?: string; updatedAt: string }>
      >("/qa/sessions"),
  });
}

export function useQASessionDetail() {
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiClient.get<{
        sessionId: string;
        messages: Array<{
          messageId: string;
          role: "user" | "assistant";
          content: string;
          citations: Array<{ knowledgeId: string; title: string; snippetRef: string }>;
          confidenceHint?: string;
          helpful: boolean | null;
        }>;
      }>(`/qa/sessions/${sessionId}`),
  });
}
