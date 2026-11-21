"""Tests for keeping data 6 months (kitchen/retention.py): what goes, what stays, and that it runs by itself."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from kitchen import retention
from kitchen.models import ChatThread, FamilyData, Household, Housekeeping, Poll, Profile
from .conftest import Api

pytestmark = pytest.mark.django_db
DAY_MS = 86400000


def ms(days_ago):
    return int((timezone.now() - timedelta(days=days_ago)).timestamp() * 1000)


def day(days_ago):
    return timezone.localdate() - timedelta(days=days_ago)


def test_old_entries_are_trimmed_from_family_data():
    history = [{'id': 'new', 'date': day(10).isoformat()}, {'id': 'old', 'date': day(200).isoformat()},
               {'id': 'old-at', 'at': ms(190)}, {'id': 'new-at', 'at': ms(3)}]
    assert [h['id'] for h in retention.prune_value('history', history)] == ['new', 'new-at']
    saved = [{'id': 'dal_tadka', 'at': ms(10)}, {'id': 'chole', 'at': ms(181)}]
    assert [s['id'] for s in retention.prune_value('savedDishes', saved)] == ['dal_tadka']
    ai = {'ai_a': {'createdAt': ms(200)}, 'ai_b': {'createdAt': ms(200)}, 'ai_c': {'createdAt': ms(5)}}
    assert set(retention.prune_value('aiRecipes', ai, saved_ids={'ai_b'})) == {'ai_b', 'ai_c'}, 'a saved AI recipe stays'
    assert retention.prune_value('pantry', [{'id': 'rice', 'addedAt': ms(400)}]) == [{'id': 'rice', 'addedAt': ms(400)}], 'the kitchen stays'


def test_an_old_phone_cannot_bring_old_meals_back(make_user):
    c = make_user()
    history = [{'id': 'a', 'date': day(1).isoformat(), 'name': 'Dal'}, {'id': 'b', 'date': day(300).isoformat(), 'name': 'Old'}]
    c.post_json('state', {'key': 'history', 'value': history, 'baseVersion': 0})
    assert [h['id'] for h in c.get_json('state')[1]['items']['history']['value']] == ['a']


def test_cleanup_removes_old_things_and_unused_accounts(make_user):
    active, idle = make_user(), make_user()
    idle_user = User.objects.get(email=idle.email)
    User.objects.filter(pk=idle_user.pk).update(date_joined=timezone.now() - timedelta(days=400))
    Profile.objects.filter(user=idle_user).update(last_seen=timezone.now() - timedelta(days=200))
    idle_family = idle_user.profile.household_id
    admin = User.objects.create_superuser('boss@ballava.test', 'boss@ballava.test', 'a-long-admin-password')
    User.objects.filter(pk=admin.pk).update(date_joined=timezone.now() - timedelta(days=900))

    active.post_json('chats', {'id': 'oldchat1', 'title': 'Old', 'at': ms(1), 'messages': []})
    active.post_json('chats', {'id': 'newchat1', 'title': 'New', 'at': ms(1), 'messages': []})
    ChatThread.objects.filter(chat_id='oldchat1').update(at=ms(190))
    user = User.objects.get(email=active.email)
    FamilyData.objects.create(household=user.profile.household, key='history', version=3,
                              value=[{'id': 'x', 'date': day(5).isoformat()}, {'id': 'y', 'date': day(250).isoformat()}])
    poll = Poll.objects.create(token='t' * 16, household=user.profile.household, title='Old vote', options=[], closes_at=timezone.now())
    Poll.objects.filter(pk=poll.pk).update(created_at=timezone.now() - timedelta(days=200))

    done = retention.cleanup()
    assert done['accounts'] == 1 and done['families'] == 1 and done['meals'] == 1 and done['chats'] == 1 and done['votes'] == 1
    assert not User.objects.filter(pk=idle_user.pk).exists() and not Household.objects.filter(pk=idle_family).exists()
    assert User.objects.filter(pk=admin.pk).exists(), 'admins are never removed'
    row = FamilyData.objects.get(household=user.profile.household, key='history')
    assert [h['id'] for h in row.value] == ['x'] and row.version == 4, 'a new version, so phones take the trimmed copy'
    assert list(ChatThread.objects.values_list('chat_id', flat=True)) == ['newchat1']


def test_cleanup_runs_by_itself_once_a_day(make_user):
    make_user()
    Housekeeping.objects.all().delete()
    assert Api().get_json('me')[0] == 200
    first = Housekeeping.objects.get(name='retention')
    assert first.last_run == timezone.localdate()
    assert retention.maybe_cleanup() is None, 'already ran today'


def test_retention_can_be_switched_off(settings):
    settings.DATA_RETENTION_DAYS = 0
    old = [{'id': 'b', 'date': day(3000).isoformat()}]
    assert retention.prune_value('history', old) == old and retention.cleanup() == {}
    assert Api().get_json('health')[1]['retentionDays'] == 0


def test_cleanup_command(make_user, capsys):
    make_user()
    call_command('cleanup_old_data')
    assert 'Removed data older than 180 days' in capsys.readouterr().out


def test_admin_dashboard_explains_the_6_month_rule(admin_client):
    retention.maybe_cleanup()
    page = admin_client.get('/admin/').content.decode()
    assert 'Data is kept for 180 days' in page and 'Last clean-up' in page
