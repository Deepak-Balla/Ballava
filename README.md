# Ballava: START HERE

*Cooks with you today. For you tomorrow.*

Ballava is a web app that runs in any browser and installs on a phone like a normal app. It:

- remembers what's in your kitchen and warns you before things spoil
- suggests dishes from what you already have (103 everyday recipes, mostly Indian)
- tells you the **one thing to buy** that unlocks the most dishes
- guides you while cooking: big steps, timers, a **pressure-cooker whistle counter**, read-aloud and hands-free voice
- **Bachao!** mode rescues dishes (too salty, burnt, split kadhi…) and says honestly when food isn't safe
- understands family needs: veg, Jain, no onion or garlic, diabetic, fasting, allergies, spice level
- keeps a shopping list you can share on WhatsApp
- optional **AI Chef**: invents new dishes and reads a photo of your fridge (needs an AI key)
- **plans the whole week** in one tap, with no repeated dishes, and lets you lock, swap or vote on meals
- **food diary and dashboard**: logs what you made and spots what's missing, like greens or protein
- **one meal, many plates**: tells you how to adjust one dish for each family member
- **tiffin planner, prep reminders, leftover ideas and fasting days**
- **family accounts**: one shared kitchen, plan and list across phones, by family code
- **admin portal** at `/admin` for recipes, ingredients, Bachao fixes, announcements and festivals

You don't need to be technical to run it. Follow the steps below in order.

---

## 1. The tools, explained simply

Think of the app as a restaurant:

| Part of the restaurant | Tool we use | What it does here | Do you need to install it? |
|---|---|---|---|
| The **building** everything runs in | **Node.js** | Runs JavaScript on your computer, both our server and our build tools. | **Yes.** This is the only thing to install. |
| The **menu card** customers see | **HTML** (`public/index.html`) | The basic page skeleton. | No, it's a file. |
| The **interior decoration** | **CSS** (`src/styles.css`) | Colours, sizes, layout, how it looks on phones. | No, it's a file. |
| The **waiters** who respond to you | **JavaScript + React** (`src/`) | Every button, screen and list. React builds screens from small reusable pieces ("components"). | Only if you change the app (step 5). |
| The **kitchen brain / head chef** | **JavaScript** (`shared/`) | The recipe book, ingredient names in Hindi, Telugu and Tamil, the matching logic, and Bachao fixes. Shared by the app, the server and the tests. | No. |
| The **back office** | **Node.js server** (`server/`) | Sends the app to browsers and answers questions at `/api/...`. Built only from Node's own parts, so nothing to install. | No. |
| The **packer** who prepares food for delivery | **esbuild** (`build.mjs`) | Bundles all of `src/` into two small files in `dist/` that browsers load quickly. | Only if you change the app. |
| The **food inspector** | **Node test runner** + **Playwright** (`tests/`) | Checks the brain and server automatically, then opens a real hidden Chrome and clicks through the whole app like a person. | Playwright only for the browser test. |
| The **guest chef** (optional) | **Claude AI** by Anthropic | Invents new recipes and reads fridge photos. | No, but you need an API key. |
| **Memory** | The browser's **localStorage** | Your kitchen, family, list and history are saved on *your* phone or computer. No account, no database. | No. |
| **Phone app wrapper** | **PWA** (`manifest.webmanifest`, `sw.js`) | Lets people "Add to Home screen" and open it offline. | No. |

**Words you'll see:**
- **Terminal** (Mac: "Terminal"; Windows: "Command Prompt" or "PowerShell"): a window where you type commands.
- **npm**: comes with Node.js. `npm start` means "run the start command written in `package.json`".
- **localhost:3000**: "this computer, door number 3000". Only you can see it until you put the app online.
- **API**: a back door where the app asks the server questions, like `/api/chat`.

---

## 2. Install Node.js (one time, about 5 minutes)

1. Go to **https://nodejs.org** and download the **LTS** version (any version 20.12 or newer works).
2. Install it like any program (Next, Next, Finish).
3. Open a Terminal and type `node -v`, then press Enter. If you see something like `v22.x.x`, it worked.

## 3. Run the app (every time)

1. Unzip the `ballava` folder somewhere easy, such as your Desktop.
2. Open a Terminal **inside that folder**:
   - **Windows:** open the folder, click the address bar, type `cmd`, press Enter.
   - **Mac:** right-click the folder and choose **New Terminal at Folder** (or type `cd ` and drag the folder into Terminal).
3. Type:
   ```
   npm start
   ```
4. You'll see **"Ballava is running! Open http://localhost:3000"**. Open that address in Chrome.
5. To stop: click the Terminal and press **Ctrl + C**.

The app is already built, so `npm start` works without installing anything else.

**First time in the app:** create an account (or tap **Continue without an account**), then tap **"Try with a sample kitchen"** to see it working instantly, or **"Add what I have"** and type something like `2 tamatar, pyaz, paneer, leftover rice`.

### Use it on your phone (same Wi-Fi)
1. Find your computer's local address: Windows: type `ipconfig` and look for "IPv4 Address", such as `192.168.1.5`. Mac: System Settings → Wi-Fi → Details → IP address.
2. On your phone's browser, open `http://192.168.1.5:3000` (use your number).
3. Voice features and "Add to Home screen" need a secure **https** address, so they fully work once the app is online (step 7).

## 4. Test that everything works

**Quick check (about 2 seconds, no install needed):**
```
npm test
```
This runs **more than 90 automatic checks**. For example: every recipe uses real ingredients, "leftover chawal" isn't mistaken for raw rice, a vegetarian family member never sees chicken, a nut allergy hides dishes that need nuts, the server can't be tricked into showing private files, and AI errors are handled politely. You should see `fail 0` at the end.

**Full browser check (about a minute, one-time install):**
```
npm install
npx playwright install chromium
npm run build
npm run test:e2e
```
This opens a hidden Chrome on a phone-sized screen and does everything a user would: adds ingredients in Hindi, filters veg dishes, cooks Dal Tadka with the whistle counter and a timer, opens Bachao, finishes with a rating, adds a Jain family member, checks the shopping list's WhatsApp link, and reloads to confirm data is saved. It also fails if any JavaScript error happens. Screenshots are saved in `tests/screenshots/`.

**Test by hand (5 minutes):** see the checklist at the end of this file.

## 5. Change the app (when you want to edit things)

1. One time: `npm install` (downloads React and esbuild into a `node_modules` folder).
2. Run `npm run dev`. This rebuilds automatically whenever you save a file. Refresh the browser to see changes.
3. Easy things to change:
   - **Add a recipe:** `shared/recipes.mjs`. Copy an existing one and follow the format at the top of the file. `|5m` at the end of a step makes a 5-minute timer; `|3w` makes a 3-whistle counter.
   - **Add an ingredient or local name:** `shared/ingredients.mjs`, as comma-separated other names.
   - **Add a Bachao fix:** `shared/rescue.mjs`.
   - **Colours:** the top of `src/styles.css`.
4. Run `npm test` after every change. It will tell you if a recipe has a typo or a wrong tag (for example, marked "gluten-free" but containing atta).
5. When done: `npm run build`, then `npm start`.

## 6. Switch on AI Chef (optional)

1. Create an account at **https://console.anthropic.com**, add billing, and create an **API key**.
2. In the `ballava` folder, copy `.env.example` to a new file named `.env`.
3. Paste your key after `ANTHROPIC_API_KEY=` and save.
4. Restart: press **Ctrl + C**, then `npm start`. The Terminal now says **AI Chef: ON**.
5. In the app, tap **✨ AI Chef**: "Create a recipe" or "Scan my fridge".

Keep the key secret: never share the `.env` file or put it in the app's code. The key stays on the server; browsers never see it. Each visitor can make at most 10 AI requests per minute (`AI_RATE_LIMIT` in `.env`), which protects your bill.

## 6b. Admin portal and accounts

**Create your admin login (one time):**
```
npm run create-admin -- you@example.com
```
This shows a password once, so save it. Then open **http://localhost:3000/admin**. Run the command again to reset the password. Use an email that isn't a normal user account.

From the portal you can add and edit recipes (draft, then review, then publish; recipes that break the safety rules can't be published), hide recipes, add ingredients and Bachao fixes, post announcements, keep the festival calendar, and disable users. Admins never see a family's diet or health details.

**Your data:** accounts and family data live in one file, `data/ballava.db`. **Back this file up.** Users can download or delete their own data from More, Account.

**Phone sign-in** needs an SMS service. To try it without one, add `OTP_DEV_MODE=1` to `.env` and the code appears on screen. For real SMS, add your Twilio details (see `.env.example`). Sending SMS to India also needs DLT registration.

## 7. Put it online (so anyone can use it)

Any host that runs Node.js works, for example Render, Railway, Fly.io, or a small cloud server:
- **Start command:** `npm start`
- **Build command:** `npm install && npm run build` (or nothing, since `dist/` is already built)
- **Environment variables:** add `ANTHROPIC_API_KEY` there if you want AI. Don't upload `.env`.
- Hosts give you an **https** address, so phone install, microphone and offline mode all work.
- **Keep your data:** the host must give you a permanent disk for `data/ballava.db`, or set `DB_PATH` to a folder on one. Without it, accounts vanish on every restart.
- Set `NODE_ENV=production`, and don't set `OTP_DEV_MODE` on a live site.

## 8. Project map

```
ballava/
├── README.md            ← this guide
├── package.json         ← project name + the commands (start, build, dev, test)
├── .env.example         ← settings template (copy to .env)
├── build.mjs            ← packs src/ into dist/
├── dist/                ← the ready-to-serve app (built, don't edit by hand)
├── public/              ← page skeleton, icons, phone-app settings, offline support
├── src/                 ← the app screens (React)
│   ├── App.jsx          ← main frame, saved data, bottom tabs
│   ├── screens/         ← Home, Pantry (Kitchen), Recipe, Cook, Bachao, Family, Shopping, AiChef
│   ├── lib.js           ← voice, timers' beep, keep-screen-on, WhatsApp links
│   └── styles.css       ← all the looks
├── shared/              ← the cooking brain (used by app, server and tests)
│   ├── ingredients.mjs  ← 93 ingredients with Hindi/Telugu/Tamil names, shelf life, allergens
│   ├── recipes.mjs      ← 52 recipes with timers and whistle counts
│   ├── rescue.mjs       ← Bachao fixes + "is it safe?" rules
│   └── engine.mjs       ← understanding text, matching dishes, family rules, buy tips
├── server/
│   ├── server.mjs       ← web server + API (/api/health, /api/chat, /api/suggest, /api/ai/...)
│   └── ai.mjs           ← talks to Claude, with food-safety rules built in
├── scripts/dev.mjs      ← "npm run dev"
└── tests/               ← automatic checks (engine, server, real browser)
```

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `node` or `npm` "not recognised" | Install Node.js (step 2), then **close and reopen** the Terminal. |
| `EADDRINUSE` / port already in use | Ballava is already running in another window, or another program uses port 3000. Close it, or run with another port: Mac/Linux `PORT=4000 npm start`; Windows `set PORT=4000 && npm start`. |
| "The app is not built yet" | Run `npm install` then `npm run build`. |
| Page looks old after an update | Refresh hard: **Ctrl + Shift + R** (Mac: **Cmd + Shift + R**). |
| Microphone button missing | Voice typing needs Chrome or Edge (or Android). Safari on iPhone doesn't support it yet; typing works everywhere. |
| AI Chef says "switched off" | Check `.env` has `ANTHROPIC_API_KEY=...`, then restart the server. |
| "The AI key on the server is not valid" | The key was mistyped or deleted. Create a new one in the Anthropic console. |
| Lost my kitchen list | Data lives in that browser on that device. Clearing browser data or using a different phone starts fresh. |

## 10. Five-minute manual test checklist

- [ ] Open the app → tap **Try with a sample kitchen** → you see "Cook now" dishes.
- [ ] **Kitchen** tab → type `palak, kodi, mysteryfruit` → spinach and chicken are added, and it says it didn't recognise "mysteryfruit".
- [ ] Press **−** on an item until it says **Use today** → the **Cook** tab shows a yellow "Use soon" banner.
- [ ] Tap **Veg only** → no egg or chicken dishes remain.
- [ ] Open a recipe with missing items → **Add missing to shopping list** → the **List** tab shows them with a badge → **Share on WhatsApp** opens WhatsApp.
- [ ] Start cooking **Dal Tadka** → tap the whistle button 4 times → it beeps and says to turn off the stove.
- [ ] Start a timer → it counts down and beeps at zero.
- [ ] Tap **Bachao!** → search "salty" → read the fixes.
- [ ] Finish → give stars → the home screen shows **1 meal cooked**.
- [ ] **Family** → add a Jain vegetarian → onion, egg and chicken dishes disappear.
- [ ] Close and reopen the browser → everything is still there.

---

**Safety notes built into Ballava:** cooked rice and meat warnings on the risky dishes, steaming sprouts, a "when in doubt, throw it out" rescue entry, and AI recipes always come with food-safety rules. Allergy matching is a helper, not a guarantee; always read packaged food labels.
