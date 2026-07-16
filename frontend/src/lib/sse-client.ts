export interface SSEMessage {
  content?: string;
  citations?: Array<{ knowledgeId: string; title: string; snippetRef: string }>;
  confidenceHint?: string;
  disclaimer?: string;
  sessionId?: string;
  messageId?: string;
  done?: boolean;
}

export function createSSEConnection(
  url: string,
  body: Record<string, unknown>,
  onMessage: (msg: SSEMessage) => void,
  onError?: (err: Error) => void,
  onComplete?: () => void,
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem("access_token");

  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`SSE连接失败: ${response.status}`);
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error("无法获取响应流");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;
            try {
              const msg: SSEMessage = JSON.parse(dataStr);
              onMessage(msg);
              if (msg.done) {
                onComplete?.();
                return;
              }
            } catch {
              // skip malformed data
            }
          }
        }
      }
      onComplete?.();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError?.(err);
      }
    });

  return controller;
}
