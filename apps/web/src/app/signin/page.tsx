"use client";

import { signIn } from "next-auth/react";

export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="text-center space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Concert Finder</h1>
        <p className="text-gray-400">Sign in to see shows ranked for your taste.</p>
        <button
          onClick={() => signIn("spotify", { callbackUrl: "/" })}
          className="bg-green-500 hover:bg-green-400 text-black font-semibold px-6 py-3 rounded-full transition-colors"
        >
          Sign in with Spotify
        </button>
      </div>
    </main>
  );
}
