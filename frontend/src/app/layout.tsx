import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Human Hub",
  description: "Turn a spoken project brief into approved user stories.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}