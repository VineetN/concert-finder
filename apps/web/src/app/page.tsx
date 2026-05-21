import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { EventFeed } from "@/components/EventFeed";

export default async function Home() {
  const session = await auth();
  if (!session || session.error === "RefreshTokenError") redirect("/signin");

  return (
    <main className="mx-auto max-w-2xl px-4 py-10 space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Concert Finder</h1>
          <p className="text-gray-400 mt-1">
            Upcoming Seattle shows, ranked for your taste.
          </p>
        </div>
        <p className="text-sm text-gray-600 pt-1">
          {session.user?.name ?? session.user?.email}
        </p>
      </div>

      <EventFeed accessToken={session.accessToken} />
    </main>
  );
}
