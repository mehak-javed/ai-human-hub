# Use Cases: Client Interview to GitHub

## Overview

A client explains their project by voice, an AI interviewer asks follow-up
questions, and approved requirements land in a private GitHub repository as
issues. Everything runs on free tiers; the only cost is the domain.

## Goals

- Turn a 10–15 minute voice conversation into clear user stories and
  acceptance criteria.
- Keep a human approval step before anything reaches GitHub.
- Never store audio or faces; store only the text people approve.
- Give admins a dashboard to review, reject and accept requirements before
  pushing them to GitHub, and give clients a dashboard to accept, reject,
  edit or delete their user stories.
- If the client requests changes, the AI rewrites the stories; only an
  approved set goes to the admin and then to GitHub.

## End-to-end flow

Client records voice → Transcribe audio (audio dropped) → Mask personal data →
AI asks follow-ups (up to 10) → AI writes stories → **Client approves?**
(no: changes requested, AI rewrites; yes: continue) → Admin reviews (edit,
merge, reject) → Push to GitHub (private repo issues)

## Actors

| Actor | Who or what | Main goal |
|---|---|---|
| Client | Business owner describing a project | Explain needs once, approve them, track progress |
| Admin | The agency team | Review requirements, manage clients, ship to developers |
| AI Interviewer | Workers AI (Llama/Qwen), Groq as backup | Ask follow-ups and structure the requirements |
| Transcriber | Workers AI Whisper | Turn audio into text |
| GitHub | GitHub API on a private repo | Hold issues, requirements file and project board |
| System | Django on Render, Neon Postgres, Clerk | Run the app, store data, control access |

IDs used below: C = Client, AI = AI system, A = Admin, G = GitHub,
P = Privacy and data, N = Non-functional.

## Client use cases

| ID | Use case | What happens | Done when |
|---|---|---|---|
| C1 | Sign up and sign in | Client opens an invite link and signs in with email or Google through Clerk | Client lands on their own dashboard and sees only their projects |
| C2 | Give consent | Before recording, client reads a short notice: audio is deleted after transcription, text kept for a set period | Recording is blocked until the box is ticked; consent time is saved |
| C3 | Start a new project | Client names the project and picks a type (website, app, dashboard, other) | Project is created with status Interviewing |
| C4 | Record a voice explanation | Client presses Record and explains the idea; can pause, stop and re-record | Audio is sent for transcription and the text appears on screen |
| C5 | Answer AI follow-up questions | AI asks one question at a time; client answers by voice or text | Every gap is answered or marked Not sure |
| C6 | Explain their data | Client describes what information the system holds (customers, orders, bookings) | Data entities and fields appear in the summary |
| C7 | Pause and resume | Client leaves mid-interview and returns later | Interview continues from the last question |
| C8 | Review the summary | Client sees user stories grouped by Must, Should and Nice to have | Client can edit wording, remove items and add missing ones |
| C9 | Approve or request changes | Client approves the summary or sends it back with a note | Approved summary is locked and sent to the admin |
| C10 | Track progress | Client sees features done versus total, synced from GitHub issues | Progress bar matches closed issues on GitHub |
| C11 | Delete my data | Client presses Delete project | Transcripts and stories are removed within 24 hours |

## AI use cases

| ID | Use case | What happens | Done when |
|---|---|---|---|
| AI1 | Transcribe audio | Audio goes to Workers AI Whisper; the file is discarded right after | Transcript is saved; no audio exists anywhere |
| AI2 | Mask personal data | Names, emails, phone numbers and addresses are replaced with tags like [NAME] before any AI prompt | No raw personal detail is sent to an AI model |
| AI3 | Find gaps and ask follow-ups | AI compares the transcript with a checklist: users, roles, features, data, payments, login, deadlines | Up to 10 follow-up questions, asked one at a time |
| AI4 | Generate user stories | "As a [role], I want [goal], so that [reason]" with acceptance criteria and priority | Output is valid JSON matching the story schema; invalid output is retried once |
| AI5 | Extract the data model | AI lists entities, fields and relationships | Entities appear in the summary for the client to confirm |
| AI6 | Switch provider on limits | If Workers AI hits its daily limit or errors, the request goes to Groq | Client sees no error; the switch is logged |
| AI7 | Record AI quality | Each story is marked accepted, edited or rejected by client and admin | Dashboard shows the share of AI stories accepted unchanged |

## Admin use cases

| ID | Use case | What happens | Done when |
|---|---|---|---|
| A1 | Invite a client | Admin invites the client through Clerk with the Client role; Django creates a matching user on first sign-in | Client can sign in and sees an empty dashboard |
| A2 | See the overview | Active clients, interviews this week, stories created, issues pushed | Numbers match the database |
| A3 | Manage interviews | Sessions listed by status: Interviewing, Awaiting client, Awaiting admin, Sent to GitHub | Admin can filter by client and status |
| A4 | Review and edit stories | Admin edits, merges, splits or rejects client-approved stories | Each change is saved with who made it and when |
| A5 | Approve for GitHub | Admin presses Send to GitHub after review | Push starts and status becomes Sent to GitHub |
| A6 | Connect a GitHub repo | Admin links a project to a private repo through the GitHub App | Connection test passes; public repos are refused |
| A7 | Monitor AI usage | Chart of daily Workers AI and Groq usage against free limits | Warning shows at 80% of the daily limit |
| A8 | View the audit log | Every AI output, edit, approval and GitHub push is listed | Log is read-only and filterable by project |
| A9 | See charts | Interviews over time, stories by priority, progress per client, AI acceptance rate | Charts load in under 2 seconds |

## GitHub integration use cases

| ID | Use case | What happens | Done when |
|---|---|---|---|
| G1 | Create issues | One issue per story: title, story text, acceptance criteria as a checklist, priority labels | Issue count equals approved story count |
| G2 | Write requirements.md | Project summary, stories and data model committed to the repo | File exists on main with a clear commit message |
| G3 | Set up a project board | Issues added to a GitHub Project with To do, In progress, Done | Board shows every new issue in To do |
| G4 | Sync status back | A webhook tells the app when an issue is closed or reopened | Progress updates within a minute |
| G5 | Avoid duplicates | Re-sending a project updates existing issues instead of creating new ones | No duplicate issues after a second push |
| G6 | Handle failures | If GitHub is down or a token expires, the push is retried and the admin is alerted | No half-finished push; the admin sees a clear error |

## Privacy, security and data use cases

| ID | Use case | What happens | Done when |
|---|---|---|---|
| P1 | Never store audio | Audio is held in memory only for transcription, then dropped | No audio column or file storage exists |
| P2 | Role-based access | Django checks the Clerk token and role on every request, plus a project-owner check in every API view; Django Admin is staff-only | A client requesting another client's project gets 404 (not found), so it can't learn the project exists |
| P3 | Automatic clean-up | A daily job deletes projects finished more than 12 months ago | Old rows are gone; the deletion is logged |
| P4 | Data export | Client can download approved requirements as Markdown | File matches what is in the app |
| P5 | Weekly backup | Database exported to a SQL file each week | Latest backup is under 8 days old |
| P6 | Secrets kept safe | GitHub and AI keys live in environment variables, never in code or the browser | Secret scanning finds nothing |
| P7 | Privacy notice | Plain-English page: what is collected, why, for how long, how to delete it | Linked from sign-up and the consent step |

Open question: the 12-month retention period is a starting assumption; confirm
before going live.

## Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| N1 | Free-tier budget | Workers AI 10,000 neurons/day; Neon 1 GB storage and 100 compute hours/month; Clerk 50,000 monthly retained users; Render free web service |
| N2 | Interview length cap | Maximum 15 minutes of audio per interview |
| N3 | Graceful limit handling | Over the limit, show "Busy today, we'll email you when ready" and queue the job |
| N4 | Speed | Transcript shown within 10 seconds of a 2-minute recording |
| N5 | Availability | Client pages never sleep; move the backend off Render free when clients go live |
| N6 | Mobile friendly | Recording and approval work on a phone browser |
| N7 | Quality | Unit tests for masking, story parsing and access checks, run on every push |
| N8 | Observability | Errors and provider switches logged; daily usage visible to admins |

## MVP scope

**In the MVP:** C1–C5, C8, C9 · AI1, AI2, AI4, AI6 · A1, A4, A5, A6 · G1, G2 ·
P1, P2, P6, P7 · N1–N3, N7

**Later:** C6, C7, C10, C11 · AI3 full checklist, AI5, AI7 · A2, A3, A7–A9 ·
G3–G6 · P3–P5 · N4, N5, N6, N8

## Build order

1. Project setup: Django + DRF, Neon Postgres, Clerk, Next.js on Cloudflare
   Pages, GitHub repo with Actions
2. Recording page and Whisper transcription (C4, AI1, P1)
3. Personal-data masking with unit tests (AI2)
4. AI story generation with JSON validation and Groq fallback (AI4, AI6)
5. Follow-up question loop (C5, AI3)
6. Client review and approval page (C8, C9)
7. Admin review and Send to GitHub (A4, A5, A6, G1, G2)
8. Dashboards and charts (A2, A3, A7, A9, C10)
9. Privacy extras: delete, clean-up, export, backups (C11, P3–P5)
10. README with architecture diagram, screenshots and a live demo link