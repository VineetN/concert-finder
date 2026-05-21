import NextAuth from "next-auth";
import { authConfig } from "./auth-config";

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);

declare module "next-auth" {
  interface Session {
    accessToken: string;
    spotifyId: string;
  }
}
