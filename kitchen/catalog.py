"""The live recipe book: built-in data plus whatever admins have published."""
from django.db.models import F

from . import engine
from .data.ingredients import ASSUMED, CATEGORIES, KITS
from .models import Announcement, CatalogStamp, Festival, HiddenRecipe, Ingredient, Recipe, Rescue
from .planner import AGE_GROUPS, GOALS

_live = {'stamp': None, 'recipes': [], 'hidden': [], 'extra': {}}


def bump():
    """Call after admins change anything users see."""
    updated = CatalogStamp.objects.filter(pk=1).update(value=F('value') + 1)
    if not updated:
        CatalogStamp.objects.create(pk=1, value=1)


def stamp():
    row = CatalogStamp.objects.filter(pk=1).first()
    return row.value if row else 0


def live():
    """Published admin recipes and hidden ids, reloaded only when admins changed something."""
    now = stamp()
    if _live['stamp'] != now:
        engine.apply_catalog(ingredients=[i.to_raw() for i in Ingredient.objects.all()], rescues=[r.to_raw() for r in Rescue.objects.all()])
        recipes = [engine.prepare_recipe(r.live) for r in Recipe.objects.exclude(live=None)]
        _live.update(stamp=now, recipes=recipes, hidden=list(HiddenRecipe.objects.values_list('recipe_id', flat=True)),
                     extra={r['id']: r for r in recipes})
    return _live


def public_catalog():
    """Everything the phone app needs to show recipes and ingredients, even offline."""
    cat = live()
    return {
        'stamp': cat['stamp'],
        'recipes': engine.recipes_from(cat['recipes'], ()),
        'hidden': cat['hidden'],
        'ingredients': engine.INGREDIENTS,
        'categories': CATEGORIES, 'kits': KITS, 'assumed': ASSUMED,
        'rescues': engine.RESCUES,
        'announcements': [{'id': str(a.pk), 'text': a.text} for a in Announcement.objects.filter(active=True)],
        'festivals': festivals(),
        'goals': GOALS, 'ageGroups': AGE_GROUPS,
    }


def festivals():
    return [{'id': str(f.pk), 'name': f.name, 'date': f.date.isoformat(), 'fast': f.fast} for f in Festival.objects.all()]
