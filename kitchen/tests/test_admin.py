"""Tests for the admin portal (/admin): who can get in, what they can see, and publishing content."""
from datetime import timedelta

import json

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.utils import timezone

from kitchen.models import Announcement, Festival, HiddenRecipe, Ingredient, Recipe, Rescue
from kitchen import recipe_editor
from .conftest import ADMIN, Api
from .test_api import gemini  # noqa: F401  (a pretend AI)

pytestmark = pytest.mark.django_db


def recipe_form(**over):
    data = {'recipe_id': 'test_khichdi', 'name': 'Test Khichdi', 'alt': '', 'cuisine': 'Test', 'meal': 'lunch, dinner',
            'time': 20, 'serves': 2, 'spice': 1, 'tags': 'gluten-free', 'ingredients': 'rice:1 cup\nmoong_dal:1/2 cup',
            'steps': 'Wash the rice and dal.\nPressure cook them together. |3w', 'prep': '', 'safety': '', 'tip': ''}
    return {**data, **over}


def act(client, action, *recipes):
    return client.post('/admin/kitchen/recipe/', {'action': action, '_selected_action': [r.pk for r in recipes]}, follow=True)


def test_normal_users_cannot_get_into_admin(make_user):
    c = make_user()
    for path in ['/admin/', '/admin/kitchen/recipe/', '/admin/auth/user/']:
        r = c.get(path)
        assert r.status_code == 302 and '/admin/login/' in r['Location'], path
    r = c.post('/admin/login/', {'username': c.email, 'password': 'kadai-masala-42'})
    assert r.status_code == 200 and b'correct' in r.content  # "Please enter the correct email and password for a staff account"


def test_admin_login_does_not_work_in_the_family_app(admin_client):
    assert Api().post_json('auth/login', {'email': ADMIN['username'], 'password': ADMIN['password']})[0] == 401
    r = admin_client.get('/api/me')
    assert r.json() == {'user': None}


def test_wrong_admin_passwords_get_locked(db):
    User.objects.create_superuser(ADMIN['username'], ADMIN['username'], ADMIN['password'])
    c = Client()
    statuses = [c.post('/admin/login/', {'username': ADMIN['username'], 'password': 'wrong-guess'}).status_code for _ in range(7)]
    assert 429 in statuses
    assert c.post('/admin/login/', ADMIN).status_code == 429, 'even the right password waits out the lock'


def test_admin_passwords_must_be_long(db):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    staff = User(username='s@x.test', is_staff=True)
    with pytest.raises(ValidationError):
        validate_password('short-pass1', staff)
    validate_password('short-pass1', User(username='u@x.test'))  # fine for family users


def test_createsuperuser_asks_again_for_a_short_password(db, monkeypatch, capsys):
    """Typing at `manage.py createsuperuser`: a short password is refused, then a long one works."""
    from django.core.management import call_command, get_commands
    assert get_commands()['createsuperuser'] == 'kitchen', "Ballava's version of the command is used"
    passwords = iter(['short-pass1', 'short-pass1', 'a-long-admin-password', 'a-long-admin-password'])
    answers = iter(['boss@ballava.test', 'boss@ballava.test', 'N'])  # username, email, "bypass validation?" -> No
    monkeypatch.setattr('getpass.getpass', lambda prompt='': next(passwords))
    monkeypatch.setattr('builtins.input', lambda prompt='': next(answers))
    call_command('createsuperuser', interactive=True, stdin=type('TTY', (), {'isatty': lambda self: True})())
    out = capsys.readouterr()
    assert 'at least 12 characters' in out.err + out.out
    boss = User.objects.get(username='boss@ballava.test')
    assert boss.is_superuser and boss.check_password('a-long-admin-password')


def test_overview_shows_stats_but_no_family_details(admin_client, make_user):
    c = make_user()
    c.post_json('state', {'key': 'members', 'value': [{'name': 'PrivateGrandma', 'diabetic': True, 'goals': ['pregnancy']}], 'baseVersion': 0})
    c.post_json('state', {'key': 'history', 'value': [{'recipeId': 'idli'}, {'recipeId': 'sambar'}], 'baseVersion': 0})
    page = admin_client.get('/admin/').content.decode()
    assert 'Meals logged' in page and 'Families' in page
    users = admin_client.get('/admin/auth/user/').content.decode()
    for page_text in (page, users):
        assert 'PrivateGrandma' not in page_text and 'pregnancy' not in page_text
    assert f'field-masked_contact">u***@ballava.test' in users, 'contacts are masked in the visible list'
    assert admin_client.get('/admin/kitchen/familydata/').status_code == 404, 'family data has no admin page'


def test_disabling_a_user_signs_them_out(admin_client, make_user):
    c = make_user()
    user = User.objects.get(email=c.email)
    user.is_active = False
    user.save()
    assert c.get_json('me')[1] == {'user': None}
    assert Api().post_json('auth/login', {'email': c.email, 'password': 'kadai-masala-42'})[0] == 401


def visible(recipe_id='test_khichdi'):
    return any(r['id'] == recipe_id for r in Api().get_json('catalog')[1]['recipes'])


@pytest.fixture
def helper_client(admin_client):
    """An admin who isn't the owner: may write recipes, but not skip the review."""
    user = User.objects.create_user('helper@x.test', 'helper@x.test', 'helper-long-password', is_staff=True)
    user.user_permissions.set(Permission.objects.filter(content_type__app_label='kitchen', codename__in=['add_recipe', 'change_recipe', 'view_recipe']))
    c = Client()
    c.force_login(user)
    return c


def test_publish_in_one_click(admin_client):
    r = admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='', _publish='1'), follow=True)
    assert r.redirect_chain[-1][0] == '/admin/recipe-book/test_khichdi/', 'the id is made from the name, and you land on the recipe'
    assert 'Users see it now' in r.content.decode() and visible()
    assert Recipe.objects.get().status == 'published'
    assert LogEntry.objects.filter(change_message='Published').exists()
    _, sug = Api().post_json('suggest', {'pantry': ['rice', 'moong_dal']})
    assert any(d['id'] == 'test_khichdi' for d in sug['ready'])


def test_a_draft_is_not_seen_until_it_is_published(admin_client):
    assert admin_client.post('/admin/kitchen/recipe/add/', recipe_form()).status_code == 302
    recipe = Recipe.objects.get(recipe_id='test_khichdi')
    assert recipe.status == 'draft' and not visible()
    assert '🚀 Publish' in admin_client.get('/admin/recipe-book/test_khichdi/').content.decode()
    assert admin_client.get('/admin/recipe-book/test_khichdi/publish/').status_code == 405
    page = admin_client.post('/admin/recipe-book/test_khichdi/publish/', follow=True).content.decode()
    assert 'Users see it now' in page and visible()


def test_half_finished_drafts_can_be_saved_but_not_published(admin_client):
    empty = recipe_form(recipe_id='', name='Half Done', meal='', ingredients='', steps='')
    r = admin_client.post('/admin/kitchen/recipe/add/', {**empty, '_publish': '1'}, follow=True)
    assert 'cannot be published yet' in r.content.decode() and not visible('half_done')
    assert r.redirect_chain[-1][0].endswith('/change/'), 'you stay in the editor to fix it'
    assert Recipe.objects.get(recipe_id='half_done').status == 'draft', 'and nothing you typed is lost'


def test_other_admins_send_recipes_to_review_first(admin_client, helper_client):
    page = helper_client.get('/admin/kitchen/recipe/add/').content.decode()
    assert 'Send to review' in page and 'name="_publish"' not in page
    r = helper_client.post('/admin/kitchen/recipe/add/', recipe_form(_publish='1'), follow=True)
    assert 'must be sent to review' in r.content.decode() and not visible()
    recipe = Recipe.objects.get()
    assert 'must be sent to review' in act(helper_client, 'publish', recipe).content.decode()
    helper_client.post(f'/admin/kitchen/recipe/{recipe.pk}/change/', recipe_form(_review='1'))
    assert Recipe.objects.get().status == 'review' and not visible()
    assert 'Users see it now' in act(admin_client, 'publish', recipe).content.decode() and visible()


def test_editing_a_live_recipe_waits_for_publishing(admin_client):
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='edit_me', name='Version One'))
    recipe = Recipe.objects.get(recipe_id='edit_me')
    act(admin_client, 'send_to_review', recipe)
    act(admin_client, 'publish', recipe)
    admin_client.post(f'/admin/kitchen/recipe/{recipe.pk}/change/', recipe_form(recipe_id='edit_me', name='Version Two'))
    assert Recipe.objects.get(pk=recipe.pk).name == 'Version Two'
    live = next(r for r in Api().get_json('catalog')[1]['recipes'] if r['id'] == 'edit_me')
    assert live['name'] == 'Version One'


def test_broken_recipes_cannot_be_published(admin_client):
    r = admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='bad_one', ingredients='atta:1 cup'), follow=True)
    assert 'gluten-free' in r.content.decode(), 'warned on save'
    recipe = Recipe.objects.get(recipe_id='bad_one')
    act(admin_client, 'send_to_review', recipe)
    page = act(admin_client, 'publish', recipe).content.decode()
    assert 'cannot be published' in page and Recipe.objects.get(pk=recipe.pk).live is None
    page = admin_client.get('/admin/recipe-book/bad_one/').content.decode()
    assert 'it contains gluten' in page
    r = admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='no_safety', tags='', ingredients='chicken:500 g'), follow=True)
    assert 'food-safety' in r.content.decode()


def test_copy_a_built_in_recipe_to_change_it(admin_client):
    form = admin_client.get('/admin/kitchen/recipe/add/?copy_from=dal_tadka').context['adminform'].form
    assert form.initial['name'] == 'Dal Tadka' and 'toor_dal' in form.initial['ingredients']
    r = admin_client.post('/admin/kitchen/recipe/add/?copy_from=dal_tadka', {**form.initial, 'time': 99, '_publish': '1'}, follow=True)
    assert 'Users see it now' in r.content.decode()
    mine = [r for r in Api().get_json('catalog')[1]['recipes'] if r['id'] == 'dal_tadka']
    assert len(mine) == 1 and mine[0]['time'] == 99, 'the edited copy replaces the built-in one'
    again = admin_client.get('/admin/kitchen/recipe/add/?copy_from=dal_tadka')
    assert again.status_code == 302 and again['Location'].endswith(f'/recipe/{Recipe.objects.get().pk}/change/'), 'editing it again opens the same version'


def test_hidden_recipe_disappears(admin_client):
    has = lambda: any(d['id'] == 'curd_rice' for d in Api().post_json('suggest', {'pantry': ['leftover_rice', 'curd']})[1]['ready'])  # noqa: E731
    assert has()
    admin_client.post('/admin/kitchen/hiddenrecipe/add/', {'recipe_id': 'curd_rice', 'reason': 'test'})
    assert HiddenRecipe.objects.count() == 1 and not has()
    HiddenRecipe.objects.all().delete()
    assert has()


def test_new_ingredients_and_fixes_work_straight_away(admin_client):
    admin_client.post('/admin/kitchen/ingredient/add/', {'ingredient_id': 'gongura', 'name': 'Gongura', 'category': 'Vegetables', 'shelf_days': 3,
                                                         'aliases': 'sorrel leaves, ambadi', 'allergens': '', 'diet': 'veg'})
    assert Ingredient.objects.count() == 1
    assert Api().post_json('parse', {'text': 'ambadi'})[1]['found'] == ['gongura']
    admin_client.post('/admin/kitchen/rescue/add/', {'rescue_id': 'smoky', 'title': 'Too smoky', 'keywords': 'dhuan fumes', 'fixes': 'Move it to a clean pan.', 'myth': ''})
    assert Rescue.objects.count() == 1
    assert Api().post_json('rescue', {'text': 'dhuan'})[1][0]['title'] == 'Too smoky'
    Ingredient.objects.all().delete()
    assert Api().post_json('parse', {'text': 'ambadi'})[1]['found'] == []


def test_built_in_ingredient_ids_are_protected(admin_client):
    r = admin_client.post('/admin/kitchen/ingredient/add/', {'ingredient_id': 'tomato', 'name': 'Fake', 'category': 'Vegetables', 'diet': 'veg'}, follow=True)
    assert 'already a built-in ingredient' in r.content.decode() and Ingredient.objects.count() == 0


def test_announcements_and_festivals_reach_the_app(admin_client):
    Announcement.objects.create(text='New recipes!', active=True)
    Announcement.objects.create(text='Old news', active=False)
    Festival.objects.create(name='Ekadashi', date='2026-11-20', fast=True)
    cat = Api().get_json('catalog')[1]
    assert [a['text'] for a in cat['announcements']] == ['New recipes!']
    assert cat['festivals'][0]['name'] == 'Ekadashi' and cat['festivals'][0]['fast'] is True


def test_a_new_festival_tells_open_apps_to_refresh(admin_client):
    stamp = lambda: Api().get_json('health')[1]['catalog']
    before = stamp()
    soon = timezone.localdate() + timedelta(days=3)
    r = admin_client.post('/admin/kitchen/festival/add/', {'name': 'Nagula Chavithi', 'date': soon.isoformat(), 'fast': 'on'}, follow=True)
    assert b'Users will see Nagula Chavithi within a minute' in r.content and b'in 3 days' in r.content
    after = stamp()
    assert after > before, 'apps that are open compare this number and fetch the festivals again'
    cat = Api().get_json('catalog')[1]
    assert cat['stamp'] == after and cat['festivals'] == [{'id': str(Festival.objects.get().pk), 'name': 'Nagula Chavithi', 'date': soon.isoformat(), 'fast': True}]
    Festival.objects.get().delete()
    assert stamp() > after and Api().get_json('catalog')[1]['festivals'] == []


def test_admin_is_warned_about_a_festival_in_the_past(admin_client):
    past = timezone.localdate() - timedelta(days=2)
    r = admin_client.post('/admin/kitchen/festival/add/', {'name': 'Dasara', 'date': past.isoformat()}, follow=True)
    assert b'has passed, so users will not see it' in r.content and b'Over, so no longer shown' in r.content


def test_changes_are_in_the_audit_log(admin_client):
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='audit_me'))
    act(admin_client, 'send_to_review', Recipe.objects.get(recipe_id='audit_me'))
    act(admin_client, 'publish', Recipe.objects.get(recipe_id='audit_me'))
    assert LogEntry.objects.filter(object_repr='Test Khichdi').count() >= 2
    assert admin_client.get('/admin/admin/logentry/').status_code == 200


def test_admin_can_change_their_password(admin_client):
    r = admin_client.post('/admin/password_change/', {'old_password': ADMIN['password'], 'new_password1': 'a-brand-new-password', 'new_password2': 'a-brand-new-password'})
    assert r.status_code == 302
    assert admin_client.get('/admin/').status_code == 200, 'stays signed in'
    fresh = Client()
    assert fresh.post('/admin/login/', ADMIN).status_code == 200, 'old password no longer works'
    assert fresh.post('/admin/login/', {'username': ADMIN['username'], 'password': 'a-brand-new-password'}).status_code == 302


def test_recipe_book_shows_every_recipe(admin_client):
    from kitchen.engine import ALL_RECIPES
    import re
    page = admin_client.get('/admin/recipe-book/').content.decode()
    links = re.findall(r'href="/admin/recipe-book/([a-z0-9_]+)/"', page)
    assert sorted(links) == sorted(r['id'] for r in ALL_RECIPES), 'every built-in recipe has a row with a details link'
    for name in ('Kanda Poha', 'Dal Tadka', 'Chicken Curry'):
        assert name in page
    page = admin_client.get('/admin/recipe-book/?q=paneer&diet=veg&sort=kcal').content.decode()
    assert 'Palak Paneer' in page and 'Chicken Curry' not in page


def test_recipe_book_includes_admin_drafts_and_hidden(admin_client):
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='draft_dish', name='Draft Only Dish'))
    HiddenRecipe.objects.create(recipe_id='curd_rice')
    page = admin_client.get('/admin/recipe-book/?state=draft').content.decode()
    assert 'Draft Only Dish' in page and 'Kanda Poha' not in page
    assert 'Curd Rice' in admin_client.get('/admin/recipe-book/?state=hidden').content.decode()


def test_recipe_details_with_calories_and_edit_link(admin_client):
    page = admin_client.get('/admin/recipe-book/dal_tadka/').content.decode()
    from kitchen.engine import RECIPE_BY_ID
    assert 'Dal Tadka' in page and 'Toor dal' in page and str(RECIPE_BY_ID['dal_tadka']['nutrition']['kcal']) in page
    assert '/admin/kitchen/recipe/add/?copy_from=dal_tadka' in page and 'Hide from users' in page
    add = admin_client.get('/admin/kitchen/recipe/add/?copy_from=dal_tadka').content.decode()
    assert 'value="Dal Tadka"' in add and 'toor_dal' in add, 'Edit starts a filled-in copy of the built-in recipe'
    assert admin_client.get('/admin/recipe-book/no_such_dish/').status_code == 404


def test_ingredient_list_with_nutrition(admin_client):
    page = admin_client.get('/admin/ingredient-book/?category=Dairy+%26+Eggs').content.decode()
    assert 'Paneer' in page and '265' in page and 'Onion' not in page
    admin_client.post('/admin/kitchen/ingredient/add/', {'ingredient_id': 'gongura', 'name': 'Gongura', 'category': 'Vegetables',
                                                         'diet': 'veg', 'kcal': 50, 'protein': 2, 'grams_per_cup': 30})
    assert 'Gongura' in admin_client.get('/admin/ingredient-book/?q=gong').content.decode()
    from kitchen import catalog, engine
    catalog.live()
    assert engine.BY_ID['gongura']['nutrition']['kcal'] == 50


def test_new_admin_look_and_dashboard(admin_client, make_user):
    page = admin_client.get('/admin/').content.decode()
    for text in ('kitchen/admin.css', 'ballava-nav', 'Recipe book', 'Needs your attention', 'AI use, last 7 days', 'Meals logged'):
        assert text in page, text
    assert 'ballava-nav' not in Client().get('/admin/login/').content.decode(), 'no section bar before signing in'
    assert make_user().get('/admin/recipe-book/').status_code == 302, 'family users cannot open the recipe book'


def test_admin_sign_out(admin_client):
    admin_client.post('/admin/logout/')
    assert admin_client.get('/admin/').status_code == 302


# ---------------------------------------------------------------- the recipe editor
WHATSAPP = """*Gongura Pappu Recipe* 😋
Serves: 4 | Prep time: 10 mins | Cook time: 25 mins
Cuisine: Andhra

*Ingredients*
- Toor dal - 1 cup
- Gongura leaves - 2 bunches
- 2 onions, chopped
- 3-4 green chillies
- Salt to taste
For the tempering:
- 1 tbsp ghee or oil
- 1/2 tsp mustard seeds (optional)

*Method*
1. Soak the dal for 2 hours and pressure cook it for 3 whistles.
2. Cook the gongura and chillies for 8-10 minutes.
3. Mash, mix and serve hot.

Tip: Serve with hot rice."""


def tool(client, which, /, **body):
    r = client.post(f'/admin/recipe-tools/{which}/', json.dumps(body), content_type='application/json')
    return r.status_code, r.json() if r['Content-Type'] == 'application/json' else {}


def test_a_recipe_pasted_from_whatsapp_fills_the_form(admin_client):
    status, out = tool(admin_client, 'read', text=WHATSAPP)
    f = out['fields']
    assert status == 200 and out['source'] == 'text'
    assert (f['name'], f['serves'], f['time'], f['cuisine']) == ('Gongura Pappu', 4, 35, 'Andhra')
    rows = [('|'.join(r['options']), r['qty'], r['optional']) for r in f['ingredients']]
    assert rows == [('toor_dal', '1 cup', False), ('gongura leaves', '2 bunches', False), ('onion', '2, chopped', False), ('green_chilli', '3-4', False),
                    ('ghee|oil', '1 tbsp', False), ('mustard_seeds', '1/2 tsp', True)], 'salt is always there, so it is left out'
    assert f['steps'] == [{'text': 'Soak the dal for 2 hours and pressure cook it for 3 whistles.', 'whistles': 3},
                          {'text': 'Cook the gongura and chillies for 8-10 minutes.', 'minutes': 10}, {'text': 'Mash, mix and serve hot.'}]
    assert f['tip'] == 'Serve with hot rice.' and 'Soak the dal' in f['prep']
    assert tool(admin_client, 'read', text='hi')[0] == 400
    assert tool(admin_client, 'read', text='Nothing to see in this text at all.')[0] == 400


@pytest.mark.parametrize('line, options, qty', [
    ('2 cups basmati rice, washed', ['rice'], '2 cups, washed'), ('½ cup toor dal (kandi pappu)', ['toor_dal'], '½ cup'), ('500g chicken', ['chicken'], '500g'),
    ('Onion 2 medium', ['onion'], '2 medium'), ('Curry leaves: a few', ['curry_leaves'], 'a few'), ('a pinch of hing', ['hing'], 'a pinch'),
    ('1 tsp turmeric powder', ['turmeric'], '1 tsp'), ('tamatar 3', ['tomato'], '3'), ('Coriander leaves for garnish', ['coriander'], 'for garnish'),
    ('Chicken masala powder - 2 tsp', ['chicken masala powder'], '2 tsp'), ('rice flour 1 cup', ['rice flour'], '1 cup'), ('ghee/oil 2 tbsp', ['ghee', 'oil'], '2 tbsp'),
])
def test_ingredient_lines_are_read_the_way_people_write_them(line, options, qty):
    (row,) = recipe_editor.read_ingredient(line)
    assert row['options'] == options and row['qty'] == qty, 'and something only similar (chicken masala) is never taken for the real thing'


def test_recipes_without_headings_and_in_one_paragraph_are_read_too():
    f = recipe_editor.read_text('Easy poha\npoha 2 cups\nonion 1\nturmeric 1/4 tsp\nWash the poha. Fry the onion for 2 minutes. Mix in the poha and serve.')
    assert f['name'] == 'Easy poha' and [r['options'][0] for r in f['ingredients']] == ['poha', 'onion', 'turmeric'] and len(f['steps']) == 3
    f = recipe_editor.read_text('Lemon rice\nIngredients: rice 2 cups, lemon 2, curry leaves a few\nMethod: Heat oil. Add curry leaves. Mix in the rice and lemon.')
    assert len(f['ingredients']) == 3 and len(f['steps']) == 3


def test_live_checks_say_what_to_fix_in_plain_words(admin_client):
    check = lambda **b: tool(admin_client, 'check', **{**recipe_form(), **b})[1]  # noqa: E731
    good = check()
    assert good['problems'] == [] and good['nutrition']['kcal'] > 100 and good['diet'] == 'veg' and good['lines'][0]['kcal'] > 0
    texts = lambda out: ' '.join(p['text'] for p in out['problems'])  # noqa: E731
    assert 'Give the dish a name' in texts(check(name='')) and 'at least one meal' in texts(check(meal=''))
    assert 'Add the ingredients' in texts(check(ingredients='')) and 'two steps' in texts(check(steps='One'))
    unknown = check(ingredients='rice:1 cup\nmysteryleaf:1 bunch')
    assert unknown['problems'][0]['unknown'] == 'mysteryleaf' and unknown['problems'][0]['field'] == 'ingredients'
    meat = check(ingredients='chicken:500 g', tags='')
    assert 'food-safety note' in texts(meat) and 'no pink' in meat['safety'] and meat['diet'] == 'nonveg'
    vague = check(ingredients='rice:some\nmoong_dal:1/2 cup')
    assert vague['lines'][0]['unclear'] and 'How much rice' in vague['advice'][0]['text']
    assert {'gluten-free', 'quick'} <= set(check(tags='')['suggested']) and 'vrat' not in check(tags='')['suggested']
    assert 'vrat' in check(tags='', ingredients='samak:1 cup\npotato:2')['suggested']
    assert any(a.get('edit') == 'dal_tadka' for a in check(name='dal tadka')['advice']), 'that dish exists already'
    assert 'lowercase' in texts(check(recipe_id='Not Good!'))
    assert check(time='', serves='x', spice=None)['problems'], 'odd input is a problem to fix, not a crash'


def test_names_make_ids_that_never_replace_another_recipe(admin_client):
    assert recipe_editor.make_id('Gongura Pappu!') == 'gongura_pappu'
    assert recipe_editor.make_id('Dal Tadka') == 'dal_tadka_2', 'never replaces a built-in recipe by accident'
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='', name='Gongura Pappu'))
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='', name='Gongura Pappu'))
    assert set(Recipe.objects.values_list('recipe_id', flat=True)) == {'gongura_pappu', 'gongura_pappu_2'}
    assert recipe_editor.make_id('పప్పు') == 'recipe'


def test_copy_an_existing_recipe_into_a_new_one(admin_client):
    f = tool(admin_client, 'source', id='sabudana_khichdi')[1]['fields']
    assert f['name'] == 'Sabudana Khichdi (copy)' and f['recipe_id'] == '' and f['ingredients'][0]['options'] == ['sabudana'] and 'vrat' in f['tags']
    assert tool(admin_client, 'source', id='nope')[0] == 400


def test_add_a_missing_ingredient_from_the_recipe(admin_client):
    guess = tool(admin_client, 'ingredient-guess', name='crab meat')[1]['fields']
    assert guess['diet'] == 'nonveg' and guess['allergens'] == ['seafood'], 'a first guess that errs on the safe side'
    status, out = tool(admin_client, 'ingredient-add', name='Gongura', category='Vegetables', diet='veg', allergens=[], aliases='ambadi, sorrel leaves', kcal='40', protein='x')
    assert status == 200 and out['ingredient']['id'] == 'gongura' and not out['existed']
    made = Ingredient.objects.get()
    assert made.kcal == 40 and made.protein is None and LogEntry.objects.filter(change_message__contains='recipe editor').exists()
    assert tool(admin_client, 'check', **recipe_form(ingredients='gongura:100 g\nrice:1 cup'))[1]['problems'] == [], 'ready to use at once'
    assert tool(admin_client, 'ingredient-add', name='Ambadi', category='Vegetables', diet='veg')[1] == {'ingredient': out['ingredient'], 'existed': True}
    assert Ingredient.objects.count() == 1 and tool(admin_client, 'ingredient-add', name='  ')[0] == 400


def test_the_ai_can_write_or_read_a_recipe(admin_client, gemini):
    assert '✨ Write it for me' not in admin_client.get('/admin/kitchen/recipe/add/').content.decode(), 'AI is off'
    answer = {'name': 'Gongura Chicken', 'cuisine': 'Andhra', 'meal': ['lunch'], 'time': 45, 'serves': 4, 'spice': 3, 'safety': 'Cook the chicken through.', 'why': 'Tangy.',
              'ingredients': [{'name': 'Chicken', 'quantity': '500 g'}, {'name': 'Gongura leaves', 'quantity': '2 bunches'}, {'name': 'Chicken masala', 'quantity': '1 tbsp'}, {'name': 'Salt', 'quantity': 'to taste'}],
              'steps': [{'text': 'Wash the chicken.', 'minutes': 2}, {'text': 'Pressure cook for 3 whistles.', 'minutes': 10}, {'text': 'Simmer with gongura.', 'minutes': 8}]}
    fake = gemini(text=json.dumps(answer))
    assert '✨ Write it for me' in admin_client.get('/admin/kitchen/recipe/add/').content.decode()
    out = tool(admin_client, 'write', name='Gongura Chicken', wish='less oil')[1]
    f = out['fields']
    assert 'Gongura Chicken. less oil' in fake.calls[0]['contents'][0]
    assert [r['options'] for r in f['ingredients']] == [['chicken'], ['gongura leaves'], ['chicken masala']] and f['meal'] == ['lunch'] and f['safety']
    assert f['steps'] == [{'text': 'Wash the chicken.'}, {'text': 'Pressure cook for 3 whistles.', 'whistles': 3}, {'text': 'Simmer with gongura.', 'minutes': 8}], 'no timer for washing'
    assert Recipe.objects.count() == 0, 'nothing is saved or published by itself'
    assert tool(admin_client, 'read', text=WHATSAPP)[1]['source'] == 'ai' and 'Gongura leaves' in fake.calls[1]['contents'][0]
    gemini(text='sorry, no')
    out = tool(admin_client, 'read', text=WHATSAPP)[1]
    assert out['source'] == 'text' and 'read it by itself' in out['note'] and out['fields']['name'] == 'Gongura Pappu', 'when the AI fails, the text is still read'
    assert tool(admin_client, 'write', name='')[0] == 400
    gemini(text=json.dumps({'name': 'Gongura', 'category': 'Vegetables', 'diet': 'veg', 'allergens': ['lies'], 'aliases': ['ambadi'], 'kcal': 38, 'grams_per_cup': 99999}))
    f = tool(admin_client, 'ingredient-guess', name='gongura', ai=True)[1]['fields']
    assert f['kcal'] == 38 and f['aliases'] == 'ambadi' and f['allergens'] == '' and f['grams_per_cup'] is None, 'impossible values are dropped'
    gemini(text='{"name": null}')
    assert tool(admin_client, 'ingredient-guess', name='bicycle', ai=True)[0] == 422


def test_only_recipe_admins_can_use_the_editor_tools(admin_client, helper_client, make_user):
    assert admin_client.get('/admin/recipe-tools/check/').status_code == 405
    assert tool(admin_client, 'nope')[0] == 404
    r = admin_client.post('/admin/recipe-tools/check/', 'not json', content_type='application/json')
    assert r.status_code == 400
    assert tool(helper_client, 'check', **recipe_form())[0] == 200
    status, body = tool(helper_client, 'ingredient-add', name='Gongura')
    assert status == 403 and 'cannot add ingredients' in body['error'] and Ingredient.objects.count() == 0
    nobody = Client()
    nobody.force_login(User.objects.create_user('viewer@x.test', is_staff=True))
    assert nobody.post('/admin/recipe-tools/check/', '{}', content_type='application/json').status_code == 403
    for c in (make_user(), Client()):
        assert c.post('/admin/recipe-tools/read/', json.dumps({'text': WHATSAPP}), content_type='application/json').status_code == 302, 'sent to sign in'
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(User.objects.get(username=ADMIN['username']))
    assert strict.post('/admin/recipe-tools/check/', '{}', content_type='application/json').status_code == 403


def test_the_recipe_form_still_works_without_scripts(admin_client):
    page = admin_client.get('/admin/kitchen/recipe/add/').content.decode()
    for k in ('name', 'cuisine', 'meal', 'time', 'serves', 'spice', 'tags', 'ingredients', 'steps', 'recipe_id'):
        assert f'name="{k}"' in page, k
    evil = '</script><script>alert(1)</script>'
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='odd', name=evil))
    page = admin_client.get(f'/admin/kitchen/recipe/{Recipe.objects.get(recipe_id="odd").pk}/change/').content.decode()
    assert '<script>alert(1)' not in page
