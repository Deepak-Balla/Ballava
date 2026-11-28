"""Ballava keeps what people do for 6 months (DATA_RETENTION_DAYS), then deletes it.

What goes after 6 months:
- each meal in the food diary, 6 months after the day it was eaten
- each saved (hearted) dish, 6 months after it was saved (saving it again starts the clock again)
- each AI recipe, 6 months after it was made, unless it's still saved
- each chat with Ballava Chef, 6 months after its last message
- each support request, 6 months after it was resolved (open ones stay until the team answers them)
- family votes, AI usage counts and sign-in attempt records
- whole accounts nobody has used for 6 months, with their family's data when nobody else in the family is active

What stays while the account is used: the kitchen, family members, the plan, the shopping list and preferences.
They describe the family today, and they're kept up to date by using the app.

Everything you use is kept between sign-ins until then: it's stored in your account, not only on the phone.

The clean-up runs by itself once a day (the first time someone opens the app that day), and can also be run by hand:
    python manage.py cleanup_old_data
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from . import supabase
from .models import AiUsage, Attempt, ChatThread, FamilyData, Household, Housekeeping, Poll, SupportRequest

log = logging.getLogger('kitchen')
DATED_KEYS = ('history', 'savedDishes', 'aiRecipes')


def days():
    return max(0, settings.DATA_RETENTION_DAYS)


def cutoff(now=None):
    """The moment before which things are deleted: (datetime, 'YYYY-MM-DD', milliseconds)."""
    when = (now or timezone.now()) - timedelta(days=days())
    return when, timezone.localtime(when).date().isoformat(), int(when.timestamp() * 1000)


def _fresh_entry(entry, day, ms):
    """A diary entry is kept if it's dated on or after the cut-off day (older entries only have a timestamp)."""
    if not isinstance(entry, dict):
        return False
    if entry.get('date'):
        return str(entry['date']) >= day
    return isinstance(entry.get('at'), (int, float)) and entry['at'] >= ms


def prune_value(key, value, now=None, saved_ids=None):
    """The same family data with everything older than 6 months taken out. Used on every save, and by the clean-up."""
    if not days() or key not in DATED_KEYS:
        return value
    _, day, ms = cutoff(now)
    if key == 'history' and isinstance(value, list):
        return [e for e in value if _fresh_entry(e, day, ms)]
    if key == 'savedDishes' and isinstance(value, list):
        return [s for s in value if isinstance(s, dict) and (not isinstance(s.get('at'), (int, float)) or s['at'] >= ms)]
    if key == 'aiRecipes' and isinstance(value, dict):
        keep = saved_ids or set()
        return {k: r for k, r in value.items() if k in keep or not isinstance((r or {}).get('createdAt'), (int, float)) or r['createdAt'] >= ms}
    return value


def cleanup(now=None):
    """Delete everything past its 6 months. Returns what was removed, by kind."""
    if not days():
        return {}
    when, day, ms = cutoff(now)
    done = {'accounts': 0, 'families': 0, 'meals': 0, 'savedDishes': 0, 'aiRecipes': 0, 'chats': 0, 'votes': 0, 'supportRequests': 0}

    # Accounts nobody has used for 6 months (never admins). Their family goes too if nobody else in it is active.
    stale = User.objects.filter(is_staff=False, profile__isnull=False).exclude(profile__last_seen__gte=when).filter(date_joined__lt=when)
    for user in stale.select_related('profile'):
        if user.profile.last_seen and user.profile.last_seen >= when:
            continue
        supabase_id = user.profile.supabase_id
        with transaction.atomic():
            household = user.profile.household
            user.delete()
            done['accounts'] += 1
            if household and not household.people.exists():
                household.delete()
                done['families'] += 1
        supabase.delete_person(supabase_id)

    # Dated family data: old meals, old saved dishes, old AI recipes.
    for household in Household.objects.all():
        rows = {r.key: r for r in FamilyData.objects.filter(household=household, key__in=DATED_KEYS)}
        saved = rows.get('savedDishes')
        new_saved = prune_value('savedDishes', saved.value, now) if saved else []
        saved_ids = {s.get('id') for s in new_saved if isinstance(s, dict)}
        for key, row in rows.items():
            new = new_saved if key == 'savedDishes' else prune_value(key, row.value, now, saved_ids)
            removed = len(row.value) - len(new) if isinstance(row.value, (list, dict)) else 0
            if removed:
                row.value, row.version = new, row.version + 1  # a new version, so every phone takes the trimmed copy
                row.save()
                done['meals' if key == 'history' else key] += removed

    done['chats'] = ChatThread.objects.filter(at__lt=ms).delete()[0]
    done['votes'] = Poll.objects.filter(created_at__lt=when).delete()[0]
    old_support = SupportRequest.objects.filter(status=SupportRequest.RESOLVED, updated_at__lt=when)
    done['supportRequests'] = old_support.delete()[1].get('kitchen.SupportRequest', 0)  # not counting their messages
    AiUsage.objects.filter(day__lt=when.date()).delete()
    Attempt.objects.filter(at__lt=when).delete()
    log.info('Removed data older than %s days: %s', days(), done)
    return done


def maybe_cleanup(now=None):
    """Run the clean-up at most once a day. Cheap to call on every app start."""
    if not days():
        return None
    today = timezone.localdate(now)
    if Housekeeping.objects.filter(name='retention', last_run=today).exists():
        return None
    Housekeeping.objects.update_or_create(name='retention', defaults={'last_run': today, 'details': {}})
    try:
        done = cleanup(now)
    except Exception:  # noqa: BLE001  a clean-up problem must never stop anyone using the app
        log.exception('Data clean-up failed')
        return None
    Housekeeping.objects.filter(name='retention').update(details=done)
    return done
