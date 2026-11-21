"""Tests for the API the phone app uses: basics, the brain endpoints and AI Chef."""
import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx  # the networking library the Anthropic SDK uses
import pytest
from django.test import Client
from google.genai import errors as gemini_errors
from google.genai import types as gemini_types

from kitchen import ai

pytestmark = pytest.mark.django_db


def test_health(api, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert api.get_json('health') == (200, {'ok': True, 'ai': False, 'aiProvider': None, 'retentionDays': 180, 'version': '2.2.0'})


def test_serves_the_app_at_the_root(api, settings, tmp_path):
    (tmp_path / 'index.html').write_text('<div id="root"></div>')
    from whitenoise.middleware import WhiteNoiseMiddleware  # noqa: F401
    r = api.get('/api/health')
    assert r['Content-Security-Policy'].startswith("default-src 'self'")
    assert r['X-Frame-Options'] == 'DENY'


def test_cannot_read_files_outside_the_app():
    c = Client()
    for path in ['/../manage.py', '/%2e%2e/manage.py', '/..%2f..%2fmanage.py', '/%2e%2e%2f.env', '/data/db.sqlite3', '/.env']:
        r = c.get(path)
        assert r.status_code != 200 or b'DJANGO_SETTINGS_MODULE' not in r.content, path


def test_parse_suggest_chat_rescue(api):
    assert sorted(api.post_json('parse', {'text': 'aloo, pyaz'})[1]['found']) == ['onion', 'potato']
    _, sug = api.post_json('suggest', {'pantry': ['egg', 'onion', 'tomato', 'green_chilli']})
    assert any(r['id'] == 'masala_omelette' for r in sug['ready'])
    assert 'Curd Rice' in api.post_json('chat', {'text': 'leftover rice and dahi'})[1]['reply']
    assert api.post_json('rescue', {'text': 'too spicy'})[1][0]['id'] == 'too_spicy'


def test_bad_requests_get_clear_errors(api):
    r = api.post('/api/parse', data='{not json', content_type='application/json')
    assert r.status_code == 400
    assert api.post_json('nope')[0] == 404
    assert api.get('/api/parse').status_code == 405
    assert api.post_json('parse', {'text': 'x' * (1100 * 1024)})[0] == 413


def test_changes_need_a_csrf_token():
    """Another website can't make a signed-in phone change things: Django's CSRF check blocks it."""
    strict = Client(enforce_csrf_checks=True)
    r = strict.post('/api/state', data='{}', content_type='application/json')
    assert r.status_code == 403
    strict.get('/api/me')
    token = strict.cookies['csrftoken'].value
    r = strict.post('/api/parse', data=json.dumps({'text': 'aloo'}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200


# ---------------------------------------------------------------- the brain
KITCHEN = ['rice', 'toor_dal', 'onion', 'tomato', 'potato', 'atta', 'curd', 'egg', 'turmeric', 'cumin', 'mustard_seeds', 'red_chilli_powder', 'poha', 'peas']


def test_home_ranks_and_flags_repeats(api):
    _, home = api.post_json('brain/home', {'pantry': KITCHEN, 'history': [{'recipeId': 'jeera_rice', 'name': 'Jeera Rice', 'date': '2000-01-01', 'slot': 'lunch'}]})
    assert home['ready'] and isinstance(home['ready'][0]['recipe'], str)
    assert {'tips', 'prep', 'today'} <= set(home)
    today = home['today']
    _, again = api.post_json('brain/home', {'pantry': KITCHEN, 'history': [{'recipeId': 'jeera_rice', 'name': 'Jeera Rice', 'date': today, 'slot': 'lunch'}]})
    jeera = next(r for r in again['ready'] + again['almost'] if r['recipe'] == 'jeera_rice')
    assert jeera['repeat']['reasons'][0] == 'Already on the menu today'


def test_plan_swap_and_info(api):
    _, out = api.post_json('brain/plan', {'pantry': KITCHEN, 'members': [{'name': 'Riya', 'age': 'child', 'tiffin': True}]})
    plan = out['plan']
    days = sorted(plan)
    assert len(days) == 7
    main = [plan[d][s] for d in days for s in ('breakfast', 'lunch', 'dinner')]
    assert len(set(main)) == 21
    _, sw = api.post_json('brain/swap', {'plan': plan, 'date': days[0], 'slot': 'dinner', 'start': days[0], 'pantry': KITCHEN})
    assert sw['recipeId'] and sw['recipeId'] not in main
    _, info = api.post_json('brain/plan-info', {'plan': plan, 'pantry': KITCHEN, 'lang': 'hi'})
    assert info['today'] == days[0] and 'आज का मेन्यू' in info['menu'] and isinstance(info['groceries'], list)
    assert api.post_json('brain/swap', {'plan': plan, 'date': days[0], 'slot': 'brunch'})[0] == 400


def test_plan_uses_the_family_time_zone(api):
    # A phone in New York (UTC-5, offset +300) and one in India get their own "today".
    _, ny = api.post_json('brain/plan-info', {'plan': {}, 'tz': 300})
    _, india = api.post_json('brain/plan-info', {'plan': {}, 'tz': -330})
    from datetime import date
    for d in (ny['today'], india['today']):
        assert abs((date.fromisoformat(d) - date.today()).days) <= 1


def test_recipe_info(api):
    members = [{'name': 'Dadaji', 'diabetic': True, 'goals': ['bp']}, {'name': 'Amma', 'diet': 'veg'}]
    _, info = api.post_json('brain/recipe', {'recipeId': 'kanda_poha', 'members': members})
    assert info['house']['ok'] and any(p['who'] == 'Dadaji' for p in info['plates'])
    assert 'Kanda Poha' in info['shareText'] and info['lastDays'] is None
    _, chicken = api.post_json('brain/recipe', {'recipeId': 'chicken_curry', 'members': members})
    assert chicken['house']['ok'] is False and chicken['plates'] == []
    assert api.post_json('brain/recipe', {'recipeId': 'nope'})[0] == 404


def test_dashboard_and_ask(api):
    history = [{'recipeId': 'jeera_rice', 'name': 'Jeera Rice', 'at': 1_800_000_000_000}, {'recipeId': None, 'name': 'Pizza', 'date': '2026-11-01', 'slot': 'dinner'}]
    _, d = api.post_json('brain/dashboard', {'history': history})
    assert d['total'] == 2
    _, a = api.post_json('brain/ask', {'text': 'I have paneer and spinach'})
    assert 'Palak Paneer' in a['reply']


def test_brain_ignores_junk_input(api):
    status, _ = api.post_json('brain/home', {'pantry': 'not a list', 'members': [1, None, 'x'], 'history': [None, 5, {}], 'tz': 'abc', 'pins': [{'bad': 1}]})
    assert status == 200


# ---------------------------------------------------------------- AI Chef
class FakeClaude:
    """Stands in for the Anthropic client so tests never call the real AI."""

    def __init__(self, text=None, error=None, stop_reason='end_turn'):
        self.calls, self.text, self.error, self.stop_reason = [], text, error, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        is_scan = isinstance(kwargs['messages'][0]['content'], list)
        text = self.text or ('{"ingredients": ["tomato", "paneer", "dragon fruit"]}' if is_scan else
                             'Here you go: {"name":"Paneer Pepper Fry","time":20,"spice":2,"ingredients":[{"name":"paneer","quantity":"200 g"}],'
                             '"steps":[{"text":"Fry it","minutes":3}],"why":"Pepper loves paneer"}')
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type='text', text=text)])


@pytest.fixture
def claude(monkeypatch):
    def install(**kw):
        fake = FakeClaude(**kw)
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
        monkeypatch.setattr(ai, '_client', lambda: fake)
        return fake
    return install


def api_error(cls, status):
    request = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    return cls('error', response=httpx.Response(status, request=request), body=None)


def test_ai_says_clearly_when_it_is_off(api, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    status, body = api.post_json('ai/invent', {'pantry': ['egg']})
    assert status == 503 and 'ANTHROPIC_API_KEY' in body['error'] and 'AI_PROVIDER is claude' in body['error']


def test_ai_invent_and_scan(api, claude, settings):
    fake = claude()
    status, inv = api.post_json('ai/invent', {'pantry': ['Paneer'], 'household': [{'diet': 'veg'}], 'wish': 'quick'})
    assert status == 200 and inv['recipe']['name'] == 'Paneer Pepper Fry' and inv['recipe']['ai'] is True
    call = fake.calls[0]
    assert call['model'] == settings.ANTHROPIC_MODEL
    assert 'Food safety' in call['system'] and 'Paneer' in call['messages'][0]['content']
    assert call['fallbacks'] == 'default' and call['betas'] == ['server-side-fallback-2026-07-01']
    _, scan = api.post_json('ai/scan', {'image': 'aGVsbG8=', 'mediaType': 'image/jpeg'})
    assert sorted(scan['found']) == ['paneer', 'tomato'] and scan['unknown'] == ['dragon fruit']
    image = fake.calls[1]['messages'][0]['content'][0]
    assert image == {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'aGVsbG8='}}
    assert api.post_json('ai/scan', {'image': 'aGVsbG8=', 'mediaType': 'text/html'})[0] == 400


@pytest.mark.parametrize('error, status, message', [
    (api_error(anthropic.AuthenticationError, 401), 500, 'not valid'),
    (api_error(anthropic.RateLimitError, 429), 503, 'busy'),
    (anthropic.APITimeoutError(httpx.Request('POST', 'https://api.anthropic.com')), 504, 'too long'),
    (anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com')), 502, 'Could not reach'),
    (api_error(anthropic.InternalServerError, 500), 502, 'AI service error'),
])
def test_ai_errors_are_reported_politely(api, claude, error, status, message):
    claude(error=error)
    code, body = api.post_json('ai/invent', {'pantry': ['egg']})
    assert code == status and message in body['error']


def test_ai_refusal_and_bad_answers(api, claude):
    claude(stop_reason='refusal', text='')
    assert "couldn't help" in api.post_json('ai/invent', {'pantry': ['egg']})[1]['error']
    claude(text='no json here')
    assert api.post_json('ai/invent', {'pantry': ['egg']}) == (502, {'error': 'AI gave an unexpected answer. Please try again.'})


def test_ai_rate_limit_protects_the_bill(api, claude, settings):
    settings.AI_RATE_LIMIT = 2
    claude(text='{"ingredients": []}')
    statuses = [api.post_json('ai/scan', {'image': 'aGk=', 'mediaType': 'image/png'})[0] for _ in range(4)]
    assert 429 in statuses


# ---------------------------------------------------------------- AI Chef with Google Gemini (AI_PROVIDER=gemini)
class FakeGemini:
    """Stands in for the Google Gemini client so tests never call the real AI."""

    def __init__(self, text=None, error=None, blocked=False, finish='STOP'):
        self.calls, self.text, self.error, self.blocked, self.finish = [], text, error, blocked, finish
        self.models = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def generate_content(self, *, model, contents, config):
        self.calls.append({'model': model, 'contents': contents, 'config': config})
        if self.error:
            raise self.error
        is_scan = len(contents) > 1
        text = self.text if self.text is not None else (
            '{"ingredients": ["tomato", "paneer", "dragon fruit"]}' if is_scan else
            '{"name":"Paneer Pepper Fry","time":20,"spice":2,"ingredients":[{"name":"paneer","quantity":"200 g"}],'
            '"steps":[{"text":"Fry it","minutes":3}],"why":"Pepper loves paneer"}')
        return SimpleNamespace(text=text, prompt_feedback=SimpleNamespace(block_reason='SAFETY' if self.blocked else None),
                               candidates=[SimpleNamespace(finish_reason=self.finish)])


@pytest.fixture
def gemini(monkeypatch, settings):
    def install(**kw):
        fake = FakeGemini(**kw)
        settings.AI_PROVIDER = 'gemini'
        monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
        monkeypatch.setattr(ai, '_gemini_client', lambda: fake)
        return fake
    return install


def test_ai_provider_setting_picks_the_key(api, monkeypatch, settings):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    assert api.get_json('health')[1]['ai'] is False, 'claude is chosen, and it has no key'
    settings.AI_PROVIDER = 'gemini'
    assert api.get_json('health')[1]['ai'] is True
    monkeypatch.delenv('GEMINI_API_KEY')
    status, body = api.post_json('ai/invent', {'pantry': ['egg']})
    assert status == 503 and 'GEMINI_API_KEY' in body['error']
    settings.AI_PROVIDER = 'chatgpt'
    status, body = api.post_json('ai/invent', {'pantry': ['egg']})
    assert status == 503 and 'AI_PROVIDER must be claude or gemini' in body['error']
    assert api.get_json('health')[1]['ai'] is False


def test_gemini_invent_and_scan(api, gemini, settings):
    fake = gemini()
    status, inv = api.post_json('ai/invent', {'pantry': ['Paneer'], 'household': [{'diet': 'veg'}], 'wish': 'quick'})
    assert status == 200 and inv['recipe']['name'] == 'Paneer Pepper Fry' and inv['recipe']['ai'] is True
    call = fake.calls[0]
    assert call['model'] == settings.GEMINI_MODEL
    assert 'Food safety' in call['config'].system_instruction and 'Paneer' in call['contents'][0]
    assert call['config'].response_mime_type == 'application/json'
    _, scan = api.post_json('ai/scan', {'image': 'aGVsbG8=', 'mediaType': 'image/jpeg'})
    assert sorted(scan['found']) == ['paneer', 'tomato'] and scan['unknown'] == ['dragon fruit']
    photo = fake.calls[1]['contents'][0]
    assert photo.inline_data.data == b'hello' and photo.inline_data.mime_type == 'image/jpeg'


def test_real_gemini_library_sends_the_request(api, monkeypatch, settings):
    """Goes through Google's real library; only the internet is replaced by a stand-in."""
    from google import genai
    seen = []

    def fake_internet(request):
        seen.append(request)
        reply = {'candidates': [{'content': {'role': 'model', 'parts': [{'text': '{"ingredients": ["tomato", "onion"]}'}]},
                                 'finishReason': 'STOP'}]}
        return httpx.Response(200, json=reply)

    real_client = genai.Client

    def client_with_fake_internet(**kw):
        kw['http_options'].client_args = {'transport': httpx.MockTransport(fake_internet)}
        return real_client(**kw)

    settings.AI_PROVIDER = 'gemini'
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(ai.genai, 'Client', client_with_fake_internet)
    status, scan = api.post_json('ai/scan', {'image': 'aGVsbG8=', 'mediaType': 'image/jpeg'})
    assert status == 200, scan
    assert sorted(scan['found']) == ['onion', 'tomato']
    request = seen[0]
    assert f'models/{settings.GEMINI_MODEL}:generateContent' in str(request.url)
    assert request.headers.get('x-goog-api-key') == 'test-key'
    body = json.loads(request.content)
    assert 'ingredients' in body['systemInstruction']['parts'][0]['text']
    photo = body['contents'][0]['parts'][0]['inlineData']
    assert photo['data'] == 'aGVsbG8=' and 'image/jpeg' in photo.values()


def gemini_error(cls, code, message='error'):
    return cls(code, {'error': {'code': code, 'message': message, 'status': 'X'}})


@pytest.mark.parametrize('error, status, message', [
    (gemini_error(gemini_errors.ClientError, 400, 'API key not valid. Please pass a valid API key.'), 500, 'not valid'),
    (gemini_error(gemini_errors.ClientError, 403), 500, 'not valid'),
    (gemini_error(gemini_errors.ClientError, 404), 500, 'GEMINI_MODEL'),
    (gemini_error(gemini_errors.ClientError, 429), 503, 'free AI limit'),
    (gemini_error(gemini_errors.ServerError, 503), 502, 'AI service error (503)'),
    (httpx.ReadTimeout('slow'), 504, 'too long'),
    (httpx.ConnectError('offline'), 502, 'Could not reach'),
])
def test_gemini_errors_are_reported_politely(api, gemini, error, status, message):
    gemini(error=error)
    code, body = api.post_json('ai/invent', {'pantry': ['egg']})
    assert code == status and message in body['error']


# ---------------------------------------------------------------- the assistant (chat on every screen)
VEG_FAMILY = {'members': [{'name': 'Amma', 'diet': 'veg', 'diabetic': True, 'allergies': ['nuts']}],
              'pantry': [{'id': 'paneer'}, {'id': 'spinach'}, {'id': 'onion'}], 'savedDishes': [{'id': 'palak_paneer', 'at': 1}]}


def chat_answer(**over):
    return json.dumps({'reply': 'Try **Palak Paneer** tonight.', 'dishes': ['palak_paneer', 'made_up_dish'], 'recipe': None,
                       'shopping': ['tomatoes', 'unicorn dust'], **over})


def test_chat_without_ai_still_answers(api):
    status, body = api.post_json('ai/chat', {'text': 'How many calories in dal tadka?', **VEG_FAMILY})
    assert status == 200 and body['source'] == 'builtin' and 'kcal per serving' in body['reply']
    assert api.post_json('ai/chat', {'text': '  '})[0] == 400


def test_chat_with_gemini_knows_the_family_and_is_checked(api, gemini):
    fake = gemini(text=chat_answer())
    history = [{'from': 'bot', 'text': 'Hi! Ask me anything.'}, {'from': 'me', 'text': 'Hello'}, {'from': 'bot', 'text': 'Hello! How can I help?'}]
    status, body = api.post_json('ai/chat', {'text': 'What should I cook tonight?', 'messages': history, 'screen': 'recipe',
                                             'recipeId': 'dal_tadka', **VEG_FAMILY})
    assert status == 200 and body['source'] == 'ai'
    assert body['reply'] == 'Try Palak Paneer tonight.', 'markdown is removed'
    assert body['dishes'] == ['palak_paneer'], 'made-up recipe ids are dropped'
    assert body['shopping'] == ['tomato'], 'shopping items are matched to real ingredients'
    call = fake.calls[0]
    system = call['config'].system_instruction
    assert 'RECIPE BOOK' in system and 'Paneer' in system and 'Dal Tadka (id dal_tadka)' in system
    assert 'vegetarian, diabetic, allergic to nuts' in system and 'Amma' not in system, 'family needs are sent, names are not'
    assert 'chicken_curry' not in system, 'only dishes that suit this family are offered to the AI'
    assert 'Saved (favourite) dishes: Palak Paneer' in system
    roles = [c.role for c in call['contents']]
    assert roles == ['model', 'user', 'model', 'user'] and call['contents'][-1].parts[0].text == 'What should I cook tonight?'


def test_chat_drops_new_recipes_that_break_family_rules(api, gemini):
    chicken = {'name': 'Quick Chicken Fry', 'diet': 'nonveg', 'ingredients': [{'name': 'Chicken', 'quantity': '500 g'}],
               'steps': ['Fry the chicken until cooked through.', 'Serve hot.']}
    gemini(text=chat_answer(recipe=chicken, dishes=[]))
    body = api.post_json('ai/chat', {'text': 'Invent a new dinner', **VEG_FAMILY})[1]
    assert body['recipe'] is None and "doesn't suit your family" in body['reply']
    veg = {**chicken, 'name': 'Paneer Saag Toast', 'diet': 'veg', 'ingredients': [{'name': 'Paneer', 'quantity': '100 g'}, {'name': 'Spinach', 'quantity': '1 cup'}]}
    gemini(text=chat_answer(recipe=veg, dishes=[]))
    body = api.post_json('ai/chat', {'text': 'Invent a new dinner', **VEG_FAMILY})[1]
    assert body['recipe']['name'] == 'Paneer Saag Toast' and body['recipe']['nutrition']['kcal'] > 0


def test_chat_survives_messy_ai_answers(api, gemini):
    gemini(text='Sure! {"reply": "Make Palak Paneer.", "dishes": ["palak_paneer"],} Enjoy!')  # trailing comma, text around it
    body = api.post_json('ai/chat', {'text': 'dinner?', **VEG_FAMILY})[1]
    assert body['reply'] == 'Make Palak Paneer.' and body['dishes'] == ['palak_paneer']
    gemini(text='Palak Paneer would be lovely tonight.')  # plain text, no JSON at all
    body = api.post_json('ai/chat', {'text': 'dinner?', **VEG_FAMILY})[1]
    assert body['reply'].startswith('Palak Paneer') and body['dishes'] == ['palak_paneer'], 'dish names in the text become buttons'


def test_chat_falls_back_when_the_ai_is_busy(api, gemini):
    gemini(error=gemini_error(gemini_errors.ClientError, 429))
    body = api.post_json('ai/chat', {'text': 'How many calories in dal tadka?', **VEG_FAMILY})[1]
    assert body['source'] == 'builtin' and 'free AI limit' in body['note'] and 'kcal' in body['reply']


def test_chat_with_claude_sends_the_conversation(api, claude):
    fake = claude(text=chat_answer())
    history = [{'from': 'bot', 'text': 'Hi!'}, {'from': 'me', 'text': 'Hello'}, {'from': 'bot', 'text': 'Hello there'}]
    body = api.post_json('ai/chat', {'text': 'Dinner idea?', 'messages': history, **VEG_FAMILY})[1]
    assert body['source'] == 'ai' and body['dishes'] == ['palak_paneer']
    roles = [m['role'] for m in fake.calls[0]['messages']]
    assert roles == ['user', 'assistant', 'user'], 'starts with the user, so the greeting is left out'


def test_ai_chef_asks_again_when_a_dish_breaks_a_family_rule(api, gemini):
    chicken = json.dumps({'name': 'Chicken Fry', 'ingredients': [{'name': 'chicken', 'quantity': '500 g'}], 'steps': ['Fry well.', 'Serve hot.']})
    fake = gemini(text=chicken)
    status, body = api.post_json('ai/invent', {'pantry': ['Chicken'], 'household': [{'diet': 'veg'}]})
    assert status == 502 and "didn't suit your family" in body['error'] and len(fake.calls) == 2
    assert 'rejected because' in fake.calls[1]['contents'][0]


# ---------------------------------------------------------------- "give me chicken biryani" gives chicken biryani
BIRYANI = {'name': 'Chicken Biryani', 'diet': 'nonveg', 'requested': True, 'serves': 4,
           'ingredients': [{'name': 'Chicken', 'quantity': '500 g'}, {'name': 'Basmati rice', 'quantity': '2 cups'},
                           {'name': 'Curd', 'quantity': '1/2 cup'}, {'name': 'Mint leaves', 'quantity': 'a handful'}],
           'steps': ['Marinate the chicken in curd and spices.', 'Layer with half-cooked rice and cook on dum.']}


def test_ai_chef_gives_exactly_the_dish_asked_for(api, gemini):
    fake = gemini(text=json.dumps(BIRYANI))
    status, body = api.post_json('ai/invent', {'pantry': ['Rice', 'Eggs', 'Tomato'], 'wish': 'chicken biryani', 'household': [{'diet': 'veg'}]})
    assert status == 200 and body['recipe']['name'] == 'Chicken Biryani', 'never swapped for a different dish'
    assert body['warning'] == "Someone doesn't eat meat or fish" and body['recipe']['requested'] is True
    assert len(fake.calls) == 1, 'no second attempt for a dish asked for by name'
    prompt = fake.calls[0]['config'].system_instruction
    assert 'give EXACTLY that dish' in prompt and 'Never swap it for a different dish' in prompt


def test_ai_chef_returns_recipe_book_dishes_without_ai(api, gemini):
    fake = gemini()
    status, body = api.post_json('ai/invent', {'pantry': ['Rice'], 'wish': 'Dal Tadka please'})
    assert status == 200 and body['fromBook'] is True and body['recipe']['id'] == 'dal_tadka' and fake.calls == []


def test_chat_answers_about_the_named_recipe_book_dish(api, gemini):
    fake = gemini(text=json.dumps({'reply': 'Here is how.', 'dishes': ['jeera_rice']}))
    body = api.post_json('ai/chat', {'text': 'How do I make chole?', **VEG_FAMILY})[1]
    assert body['dishes'][0] == 'chole', 'the dish they named always comes first'
    system = fake.calls[0]['config'].system_instruction
    assert 'answer about exactly this dish' in system and 'Chole' in system and 'They are missing:' in system


def test_chat_keeps_a_requested_dish_with_a_warning(api, gemini):
    gemini(text=json.dumps({'reply': 'Here is chicken biryani.', 'recipe': BIRYANI, 'followups': ['Make it spicier', 'Veg version?']}))
    body = api.post_json('ai/chat', {'text': 'Give me chicken biryani recipe', **VEG_FAMILY})[1]
    assert body['recipe']['name'] == 'Chicken Biryani' and body['recipe']['warning'] == "Amma doesn't eat meat or fish"
    assert body['followups'] == ['Make it spicier', 'Veg version?']


def test_built_in_chat_names_the_exact_dish_and_whats_missing(api):
    body = api.post_json('ai/chat', {'text': 'How do I make dal tadka?', 'pantry': [{'id': 'tomato'}]})[1]
    assert body['dishes'] == ['dal_tadka'] and "You're missing: Toor dal" in body['reply']
    body = api.post_json('ai/chat', {'text': 'Give me chicken biryani recipe', **VEG_FAMILY})[1]
    assert "isn't in the recipe book" in body['reply'] and 'AI' in body['reply']


def test_ai_estimates_calories_for_food_from_outside(api, gemini):
    gemini(text='{"name": "Pizza", "kcal": 700, "protein": 25, "carbs": 80, "fat": 30}')
    status, body = api.post_json('ai/estimate', {'name': 'Pizza from outside'})
    assert status == 200 and body == {'kcal': 700, 'protein': 25.0, 'carbs': 80.0, 'fat': 30.0, 'source': 'ai'}
    gemini(text='{"kcal": null}')
    assert api.post_json('ai/estimate', {'name': 'a bicycle'})[0] == 422
    assert api.post_json('ai/estimate', {'name': ''})[0] == 400


def test_calorie_dashboard(api):
    status, d = api.post_json('brain/calories', {'days': 7, 'tz': -330, 'history': [
        {'id': 'a', 'recipeId': 'dal_tadka', 'name': 'Dal Tadka', 'date': '2026-11-21', 'slot': 'lunch', 'at': 1},
        {'id': 'b', 'name': 'Pizza from outside', 'date': '2026-11-21', 'slot': 'dinner', 'at': 2, 'nutrition': {'kcal': 700, 'protein': 25, 'source': 'ai'}},
        {'id': 'c', 'name': 'Mystery', 'date': '2026-11-21', 'slot': 'dinner', 'at': 3}]})
    assert status == 200 and len(d['days']) == 7 and set(d['macros']['split']) == {'protein', 'carbs', 'fat'}
    names = {m['name']: m for m in d['meals']}
    assert names['Pizza from outside']['kcal'] == 700 and names['Pizza from outside']['source'] == 'ai'
    assert names['Mystery'].get('kcal') is None and d['uncounted'] == 1


def test_saved_dishes_count_as_liked(api):
    pantry = [{'id': i} for i in ['paneer', 'spinach', 'onion', 'tomato', 'ginger', 'garlic', 'green_chilli', 'cumin', 'garam_masala']]
    plain = api.post_json('brain/home', {'pantry': pantry})[1]['ready']
    liked = api.post_json('brain/home', {'pantry': pantry, 'savedDishes': [{'id': 'palak_paneer', 'at': 1}]})[1]['ready']
    rank = lambda rows: next(r['rank'] for r in rows if r['recipe'] == 'palak_paneer')  # noqa: E731
    assert rank(liked) > rank(plain)


def test_gemini_refusal_and_cut_off_answers(api, gemini):
    gemini(blocked=True)
    assert "couldn't help" in api.post_json('ai/invent', {'pantry': ['egg']})[1]['error']
    gemini(text='', finish='SAFETY')
    assert "couldn't help" in api.post_json('ai/invent', {'pantry': ['egg']})[1]['error']
    gemini(text='', finish=gemini_types.FinishReason.MAX_TOKENS)
    assert 'cut short' in api.post_json('ai/invent', {'pantry': ['egg']})[1]['error']
