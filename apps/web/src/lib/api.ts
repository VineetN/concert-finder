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
  const params = new URLSearchParams();
  if (category) params.set("category", category);

  const query = params.toString();
  const res = await fetch(`${API_BASE}/events${query ? `?${query}` : ""}`, {
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

export async function fetchTasteMap(accessToken: string): Promise<{
  user_points: { x: number; y: number; label: string }[];
  event_points: { x: number; y: number; label: string; venue: string }[];
}> {
  const res = await fetch(`${API_BASE}/events/taste-map?spotify_user_id=me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
