# Put Ballava online

About an hour, the first time. Everything here is free except the domain name.

| What | Tool | Cost | Why |
|---|---|---|---|
| Sign-in and database | **Supabase** | Free: 500 MB, 50,000 users a month | Email codes, password reset, Google, and a Postgres database, in one place |
| Hosting | **Render** | Free: 750 hours a month (enough for one app all month) | Runs your Dockerfile, updates itself when you push to GitHub, https included |
| Emails (sign-in codes) | **Resend** | Free: 3,000 a month, 100 a day | Supabase's own sender is only for testing |
| Google button | **Google Cloud** (sign-in only) | Free | "Continue with Google" |
| Domain and DNS | **Cloudflare** | About $10-11 a year for a .com | No one gives a .com away free. Until then: `something.onrender.com`, free |
| Keeping it awake | **UptimeRobot** or **cron-job.org** | Free | Free apps fall asleep; free databases pause |

You can stop after step 3 with a working website, and do the rest any day.

## 1. Supabase: sign-in and database (15 minutes)

1. Make an account at [supabase.com](https://supabase.com) and a **New project**. Region: **Southeast Asia (Singapore)**. Save the database password it gives you somewhere safe.
2. **Turn the Data API off:** Integrations > Data API > *Enable Data API* off. Ballava doesn't use it. (Ballava also locks its own tables every time it starts, so this is a second lock on the same door.)
3. Copy these into a private note. You need them in step 2:
   - **Connect** (top of the page) > the **Direct** tab > **Session pooler**: the address with port **5432** and `pooler` in it. [This link](https://supabase.com/dashboard/project/_?showConnect=true&connectTab=direct&method=session) opens it. Only see *Transaction pooler*? Copy that one and change `6543` to `5432`. Put your database password in its place in the address (forgot it? *Reset database password*, also under Connect). This is `DATABASE_URL`. If the password has symbols like `@ / # :`, choose a new one with only letters and numbers.
   - **Connect** also shows the project URL, like `https://abcd.supabase.co` (`SUPABASE_URL`).
   - **Settings > API Keys:** the **publishable** key (`SUPABASE_PUBLISHABLE_KEY`) and a **secret** key (`SUPABASE_SECRET_KEY`). Create them there if there are none yet.
4. **Authentication > Sign In / Providers > Email:** *Confirm email* **on** (important: it's what stops anyone claiming someone else's address), minimum password length **8**.
5. **Authentication > Emails > Templates:** replace *Confirm sign up* with [deploy/emails/confirm-signup.html](deploy/emails/confirm-signup.html) and *Reset password* with [deploy/emails/reset-password.html](deploy/emails/reset-password.html). They send a 6-digit code. They only take effect once you use your own email sender (step 4): [since June 2026](https://supabase.com/changelog/46599-changes-to-email-template-customisation-on-free-tier), new free projects on Supabase's own sender send its standard email, with a link instead of a code. Ballava works with both.

Never put the secret key or the database password in GitHub, in a message, or anywhere but Render's settings.

## 2. Render: hosting (15 minutes)

1. Push this project to GitHub (`main`). Nothing secret is in it: `.env`, `data/` and backups are left out.
2. Make an account at [render.com](https://render.com) with your GitHub, then **New > Blueprint** and choose the repository. It reads [render.yaml](render.yaml).
3. It asks for the values from step 1, plus `GEMINI_API_KEY`. Leave `SITE_DOMAIN` empty for now. **Apply**.
4. After some minutes your site is at `https://<name>.onrender.com`. Open it.
5. Back in Supabase, **Authentication > URL Configuration:** Site URL `https://<name>.onrender.com`, and add the redirect URL `https://<name>.onrender.com/**`.

Try it: create an account. Until you set up emails (step 4), Supabase's own sender only emails addresses in your Supabase team (2 an hour), so use the email you signed up to Supabase with.

## 3. Your admin, and the data you already have (10 minutes)

The online database is new and empty. On your computer, in this folder (PowerShell):

```powershell
# Save what is in your Docker app (it holds private family data: keep it safe)
docker compose exec -T web python manage.py export_data /tmp/backup.json
docker compose cp web:/tmp/backup.json backup.json

# Put it into Supabase. Paste your own DATABASE_URL between the quotes.
.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://postgres.xxxx:password@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py import_data backup.json
Remove-Item Env:DATABASE_URL
Remove-Item backup.json
```

It refuses if the online database already has accounts, so nothing is ever overwritten: do this **before** creating accounts online (or delete them first). Your admin sign-in comes along. Starting fresh instead? Run `manage.py createsuperuser` in place of `import_data`.

People who already had a Ballava account sign in online with the **same email** (create account, or Google): they get everything they had. Old passwords aren't used any more. Admins still sign in at `/admin` with their own password.

## 4. Your own domain (20 minutes, about $10-11 a year)

1. Buy it at [Cloudflare](https://www.cloudflare.com/products/registrar/) (sold at cost, privacy included). Check there that the name is free to buy. If `ballava.com` is taken, try `.in`, `.app`, `getballava.com`...
2. In Render: your service > **Settings > Custom Domains > Add** your domain (www is added for you).
3. In Cloudflare > DNS: remove any `AAAA` records, then add two records, both **DNS only** (grey cloud): `CNAME  @  <name>.onrender.com` and `CNAME  www  <name>.onrender.com`. Under SSL/TLS choose **Full**.
4. Wait for Render to say *Verified* and *Certificate issued*. https is automatic.
5. In Render > **Environment**, set `SITE_DOMAIN` to your domain (`ballava.com`). WhatsApp vote links use it from then on.
6. In Supabase > Authentication > **URL Configuration**: Site URL `https://ballava.com`, and add the redirect URL `https://ballava.com/**`.

**Emails from "Ballava", to everyone, without a domain:** make a new Gmail address just for this, switch on 2-Step Verification, and create an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). In Supabase > [SMTP settings](https://supabase.com/dashboard/project/_/auth/smtp): sender name `Ballava`, sender email and username = that Gmail address, host `smtp.gmail.com`, port `465`, password = the app password without spaces. Gmail allows about 500 emails a day. Set the subjects under Email Templates too.

**Emails from your own address** (needs the domain): make an account at [resend.com](https://resend.com), add the domain and copy the DNS records it shows into Cloudflare. Then in Supabase > Authentication > **Emails > SMTP Settings**: host `smtp.resend.com`, port `465`, user `resend`, password = a Resend API key, sender `hello@ballava.com`. Supabase then allows 30 emails an hour; raise it under *Rate Limits* when you need to. **Then paste the two email templates (step 1) again**: they work from now on.

## 5. "Continue with Google" (10 minutes)

1. [console.cloud.google.com](https://console.cloud.google.com) > new project > **Google Auth Platform**. Fill in the app name and your email, audience **External**.
2. **Clients > Create > Web application.** Authorized JavaScript origins: your site's address. Authorized redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback` (Supabase shows it on its Google page).
3. Supabase > Authentication > **Sign In / Providers > Google**: switch on, paste the client ID and secret.
4. In Google, **Publish app**, so anyone can use it. (It may ask for a link to a privacy page.)

The button appears on the sign-in screen by itself within 5 minutes.

## 6. Keep it awake

A free Render app sleeps after 15 minutes without visitors, and takes up to a minute to wake. A free Supabase project pauses after a week without use. One free monitor fixes both: at [uptimerobot.com](https://uptimerobot.com) or [cron-job.org](https://cron-job.org), open `https://your-address/api/health` every 10 minutes. It also emails you when the site is down. (Render's rules don't mention such pings either way. If they ever mind, the app simply sleeps.)

## What free doesn't include

- **Backups.** Supabase's free plan has none. Every week or so, set `DATABASE_URL` as in step 3, run `.venv\Scripts\python manage.py export_data backup.json`, and keep the file somewhere private.
- **Speed.** Render's free plan has a tenth of a processor. Pages are quick; planning a week takes about 3 seconds; the first visit after sleeping, up to a minute. Their paid plans remove the sleeping.
- **A promise.** Free services can be slow, paused or changed. When real families depend on Ballava, pay for hosting first, then the database.

## If something isn't right

| You see | Do this |
|---|---|
| The deploy fails with `DATABASE_URL must look like...` or a password error | Use the **Session pooler** address, with your password filled in |
| `Set DJANGO_SECRET_KEY` | Render > Environment: add `DJANGO_SECRET_KEY`, any 50+ random characters |
| `SUPABASE_PUBLISHABLE_KEY holds a SECRET key` | The two keys are swapped. Make a new secret key in Supabase, since that one was in the wrong place |
| "Emails can't be sent to this address yet" | Step 4, *Emails from "Ballava"* |
| Google says `redirect_uri_mismatch` | The redirect URI in step 5 must match Supabase's exactly |
| After Google you land on the wrong address | Supabase > URL Configuration: add your address with `/**` at the end |
| "An account with this email already exists" | Supabase > Email provider: switch *Confirm email* on |
| Changes don't show | Render > your service > Events: wait for *Deploy live*, then reload |

Moving elsewhere later is easy: it's an ordinary Docker image and an ordinary Postgres database. Any host that runs Docker works with the same settings (`PORT`, `DJANGO_SECRET_KEY`, `DJANGO_SECURE=1`, `DATABASE_URL`, `SITE_DOMAIN`, and the Supabase ones).
