"""AI Chef: talks to Claude (Anthropic's AI) with the official `anthropic` Python library.

The secret API key stays on the server and is never sent to the browser.
AI Chef switches on when ANTHROPIC_API_KEY is set (in .env or the environment).
"""
import json
import os
import re

import anthropic
from django.conf import settings

from .security import ApiError

SAFETY_RULES = """Food safety is non-negotiable:
- Chicken and meat must be cooked until no pink remains (75°C inside). Fish until opaque and flaky. Eggs fully set for kids, elders and pregnant women.
- Dried kidney beans (rajma) must be soaked and boiled hard for at least 10 minutes. Never slow-cook them raw.
- Leftover rice must have been refrigerated within 1-2 hours; reheat only once.
- Respect every allergy and diet given. Never include an ingredient someone is allergic to."""

INVENT_SYSTEM = f"""You are Ballava, a warm, practical Indian home-cooking chef. You invent ONE realistic dish a home cook can make tonight, mostly from what they already have.
{SAFETY_RULES}
Reply with ONLY a JSON object, no other text, in exactly this shape:
{{"name": "...", "alt": "local name if any", "cuisine": "...", "time": minutes, "serves": number, "spice": 1|2|3,
 "ingredients": [{{"name": "plain English ingredient name", "quantity": "...", "optional": false}}],
 "steps": [{{"text": "one clear instruction", "minutes": number or null}}],
 "why": "one sentence on why the flavours work", "safety": "a safety note if needed, else empty"}}
Assume salt, oil and water are available. Use at most 2 ingredients that are not in the kitchen, and mark nice-to-haves optional. 4-9 steps."""

SCAN_SYSTEM = ('You identify food ingredients in a kitchen photo (fridge, shelf, basket, counter). Reply with ONLY JSON: '
               '{"ingredients": ["tomato", "paneer", ...]} using simple common names. Include only things you can clearly see. '
               'Do not guess hidden items.')

IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')


def ai_key():
    return os.environ.get('ANTHROPIC_API_KEY', '')


def _client():
    # One retry for short network blips; 90 seconds is plenty for one recipe.
    return anthropic.Anthropic(api_key=ai_key(), timeout=90.0, max_retries=1)


def call_claude(system, content, max_tokens=8000):
    if not ai_key():
        raise ApiError(503, 'AI is not set up on this server (no ANTHROPIC_API_KEY).')
    try:
        response = _client().beta.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{'role': 'user', 'content': content}],
            # If the model declines for safety reasons, Anthropic retries on a suitable fallback model.
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
        )
    except anthropic.AuthenticationError as err:
        raise ApiError(500, 'The AI key on the server is not valid.') from err
    except anthropic.PermissionDeniedError as err:
        raise ApiError(500, 'The AI key on the server is not allowed to use this model.') from err
    except anthropic.RateLimitError as err:
        raise ApiError(503, 'The AI is busy right now. Please try again in a minute.') from err
    except anthropic.APITimeoutError as err:
        raise ApiError(504, 'The AI took too long. Please try again.') from err
    except anthropic.APIConnectionError as err:
        raise ApiError(502, 'Could not reach the AI service. Please check the internet connection.') from err
    except anthropic.APIStatusError as err:
        raise ApiError(502, f'AI service error ({err.status_code}). Please try again.') from err
    if response.stop_reason == 'refusal':
        raise ApiError(502, "The AI couldn't help with that request. Please try different words.")
    return '\n'.join(block.text for block in response.content if block.type == 'text')


def extract_json(text):
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        raise ApiError(502, 'AI gave an unexpected answer. Please try again.')
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as err:
        raise ApiError(502, 'AI gave an unexpected answer. Please try again.') from err


def invent_recipe(pantry=(), household=(), wish=''):
    content = (f"Kitchen has: {', '.join(map(str, list(pantry)[:80])) or 'very little'}.\n"
               f"Household: {json.dumps(household)[:1500] if household else 'not specified'}.\n"
               f"Request: {str(wish)[:300] or 'surprise me with something tasty and doable'}.")
    return extract_json(call_claude(INVENT_SYSTEM, content))


def scan_photo(image, media_type='image/jpeg'):
    if not image or not isinstance(image, str):
        raise ApiError(400, 'No photo received')
    if media_type not in IMAGE_TYPES or not re.fullmatch(r'[A-Za-z0-9+/=\s]+', image[:200]):
        raise ApiError(400, 'Unsupported image type')
    text = call_claude(SCAN_SYSTEM, [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': image}},
        {'type': 'text', 'text': 'What ingredients can you see?'},
    ], max_tokens=4000)
    found = extract_json(text).get('ingredients')
    return [str(x) for x in found][:60] if isinstance(found, list) else []
