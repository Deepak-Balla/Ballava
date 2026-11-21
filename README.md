# Ballava: START HERE

*Cooks with you today. For you tomorrow.*

Ballava is a web app that runs in any browser and installs on a phone like a normal app. It:

- **plans the whole week** in one tap, with no repeated dishes, and lets you lock, swap or vote on meals
- remembers what's in your kitchen and warns you before things spoil
- suggests dishes from what you already have (103 everyday recipes, mostly Indian)
- understands family needs: veg, Jain, no onion or garlic, diabetic, fasting, allergies, spice level, age and health goals
- **one meal, many plates**: tells you how to adjust one dish for each family member
- **food diary and dashboard**: logs what you made and spots what's missing, like greens or protein
- tiffin planner, prep reminders, leftover ideas and fasting days
- guides you while cooking: big steps, timers, a **pressure-cooker whistle counter**, read-aloud and hands-free voice
- **Bachao!** mode rescues dishes (too salty, burnt, split kadhi…) and says honestly when food isn't safe
- **family accounts**: one shared kitchen, plan and list across phones, by family code
- **admin portal** at `/admin` for recipes, ingredients, Bachao fixes, announcements and festivals
- optional AI (needs an AI key): **Ballava Chef**, a chat for any recipe by name, calories and swaps, and **Recipe Studio**, which gets or invents a recipe and reads a photo of your fridge

**The app is written in Python (Django).** Only the phone screens are JavaScript (React), because browsers can only run JavaScript.

---

## 1. The tools, explained

| Tool | What it is | What it does in Ballava | Where |
|---|---|---|---|
| **Python** | The programming language | All the thinking: matching dishes, weekly plans, no-repeat rules, family diets, the dashboard, Chef's built-in answers | `kitchen/engine.py`, `kitchen/planner.py` |
| **Django** | Python's most popular web framework | The web server, the API the phone screens call, sign-in, the database layer and the **admin portal** | `config/`, `kitchen/` |
| **Django admin** | The admin portal that comes with Django | Lets admins add recipes, ingredients, fixes, announcements and festivals, and manage users | `/admin`, set up in `kitchen/admin.py` |
| **SQLite** | A database stored in one file | Keeps accounts and each family's data | `data/db.sqlite3` (**back this up**) |
| **pytest** | Python's test runner | Runs over 150 automatic checks | `kitchen/tests/` |
| **Playwright** | Remote control for a real browser | Opens Chrome and clicks through the whole app like a person | `kitchen/tests/test_e2e_*.py` |
| **google-genai** | Google's official Python library | Talks to Gemini for Ballava Chef and Recipe Studio when `AI_PROVIDER=gemini` | `kitchen/ai.py` |
| **anthropic** | Anthropic's official Python library | Talks to Claude for Ballava Chef and Recipe Studio when `AI_PROVIDER=claude` | `kitchen/ai.py` |
| **WhiteNoise** | A small Django add-on | Serves the phone app's files quickly | `config/settings.py` |
| **React** (JavaScript) | A library for building screens | Every button and screen on the phone. It asks Python whenever it needs thinking done | `src/` |
| **Node.js + esbuild** | JavaScript tools | Packs `src/` into `dist/`. **Only needed if you change the screens** | `build.mjs`, `package.json` |
| **Docker** *(optional)* | Packs the whole app into one "container" | Runs Ballava the same way on any computer or server, with one command | `Dockerfile`, `docker-compose.yml` |
| **gunicorn** | A production web server for Python | Runs Django inside Docker (and on live servers). Not used on Windows | `Dockerfile` |

**Do you need Docker?** No. On your own computer, plain Python (step 3) is simplest. Docker is handy for putting Ballava online, or for running it exactly the same way everywhere (step 6).

**Words you'll see:**
- **Terminal**: a window where you type commands. On Windows, use **PowerShell**.
- **Virtual environment (`.venv`)**: a private folder of Python libraries just for Ballava, so it doesn't clash with other projects.
- **localhost:8000**: "this computer, door number 8000". Only you can see it until you put the app online.
- **API**: the back door where the phone screens ask Django questions, like `/api/brain/plan`.
- **Migration**: Django's instructions for creating or updating database tables. `migrate` applies them.

---

## 2. Install Python (one time)

1. Go to **https://www.python.org/downloads/** and install Python **3.12 or newer**. On Windows, tick **"Add python.exe to PATH"**.
2. Open PowerShell and type `python --version`. You should see something like `Python 3.13.x`.

## 3. Run Ballava (without Docker)

Open PowerShell **inside the Ballava folder** (in File Explorer, click the address bar, type `powershell`, press Enter).

**First time only:**
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
```
- The first line creates the virtual environment, and the second installs Django and the other libraries into it.
- `migrate` creates the database in `data/db.sqlite3`.
- `createsuperuser` creates your **admin login**. Use your email as the username. It asks for the password twice and **hides what you type** (that's normal). Admin passwords need at least 12 characters.

**Every time:**
```
.venv\Scripts\python manage.py runserver
```
Then open **http://localhost:8000** (the app) or **http://localhost:8000/admin** (the admin portal). Press **Ctrl + C** in PowerShell to stop.

> **Tip:** you can "activate" the environment once with `.venv\Scripts\Activate.ps1`, and then just type `python manage.py runserver`. If PowerShell refuses with a "running scripts is disabled" error, keep using the full `.venv\Scripts\python` form shown above.

**Use it on your phone (same Wi-Fi):** run `.venv\Scripts\python manage.py runserver 0.0.0.0:8000`, find your computer's address with `ipconfig` ("IPv4 Address", like `192.168.1.5`), and open `http://192.168.1.5:8000` on your phone. Voice features and "Add to Home screen" need **https**, so they fully work once the app is online.

**First time in the app:** create an account (or tap **Continue without an account**), then tap **Try with a sample kitchen**.

**The sign-in page has three tabs:** **Sign in** and **Create account** (by email, or by phone when SMS is set up) for families, and **Admin**, which signs admins straight into the admin portal.

**The app opens on the Dashboard**, which greets you by name ("Good morning, Deepak"; guests can tell it their name) and shows today's menu, shortcuts, what to use up soon and your calories.

**The navigation bar:** **Dashboard** (the first screen: greeting, today, calories, every meal with its calories, and the food diary) · **Cook** (what to cook now) · **Plan** (the week) · **🧑‍🍳 Chef** (in the middle: your AI chef, on any screen) · **Kitchen** (what you have) · **List** (shopping) · **More** (saved dishes, family, Bachao, Recipe Studio, account).

**On a computer** the bar becomes a sidebar on the left, pages use the full width (dishes and plans in several columns, recipes with ingredients and steps beside the details), and on wide screens Chef opens as a panel docked on the right. Phones look the same as before.

## 4. Admin logins and passwords

- **Create an admin:** `.venv\Scripts\python manage.py createsuperuser`
- **Forgot an admin password?** `.venv\Scripts\python manage.py changepassword you@example.com` (it asks for the new one twice, hidden). Old passwords can't be looked up, only replaced.
- **Change it while signed in:** in the admin portal, click **Change password** at the top right.
- **Stop someone signing in:** in the admin portal, open **Users**, untick **Active**, and save. They are signed out at once.

What the admin portal does:
- **Dashboard:** numbers at a glance, quick actions, recipes waiting for review, recent changes, and AI use for the last 7 days. The bar under the header jumps to every section.
- **Recipe book:** *every* recipe in one list, including the 103 built-in ones that live in the code, with search, filters (meal, diet, built-in or added, live, hidden or draft) and calories per serving. Click a dish to see everything about it: ingredients with grams and calories for each line, steps, allergens, Jain and onion/garlic checks. From there, **Edit** (for a built-in dish this starts your own copy), **Hide from users**, or **Open in the app**.
- **Ingredients:** every ingredient with calories, protein, carbs, fat and fibre per 100 g, what a cup or piece weighs, and how many recipes use it. When you add an ingredient, fill in its nutrition so recipes count its calories.
- **Recipes:** add new ones, or pick **Start from a built-in recipe** to change an existing one. Every edit starts as a *draft*. Select it in the list and use the actions menu: **Send to review**, then **Publish**. Recipes that break the safety rules (for example "gluten-free" with atta, or meat without a food-safety note) can't be published. Users keep seeing the last published version while you edit.
- **Hidden recipes**, **Ingredients**, **Rescues** (Bachao fixes), **Announcements**, **Festivals**: changes reach users straight away.
- **Audit log:** every change, with who made it and when.
- **Privacy:** admins see accounts only. Family kitchens, diets, health goals and meal diaries are never shown in the portal.

After 5 wrong admin passwords, that login is locked for 15 minutes.

## 5. Test that everything works

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```
This runs **190 checks** in about two minutes: the recipe book has no typos, a vegetarian never sees chicken, a week has 21 different meals, families can't see each other's data, admins can't see family health details, wrong passwords get locked out, and much more. You should see `190 passed`. The tests never call a real AI or use your keys.

**Real-browser checks (about a minute):**
```
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m pytest -m e2e
```
This opens a hidden Chrome on a phone-sized screen and uses the whole app like a family would: sign up, plan the week, cook with the whistle counter, log meals, join a family on a second phone, edit offline, vote, and publish a recipe as an admin. It also tries hands-free cooking with a pretend microphone, a fridge photo with a pretend AI, and the computer layout. Screenshots go to `test-screenshots/`. You should see `48 passed`.

> The tests switch AI **off** on purpose (so they never use your key or your free limit). That's why the test screenshots say "AI is off"; your own app is not affected.

## 6. Run Ballava with Docker (optional)

1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ and start it.
2. In the Ballava folder:
   ```
   docker compose up --build
   ```
   The first build takes a few minutes. Then open **http://localhost:8000**.
3. Create your admin login (in a second PowerShell window):
   ```
   docker compose exec web python manage.py createsuperuser
   ```
4. Stop it with **Ctrl + C**, or `docker compose down`.

Your data lives in a Docker **volume** called `ballava-data`, so it survives restarts and rebuilds. `docker compose down -v` **deletes** it, so be careful with `-v`.

What the Docker setup does: it builds the phone screens with Node.js, installs Python and the libraries, then runs Django with **gunicorn** (a production web server) as a normal (non-root) user. It also updates the database tables each time it starts, and checks every 30 seconds that the app is healthy.

## 7. Change the app

- **Add or change a recipe:** `kitchen/data/recipes.py` or `recipes_more.py` (the format is explained at the top of the file), or use the admin portal with no code at all. Then run `pytest`. It tells you if a recipe has a typo or a wrong tag.
- **Add an ingredient or a local name:** `kitchen/data/ingredients.py`, as comma-separated other names. Give every new ingredient a row in `kitchen/data/nutrition.py` too (calories per 100 g and what a cup or piece weighs); a test checks that none are missing.
- **Add a Bachao fix:** `kitchen/data/rescue.py`.
- **Change how dishes are chosen:** `kitchen/engine.py` (matching) and `kitchen/planner.py` (weekly plans, no repeats, family goals, dashboard).
- **Change a screen or colours:** files in `src/` (colours are at the top of `src/styles.css`). This needs **Node.js** (https://nodejs.org, LTS). Once: `npm install`. Then `npm run build` (or `npm run dev` to rebuild every time you save). Refresh the browser to see changes.
- **Change the database tables:** edit `kitchen/models.py`, then run `python manage.py makemigrations` and `python manage.py migrate`.

## 8. Switch on AI (optional)

**What AI adds:**
- **Ballava Chef (🧑‍🍳 Chef, in the middle of the navigation bar on a phone, at the top of the sidebar on a computer):** a short chat window that knows your kitchen, your family's needs (without their names), recent meals, the plan, your saved dishes and the whole recipe book with calories. It also knows which screen and recipe you're on.
  - **Ask for any dish by name and you get exactly that dish.** "Chicken biryani" gives chicken biryani, never something else. If it's in the recipe book you get that recipe; if not, the AI writes it. Either way you see **what you're missing**, with **🛒 Add missing** for your shopping list. If it breaks a family rule (for example meat for a vegetarian), you still get it, with a clear warning.
  - Every answer's dishes come with **Open recipe**, **🛒 Add missing**, **📅 Tomorrow** (adds it to tomorrow's plan) and **♡ Save**, plus suggested follow-up questions.
  - **🕘 Your chats:** every conversation is saved. When you're signed in they're kept in your account (private to you, not shared with the family or shown to admins), so they survive signing out and follow you to your other phones and computers. Without an account they stay on that device. Open an old one to carry on (a new chat shows your recent ones), start a **＋ New chat**, or delete them.
  - 📷 **Photo of your fridge:** tap 📷, then **Take a photo** (a phone opens its camera; a computer with a webcam opens a live camera in the app) or **Choose a photo**. The AI names what it sees and the items go **straight into your kitchen**, with **Undo**. The same 📷 button is in the **Kitchen** tab, next to 🎤, and in Recipe Studio.
  - 🎤 listens, 🔊 reads answers aloud. The window shows which AI is connected, and checks again each time it opens.
- **Recipe Studio (More → Recipe Studio, or the button on the Cook screen):** name a dish for its exact recipe, or leave it empty to invent one from your kitchen for a chosen meal. Dishes already in the recipe book open straight away, with no AI needed.
- **Calories for food from outside:** on the Dashboard, **✨ Estimate** asks the AI for the calories of a meal like "pizza from outside" (or type them yourself).
- Every AI answer is checked before you see it: only real recipes are linked, and the AI never *suggests* a new dish that breaks a family rule (diet, Jain, allergies, diabetes). A dish you ask for by name always comes, with a clear warning if it breaks one. Diet and allergens of AI recipes are worked out from the ingredients, not just from what the AI claims, and calories are counted by Ballava when it knows the ingredients.

**Without AI** (or when the free limit is used up), Chef still answers simple questions on its own: any recipe-book dish by name with what you're missing, what to cook, tiffin ideas, the plan, calories of any dish or ingredient, protein-rich or light ideas, and fixes for common mistakes.

**The Dashboard tab** (works with or without AI):
- **Today:** a ring showing calories against your daily goal (default 1,800 kcal per person; tap to change), plus protein, carbs and fat, and the calories of today's and tomorrow's plan.
- **Over 7, 14 or 30 days:** average calories and protein a day, a calories-per-day chart with your goal line, where calories come from (protein, carbs, fat), and the average for each meal.
- **Every meal you logged, by name, with its calories**, and the dishes adding the most calories.
- **A lighter swap** that suits your family, and a WhatsApp summary.
- The **Food diary** is the second view on the same tab.
- Calories are one serving of each logged meal: a rough guide per person, not medical advice.

AI can use either of two providers. You choose with one line in `.env`, and can switch any time:

| `AI_PROVIDER=` | AI | Cost | Key setting | Get a key |
|---|---|---|---|---|
| `gemini` | Google Gemini | **Free tier** (daily limits) | `GEMINI_API_KEY` | https://aistudio.google.com/apikey (sign in with a Google account, click **Create API key**) |
| `claude` | Anthropic Claude | Paid (about a rupee or two per recipe) | `ANTHROPIC_API_KEY` | https://platform.claude.com (add billing, then **API Keys**) |

1. If you don't have a `.env` file yet, copy `.env.example` to a new file named `.env` in the Ballava folder.
2. In `.env`, set `AI_PROVIDER=gemini` (or `claude`) and paste the key after the matching `..._API_KEY=`. Save.
3. Restart the server (Docker: `docker compose up -d --force-recreate`). In the app, tap **🧑‍🍳 Chef** and ask for any recipe, or open **More → Recipe Studio**.

To switch later, change `AI_PROVIDER` and restart. You can keep both keys in `.env`; only the chosen one is used. To pick a different model, set `GEMINI_MODEL` or `ANTHROPIC_MODEL`.

Good to know:
- **Free tier and privacy:** on Gemini's free tier, Google may use what Ballava sends (kitchen items, and family diet needs like allergies or diabetes) to improve its products. Before real families use your online app, switch to `claude`, or to Gemini's paid tier.
- **Free limits:** when the day's free Gemini limit is used up, Chef says so and the rest of the app keeps working.
- Keep keys secret: never share `.env` or put keys in the code. Keys stay on the server and browsers never see them.
- Each family can make at most 10 AI requests per minute (`AI_RATE_LIMIT`).
- Both AIs get the same safety rules, and their answers go through the same checks. With Claude, if the AI declines a request for safety reasons, Anthropic automatically retries it on a suitable fallback model.

**Chef or Recipe Studio?** Both use the same AI. **Chef** is a conversation: ask anything, follow up, get several ideas, plan and shop from the answers. **Recipe Studio** (More → Recipe Studio) is the one-tap form: type a dish (or nothing), pick a meal, and get one full recipe card, plus the fridge-photo scanner.

**Hands-free cooking** (in cook mode, Chrome or Edge): tick **🎤 Hands-free**, then say **"next"**, **"back"**, **"repeat"**, **"timer 5 minutes"** (or just "timer" on a step with a time), **"whistle"** (counts a pressure-cooker whistle), **"done"** on the last step, **"stop"** to stop reading, or **"help"**. Hindi works too: aage, peeche, dobara, seeti. Every new step is read aloud, a box shows when it's listening and what it heard, and it ignores its own voice reading the steps. The microphone works on `localhost` and on `https` sites; on a plain `http://192.168…` address, phones block it.

## Your data: kept in your account, for 6 months

- **Everything you do is saved in your account:** kitchen, family, plan, shopping list, food diary, saved (❤️) dishes, AI recipes, your calorie goal and name, and your chats with Chef. Sign out and in again, or use another phone or computer, and it's all there. (Signing out clears the phone itself, because phones get shared.)
- **After 6 months it goes:** each diary meal, saved dish, AI recipe (unless still saved) and chat is deleted 6 months after its date, and a family account nobody has used for 6 months is deleted with its data. Your kitchen, family and plan stay while you use Ballava. Admin accounts are never removed.
- This happens **by itself once a day**. To run it now: `.venv\Scripts\python manage.py cleanup_old_data` (Docker: `docker compose exec web python manage.py cleanup_old_data`). Change the period with `DATA_RETENTION_DAYS` in `.env` (`0` keeps everything). The admin dashboard shows the last clean-up.

## 9. Phone sign-in

Phone sign-in needs an SMS service.
- **To try it on your computer:** add `OTP_DEV_MODE=1` to `.env`, and the code appears on screen instead of by SMS. This is ignored on a live site.
- **For real SMS:** add your Twilio details to `.env` (see `.env.example`). Sending SMS to India also needs DLT registration.

## 10. Put it online

Any host that runs Docker or Python works, for example Render, Railway, Fly.io, or a small cloud server.
- **Easiest:** deploy with the included `Dockerfile`.
- **Environment variables:** `DJANGO_ALLOWED_HOSTS=yourdomain.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com` and `DJANGO_SECURE=1`. For Ballava Chef and Recipe Studio, add `AI_PROVIDER` and its key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`) in the host's settings page. Don't upload `.env`.
- **Keep your data:** the host must give you a **permanent disk** mounted at `/data` (Docker), or set `DATA_DIR` to one. Without it, accounts vanish on every restart.
- Check your settings with `python manage.py check --deploy`.
- Hosts give you an **https** address, so phone install, microphone and offline mode all work.

## 11. Project map

```
ballava/
├── README.md              ← this guide
├── manage.py              ← Django's command line (runserver, migrate, createsuperuser…)
├── requirements.txt       ← Python libraries the app needs
├── requirements-dev.txt   ← extra libraries for testing
├── .env.example           ← settings template (copy to .env)
├── Dockerfile, docker-compose.yml, .dockerignore   ← Docker set-up (optional)
├── config/                ← Django settings and web addresses
│   ├── settings.py
│   └── urls.py            ← /admin, /api/…, and the app itself
├── kitchen/               ← the Ballava Django app (all Python)
│   ├── data/              ← recipes, ingredients (with Hindi/Telugu/Tamil names), nutrition per 100 g, Bachao fixes
│   ├── templates/, static/ ← the admin portal's look, dashboard, recipe book and ingredient pages
│   ├── engine.py          ← understanding what people type, matching dishes, family rules
│   ├── planner.py         ← weekly plans, no repeats, goals, plates, tiffins, dashboard, Chef's built-in answers (when AI is off)
│   ├── nutrition.py       ← calories: turns "1/2 cup", "2 cloves" into grams, then kcal per serving
│   ├── assistant.py       ← what Ballava Chef is told about the family, and the checks on its answers
│   ├── api.py, urls.py    ← the API the phone screens call
│   ├── models.py          ← database tables
│   ├── admin.py           ← the admin portal
│   ├── ai.py              ← Ballava Chef and Recipe Studio (Gemini or Claude, chosen by AI_PROVIDER)
│   ├── security.py        ← rate limits and phone codes
│   └── tests/             ← pytest checks and real-browser tests
├── src/                   ← the phone screens (React, JavaScript)
├── public/                ← page skeleton, icons, offline support
├── dist/                  ← the built screens Django serves (made by `npm run build`)
├── data/                  ← the database and secret key (created when you run it; back it up)
└── legacy_js/             ← the old JavaScript server, kept for reference (safe to delete)
```

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| `python` is "not recognised" | Reinstall Python with **Add python.exe to PATH** ticked, then close and reopen PowerShell. |
| "Error: That port is already in use" | Ballava is already running in another window. Close it, or use another port: `runserver 8001`. |
| "No module named django" | You're not using the virtual environment. Use `.venv\Scripts\python …`, or run the install step again. |
| "no such table" | Run `.venv\Scripts\python manage.py migrate`. |
| The page says "Loading recipes…" forever | The server isn't running, or the phone can't reach it. Start `runserver` and refresh. |
| Typing ingredients doesn't work offline | Reading typed words happens on the server. Offline, pick items from the list instead. |
| Forgot the admin password | `.venv\Scripts\python manage.py changepassword you@example.com` |
| Chef says "AI is off", or Recipe Studio says it needs AI | First reload the page (or tap **Check again**): the app may have opened while the server was restarting. If it still says so, check `.env` has `AI_PROVIDER=gemini` with `GEMINI_API_KEY=...` (or `claude` with `ANTHROPIC_API_KEY=...`), then restart the server. |
| Chef says "free AI limit is used up" | Gemini's free daily limit is reached. Wait (it resets daily), or switch to `AI_PROVIDER=claude`. |
| Page looks old after an update | Refresh hard: **Ctrl + Shift + R**. |
| "no such column" after an update | Run `.venv\Scripts\python manage.py migrate` (Docker does this by itself when it starts). |

---

**Safety notes built into Ballava:** cooked rice and meat warnings on the risky dishes, steaming sprouts, a "when in doubt, throw it out" rescue entry, raw sprouts hidden in pregnancy, and AI recipes always come with food-safety rules. Allergy matching and health goals are helpers, not guarantees or medical advice. Always read packaged food labels and follow your doctor.
