import { useEffect, useRef } from "react";

interface StreamingTextProps {
  text: string;
  isStreaming: boolean;
  className?: string;
}

export function StreamingText({ text, isStreaming, className }: StreamingTextProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [text]);

  return (
    <div ref={containerRef} className={`whitespace-pre-wrap text-sm leading-relaxed ${className || ""}`}>
      {text}
      {isStreaming && <span className="inline-block h-4 w-0.5 animate-pulse bg-primary ml-0.5" />}
    </div>
  );
}