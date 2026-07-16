import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Btn, Badge } from "@/components/panel";
import { Send, FileText, Sparkles, StopCircle, History } from "lucide-react";
import { Modal, useModal } from "@/components/modal";
import { useState, useCallback, useRef, useEffect } from "react";
import { useQA, useQAFeedback, useQASessions, useQASessionDetail } from "@/hooks/use-qa";
import { StreamingText } from "@/components/streaming-text";
import { CitationList } from "@/components/citation-list";

export const Route = createFileRoute("/qa")({
  component: QA,
  head: () => ({ meta: [{ title: "智能问答 · Aether PHM" }] }),
});

interface Message {
  messageId?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Array<{ knowledgeId: string; title: string; snippetRef?: string }>;
}

function QA() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [domain, setDomain] = useState<string | undefined>(undefined);
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, boolean>>({});
  const {
    streamingText,
    citations,
    isStreaming,
    sessionId,
    lastMessageId,
    askStream,
    stopStream,
    resetSession,
  } = useQA();
  const feedback = useQAFeedback();
  const sessions = useQASessions();
  const sessionDetail = useQASessionDetail();
  const historyModal = useModal();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingText]);

  const handleSend = useCallback(() => {
    const q = input.trim();
    if (!q || isStreaming) return;
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    askStream(q, domain);
  }, [input, isStreaming, askStream, domain]);

  useEffect(() => {
    if (!isStreaming && streamingText) {
      setMessages((prev) => [
        ...prev,
        {
          messageId: lastMessageId,
          role: "assistant",
          content: streamingText,
          citations: citations || undefined,
        },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleQuickQuestion = useCallback(
    (q: string) => {
      setInput(q);
      setMessages((prev) => [...prev, { role: "user", content: q }]);
      askStream(q, domain);
    },
    [askStream, domain],
  );

  const handleFeedback = useCallback(
    (messageId: string | undefined, helpful: boolean) => {
      if (!messageId || !sessionId) return;
      feedback.mutate({ session_id: sessionId, message_id: messageId, helpful });
      setFeedbackGiven((prev) => ({ ...prev, [messageId]: true }));
    },
    [feedback, sessionId],
  );

  const handleNewSession = useCallback(() => {
    setMessages([]);
    resetSession();
  }, [resetSession]);

  const handleOpenHistory = useCallback(() => {
    historyModal.openModal();
    sessions.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyModal]);

  const handleLoadSession = useCallback(
    (id: string) => {
      sessionDetail.mutate(id, {
        onSuccess: (detail) => {
          setMessages(
            detail.messages.map((m) => ({
              messageId: m.messageId,
              role: m.role,
              content: m.content,
              citations: m.citations,
            })),
          );
          historyModal.closeModal();
        },
      });
    },
    [sessionDetail, historyModal],
  );

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M08 · Knowledge Q&A"
        title="智能知识问答"
        description="融合 RAG、图谱推理与 Agent 编排的领域问答界面，答案携带证据链与置信度，可回溯至原文位置。"
        actions={
          <>
            <select
              value={domain || ""}
              onChange={(e) => setDomain(e.target.value || undefined)}
              className="rounded border border-border bg-white/5 px-2 py-1 text-xs"
            >
              <option value="">全部领域</option>
              <option value="aerospace">航空</option>
              <option value="energy">能源</option>
              <option value="transportation">轨交</option>
              <option value="general">通用</option>
            </select>
            <Btn variant="outline" onClick={handleOpenHistory}>
              会话历史
            </Btn>
            <Btn variant="primary" onClick={handleNewSession}>
              新建会话
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-4">
        <div className="xl:col-span-1 space-y-3">
          <SectionHeader title="常用提问" />
          {[
            "GT-40 燃气轮机高温预警处置流程",
            "液压泵密封老化的早期征兆有哪些",
            "叶片裂纹寿命预测常用模型对比",
            "变频器过流保护规则集摘要",
            "冷却回路故障典型传播路径",
          ].map((q) => (
            <button
              key={q}
              onClick={() => handleQuickQuestion(q)}
              className="w-full border border-border bg-card/40 p-3 text-left text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
            >
              {q}
            </button>
          ))}
        </div>

        <div className="xl:col-span-3">
          <SectionHeader
            title="当前会话"
            action={<Badge tone="primary">RAG + Graph + Agent</Badge>}
          />
          <div className="flex h-[600px] flex-col border border-border bg-card">
            <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto p-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={msg.role === "user" ? "flex justify-end gap-3" : "flex gap-3"}
                >
                  {msg.role === "user" ? (
                    <>
                      <div className="max-w-[70%] rounded bg-primary/10 border border-primary/20 px-4 py-2 text-sm text-foreground">
                        {msg.content}
                      </div>
                      <div className="grid size-8 shrink-0 place-items-center rounded border border-border bg-white/5 font-mono text-[10px] text-muted-foreground">
                        U
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="grid size-8 shrink-0 place-items-center rounded border border-primary/40 bg-primary/10 font-mono text-[10px] font-bold text-primary">
                        AI
                      </div>
                      <div className="max-w-[80%] space-y-3">
                        <div className="text-sm leading-relaxed">{msg.content}</div>
                        {msg.citations && msg.citations.length > 0 && (
                          <CitationList citations={msg.citations} />
                        )}
                        <div className="flex gap-2">
                          {feedbackGiven[msg.messageId || ""] ? (
                            <span className="text-[10px] text-muted-foreground">感谢反馈</span>
                          ) : (
                            <>
                              <button
                                onClick={() => handleFeedback(msg.messageId, true)}
                                disabled={!msg.messageId}
                                className="text-[10px] text-muted-foreground hover:text-success disabled:opacity-40"
                              >
                                👍 有帮助
                              </button>
                              <button
                                onClick={() => handleFeedback(msg.messageId, false)}
                                disabled={!msg.messageId}
                                className="text-[10px] text-muted-foreground hover:text-destructive disabled:opacity-40"
                              >
                                👎 无帮助
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ))}

              {isStreaming && (
                <div className="flex gap-3">
                  <div className="grid size-8 shrink-0 place-items-center rounded border border-primary/40 bg-primary/10 font-mono text-[10px] font-bold text-primary">
                    AI
                  </div>
                  <div className="max-w-[80%]">
                    <StreamingText text={streamingText} isStreaming={isStreaming} />
                    {citations && citations.length > 0 && <CitationList citations={citations} />}
                  </div>
                </div>
              )}

              {messages.length === 0 && !isStreaming && (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  输入问题开始对话，或点击左侧常用提问
                </div>
              )}
            </div>

            <div className="border-t border-border p-4">
              <div className="relative">
                <Sparkles className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-primary" />
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="继续追问 · Enter 发送 · Shift+Enter 换行"
                  className="w-full border border-border bg-white/5 py-3 pl-9 pr-12 text-xs focus:border-primary/50 focus:outline-none"
                />
                {isStreaming ? (
                  <button
                    onClick={stopStream}
                    className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded bg-destructive text-primary-foreground"
                  >
                    <StopCircle className="size-3.5" />
                  </button>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!input.trim()}
                    className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded bg-primary text-primary-foreground disabled:opacity-50"
                  >
                    <Send className="size-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {historyModal.open && (
        <Modal title="会话历史" onClose={historyModal.closeModal}>
          <div className="space-y-3">
            {sessions.isPending ? (
              <div className="text-xs text-muted-foreground py-4 text-center">加载中…</div>
            ) : sessions.data && sessions.data.length > 0 ? (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {sessions.data.map((s) => (
                  <button
                    key={s.sessionId}
                    onClick={() => handleLoadSession(s.sessionId)}
                    className="w-full border border-border bg-card/50 p-3 text-left text-xs transition hover:border-primary/40"
                  >
                    <div className="font-bold">{s.title || s.sessionId}</div>
                    <div className="mt-1 font-mono text-[9px] text-muted-foreground">
                      {new Date(s.updatedAt).toLocaleString()}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-4 text-center">暂无历史会话</div>
            )}
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={historyModal.closeModal}>
                关闭
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
