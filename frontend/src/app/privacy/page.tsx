import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy notice · AI Human Hub",
  description: "What AI Human Hub collects, why, for how long, and how to delete it.",
};

// P7: a plain-English privacy notice. If the wording of the recording notice
// on the new-project form changes, bump CONSENT_VERSION in backend/projects/models.py.

export default function PrivacyPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 px-4 py-12 leading-relaxed">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold">Privacy notice</h1>
        <p className="text-neutral-600 dark:text-neutral-300">
          In plain English: what we collect, why, for how long, and how you can delete it.
        </p>
      </header>

      <Section title="What we collect">
        <ul className="list-disc pl-5">
          <li>
            <strong>Your account:</strong> your name and email address, from the sign-in service
            (Clerk).
          </li>
          <li>
            <strong>Your voice recordings, as text only.</strong> The audio is turned into text and
            deleted straight away. We never store it.
          </li>
          <li>
            <strong>A masked copy of that text,</strong> with names, email addresses, phone numbers
            and postal addresses replaced by tags such as [NAME].
          </li>
          <li>
            <strong>Your answers</strong> to our follow-up questions, and the{" "}
            <strong>user stories</strong> written from what you told us, including any changes you
            or our team make to them.
          </li>
        </ul>
      </Section>

      <Section title="Why we collect it">
        <p>
          Only to turn your explanation into clear requirements for your project, and to deliver
          them to your own private GitHub repository once you and our team have approved them. We
          don&apos;t use your data for anything else, and we don&apos;t sell it.
        </p>
      </Section>

      <Section title="Who else handles it">
        <ul className="list-disc pl-5">
          <li>
            <strong>AI services</strong> (Cloudflare Workers AI, with Groq as a backup) turn speech
            into text and draft questions and stories. Apart from the recording needed for
            transcription, they only ever receive the <em>masked</em> text.
          </li>
          <li>
            <strong>Hosting:</strong> Neon (database), Render (our server) and Vercel (this
            website). Clerk handles sign-in.
          </li>
          <li>
            <strong>GitHub</strong> receives your approved stories, and only in the private
            repository you give us.
          </li>
        </ul>
        <p>Our own team sees the masked text too, not the original.</p>
      </Section>

      <Section title="How long we keep it">
        <p>
          We keep a project for <strong>12 months</strong> after it is sent to GitHub, or 12 months
          after it was last changed if it never got that far. After that it is deleted
          automatically. We keep only a note that a project was deleted and when, with no content.
        </p>
      </Section>

      <Section title="How to delete it">
        <p>
          Open your project from your <Link href="/dashboard" className="underline">dashboard</Link>{" "}
          and press <strong>Delete project</strong>. Everything in it (text, answers and stories)
          is removed immediately and can&apos;t be recovered. Issues already delivered to your own
          GitHub repository stay there, because that repository belongs to you.
        </p>
        <p>
          Before deleting, you can download a copy of your approved requirements with{" "}
          <strong>Download requirements</strong>.
        </p>
      </Section>

      <p className="text-sm text-neutral-500">Last updated 25 November 2026.</p>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}
