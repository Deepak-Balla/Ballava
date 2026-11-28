"""Tests for Help & support: people send a problem or question from the app, admins answer it in the admin portal."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from kitchen import retention
from kitchen.models import SupportMessage, SupportRequest
from .conftest import ADMIN, Api

pytestmark = pytest.mark.django_db
PROBLEM = {'category': 'problem', 'subject': 'Timer stops', 'message': 'The cooker timer stops when my screen turns off.'}


def send(c, **over):
    status, data = c.post_json('support', {**PROBLEM, **over}, HTTP_USER_AGENT='TestPhone/1.0')
    assert status == 200, data
    return data['request']


def admin_reply(admin_client, ticket_id, text, status='open'):
    r = admin_client.post(f'/admin/kitchen/supportrequest/{ticket_id}/change/', {'status': status, 'reply': text, '_save': 'Save'})
    assert r.status_code == 302, r.content.decode()[:2000]


def test_support_needs_a_sign_in(api):
    assert api.get_json('support')[0] == 401
    assert api.post_json('support', PROBLEM)[0] == 401
    assert api.post_json('support/1/reply', {'text': 'hi'})[0] == 401


def test_send_a_request_and_see_it(make_user):
    c = make_user()
    sent = send(c)
    assert sent['status'] == 'open' and sent['statusLabel'] == 'Open' and sent['categoryLabel'] == "Something isn't working"
    assert sent['messages'] == [{'fromTeam': False, 'text': PROBLEM['message'], 'at': sent['messages'][0]['at']}]
    assert sent['unread'] is False
    assert [r['id'] for r in c.get_json('support')[1]['requests']] == [sent['id']]
    assert SupportRequest.objects.get(pk=sent['id']).device == 'TestPhone/1.0', 'the browser is kept, to help find the problem'


def test_support_checks_what_is_sent(make_user):
    c = make_user()
    assert c.post_json('support', {**PROBLEM, 'subject': '  '})[0] == 400
    assert c.post_json('support', {**PROBLEM, 'message': ''})[0] == 400
    status, data = c.post_json('support', {**PROBLEM, 'message': 'x' * 2001})
    assert status == 400 and '2000' in data['error']
    assert send(c, category='made-up')['category'] == 'other'


def test_requests_are_private_even_inside_a_family(make_user):
    owner, relative = make_user(), make_user()
    code = owner.get_json('me')[1]['household']['inviteCode']
    assert relative.post_json('household/join', {'code': code})[0] == 200
    sent = send(owner)
    assert relative.get_json('support')[1]['requests'] == []
    for action in ('reply', 'resolve', 'read'):
        assert relative.post_json(f'support/{sent["id"]}/{action}', {'text': 'not mine'})[0] == 404, action
    assert SupportMessage.objects.filter(ticket_id=sent['id']).count() == 1


def test_admin_replies_and_the_person_sees_it(make_user, admin_client):
    c = make_user()
    sent = send(c)

    page = admin_client.get('/admin/kitchen/supportrequest/').content.decode()
    assert 'Timer stops' in page and 'Needs a reply' in page and 'class="b-count"' in page
    home = admin_client.get('/admin/').content.decode()
    assert 'Support: needs a reply' in home and f'#{sent["id"]} Timer stops' in home
    assert PROBLEM['message'] in admin_client.get(f'/admin/kitchen/supportrequest/{sent["id"]}/change/').content.decode()
    assert 'Timer stops' in admin_client.get('/admin/kitchen/supportrequest/?q=screen+turns').content.decode(), 'search finds words in messages'
    assert 'Timer stops' not in admin_client.get('/admin/kitchen/supportrequest/?q=biryani').content.decode()

    admin_reply(admin_client, sent['id'], 'Thanks! Please keep the screen on while cooking. A fix is coming.')
    ticket = SupportRequest.objects.get(pk=sent['id'])
    assert ticket.status == SupportRequest.IN_PROGRESS, 'replying moves an open request to In progress'
    reply = ticket.messages.last()
    assert reply.from_team and reply.author.username == ADMIN['username']

    assert c.get_json('me')[1]['supportUnread'] == 1
    mine = c.get_json('support')[1]['requests'][0]
    assert mine['unread'] and mine['status'] == 'in_progress' and mine['messages'][-1]['fromTeam']
    assert 'author' not in mine['messages'][-1], 'the person sees "Ballava team", not which admin answered'

    assert c.post_json(f'support/{sent["id"]}/read')[0] == 200
    assert c.get_json('me')[1]['supportUnread'] == 0 and not c.get_json('support')[1]['requests'][0]['unread']
    assert 'Answered, waiting for them' in admin_client.get('/admin/kitchen/supportrequest/').content.decode()
    assert 'class="b-count"' not in admin_client.get('/admin/').content.decode(), 'nothing waits for a reply now'


def test_resolving_and_writing_again(make_user, admin_client):
    c = make_user()
    sent = send(c)
    admin_reply(admin_client, sent['id'], 'Fixed in the latest version.', status='resolved')
    ticket = SupportRequest.objects.get(pk=sent['id'])
    assert ticket.status == SupportRequest.RESOLVED and ticket.resolved_at

    status, data = c.post_json(f'support/{sent["id"]}/reply', {'text': 'It happened again today.'})
    assert status == 200 and data['request']['status'] == 'open', 'writing on a resolved request opens it again'
    assert SupportRequest.objects.get(pk=sent['id']).resolved_at is None

    status, data = c.post_json(f'support/{sent["id"]}/resolve')
    assert status == 200 and data['request']['status'] == 'resolved'


def test_admin_actions_change_many_at_once(make_user, admin_client):
    c = make_user()
    a, b = send(c), send(c, subject='Second')
    admin_client.post('/admin/kitchen/supportrequest/', {'action': 'mark_resolved', '_selected_action': [a['id'], b['id']]})
    assert set(SupportRequest.objects.values_list('status', flat=True)) == {SupportRequest.RESOLVED}
    admin_client.post('/admin/kitchen/supportrequest/', {'action': 'mark_in_progress', '_selected_action': [a['id']]})
    assert SupportRequest.objects.get(pk=a['id']).status == SupportRequest.IN_PROGRESS


def test_only_the_app_creates_requests_and_family_users_stay_out_of_admin(make_user, admin_client):
    assert admin_client.get('/admin/kitchen/supportrequest/add/').status_code == 403
    r = make_user().get('/admin/kitchen/supportrequest/')
    assert r.status_code == 302 and '/admin/login/' in r['Location']


def test_what_people_write_is_shown_safely_to_admins(make_user, admin_client):
    c = make_user()
    sent = send(c, subject='<b>bold</b>', message='<script>alert(1)</script>\nsecond line')
    page = admin_client.get(f'/admin/kitchen/supportrequest/{sent["id"]}/change/').content.decode()
    assert '<script>alert(1)</script>' not in page and '&lt;script&gt;alert(1)&lt;/script&gt;' in page


def test_users_list_shows_open_requests(make_user, admin_client):
    c = make_user()
    send(c)
    user = User.objects.get(email=c.email)
    page = admin_client.get('/admin/auth/user/').content.decode()
    assert '1 open' in page and f'user__id__exact={user.pk}' in page
    filtered = admin_client.get(f'/admin/kitchen/supportrequest/?user__id__exact={user.pk}')
    assert filtered.status_code == 200 and 'Timer stops' in filtered.content.decode()


def test_too_many_requests_in_a_day_wait(make_user):
    c = make_user()
    statuses = [c.post_json('support', PROBLEM)[0] for _ in range(11)]
    assert statuses[:10] == [200] * 10 and statuses[10] == 429


def test_requests_go_in_your_download_and_with_your_account(make_user):
    c = make_user()
    send(c)
    assert c.get_json('account/export')[1]['support'][0]['subject'] == 'Timer stops'
    assert c.post_json('account/delete', {'confirm': 'DELETE'})[0] == 200
    assert not SupportRequest.objects.exists() and not SupportMessage.objects.exists()


def test_cleanup_removes_old_resolved_requests_only(make_user):
    c = make_user()
    old_done, old_open, new_done = send(c), send(c), send(c)
    SupportRequest.objects.filter(pk__in=[old_done['id'], new_done['id']]).update(status=SupportRequest.RESOLVED)
    SupportRequest.objects.filter(pk__in=[old_done['id'], old_open['id']]).update(updated_at=timezone.now() - timedelta(days=200))
    assert retention.cleanup()['supportRequests'] == 1
    assert set(SupportRequest.objects.values_list('pk', flat=True)) == {old_open['id'], new_done['id']}, 'open ones wait for the team'


def test_signed_in_users_see_how_many_replies_are_new(make_user):
    assert Api().get_json('me')[1] == {'user': None}
    assert make_user().get_json('me')[1]['supportUnread'] == 0
