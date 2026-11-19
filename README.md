# AI Human Hub

Clients often struggle to explain what they want built, and developers lose days
chasing missing details. AI Human Hub lets a client describe their project by
voice. An AI interviewer asks follow-up questions to fill the gaps, then drafts
user stories with acceptance criteria and priorities. Nothing reaches the
development team until a human has approved it: first the client, then an admin.
Approved stories are pushed to a private GitHub repository as issues.

## How it works

1. **Record**: the client explains their idea by voice in the browser.
2. **Transcribe**: speech is converted to text; the audio is discarded immediately.
3. **Mask**: names, emails, phone numbers and addresses are replaced with tags
   such as `[NAME]` before any text is sent to an AI model.
4. **Interview**: the AI checks the transcript for gaps (users, roles, data,
   payments, login, deadlines) and asks up to 10 follow-up questions.
5. **Draft**: the AI writes user stories as validated JSON, grouped into Must,
   Should and Nice to have.
6. **Client approval**: the client edits, approves or sends the stories back
   with a note.
7. **Admin approval**: an admin reviews, edits, merges or rejects stories.
8. **Ship**: approved stories become GitHub issues, and a `requirements.md`
   file is committed to the client's private repo.

## Design principles

- **Human in the loop**: AI drafts, people decide. Nothing is pushed without
  client and admin approval.
- **Privacy by design**: audio is never stored; personal data is masked before
  any AI call; clients can delete their project at any time.
- **Least privilege**: every API request checks the user's role and project
  ownership; only private GitHub repositories can be connected.
- **Free-tier first**: runs within free tiers, with automatic fallback to a
  second AI provider when limits are reached.

## Tech stack

| Layer | Technology |
|---|---|
| Backend and API | Python, Django, Django REST Framework |
| Admin dashboard | Django Admin with custom chart pages |
| Frontend | Next.js (React, TypeScript) on Cloudflare Pages |
| Database | PostgreSQL (Neon) |
| Authentication | Clerk |
| Speech-to-text | Whisper via Cloudflare Workers AI |
| LLM | Cloudflare Workers AI (Llama/Qwen), Groq as fallback |
| Integration | GitHub App (issues, commits, project boards) |
| Testing and CI | pytest, GitHub Actions |

## Repository structure

    backend/     Django + DRF API and admin
    frontend/    Next.js client application
    docs/        Use cases and Architecture Decision Records (ADRs)

## Roadmap

- [ ] Project setup: Django + DRF, Postgres, Clerk, Next.js, CI
- [ ] Voice recording and transcription
- [ ] Personal-data masking with unit tests
- [ ] AI story generation with JSON validation and provider fallback
- [ ] Follow-up question loop
- [ ] Client review and approval
- [ ] Admin review and push to GitHub
- [ ] Dashboards and charts
- [ ] Data deletion, retention clean-up, export and backups

## Documentation

- [Use cases](docs/use-cases.md)
- [Architecture Decision Records](docs/adr/)

## Status

In development, MVP in progress.

## License

[MIT](LICENSE)