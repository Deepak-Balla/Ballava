// Talks to Claude (Anthropic's AI) for the two optional AI features.
// The secret API key stays on the server and is never sent to the browser.

const API_URL = 'https://api.anthropic.com/v1/messages';

export const aiConfig = () => ({
  key: process.env.ANTHROPIC_API_KEY || '',
  model: process.env.ANTHROPIC_MODEL || 'claude-sonnet-5-5',
});

async function callClaude({ system, content, maxTokens = 1500 }) {
  const { key, model } = aiConfig();
  if (!key) { const e = new Error('AI is not set up on this server (no ANTHROPIC_API_KEY).'); e.status = 503; throw e; }
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 60000);
  try {
    const res = await fetch(API_URL, {
      method: 'POST',
      signal: ctrl.signal,
      headers: { 'content-type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model, max_tokens: maxTokens, system, messages: [{ role: 'user', content }] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = new Error(data?.error?.message || `AI service error (${res.status})`);
      e.status = res.status === 401 ? 500 : 502;
      if (res.status === 401) e.message = 'The AI key on the server is not valid.';
      throw e;
    }
    return (data.content || []).filter(b => b.type === 'text').map(b => b.text).join('\n');
  } catch (err) {
    if (err.name === 'AbortError') { const e = new Error('The AI took too long. Please try again.'); e.status = 504; throw e; }
    throw err;
  } finally { clearTimeout(t); }
}

export function extractJson(text) {
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start === -1 || end <= start) throw Object.assign(new Error('AI gave an unexpected answer. Please try again.'), { status: 502 });
  try { return JSON.parse(text.slice(start, end + 1)); } catch {
    throw Object.assign(new Error('AI gave an unexpected answer. Please try again.'), { status: 502 });
  }
}

const SAFETY_RULES = `Food safety is non-negotiable:
- Chicken and meat must be cooked until no pink remains (75°C inside). Fish until opaque and flaky. Eggs fully set for kids, elders and pregnant women.
- Dried kidney beans (rajma) must be soaked and boiled hard for at least 10 minutes. Never slow-cook them raw.
- Leftover rice must have been refrigerated within 1-2 hours; reheat only once.
- Respect every allergy and diet given. Never include an ingredient someone is allergic to.`;

export async function inventRecipe({ pantry = [], household = [], wish = '' }) {
  const system = `You are Ballava, a warm, practical Indian home-cooking chef. You invent ONE realistic dish a home cook can make tonight, mostly from what they already have.
${SAFETY_RULES}
Reply with ONLY a JSON object, no other text, in exactly this shape:
{"name": "...", "alt": "local name if any", "cuisine": "...", "time": minutes, "serves": number, "spice": 1|2|3,
 "ingredients": [{"name": "plain English ingredient name", "quantity": "...", "optional": false}],
 "steps": [{"text": "one clear instruction", "minutes": number or null}],
 "why": "one sentence on why the flavours work", "safety": "a safety note if needed, else empty"}
Assume salt, oil and water are available. Use at most 2 ingredients that are not in the kitchen, and mark nice-to-haves optional. 4-9 steps.`;
  const content = `Kitchen has: ${pantry.slice(0, 80).join(', ') || 'very little'}.
Household: ${household.length ? JSON.stringify(household).slice(0, 1500) : 'not specified'}.
Request: ${String(wish).slice(0, 300) || 'surprise me with something tasty and doable'}.`;
  return extractJson(await callClaude({ system, content }));
}

export async function scanPhoto({ image, mediaType = 'image/jpeg' }) {
  if (!image || typeof image !== 'string') throw Object.assign(new Error('No photo received'), { status: 400 });
  if (!/^image\/(jpeg|png|webp|gif)$/.test(mediaType)) throw Object.assign(new Error('Unsupported image type'), { status: 400 });
  const system = 'You identify food ingredients in a kitchen photo (fridge, shelf, basket, counter). Reply with ONLY JSON: {"ingredients": ["tomato", "paneer", ...]} using simple common names. Include only things you can clearly see. Do not guess hidden items.';
  const text = await callClaude({
    system, maxTokens: 600,
    content: [
      { type: 'image', source: { type: 'base64', media_type: mediaType, data: image } },
      { type: 'text', text: 'What ingredients can you see?' },
    ],
  });
  const json = extractJson(text);
  return Array.isArray(json.ingredients) ? json.ingredients.map(String).slice(0, 60) : [];
}
