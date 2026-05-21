"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as Tabs from "@radix-ui/react-tabs";
import { clsx } from "clsx";
import { EventCard } from "./EventCard";
import { TasteMap } from "./TasteMap";
import { fetchEvents, syncUser, type ScoredEvent } from "@/lib/api";

type Status = "loading" | "needs-sync" | "error" | "ready";

const EVENT_TABS = [
  { value: "all",          label: "All" },
  { value: "safe_bet",     label: "Safe Bets" },
  { value: "stretch_pick", label: "Stretch Picks" },
] as const;

type EventTabValue = typeof EVENT_TABS[number]["value"];

const ALL_TABS = [
  ...EVENT_TABS,
  { value: "taste_map", label: "Taste Map" },
] as const;

function partition(events: ScoredEvent[]): Record<EventTabValue, ScoredEvent[]> {
  return {
    all:          events,
    safe_bet:     events.filter((e) => e.category === "safe_bet"),
    stretch_pick: events.filter((e) => e.category === "stretch_pick"),
  };
}

export function EventFeed({ accessToken }: { accessToken: string }) {
  const [events, setEvents]   = useState<ScoredEvent[]>([]);
  const [status, setStatus]   = useState<Status>("loading");
  const [error,  setError]    = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await fetchEvents(accessToken);
      setEvents(data);
      setStatus("ready");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401")) {
        router.push("/signin");
        return;
      }
      if (msg.includes("404")) {
        setStatus("needs-sync");
      } else {
        setError(msg);
        setStatus("error");
      }
    }
  }, [accessToken, router]);

  useEffect(() => { load(); }, [load]);

  async function handleSync() {
    setSyncing(true);
    try {
      await syncUser(accessToken);
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      if (msg.includes("401")) {
        router.push("/signin");
        return;
      }
      setError(msg);
      setStatus("error");
    } finally {
      setSyncing(false);
    }
  }

  if (status === "loading") return <EventFeedSkeleton />;

  if (status === "needs-sync") {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-10 text-center space-y-4">
        <p className="text-gray-300">
          Sync your Spotify listening history to get personalized recommendations.
        </p>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="rounded-lg bg-green-600 hover:bg-green-500 disabled:opacity-50 px-6 py-2 text-sm font-medium transition-colors"
        >
          {syncing ? "Syncing…" : "Sync Spotify"}
        </button>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-xl border border-red-900 bg-red-950/30 p-6 text-center space-y-3">
        <p className="text-red-400 text-sm">Failed to load events: {error}</p>
        <button
          onClick={load}
          className="text-xs text-gray-500 hover:text-gray-300 underline transition-colors"
        >
          Try again
        </button>
      </div>
    );
  }

  const tabs = partition(events);

  return (
    <Tabs.Root defaultValue="all">
      <div className="flex items-center justify-between border-b border-gray-800 mb-6">
        <Tabs.List className="flex gap-1">
          {ALL_TABS.map(({ value, label }) => {
            const count = value !== "taste_map"
              ? tabs[value as EventTabValue].length
              : null;
            return (
              <Tabs.Trigger
                key={value}
                value={value}
                className={clsx(
                  "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
                  "border-transparent text-gray-400 hover:text-gray-200",
                  "data-[state=active]:border-white data-[state=active]:text-white",
                )}
              >
                {label}
                {count != null && count > 0 && (
                  <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs text-gray-500">
                    {count}
                  </span>
                )}
              </Tabs.Trigger>
            );
          })}
        </Tabs.List>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="text-xs text-gray-500 hover:text-gray-300 disabled:opacity-40 transition-colors pb-2"
        >
          {syncing ? "Syncing…" : "Re-sync"}
        </button>
      </div>

      {EVENT_TABS.map(({ value, label }) => (
        <Tabs.Content key={value} value={value} className="space-y-3 outline-none">
          {tabs[value].length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-600">
              No {value === "all" ? "" : label.toLowerCase() + " "}events right now.
            </p>
          ) : (
            tabs[value].map((ev) => <EventCard key={ev.id} event={ev} />)
          )}
        </Tabs.Content>
      ))}

      <Tabs.Content value="taste_map" className="outline-none">
        <TasteMap accessToken={accessToken} />
      </Tabs.Content>
    </Tabs.Root>
  );
}

function EventFeedSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="flex gap-6 border-b border-gray-800 pb-2 mb-6">
        {["All", "Safe Bets", "Stretch Picks", "Taste Map"].map((label) => (
          <div key={label} className="h-5 w-20 rounded bg-gray-800" />
        ))}
      </div>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-3">
          <div className="flex justify-between">
            <div className="h-4 w-40 rounded bg-gray-800" />
            <div className="h-4 w-16 rounded bg-gray-800" />
          </div>
          <div className="h-5 w-52 rounded bg-gray-800" />
          <div className="h-4 w-36 rounded bg-gray-800" />
          <div className="flex justify-between">
            <div className="h-3 w-28 rounded bg-gray-800" />
            <div className="h-3 w-16 rounded bg-gray-800" />
          </div>
        </div>
      ))}
    </div>
  );
}
