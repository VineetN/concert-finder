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
        token.expiresAt = account.expires_at;
        token.spotifyId = account.providerAccountId;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      session.spotifyId = (token.spotifyId ?? token.sub) as string;
      return session;
    },
  },
};
