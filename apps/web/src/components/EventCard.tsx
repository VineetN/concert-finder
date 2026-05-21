"use client";

import { clsx } from "clsx";
import type { ScoredEvent } from "@/lib/api";

const CATEGORY_CHIP: Record<string, { label: string; className: string }> = {
  safe_bet: {
    label: "Safe Bet",
    className: "border-green-700 bg-green-900/40 text-green-300",
  },
  stretch_pick: {
    label: "Stretch Pick",
    className: "border-purple-700 bg-purple-900/40 text-purple-300",
  },
  regular: { label: "", className: "" },
};

export function EventCard({ event }: { event: ScoredEvent }) {
  const chip = CATEGORY_CHIP[event.category];
  const date = new Date(event.date).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  return (
    <article className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-3">
      <header className="flex items-center justify-between gap-2">
        <span className="text-sm text-gray-400">
          {date} · {event.venue}
        </span>
        {chip.label && (
          <span className={clsx("shrink-0 rounded-full border px-2 py-0.5 text-xs", chip.className)}>
            {chip.label}
          </span>
        )}
      </header>

      <div className="space-y-0.5">
        {event.artists.map((a) => (
          <p
            key={a.name}
            className={clsx(
              "font-medium",
              a.billing_position === 0 ? "text-white" : "text-sm text-gray-400",
              a.is_match_driver && "underline decoration-dotted decoration-gray-500",
            )}
          >
            {a.name}
          </p>
        ))}
      </div>

      {event.explanation && (
        <p className="text-sm italic text-gray-500">{event.explanation}</p>
      )}

      <footer className="flex items-center justify-between text-xs text-gray-500">
        <span>
          {(event.score * 100).toFixed(0)}% match · {event.driver_mode}
        </span>
        <span className="flex items-center gap-3">
          {event.price_min != null && (
            <span>${event.price_min}{event.price_max != null ? `–$${event.price_max}` : "+"}</span>
          )}
          {event.ticket_url && (
            <a
              href={event.ticket_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              Tickets →
            </a>
          )}
        </span>
      </footer>
    </article>
  );
}
