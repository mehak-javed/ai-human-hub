import { BackendStatus } from "@/components/BackendStatus";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-4">
      <h1 className="text-3xl font-semibold">AI Human Hub</h1>
      <p className="text-lg text-neutral-600 dark:text-neutral-300">
        Describe your project by voice. We turn it into clear user stories that you approve
        before anything reaches the development team.
      </p>
      <BackendStatus />
    </main>
  );
}