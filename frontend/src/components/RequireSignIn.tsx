import { auth } from "@clerk/nextjs/server";

/**
 * Render children only for signed-in users; send everyone else to sign in.
 * Must be placed inside <Suspense>, because it reads the request's session.
 */
export async function RequireSignIn({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, redirectToSignIn } = await auth();
  if (!isAuthenticated) {
    return redirectToSignIn();
  }
  return <>{children}</>;
}