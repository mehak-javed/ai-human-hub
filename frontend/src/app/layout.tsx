import { ClerkProvider, Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

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
      <body className="antialiased">
        <ClerkProvider>
          <header className="flex items-center justify-between border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
            <Link href="/" className="font-semibold">
              AI Human Hub
            </Link>
            <nav className="flex items-center gap-3 text-sm">
              <Suspense>
                <Show when="signed-out">
                  <SignInButton />
                  <SignUpButton />
                </Show>
                <Show when="signed-in">
                  <Link href="/dashboard">Dashboard</Link>
                  <UserButton />
                </Show>
              </Suspense>
            </nav>
          </header>
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}