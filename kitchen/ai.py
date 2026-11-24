"""AI Chef: invents dishes and reads fridge photos, using the AI you choose.

Pick the AI with AI_PROVIDER in .env (restart the server after changing it):
- AI_PROVIDER=gemini   Google Gemini, with the official `google-genai` library. Has a free tier. Key: GEMINI_API_KEY
- AI_PROVIDER=claude   Anthropic Claude, with the official `anthropic` library. Paid.        Key: ANTHROPIC_API_KEY

The secret key stays on the server and is never sent to the browser.
Both providers get the same instructions and safety rules, and their answers go through the same checks.
"""
import base64
import binascii
import json
import logging
import os
import re

import anthropic
import httpx2  # the networking library both AI libraries use
from django.conf import settings
from google import genai
from google.genai import errors as gemini_errors
from google.genai import types as gemini_types

from .security import ApiError

log = logging.getLogger(__name__)

# Which key each AI needs.
PROVIDERS = {'claude': 'ANTHROPIC_API_KEY', 'gemini': 'GEMINI_API_KEY'}

SAFETY_RULES = """Food safety is non-negotiable:
- Chicken and meat must be cooked until no pink remains (75°C inside). Fish until opaque and flaky. Eggs fully set for kids, elders and pregnant women.
- Dried kidney beans (rajma) must be soaked and boiled hard for at least 10 minutes. Never slow-cook them raw.
- Leftover rice must have been refrigerated within 1-2 hours; reheat only once.
- Respect every allergy and diet given. Never include an ingredient someone is allergic to."""

RECIPE_SHAPE = """{"name": "...", "alt": "local name if any", "cuisine": "...", "meal": ["breakfast" and/or "lunch" and/or "dinner" and/or "snack"],
 "diet": "veg" or "egg" or "nonveg", "time": total minutes, "serves": number, "spice": 1 or 2 or 3,
 "ingredients": [{"name": "ingredient name", "quantity": "like 1/2 cup, 2 tbsp, 1 tsp, 200 g or 2", "optional": false}],
 "steps": [{"text": "one clear instruction", "minutes": number or null}],
 "nutrition": {"kcal": calories per serving, "protein": grams per serving, "carbs": grams, "fat": grams},
 "allergens": ["dairy" / "gluten" / "nuts" / "egg" / "seafood" that the dish contains],
 "requested": true if the user asked for this dish by name, else false,
 "why": "one sentence on why the flavours work", "safety": "a food-safety note if needed, else empty"}"""

RECIPE_RULES = """Recipe rules: realistic home cooking, 4-10 short steps, give every ingredient a quantity, include the cooking oil or ghee you use,
assume salt and water are available, mark nice-to-haves optional.
- If the user names a specific dish (for example "chicken biryani"), give EXACTLY that dish, the real way it is made, with its full
  ingredient list, even when the kitchen doesn't have everything. Never swap it for a different dish, and set "requested": true.
  The app shows them what is missing and adds it to their shopping list.
- Only when they don't name a dish, invent one mostly from what is in the kitchen (at most 2 ingredients they don't have),
  and never break a family rule (diet, Jain, no onion/garlic, allergies, diabetes means no sweet dishes)."""


def ingredient_names():
    """The app's own ingredient names, so the AI's words map onto the kitchen and the calorie table."""
    from .engine import INGREDIENTS  # late import: engine is plain Python and imports nothing from here
    return ', '.join(i['name'] for i in INGREDIENTS if i['id'] not in ('salt', 'water'))


def invent_system():
    return f"""You are Ballava, a warm, practical Indian home-cooking chef. You give ONE realistic recipe: exactly the dish the cook asks for
when they name one, otherwise a dish invented mostly from what they already have.
{SAFETY_RULES}
{RECIPE_RULES}
When an ingredient is one of these, use exactly this name: {ingredient_names()}.
Reply with ONLY a JSON object, no other text, in exactly this shape:
{RECIPE_SHAPE}"""


def scan_system():
    return ('You identify food ingredients in a kitchen photo (fridge, shelf, basket, counter). Reply with ONLY JSON: '
            '{"ingredients": ["Tomato", "Paneer", ...]}. Include only things you can clearly see, and do not guess hidden items. '
            f'When an item is one of these, use exactly this name: {ingredient_names()}. Otherwise use a simple common name.')


CHAT_SYSTEM = f"""You are Ballava Chef, the kitchen assistant inside Ballava, a cooking app for Indian families. Most users are busy home cooks
(often mothers) who cook healthy, tasty food every day. Be the friend in the kitchen who knows a lot about food.
You can help with: what to cook (from their kitchen and their recipe book), recipes and steps, substitutes, fixing cooking mistakes,
calories and nutrition, food for kids, elders, diabetes, BP, pregnancy, fasting and festivals, tiffin ideas, storage and leftovers,
shopping, and how to use this app.
{SAFETY_RULES}
- Health conditions: give general food guidance only, and suggest checking with their doctor for medical advice.
- Calories are estimates. For recipe-book dishes, use the kcal numbers given below.
- If a question is not about food, cooking, nutrition, the family's meals or the app, say kindly that you can only help with the kitchen.
How the app works (for "how do I" questions):
- Dashboard tab (the first screen): greeting, today's menu, calories against a daily goal, every meal with its calories, a lighter swap, and the food diary.
- Cook tab: dishes ranked by what is in the kitchen and what is about to spoil; filters like veg, quick, light, high protein.
- Plan tab: "Plan my week" plans 7 days with no repeats; swap or lock a meal, plan tiffins, share the menu on WhatsApp.
- Chef (you): the button in the middle of the navigation bar. Chats are saved in "Your chats".
- Kitchen tab: add what you have by typing or speaking (Hindi, Telugu, Tamil names work) or with a fridge photo; it warns before things spoil.
- List tab: the shopping list. More: Saved dishes, Family (diets, allergies, health goals), Bachao (fix a dish), Recipe Studio (get or invent a recipe, scan the fridge), Account (family code).
- On a recipe: the heart saves it, Pin makes it a weekly tradition, add missing items to the list, Start cooking for timers and a whistle counter.
Style: warm, practical and short (usually under 120 words; longer only for steps). Plain text only: no markdown, no headings, no tables,
no asterisks. Use short lines, or lines starting with "- " for lists. Reply in the language the user writes in (English, Hindi, Telugu,
Tamil, or a mix like Hinglish).
When the user asks for a SPECIFIC dish by name ("chicken biryani", "how do I make dal tadka"), answer about exactly that dish:
- If it is in the RECIPE BOOK, put its id FIRST in "dishes", give a short summary, and say which of its ingredients they don't have.
- If it is not in the recipe book, put that exact dish in "recipe" (never a different or "easier" dish) and say what they need to buy.
- If it breaks a family rule (for example meat for a vegetarian member), still give it, say so kindly, and suggest a version that suits them.
When they ask for ideas without naming a dish, prefer RECIPE BOOK dishes that suit the family (and that they can cook now), name them in
the reply, and put their ids in "dishes" (at most 4). Only use ids from the recipe book.
When they ask for a new or different dish that is not in the recipe book, put one full new recipe in "recipe". {RECIPE_RULES}
When the user wants to buy something, or you suggest buying a few items, put the ingredient names in "shopping".
In "followups", suggest 2 or 3 short next questions they might tap (under 6 words each).
Only when the context says THE USER ASKED TO PLAN a day, put the final day plan in "plan" as recipe-book ids:
{{"breakfast": "id", "lunch": "id", "dinner": "id"}} (keep the drafted ids for meals you don't change). Every dish you
name for a meal in "reply" must be the one in "plan".
Reply with ONLY a JSON object, no other text:
{{"reply": "your answer", "dishes": ["recipe_id", ...], "recipe": null, "shopping": [], "followups": [], "plan": null}}
where "recipe", when you include one, has this shape:
{RECIPE_SHAPE}"""

IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')

TIMEOUT_SECONDS = 90  # plenty for one recipe
REFUSED = "The AI couldn't help with that request. Please try different words."


def provider():
    return settings.AI_PROVIDER


def key_name():
    return PROVIDERS.get(provider(), '')


def provider_label():
    """For the chat window: which AI is answering."""
    return {'gemini': 'Google Gemini', 'claude': 'Anthropic Claude'}.get(provider(), provider())


def ai_key():
    """The key for the chosen AI, or '' when AI Chef is switched off."""
    return os.environ.get(key_name(), '') if key_name() else ''


def call_ai(system, text, image=None, media_type=None, max_tokens=8000, history=()):
    """Ask the chosen AI. `image` is optional base64 photo data. `history` is the conversation so far,
    oldest first, as ('user' or 'assistant', text) pairs. Returns the AI's text reply."""
    if provider() not in PROVIDERS:
        log.warning('Unknown AI_PROVIDER %r. Use one of: %s', provider(), ', '.join(PROVIDERS))
        raise ApiError(503, f'AI is not set up on this server (AI_PROVIDER must be {" or ".join(PROVIDERS)}).')
    if not ai_key():
        raise ApiError(503, f'AI is not set up on this server (AI_PROVIDER is {provider()}, but there is no {key_name()}).')
    history = [(('assistant' if role == 'assistant' else 'user'), str(t)) for role, t in history if str(t or '').strip()]
    if provider() == 'gemini':
        return _call_gemini(system, text, image, media_type, max_tokens, history)
    return _call_claude(system, text, image, media_type, max_tokens, history)


# ---- Claude (Anthropic) ---------------------------------------------------

def _client():
    # One retry for short network blips.
    return anthropic.Anthropic(api_key=ai_key(), timeout=float(TIMEOUT_SECONDS), max_retries=1)


def _call_claude(system, text, image, media_type, max_tokens, history=()):
    content = text
    if image:
        content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': image}},
                   {'type': 'text', 'text': text}]
    messages = []
    for role, past in history:
        if messages or role == 'user':  # a conversation must start with the user
            messages.append({'role': role, 'content': past})
    messages.append({'role': 'user', 'content': content})
    try:
        response = _client().beta.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            # If the model declines for safety reasons, Anthropic retries on a suitable fallback model.
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
        )
    except anthropic.AuthenticationError as err:
        raise ApiError(500, 'The AI key on the server is not valid.') from err
    except anthropic.PermissionDeniedError as err:
        raise ApiError(500, 'The AI key on the server is not allowed to use this model.') from err
    except anthropic.NotFoundError as err:
        raise ApiError(500, 'The AI model name on the server is wrong (check ANTHROPIC_MODEL).') from err
    except anthropic.RateLimitError as err:
        raise ApiError(503, 'The AI is busy right now. Please try again in a minute.') from err
    except anthropic.APITimeoutError as err:
        raise ApiError(504, 'The AI took too long. Please try again.') from err
    except anthropic.APIConnectionError as err:
        raise ApiError(502, 'Could not reach the AI service. Please check the internet connection.') from err
    except anthropic.APIStatusError as err:
        raise ApiError(502, f'AI service error ({err.status_code}). Please try again.') from err
    if response.stop_reason == 'refusal':
        raise ApiError(502, REFUSED)
    return '\n'.join(block.text for block in response.content if block.type == 'text')


# ---- Gemini (Google) --------------------------------------------------------

def _gemini_client():
    # Timeout is in milliseconds here. One retry for short blips and overloads (not for "limit used up").
    return genai.Client(api_key=ai_key(), http_options=gemini_types.HttpOptions(
        timeout=TIMEOUT_SECONDS * 1000,
        retry_options=gemini_types.HttpRetryOptions(attempts=2, http_status_codes=[408, 500, 502, 503, 504]),
    ))


def _call_gemini(system, text, image, media_type, max_tokens, history=()):
    contents = [text]
    if image:
        try:
            data = base64.b64decode(image, validate=False)
        except (binascii.Error, ValueError) as err:
            raise ApiError(400, 'Unsupported image type') from err
        contents = [gemini_types.Part.from_bytes(data=data, mime_type=media_type), text]
    if history:
        # Gemini calls the AI's side of the conversation "model".
        turn = lambda role, parts: gemini_types.Content(role='model' if role == 'assistant' else 'user', parts=parts)  # noqa: E731
        last = [p if isinstance(p, gemini_types.Part) else gemini_types.Part.from_text(text=p) for p in contents]
        contents = [turn(role, [gemini_types.Part.from_text(text=past)]) for role, past in history] + [turn('user', last)]
    config = gemini_types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        response_mime_type='application/json',  # both AI Chef jobs want a JSON answer
    )
    try:
        # Keep hold of the client while it works: a client nobody holds on to shuts its connection straight away.
        with _gemini_client() as client:
            response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=contents, config=config)
    except gemini_errors.APIError as err:
        raise _gemini_error(err) from err
    except httpx2.TimeoutException as err:
        raise ApiError(504, 'The AI took too long. Please try again.') from err
    except httpx2.TransportError as err:
        raise ApiError(502, 'Could not reach the AI service. Please check the internet connection.') from err

    feedback = getattr(response, 'prompt_feedback', None)
    if feedback is not None and getattr(feedback, 'block_reason', None):
        raise ApiError(502, REFUSED)
    reply = response.text
    if not reply:
        candidates = getattr(response, 'candidates', None) or []
        finish = getattr(candidates[0], 'finish_reason', None) if candidates else None
        if finish == gemini_types.FinishReason.MAX_TOKENS:
            raise ApiError(502, 'The AI answer was cut short. Please try again.')
        raise ApiError(502, REFUSED)
    return reply


def _gemini_error(err):
    code, message = err.code or 0, (err.message or '')
    if code == 400 and 'api key' in message.lower():
        return ApiError(500, 'The AI key on the server is not valid.')
    if code in (401, 403):
        return ApiError(500, 'The AI key on the server is not valid, or not allowed to use this model.')
    if code == 404:
        return ApiError(500, 'The AI model name on the server is wrong (check GEMINI_MODEL).')
    if code == 429:
        return ApiError(503, "The AI is busy, or today's free AI limit is used up. Please try again later.")
    return ApiError(502, f'AI service error ({code}). Please try again.')


# ---- What AI Chef asks -------------------------------------------------------

def extract_json(text):
    """The JSON object in an AI answer. Forgives the usual slips: text around it, code fences, trailing commas."""
    text = str(text or '')
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        raise ApiError(502, 'AI gave an unexpected answer. Please try again.')
    body = text[start:end + 1]
    for attempt in (body, re.sub(r',\s*([}\]])', r'\1', body)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            pass
        try:
            return json.JSONDecoder().raw_decode(attempt)[0]  # a valid object followed by extra text
        except json.JSONDecodeError:
            pass
    raise ApiError(502, 'AI gave an unexpected answer. Please try again.')


def salvage_reply(raw):
    """When a chat answer isn't valid JSON, rescue what we can rather than showing code to the user."""
    data = {}
    m = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.S)
    if m:
        try:
            data['reply'] = json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            data['reply'] = m.group(1)
    for key in ('dishes', 'shopping'):
        m = re.search(rf'"{key}"\s*:\s*(\[[^\]]*\])', raw)
        if m:
            try:
                data[key] = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    m = re.search(r'"recipe"\s*:\s*\{', raw)
    if m:
        try:
            data['recipe'] = extract_json(raw[m.end() - 1:])
        except ApiError:
            pass
    if 'reply' not in data and not raw.lstrip().startswith('{'):
        data['reply'] = raw.strip()  # the AI simply answered in plain text
    return data


MEALS = ('breakfast', 'lunch', 'dinner', 'snack')


def invent_recipe(pantry=(), household=(), wish='', meal=None, avoid=None, fasting=False):
    """One new dish. `avoid` is a reason the last attempt was rejected (for example a family rule it broke)."""
    content = (f"Kitchen has: {', '.join(map(str, list(pantry)[:80])) or 'very little'}.\n"
               f"Family rules: {json.dumps(household)[:1500] if household else 'none given'}.\n"
               f"Meal: {meal if meal in MEALS else 'any'}.\n"
               f"Request: {str(wish)[:300] or 'surprise me with something tasty and doable'}.")
    if fasting:
        from .engine import VRAT_FOODS
        content += f"\nEveryone is fasting (vrat) today, so use only fasting foods: {VRAT_FOODS}. (A dish they name is still given exactly.)"
    if avoid:
        content += f'\nYour last idea was rejected because: {avoid}. Make a different dish that follows every family rule.'
    return extract_json(call_ai(invent_system(), content, max_tokens=6000))


def read_system():
    return f"""You turn a recipe that someone wrote down (in any language) into the app's format, in English. Keep to what it says: the same dish,
ingredients, amounts and steps. Don't add or drop ingredients. If it doesn't say the time or how many it serves, estimate them.
Mention pressure-cooker whistles in the step text. Set "requested" to true.
{SAFETY_RULES}
When an ingredient is one of these, use exactly this name: {ingredient_names()}.
Reply with ONLY a JSON object, no other text, in exactly this shape:
{RECIPE_SHAPE}"""


def read_recipe(text):
    """A pasted recipe, for the admin's recipe editor."""
    return extract_json(call_ai(read_system(), 'The recipe:\n' + str(text)[:8000], max_tokens=6000))


INGREDIENT_SYSTEM = """You fill in the details of ONE cooking ingredient for an Indian home-cooking app. Values are per 100 g, as it goes into the pot
(dry for dals and flours). Reply with ONLY JSON, no other text:
{"name": "tidy English name", "category": one of CATEGORIES, "diet": "veg" or "egg" or "nonveg", "allergens": any of ["dairy", "gluten", "nuts", "egg", "seafood"],
 "aliases": ["Hindi, Telugu, Tamil and other names people type, in English letters"], "kcal": number, "protein": grams, "carbs": grams, "fat": grams, "fibre": grams,
 "grams_per_cup": grams in a 240 ml cup or null, "grams_per_piece": grams in one medium piece or null, "shelf_days": days it keeps, or null if months}
If it is not something people cook with, reply {"name": null}."""


def describe_ingredient(name):
    """Category, other names and nutrition of a new ingredient, for the admin to check and save."""
    from .data.ingredients import CATEGORIES
    data = extract_json(call_ai(INGREDIENT_SYSTEM.replace('CATEGORIES', json.dumps(CATEGORIES)), f'Ingredient: {str(name)[:60]}', max_tokens=1500))
    if not data.get('name'):
        raise ApiError(422, "That doesn't look like a cooking ingredient.")
    return data


ESTIMATE_SYSTEM = """You estimate the nutrition of ONE ordinary Indian home or restaurant serving of the food named.
Reply with ONLY JSON: {"name": "tidy name of the food", "kcal": number, "protein": grams, "carbs": grams, "fat": grams}.
If it isn't a food, reply {"kcal": null}."""


def estimate_meal(name):
    """Calories for a meal that isn't in the recipe book ('pizza from outside', 'masala dosa at a hotel')."""
    data = extract_json(call_ai(ESTIMATE_SYSTEM, f'Food: {str(name)[:120]}', max_tokens=1500))
    try:
        kcal = float(data.get('kcal'))
    except (TypeError, ValueError):
        raise ApiError(422, "That doesn't look like a food I can estimate.") from None
    if not 5 <= kcal <= 3000:
        raise ApiError(422, "That doesn't look like a food I can estimate.")

    def grams(key):
        try:
            return round(max(0.0, min(400.0, float(data.get(key) or 0))), 1)
        except (TypeError, ValueError):
            return 0.0
    return {'kcal': round(kcal), 'protein': grams('protein'), 'carbs': grams('carbs'), 'fat': grams('fat'), 'source': 'ai'}


def scan_photo(image, media_type='image/jpeg'):
    if not image or not isinstance(image, str):
        raise ApiError(400, 'No photo received')
    if media_type not in IMAGE_TYPES or not re.fullmatch(r'[A-Za-z0-9+/=\s]+', image[:200]):
        raise ApiError(400, 'Unsupported image type')
    text = call_ai(scan_system(), 'What ingredients can you see?', image=image, media_type=media_type, max_tokens=4000)
    found = extract_json(text).get('ingredients')
    return [str(x) for x in found][:60] if isinstance(found, list) else []


def chat(question, context, history=()):
    """The kitchen assistant. Returns the AI's answer as a dict: reply, dishes, recipe, shopping."""
    history = [(role, str(t)[:1500]) for role, t in list(history)[-8:]]
    raw = call_ai(CHAT_SYSTEM + '\n\n' + context, str(question)[:1000], history=history, max_tokens=6000)
    try:
        data = extract_json(raw)
    except ApiError:
        data = salvage_reply(raw)
    return data if isinstance(data, dict) and (data.get('reply') or data.get('recipe')) else salvage_reply(raw)
