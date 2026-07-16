export function GraphPreview({ className = "" }: { className?: string }) {
  // Static SVG mock — nodes & edges representing an ontology sample.
  return (
    <svg viewBox="0 0 600 400" className={className} preserveAspectRatio="xMidYMid meet">
      <defs>
        <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.9" />
          <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
        </radialGradient>
        <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="var(--color-border)" opacity="0.6" />
        </pattern>
      </defs>
      <rect width="600" height="400" fill="url(#dots)" />

      {/* edges */}
      <g stroke="var(--color-primary)" strokeOpacity="0.35" strokeWidth="1">
        <line x1="300" y1="200" x2="130" y2="90" />
        <line x1="300" y1="200" x2="480" y2="110" />
        <line x1="300" y1="200" x2="150" y2="320" />
        <line x1="300" y1="200" x2="470" y2="310" />
        <line x1="300" y1="200" x2="380" y2="200" />
        <line x1="130" y1="90" x2="80" y2="200" />
        <line x1="480" y1="110" x2="540" y2="220" />
        <line x1="470" y1="310" x2="380" y2="360" />
      </g>

      {/* halos */}
      <circle cx="300" cy="200" r="60" fill="url(#node-glow)" />
      <circle cx="130" cy="90" r="30" fill="url(#node-glow)" opacity="0.5" />
      <circle cx="480" cy="110" r="30" fill="url(#node-glow)" opacity="0.5" />

      {/* nodes */}
      {[
        { x: 300, y: 200, r: 10, color: "var(--color-primary)", label: "液压系统" },
        { x: 130, y: 90, r: 6, color: "var(--color-graph-2)", label: "过滤器堵塞" },
        { x: 480, y: 110, r: 6, color: "var(--color-graph-2)", label: "高温预警" },
        { x: 150, y: 320, r: 6, color: "var(--color-graph-3)", label: "维修策略-A" },
        { x: 470, y: 310, r: 6, color: "var(--color-graph-4)", label: "传感器-77203" },
        { x: 380, y: 200, r: 5, color: "var(--color-primary)", label: "冷却回路" },
        { x: 80, y: 200, r: 4, color: "var(--color-muted-foreground)" },
        { x: 540, y: 220, r: 4, color: "var(--color-muted-foreground)" },
        { x: 380, y: 360, r: 4, color: "var(--color-muted-foreground)" },
      ].map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={n.r} fill={n.color} />
          {n.label && (
            <text x={n.x + n.r + 6} y={n.y + 3} fontSize="10" fill="var(--color-foreground)" fontFamily="Inter">
              {n.label}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
