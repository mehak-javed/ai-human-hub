# Setting up the GitHub App

AI Human Hub sends approved stories to GitHub as a **GitHub App**. You create
the App once; then you install it on each client's private repository.

## 1. Create the App

1. On GitHub, go to **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Fill in:
   - **GitHub App name:** something unique, for example `ai-human-hub-yourname`.
     The URL-friendly version of this name is the **slug** (shown later in the
     App's public link, `github.com/apps/<slug>`).
   - **Homepage URL:** `https://ai-human-hub.vercel.app`
   - **Webhook:** leave it for now; step 5 turns it on.
3. **Repository permissions**, and nothing else:
   - **Contents:** Read and write
   - **Issues:** Read and write
   - **Metadata:** Read-only (set automatically)
4. **Where can this GitHub App be installed?** Only on this account.
5. Press **Create GitHub App**.

## 2. Get the App's ID and private key

1. On the App's page, copy the **App ID** (a number).
2. Scroll to **Private keys → Generate a private key**. A `.pem` file
   downloads. Treat it like a password: never commit it, paste it in chat or
   screenshot it.
3. Turn the key into a single line for the hosting dashboard:

   ```bash
   base64 -i ~/Downloads/your-app-name.*.private-key.pem | tr -d '\n' | pbcopy
   ```

   The key is now on your clipboard.

## 3. Add the settings to Render

In the Render dashboard → **ai-human-hub-api → Environment**, add:

| Key | Value |
|---|---|
| `GITHUB_APP_ID` | the App ID |
| `GITHUB_APP_PRIVATE_KEY` | paste from the clipboard (step 2.3) |
| `GITHUB_APP_SLUG` | the App's slug |

Save; Render redeploys. Then delete the downloaded `.pem` file, or move it
somewhere safe outside the project folder.

## 4. Install the App on a client's repository

1. Create a **private** repository for the client, with a README so it has a
   `main` branch.
2. Open `https://github.com/apps/<slug>/installations/new`, choose
   **Only select repositories**, and pick that repository.
3. In AI Human Hub, open the project in **Team review**, enter the
   repository as `owner/name` and press **Connect repository**.

## 5. Turn on progress updates (webhook)

When the team closes an issue, the client's progress bar should move. GitHub
tells us through a webhook.

1. Make a random secret and copy it (in your own terminal):

   ```bash
   openssl rand -hex 32 | pbcopy
   ```

2. In the App's settings (**General** tab), under **Webhook**:
   - tick **Active**
   - **Webhook URL:** `https://ai-human-hub-api.onrender.com/api/github/webhook/`
   - **Secret:** paste (⌘V)
   - press **Save changes**
3. **Permissions & events** tab → **Subscribe to events** → tick **Issues** →
   **Save changes**. (Issues is listed only because the App already has
   Issues permission.)
4. In Render → **ai-human-hub-api → Environment**, add
   `GITHUB_WEBHOOK_SECRET` with the same value (paste again; don't copy
   anything else in between). Save, rebuild and deploy.
5. Check it: the App's **Advanced** tab lists recent deliveries. The first
   `ping` may fail if the API was asleep; press **Redeliver** once it's awake.
   Progress still catches up within a minute when a project is opened, even
   if a delivery is lost (ADR 0009).
