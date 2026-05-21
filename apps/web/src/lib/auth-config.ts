import Spotify from "next-auth/providers/spotify";
import type { NextAuthConfig } from "next-auth";

const SPOTIFY_SCOPES = [
  "user-top-read",
  "user-read-private",
  "user-read-email",
].join(" ");

export const authConfig: NextAuthConfig = {
  secret: process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET,
  trustHost: true,
  basePath: "/api/auth",
  pages: { signIn: "/signin" },
  providers: [
    Spotify({
      clientId: process.env.SPOTIFY_CLIENT_ID!,
      clientSecret: process.env.SPOTIFY_CLIENT_SECRET!,
      authorization: {
        url: "https://accounts.spotify.com/authorize",
        params: { scope: SPOTIFY_SCOPES },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        // expires_at is seconds since epoch
        token.expiresAt = account.expires_at;
        token.spotifyId = account.providerAccountId;
        return token;
      }

      // Return early if token is still valid (with 60s buffer)
      if (Date.now() < ((token.expiresAt as number) - 60) * 1000) {
        return token;
      }

      // Refresh the access token
      try {
        const resp = await fetch("https://accounts.spotify.com/api/token", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            Authorization:
              "Basic " +
              Buffer.from(
                `${process.env.SPOTIFY_CLIENT_ID}:${process.env.SPOTIFY_CLIENT_SECRET}`
              ).toString("base64"),
          },
          body: new URLSearchParams({
            grant_type: "refresh_token",
            refresh_token: token.refreshToken as string,
          }),
        });
        const refreshed = await resp.json();
        if (!resp.ok) throw refreshed;
        token.accessToken = refreshed.access_token;
        token.expiresAt = Math.floor(Date.now() / 1000) + refreshed.expires_in;
        if (refreshed.refresh_token) token.refreshToken = refreshed.refresh_token;
      } catch (err) {
        console.error("Spotify token refresh failed", err);
        token.error = "RefreshTokenError";
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      session.spotifyId = (token.spotifyId ?? token.sub) as string;
      if (token.error) session.error = token.error as string;
      return session;
    },
  },
};
