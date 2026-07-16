import { useEffect, useRef, useCallback } from "react";

interface GraphNode {
  id: string;
  name: string;
  type: string;
  properties?: Record<string, unknown>;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  properties?: Record<string, unknown>;
}

interface GraphRendererProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (nodeId: string) => void;
  layout?: "force" | "dagre";
  className?: string;
}

const NODE_COLORS: Record<string, string> = {
  Equipment: "#6366f1",
  Component: "#8b5cf6",
  FailureMode: "#ef4444",
  Symptom: "#f59e0b",
  DiagnosisMethod: "#10b981",
  MaintenanceStrategy: "#3b82f6",
  RULModel: "#ec4899",
  HealthState: "#14b8a6",
};

export function GraphRenderer({
  nodes,
  edges,
  onNodeClick,
  layout = "force",
  className,
}: GraphRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<unknown>(null);

  const renderFallback = useCallback(() => {
    if (!containerRef.current) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    svg.setAttribute("viewBox", "0 0 800 600");
    containerRef.current.innerHTML = "";
    containerRef.current.appendChild(svg);

    const nodePositions = nodes.map((n, i) => ({
      ...n,
      x: 400 + 200 * Math.cos((2 * Math.PI * i) / Math.max(nodes.length, 1)),
      y: 300 + 200 * Math.sin((2 * Math.PI * i) / Math.max(nodes.length, 1)),
    }));

    edges.forEach((e) => {
      const src = nodePositions.find((n) => n.id === e.source);
      const tgt = nodePositions.find((n) => n.id === e.target);
      if (src && tgt) {
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", String(src.x));
        line.setAttribute("y1", String(src.y));
        line.setAttribute("x2", String(tgt.x));
        line.setAttribute("y2", String(tgt.y));
        line.setAttribute("stroke", "#4b5563");
        line.setAttribute("stroke-width", "1");
        svg.appendChild(line);
      }
    });

    nodePositions.forEach((n) => {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", String(n.x));
      circle.setAttribute("cy", String(n.y));
      circle.setAttribute("r", "16");
      circle.setAttribute("fill", NODE_COLORS[n.type] || "#6b7280");
      circle.setAttribute("opacity", "0.8");
      circle.style.cursor = "pointer";
      circle.addEventListener("click", () => onNodeClick?.(n.id));
      svg.appendChild(circle);

      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", String(n.x));
      text.setAttribute("y", String(n.y + 28));
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("fill", "#9ca3af");
      text.setAttribute("font-size", "10");
      text.textContent = n.name;
      svg.appendChild(text);
    });
  }, [nodes, edges, onNodeClick]);

  const initGraph = useCallback(async () => {
    if (!containerRef.current) return;

    try {
      const G6 = await import("@antv/g6");

      if (graphRef.current) {
        (graphRef.current as { destroy: () => void }).destroy();
      }

      const graphData = {
        nodes: nodes.map((n) => ({
          id: n.id,
          data: {
            label: n.name,
            type: n.type,
            ...n.properties,
          },
          style: {
            fill: NODE_COLORS[n.type] || "#6b7280",
            stroke: NODE_COLORS[n.type] || "#6b7280",
          },
        })),
        edges: edges.map((e, i) => ({
          id: `edge-${i}`,
          source: e.source,
          target: e.target,
          data: {
            label: e.relation,
            ...e.properties,
          },
        })),
      };

      const graph = new G6.Graph({
        container: containerRef.current,
        data: graphData,
        layout:
          layout === "force"
            ? { type: "force", preventOverlap: true, nodeSize: 40 }
            : { type: "dagre", rankdir: "TB" },
        /* eslint-disable @typescript-eslint/no-explicit-any -- @antv/g6's NodeData/EdgeData/IEvent
           generics are too deeply nested to replicate here for a handful of inline style callbacks */
        node: {
          style: {
            size: 32,
            labelText: (d: any) => d.data?.label ?? "",
            labelPlacement: "bottom",
            labelFontSize: 10,
            fill: (d: any) => d.style?.fill ?? "#6b7280",
            stroke: (d: any) => d.style?.stroke ?? "#6b7280",
            lineWidth: 2,
          },
        },
        edge: {
          style: {
            labelText: (d: any) => d.data?.label ?? "",
            labelFontSize: 8,
            labelBackground: true,
            labelBackgroundFill: "#1e1e2e",
            labelBackgroundOpacity: 0.8,
            stroke: "#4b5563",
            endArrow: true,
          },
        },
        behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
        animation: true,
      } as any);

      graph.on("node:click", (evt: any) => {
        const nodeId = evt.target?.id;
        if (nodeId && onNodeClick) {
          onNodeClick(nodeId);
        }
      });
      /* eslint-enable @typescript-eslint/no-explicit-any */

      await graph.render();
      graphRef.current = graph;
    } catch {
      renderFallback();
    }
  }, [nodes, edges, onNodeClick, layout, renderFallback]);

  useEffect(() => {
    initGraph();
    return () => {
      if (graphRef.current) {
        (graphRef.current as { destroy: () => void }).destroy();
        graphRef.current = null;
      }
    };
  }, [initGraph]);

  return (
    <div ref={containerRef} className={className || "h-full w-full"} style={{ minHeight: 400 }} />
  );
}
