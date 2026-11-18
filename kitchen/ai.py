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

TIMEOUT_SECONDS = 90  # plenty for one recipe
REFUSED = "The AI couldn't help with that request. Please try different words."


def provider():
    return settings.AI_PROVIDER


def key_name():
    return PROVIDERS.get(provider(), '')


def ai_key():
    """The key for the chosen AI, or '' when AI Chef is switched off."""
    return os.environ.get(key_name(), '') if key_name() else ''


def call_ai(system, text, image=None, media_type=None, max_tokens=8000):
    """Ask the chosen AI. `image` is optional base64 photo data. Returns the AI's text reply."""
    if provider() not in PROVIDERS:
        log.warning('Unknown AI_PROVIDER %r. Use one of: %s', provider(), ', '.join(PROVIDERS))
        raise ApiError(503, f'AI is not set up on this server (AI_PROVIDER must be {" or ".join(PROVIDERS)}).')
    if not ai_key():
        raise ApiError(503, f'AI is not set up on this server (AI_PROVIDER is {provider()}, but there is no {key_name()}).')
    if provider() == 'gemini':
        return _call_gemini(system, text, image, media_type, max_tokens)
    return _call_claude(system, text, image, media_type, max_tokens)


# ---- Claude (Anthropic) ---------------------------------------------------

def _client():
    # One retry for short network blips.
    return anthropic.Anthropic(api_key=ai_key(), timeout=float(TIMEOUT_SECONDS), max_retries=1)


def _call_claude(system, text, image, media_type, max_tokens):
    content = text
    if image:
        content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': image}},
                   {'type': 'text', 'text': text}]
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


def _call_gemini(system, text, image, media_type, max_tokens):
    contents = [text]
    if image:
        try:
            data = base64.b64decode(image, validate=False)
        except (binascii.Error, ValueError) as err:
            raise ApiError(400, 'Unsupported image type') from err
        contents = [gemini_types.Part.from_bytes(data=data, mime_type=media_type), text]
    config = gemini_types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        response_mime_type='application/json',  # both AI Chef jobs want a JSON answer
    )
    try:
        response = _gemini_client().models.generate_content(model=settings.GEMINI_MODEL, contents=contents, config=config)
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
    return extract_json(call_ai(INVENT_SYSTEM, content))


def scan_photo(image, media_type='image/jpeg'):
    if not image or not isinstance(image, str):
        raise ApiError(400, 'No photo received')
    if media_type not in IMAGE_TYPES or not re.fullmatch(r'[A-Za-z0-9+/=\s]+', image[:200]):
        raise ApiError(400, 'Unsupported image type')
    text = call_ai(SCAN_SYSTEM, 'What ingredients can you see?', image=image, media_type=media_type, max_tokens=4000)
    found = extract_json(text).get('ingredients')
    return [str(x) for x in found][:60] if isinstance(found, list) else []
