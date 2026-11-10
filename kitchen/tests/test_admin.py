"""Tests for the admin portal (/admin): who can get in, what they can see, and publishing content."""
import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.test import Client

from kitchen.models import Announcement, Festival, HiddenRecipe, Ingredient, Recipe, Rescue
from .conftest import ADMIN, Api

pytestmark = pytest.mark.django_db


def recipe_form(**over):
    data = {'copy_from': '', 'recipe_id': 'test_khichdi', 'name': 'Test Khichdi', 'alt': '', 'cuisine': 'Test', 'meal': 'lunch, dinner',
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


def test_recipe_goes_draft_review_live(admin_client):
    visible = lambda: any(r['id'] == 'test_khichdi' for r in Api().get_json('catalog')[1]['recipes'])  # noqa: E731
    r = admin_client.post('/admin/kitchen/recipe/add/', recipe_form())
    assert r.status_code == 302, r.content[:2000]
    recipe = Recipe.objects.get(recipe_id='test_khichdi')
    assert recipe.status == 'draft' and not visible()
    page = act(admin_client, 'publish', recipe).content.decode()
    assert 'must be sent to review' in page and not visible()
    act(admin_client, 'send_to_review', recipe)
    page = act(admin_client, 'publish', recipe).content.decode()
    assert 'Users see it now' in page and visible()
    _, sug = Api().post_json('suggest', {'pantry': ['rice', 'moong_dal']})
    assert any(d['id'] == 'test_khichdi' for d in sug['ready'])


def test_editing_a_live_recipe_waits_for_publishing(admin_client):
    admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='edit_me', name='Version One'))
    recipe = Recipe.objects.get(recipe_id='edit_me')
    act(admin_client, 'send_to_review', recipe)
    act(admin_client, 'publish', recipe)
    admin_client.post(f'/admin/kitchen/recipe/{recipe.pk}/change/', {k: v for k, v in recipe_form(recipe_id='edit_me', name='Version Two').items() if k != 'copy_from'})
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
    r = admin_client.post('/admin/kitchen/recipe/add/', recipe_form(recipe_id='no_safety', tags='', ingredients='chicken:500 g'), follow=True)
    assert 'food-safety' in r.content.decode()


def test_copy_a_built_in_recipe_to_change_it(admin_client):
    r = admin_client.post('/admin/kitchen/recipe/add/', {**{k: '' for k in recipe_form()}, 'copy_from': 'dal_tadka', 'time': 1, 'serves': 1, 'spice': 1})
    assert r.status_code == 302, r.content[:3000]
    copy = Recipe.objects.get(recipe_id='dal_tadka')
    assert copy.name == 'Dal Tadka' and 'toor_dal' in copy.ingredients
    act(admin_client, 'send_to_review', copy)
    act(admin_client, 'publish', copy)
    names = [r['id'] for r in Api().get_json('catalog')[1]['recipes']]
    assert names.count('dal_tadka') == 1, 'the edited copy replaces the built-in one'


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


def test_admin_sign_out(admin_client):
    admin_client.post('/admin/logout/')
    assert admin_client.get('/admin/').status_code == 302
