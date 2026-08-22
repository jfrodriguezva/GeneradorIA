"use client";

import { useRef, useState } from "react";
import styles from "./page.module.css";

type Role = "system" | "user" | "assistant";

interface Message {
  role: Role;
  content: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:20001";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function sendMessage() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    setError(null);
    const nextMessages: Message[] = [...messages, { role: "user", content: trimmed }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages, stream: true }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`El servidor respondió con estado ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (payload === "[DONE]") continue;

          try {
            const parsed = JSON.parse(payload) as { content?: string };
            if (parsed.content) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + parsed.content,
                };
                return updated;
              });
            }
          } catch {
            // fragmento incompleto, se completará en el próximo chunk
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message || "Ocurrió un error al conectar con el chat.");
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.chatMain}>
        <h1 className={styles.title}>Generativa — Chat</h1>

        <div className={styles.messages}>
          {messages.length === 0 && (
            <p className={styles.placeholder}>Escribe un mensaje para empezar la conversación.</p>
          )}
          {messages.map((message, index) => (
            <div key={index} className={`${styles.bubble} ${styles[message.role]}`}>
              <span className={styles.role}>{message.role === "user" ? "Tú" : "Asistente"}</span>
              <p>{message.content || (isStreaming && index === messages.length - 1 ? "…" : "")}</p>
            </div>
          ))}
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.inputRow}>
          <textarea
            className={styles.textarea}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribe tu mensaje… (Enter para enviar, Shift+Enter para salto de línea)"
            rows={3}
            disabled={isStreaming}
          />
          <button
            className={styles.sendButton}
            onClick={sendMessage}
            disabled={isStreaming || !input.trim()}
          >
            {isStreaming ? "Generando…" : "Enviar"}
          </button>
        </div>
      </main>
    </div>
  );
}
