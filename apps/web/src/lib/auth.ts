import NextAuth from "next-auth";
import Spotify from "next-auth/providers/spotify";

// Scopes needed: read top artists/tracks + basic profile
const SPOTIFY_SCOPES = [
  "user-top-read",
  "user-read-private",
  "user-read-email",
].join(" ");

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Spotify({
      clientId: process.env.SPOTIFY_CLIENT_ID!,
      clientSecret: process.env.SPOTIFY_CLIENT_SECRET!,
      authorization: { params: { scope: SPOTIFY_SCOPES } },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // Persist Spotify tokens in the JWT on first sign-in
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
      }
      return token;
    },
    async session({ session, token }) {
      // Expose access token to the frontend so it can call FastAPI
      session.accessToken = token.accessToken as string;
      return session;
    },
  },
});

// Extend next-auth types
declare module "next-auth" {
  interface Session {
    accessToken: string;
  }
}
