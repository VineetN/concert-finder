"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { fetchTasteMap, type TasteMapData } from "@/lib/api";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

// Soft, distinct palette that reads well on dark backgrounds
const MODE_COLORS = ["#818cf8", "#34d399", "#f472b6", "#60a5fa", "#a78bfa"];

export function TasteMap({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<TasteMapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchTasteMap(accessToken)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [accessToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-80 text-slate-500 text-sm">
        Building taste map…
      </div>
    );
  }

  if (error || !data || data.user_artists.length === 0) {
    return (
      <div className="flex items-center justify-center h-80 text-slate-600 text-sm">
        {error ? "Taste map unavailable" : "Sync your Spotify data to see your taste map."}
      </div>
    );
  }

  const modeIds = [...new Set(data.user_artists.map((a) => a.mode_id))].sort();

  const userTraces = modeIds.map((modeId, i) => {
    const pts = data.user_artists.filter((a) => a.mode_id === modeId);
    const modeLabel = pts[0]?.mode_label ?? modeId;
    const isDominant = pts[0]?.is_dominant ?? false;
    const color = MODE_COLORS[i % MODE_COLORS.length];

    return {
      x: pts.map((p) => p.x),
      y: pts.map((p) => p.y),
      customdata: pts.map((p) => [p.name, modeLabel]),
      type: "scatter" as const,
      mode: "markers" as const,
      name: `${isDominant ? "★ " : ""}${modeLabel}`,
      marker: {
        color,
        size: 8,
        opacity: 0.75,
        line: { width: 0 },
      },
      hovertemplate:
        "<b>%{customdata[0]}</b><br>" +
        "<span style='color:#94a3b8'>%{customdata[1]}</span>" +
        "<extra></extra>",
    };
  });

  const eventTrace = {
    x: data.event_artists.map((p) => p.x),
    y: data.event_artists.map((p) => p.y),
    customdata: data.event_artists.map((p) => [
      p.name,
      p.venue,
      p.date.slice(0, 10),
    ]),
    type: "scatter" as const,
    mode: "markers" as const,
    name: "Upcoming shows",
    marker: {
      color: "#fbbf24",
      size: 10,
      symbol: "diamond",
      opacity: 0.85,
      line: { width: 1, color: "rgba(255,255,255,0.2)" },
    },
    hovertemplate:
      "<b>%{customdata[0]}</b><br>" +
      "%{customdata[1]}<br>" +
      "<span style='color:#94a3b8'>%{customdata[2]}</span>" +
      "<extra></extra>",
  };

  const layout = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#64748b", size: 11, family: "inherit" },
    xaxis: { showgrid: false, zeroline: false, showticklabels: false, showline: false },
    yaxis: { showgrid: false, zeroline: false, showticklabels: false, showline: false },
    legend: {
      bgcolor: "rgba(15,23,42,0.6)",
      bordercolor: "rgba(100,116,139,0.2)",
      borderwidth: 1,
      font: { size: 11, color: "#94a3b8" },
      x: 1,
      xanchor: "right" as const,
      y: 1,
    },
    margin: { t: 16, b: 16, l: 16, r: 16 },
    hovermode: "closest" as const,
    hoverlabel: {
      bgcolor: "#1e293b",
      bordercolor: "#334155",
      font: { color: "#e2e8f0", size: 12 },
    },
    autosize: true,
  };

  return (
    <Plot
      data={[...userTraces, eventTrace]}
      layout={layout}
      style={{ width: "100%", height: "420px" }}
      config={{ responsive: true, displayModeBar: false }}
      useResizeHandler
    />
  );
}
