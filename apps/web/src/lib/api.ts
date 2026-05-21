const API_BASE = "/api/v1";

export type EventCategory = "safe_bet" | "stretch_pick" | "regular";

export interface BilledArtist {
  name: string;
  billing_position: number;
  is_match_driver: boolean;
}

export interface ScoredEvent {
  id: string;
  date: string;
  venue: string;
  artists: BilledArtist[];
  score: number;
  category: EventCategory;
  driver_artist: string;
  driver_mode: string;
  explanation: string | null;
  ticket_url: string | null;
  price_min: number | null;
  price_max: number | null;
}

export async function fetchEvents(
  accessToken: string,
  category?: EventCategory,
): Promise<ScoredEvent[]> {
  const params = new URLSearchParams({ limit: "200" });
  if (category) params.set("category", category);

  const query = params.toString();
  const res = await fetch(`${API_BASE}/events?${query}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function syncUser(accessToken: string): Promise<void> {
  const res = await fetch(`${API_BASE}/user/sync`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Sync failed ${res.status}: ${await res.text()}`);
}

export interface TasteMapUserArtist {
  id: string;
  name: string;
  x: number;
  y: number;
  mode_id: string;
  mode_label: string;
  is_dominant: boolean;
}

export interface TasteMapEventArtist {
  id: string;
  name: string;
  x: number;
  y: number;
  event_id: string;
  venue: string;
  date: string;
}

export interface TasteMapData {
  user_artists: TasteMapUserArtist[];
  event_artists: TasteMapEventArtist[];
}

export async function fetchTasteMap(accessToken: string): Promise<TasteMapData> {
  const res = await fetch(`${API_BASE}/events/taste-map`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
