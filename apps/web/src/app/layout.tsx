import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Concert Finder",
  description: "Ranked Seattle shows, personalized to your taste.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        {children}
      </body>
    </html>
  );
}
