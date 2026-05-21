import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";

export default async function Home() {
  const session = await auth();
  if (!session) redirect("/api/auth/signin");

  return (
    <main className="mx-auto max-w-2xl px-4 py-10 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Concert Finder</h1>
        <p className="text-gray-400 mt-1">
          Upcoming Seattle shows, ranked for your taste.
        </p>
      </div>

      {/* TODO: <EventFeed accessToken={session.accessToken} /> */}
      {/* TODO: <TasteMap userId={session.user?.id} />           */}

      <p className="text-sm text-gray-600">
        Signed in as {session.user?.name ?? session.user?.email}
      </p>
    </main>
  );
}
