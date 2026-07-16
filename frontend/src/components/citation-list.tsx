interface Citation {
  knowledgeId: string;
  title: string;
  snippetRef?: string;
}

interface CitationListProps {
  citations: Citation[];
  onCitationClick?: (knowledgeId: string) => void;
}

export function CitationList({ citations, onCitationClick }: CitationListProps) {
  if (!citations.length) return null;

  return (
    <div className="space-y-2 mt-3">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">引用来源</div>
      {citations.map((c, i) => (
        <div
          key={c.knowledgeId}
          className="flex items-start gap-2 rounded border border-border/50 bg-muted/30 px-3 py-2 text-xs cursor-pointer hover:bg-muted/50 transition"
          onClick={() => onCitationClick?.(c.knowledgeId)}
        >
          <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-primary text-[10px]">
            {i + 1}
          </span>
          <div className="min-w-0">
            <div className="font-medium truncate">{c.title}</div>
            {c.snippetRef && (
              <div className="text-muted-foreground mt-0.5 line-clamp-2">{c.snippetRef}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}