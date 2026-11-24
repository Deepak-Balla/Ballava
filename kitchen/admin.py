"""The admin portal at /admin, built on Django's admin.

What admins can do: add and edit recipes (draft -> review -> publish, with safety checks), hide recipes,
add ingredients and Bachao fixes, post announcements, keep the festival calendar, and disable users.
What admins cannot see: any family's kitchen, members, diets, health goals or meal diary.
"""
import json
from collections import Counter
from datetime import timedelta
from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Sum
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone

from . import ai, api, catalog, engine, recipe_editor
from .data.ingredients import CATEGORIES
from .data.recipes import RECIPES
from .models import AiUsage, Announcement, FamilyData, Festival, HiddenRecipe, Household, Housekeeping, Ingredient, Recipe, Rescue
from .security import ApiError, clear_limit, client_ip, limited

BUILT_IN = {r['id']: r for r in RECIPES}
DIETS = {'veg': 'Vegetarian', 'egg': 'Egg', 'nonveg': 'Non-veg'}
SPICE = {1: 'Mild', 2: 'Medium', 3: 'Hot'}


# ---------------------------------------------------------------- publishing
def can_publish(user, recipe):
    """Superusers publish straight away. Other admins' recipes are reviewed first."""
    return user.has_perm('kitchen.change_recipe') and (user.is_superuser or recipe.status == Recipe.REVIEW)


def publish_recipe(site, request, recipe):
    """Makes it live if it passes every check. Tells the admin how it went; returns True when it's live."""
    link = format_html('<a href="{}">{}</a>', reverse('admin:recipe_detail', args=[recipe.recipe_id]), recipe.name)
    if not can_publish(request.user, recipe):
        messages.error(request, format_html('{} must be sent to review before publishing.', link))
        return False
    problems = recipe_editor.problems_of(recipe.to_raw())
    if problems:
        messages.error(request, format_html('{} cannot be published yet: {}', link, ' '.join(p['text'] for p in problems)))
        return False
    recipe.live, recipe.status = recipe.to_raw(), Recipe.PUBLISHED
    recipe.save()
    LogEntry.objects.log_actions(request.user.pk, [recipe], CHANGE, change_message='Published', single_object=True)
    messages.success(request, format_html('{} is published. Users see it now.', link))
    return True


# ---------------------------------------------------------------- the recipe book (every recipe, in one place)
def book_entry(r, row, hidden, draft_only=False):
    """One recipe as the recipe book shows it. `row` is the admin's Recipe, if there is one."""
    builtin = r['id'] in BUILT_IN
    source_key = ('edited' if row else 'builtin') if builtin else 'custom'
    if draft_only:
        state, status = 'draft', f'{row.get_status_display()}, not live'
    elif r['id'] in hidden:
        state, status = 'hidden', 'Hidden'
    else:
        state, status = 'live', 'Live'
    n = r.get('nutrition') or {}
    return {
        'id': r['id'], 'r': r, 'row': row, 'state': state, 'status': status, 'source_key': source_key,
        'source': {'builtin': 'Built-in', 'edited': 'Built-in, edited', 'custom': 'Added by admin'}[source_key],
        'pending': bool(row and not draft_only and row.status != Recipe.PUBLISHED),
        'kcal': n.get('kcal'), 'protein': n.get('protein'), 'meals': ', '.join(m.capitalize() for m in r.get('meal') or []),
        'diet_label': DIETS.get(r.get('diet'), r.get('diet')), 'spice_label': SPICE.get(r.get('spice'), r.get('spice')),
    }


def book_entries():
    """Every recipe: what users see (built-in, admin edits and admin additions), hidden ones, and drafts never published."""
    live = catalog.live()
    hidden = set(live['hidden'])
    rows = {r.recipe_id: r for r in Recipe.objects.all()}
    out = [book_entry(r, rows.get(r['id']), hidden) for r in engine.recipes_from(live['recipes'], ())]
    for rid, row in rows.items():
        if row.live is None:
            try:
                out.append(book_entry(engine.prepare_recipe(row.to_raw()), row, hidden, draft_only=True))
            except (KeyError, ValueError, TypeError):
                continue
    return out


class BallavaAdminSite(admin.AdminSite):
    site_header = 'Ballava Admin'
    site_title = 'Ballava Admin'
    index_title = 'Overview'
    index_template = 'kitchen/admin_index.html'

    def login(self, request, extra_context=None):
        """Django's admin sign-in, plus a 15-minute lock after 5 wrong passwords."""
        if request.method != 'POST':
            return super().login(request, extra_context)
        key = f"admin:{request.POST.get('username', '').strip().lower()}:{client_ip(request)}"
        if limited(key, 5, 900):
            return HttpResponse('Too many tries. Please wait 15 minutes and try again.', status=429, content_type='text/plain')
        response = super().login(request, extra_context)
        if request.user.is_authenticated and request.user.is_staff:
            clear_limit(key)
        return response

    def get_urls(self):
        return [
            path('recipe-book/', self.admin_view(self.recipe_book), name='recipe_book'),
            path('recipe-book/<slug:recipe_id>/', self.admin_view(self.recipe_detail), name='recipe_detail'),
            path('recipe-book/<slug:recipe_id>/publish/', self.admin_view(self.recipe_publish), name='recipe_publish'),
            path('recipe-tools/<slug:tool>/', self.admin_view(self.recipe_tools), name='recipe_tools'),
            path('ingredient-book/', self.admin_view(self.ingredient_book), name='ingredient_book'),
        ] + super().get_urls()

    def index(self, request, extra_context=None):
        week_ago = timezone.now() - timedelta(days=7)
        today = timezone.localdate()
        month_ago = today - timedelta(days=29)
        meals = sum(len(v) for v in FamilyData.objects.filter(key='history').values_list('value', flat=True) if isinstance(v, list))
        review = list(Recipe.objects.filter(status=Recipe.REVIEW)[:8])
        stats = [
            ('👥', 'Users', User.objects.filter(is_staff=False).count(), ''),
            ('🟢', 'Active in 7 days', User.objects.filter(is_staff=False, profile__last_seen__gte=week_ago).count(), ''),
            ('🏠', 'Families', Household.objects.count(), ''),
            ('🍽', 'Meals logged', meals, ''),
            ('📖', 'Built-in recipes', len(RECIPES), ''),
            ('✏️', 'Custom recipes live', Recipe.objects.exclude(live=None).count(), ''),
            ('⏳', 'Waiting for review', Recipe.objects.filter(status=Recipe.REVIEW).count(), 'warn' if review else ''),
            ('✨', 'AI calls, 30 days', AiUsage.objects.filter(day__gte=month_ago).aggregate(n=Sum('calls'))['n'] or 0, ''),
        ]
        drafts = [(r, recipe_editor.problems_of(r.to_raw())) for r in Recipe.objects.filter(status=Recipe.DRAFT).order_by('-updated_at')[:6]]
        entries = book_entries()
        live = [e for e in entries if e['state'] == 'live']
        kcals = [e['kcal'] for e in live if e['kcal'] is not None]
        book = {
            'total': len(entries), 'live': len(live), 'hidden': sum(1 for e in entries if e['state'] == 'hidden'),
            'breakfast': sum(1 for e in live if 'breakfast' in e['r']['meal']),
            'main': sum(1 for e in live if {'lunch', 'dinner'} & set(e['r']['meal'])),
            'snack': sum(1 for e in live if 'snack' in e['r']['meal']),
            **{d: sum(1 for e in live if e['r']['diet'] == d) for d in DIETS},
            'avg_kcal': round(sum(kcals) / len(kcals)) if kcals else '–',
        }
        calls = dict(AiUsage.objects.filter(day__gte=today - timedelta(days=6)).values('day').annotate(n=Sum('calls')).values_list('day', 'n'))
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        top = max([calls.get(d, 0) for d in days] + [1])
        hour = timezone.localtime().hour
        return super().index(request, {
            'ballava_stats': stats, 'ballava_review': review, 'ballava_drafts': drafts, 'ballava_book': book,
            'ballava_recent': LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')[:8],
            'ballava_ai_days': [(d.strftime('%a'), calls.get(d, 0), round(calls.get(d, 0) / top * 100)) for d in days],
            'ballava_ai_limit': settings.AI_RATE_LIMIT,
            'ballava_retention': {'days': settings.DATA_RETENTION_DAYS, 'last': Housekeeping.objects.filter(name='retention').first()},
            'ballava_greeting': 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening',
            **(extra_context or {}),
        })

    # ---- Recipe book: every recipe, including the built-in ones that live in the code
    MEAL_CHOICES = [('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner'), ('snack', 'Snack'), ('side', 'Side'), ('dessert', 'Dessert')]
    SOURCE_CHOICES = [('builtin', 'Built-in'), ('edited', 'Built-in, edited'), ('custom', 'Added by admin')]
    STATE_CHOICES = [('live', 'Live'), ('hidden', 'Hidden'), ('draft', 'Draft, not live')]
    SORTS = {'name': ('Name', lambda e: e['r']['name'].lower()), 'time': ('Quickest', lambda e: e['r']['time']),
             'kcal': ('Fewest calories', lambda e: e['kcal'] if e['kcal'] is not None else 9999),
             'protein': ('Most protein', lambda e: -(e['protein'] or 0))}

    def recipe_book(self, request):
        entries = book_entries()
        p = {k: request.GET.get(k, '').strip() for k in ('q', 'meal', 'diet', 'source', 'state', 'sort')}
        q = p['q'].lower()

        def matches(e):
            r = e['r']
            text = ' '.join([r['id'], r['name'], r.get('alt') or '', r.get('cuisine') or '', *r.get('tags', []),
                             *(engine.name_of(i) for it in r['ingredients'] for i in it['options'])]).lower()
            return ((not q or q in text) and (not p['meal'] or p['meal'] in r['meal']) and (not p['diet'] or r['diet'] == p['diet'])
                    and (not p['source'] or e['source_key'] == p['source']) and (not p['state'] or e['state'] == p['state']))
        shown = sorted(filter(matches, entries), key=self.SORTS.get(p['sort'], self.SORTS['name'])[1])
        counts = {k: sum(1 for e in entries if k in (e['source_key'], e['state'])) for k in ('builtin', 'edited', 'custom', 'live', 'hidden', 'draft')}
        return TemplateResponse(request, 'kitchen/recipe_book.html', {
            **self.each_context(request), 'title': 'Recipe book', 'entries': shown, 'total': len(entries), 'counts': counts,
            'builtin_total': len(BUILT_IN), 'params': p, 'meal_choices': self.MEAL_CHOICES, 'diet_choices': list(DIETS.items()),
            'source_choices': self.SOURCE_CHOICES, 'state_choices': self.STATE_CHOICES,
            'sort_choices': [(k, v[0]) for k, v in self.SORTS.items()],
        })

    def recipe_detail(self, request, recipe_id):
        e = next((x for x in book_entries() if x['id'] == recipe_id), None)
        if not e:
            raise Http404('No recipe with that id.')
        r = e['r']
        lines = []
        for i, it in enumerate(r['ingredients']):
            got = (r.get('nutrition') or {}).get('lines', [None] * len(r['ingredients']))[i]
            lines.append({'label': it.get('custom') or ' or '.join(engine.name_of(o) for o in it['options']), 'ids': ' | '.join(it['options']),
                          'qty': it['qty'], 'optional': it['optional'], 'unknown': not all(o in engine.BY_ID for o in it['options']),
                          'grams': got and got['grams'], 'kcal': got and got['kcal']})
        row, hidden = e['row'], HiddenRecipe.objects.filter(recipe_id=recipe_id).first()
        edit_url = (reverse('admin:kitchen_recipe_change', args=[row.pk]) if row
                    else reverse('admin:kitchen_recipe_add') + '?' + urlencode({'copy_from': recipe_id}))
        return TemplateResponse(request, 'kitchen/recipe_detail.html', {
            **self.each_context(request), 'title': r['name'], 'e': e, 'lines': lines,
            'problems': recipe_editor.problems_of(row.to_raw()) if row else [],
            'publish': bool(row) and row.status != Recipe.PUBLISHED and can_publish(request.user, row),
            'can_change': request.user.has_perm('kitchen.change_recipe') and request.user.has_perm('kitchen.add_recipe'),
            'edit_url': edit_url,
            'hide_url': (reverse('admin:kitchen_hiddenrecipe_add') + '?' + urlencode({'recipe_id': recipe_id}))
            if request.user.has_perm('kitchen.add_hiddenrecipe') else None,
            'hidden_url': reverse('admin:kitchen_hiddenrecipe_delete', args=[hidden.pk]) if hidden else None,
        })

    def recipe_publish(self, request, recipe_id):
        """The Publish button on a recipe's page."""
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        recipe = Recipe.objects.filter(recipe_id=recipe_id).first()
        if not recipe:
            raise Http404('No recipe with that id.')
        if not request.user.has_perm('kitchen.change_recipe'):
            raise PermissionDenied
        publish_recipe(self, request, recipe)
        return HttpResponseRedirect(reverse('admin:recipe_detail', args=[recipe_id]))

    # ---- What the recipe editor asks while an admin types (kitchen/static/kitchen/recipe_editor.js)
    def recipe_tools(self, request, tool):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        if not (request.user.has_perm('kitchen.add_recipe') or request.user.has_perm('kitchen.change_recipe')):
            raise PermissionDenied
        action = {'check': self._tool_check, 'read': self._tool_read, 'lines': self._tool_lines, 'write': self._tool_write, 'source': self._tool_source,
                  'ingredient-guess': self._tool_guess, 'ingredient-add': self._tool_add_ingredient}.get(tool)
        if not action:
            raise Http404
        try:
            body = json.loads(request.body or '{}')
            if not isinstance(body, dict):
                raise ValueError('Unexpected request.')
            catalog.live()
            return JsonResponse(action(request, body))
        except ApiError as err:
            return JsonResponse({'error': err.message}, status=err.status)
        except (ValueError, KeyError, TypeError) as err:
            return JsonResponse({'error': str(err) if type(err) is ValueError else 'That could not be read.'}, status=400)

    def _tool_check(self, request, body):
        text = lambda k, n=4000: str(body.get(k) or '')[:n]  # noqa: E731

        def number(k):
            try:
                return int(float(body.get(k)))
            except (TypeError, ValueError):
                return 0
        own = text('recipe_id', 40)
        draft = Recipe(recipe_id=own or 'new_recipe', name=text('name', 80), cuisine=text('cuisine', 40), meal=text('meal', 80), tags=text('tags', 200), time=number('time'),
                       serves=number('serves'), spice=number('spice'), ingredients=text('ingredients'), steps=text('steps', 12000), safety=text('safety', 400))
        return recipe_editor.check(draft.to_raw(), own)

    def _tool_read(self, request, body):
        """A pasted recipe. The AI reads it when it's on; otherwise (or when it's busy) Ballava reads it by itself."""
        text = str(body.get('text') or '').strip()
        if len(text) < 15:
            raise ValueError('Please paste the whole recipe.')
        note = None
        if ai.ai_key() and body.get('ai') is not False:
            try:
                api._ai_allowed(request)
                return {'fields': recipe_editor.from_ai(ai.read_recipe(text)), 'source': 'ai'}
            except (ApiError, ValueError) as err:
                note = f'The AI could not read it ({getattr(err, "message", err)}), so Ballava read it by itself.'
        fields = recipe_editor.read_text(text)
        if not fields['ingredients'] and not fields['steps']:
            raise ValueError("No ingredients or steps were found in that. Please paste the whole recipe.")
        return {'fields': fields, 'source': 'text', 'note': note}

    def _tool_lines(self, request, body):
        """Several lines pasted into an ingredient box or a step box."""
        lines = [x for x in str(body.get('text') or '')[:8000].splitlines() if x.strip()]
        return {'ingredients': recipe_editor.drop_basics([r for x in lines for r in recipe_editor.read_ingredient(x)])[:40],
                'steps': [recipe_editor.read_step(x) for x in lines][:25]}

    def _tool_write(self, request, body):
        """The AI writes a recipe from its name."""
        name = str(body.get('name') or '').strip()[:80]
        if not name:
            raise ValueError('Please type the name of the dish.')
        api._ai_allowed(request)
        wish = f'{name}. {str(body.get("wish") or "").strip()[:200]}'.strip()
        return {'fields': recipe_editor.from_ai(ai.invent_recipe(wish=wish)), 'source': 'ai'}

    def _tool_source(self, request, body):
        """An existing recipe, to copy into a new one."""
        e = next((x for x in book_entries() if x['id'] == body.get('id')), None)
        if not e:
            raise ValueError('That recipe was not found.')
        raw = e['row'].to_raw() if e['row'] else BUILT_IN[e['id']]
        return {'fields': {**recipe_editor.fields_of(raw), 'recipe_id': '', 'name': f"{raw['name']} (copy)"}, 'source': 'copy'}

    def _tool_guess(self, request, body):
        """Details for a new ingredient: from its name, or from the AI."""
        name = str(body.get('name') or '').strip()[:60]
        if body.get('ai') is not True:
            return {'fields': recipe_editor.guess_ingredient(name)}
        api._ai_allowed(request)
        return {'fields': recipe_editor.clean_ingredient(ai.describe_ingredient(name))}

    def _tool_add_ingredient(self, request, body):
        if not request.user.has_perm('kitchen.add_ingredient'):
            raise ApiError(403, 'Your account cannot add ingredients.')
        made, id_ = recipe_editor.new_ingredient(body)
        if made:
            LogEntry.objects.log_actions(request.user.pk, [made], ADDITION, change_message='Added from the recipe editor', single_object=True)
            catalog.live()
        return {'ingredient': next(i for i in recipe_editor.ingredient_list() if i['id'] == id_), 'existed': not made}

    ING_SORTS = {'name': ('Name', lambda i: i['name'].lower()), 'kcal': ('Most calories', lambda i: -(i['n'] or {}).get('kcal', -1)),
                 'protein': ('Most protein', lambda i: -(i['n'] or {}).get('protein', -1)), 'used': ('Most used', lambda i: -i['used'])}

    def ingredient_book(self, request):
        live = catalog.live()
        used = Counter(o for r in engine.recipes_from(live['recipes'], live['hidden']) for it in r['ingredients'] for o in set(it['options']))
        added = set(Ingredient.objects.values_list('ingredient_id', flat=True))
        rows = [{'id': i['id'], 'name': i['name'], 'category': i['category'], 'diet': i.get('diet', 'veg'), 'n': i.get('nutrition'),
                 'm': i.get('measures') or {}, 'used': used.get(i['id'], 0), 'aliases': ', '.join(i.get('aliases') or []),
                 'allergens': i.get('allergens') or [], 'shelf': i.get('shelfDays'), 'admin': i['id'] in added} for i in engine.INGREDIENTS]
        p = {k: request.GET.get(k, '').strip() for k in ('q', 'category', 'sort')}
        q = p['q'].lower()
        shown = [i for i in rows if (not q or q in f"{i['id']} {i['name']} {i['aliases']}".lower()) and (not p['category'] or i['category'] == p['category'])]
        shown.sort(key=self.ING_SORTS.get(p['sort'], self.ING_SORTS['name'])[1])
        return TemplateResponse(request, 'kitchen/ingredient_book.html', {
            **self.each_context(request), 'title': 'Ingredients', 'rows': shown, 'total': len(rows), 'params': p,
            'categories': sorted({i['category'] for i in rows}), 'sort_choices': [(k, v[0]) for k, v in self.ING_SORTS.items()],
        })


admin_site = BallavaAdminSite(name='admin')


# ---------------------------------------------------------------- recipes
class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        exclude = ['status', 'live']
        widgets = {'ingredients': forms.Textarea(attrs={'rows': 10, 'cols': 70}), 'steps': forms.Textarea(attrs={'rows': 10, 'cols': 70})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recipe_id'].required = False  # made from the name
        # A draft can be saved half-finished. Publishing checks everything.
        for name in ('meal', 'ingredients', 'steps'):
            self.fields[name].required = False

    def clean(self):
        data = super().clean()
        if not data.get('recipe_id') and 'recipe_id' not in self.errors and data.get('name'):
            data['recipe_id'] = self.instance.recipe_id or recipe_editor.make_id(data['name'])
        return data


@admin.register(Recipe, site=admin_site)
class RecipeAdmin(admin.ModelAdmin):
    form = RecipeForm
    change_form_template = 'kitchen/recipe_form.html'
    list_display = ['name', 'cuisine', 'meal', 'time', 'kcal_per_serving', 'status', 'is_live', 'replaces_built_in', 'updated_at']
    list_filter = ['status']
    search_fields = ['name', 'recipe_id', 'cuisine']
    actions = ['publish', 'send_to_review', 'back_to_draft']
    fields = ['recipe_id', 'name', 'alt', 'cuisine', 'meal', 'time', 'serves', 'spice', 'tags', 'ingredients', 'steps', 'prep', 'safety', 'tip']

    # ---- the editor page
    def get_changeform_initial_data(self, request):
        source = BUILT_IN.get(request.GET.get('copy_from', ''))
        if not source:
            return super().get_changeform_initial_data(request)
        return {'recipe_id': source['id'], 'name': source['name'], 'alt': source.get('alt', ''), 'cuisine': source.get('cuisine', ''),
                'meal': ', '.join(source['meal']), 'time': source['time'], 'serves': source['serves'], 'spice': source['spice'],
                'tags': ', '.join(source.get('tags', [])), 'ingredients': '\n'.join(source['ing']), 'steps': '\n'.join(source['steps']),
                'prep': source.get('prep', ''), 'safety': source.get('safety', ''), 'tip': source.get('tip', '')}

    def add_view(self, request, form_url='', extra_context=None):
        # Editing a built-in recipe that already has an admin version opens that version.
        existing = Recipe.objects.filter(recipe_id=request.GET.get('copy_from') or None).first()
        if existing and request.method == 'GET':
            return HttpResponseRedirect(reverse('admin:kitchen_recipe_change', args=[existing.pk]))
        return super().add_view(request, form_url, extra_context)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        catalog.live()
        rows = {r.recipe_id: r.pk for r in Recipe.objects.all()}
        live = engine.recipes_from(catalog.live()['recipes'], ())
        copying = BUILT_IN.get(request.GET.get('copy_from', '')) if add else None
        status = obj.status if obj else Recipe.DRAFT
        context.update(
            editor_data={
                'ingredients': recipe_editor.ingredient_list(), 'amounts': recipe_editor.AMOUNTS, 'isNew': add and not copying, 'ai': bool(ai.ai_key()),
                'aiName': ai.provider_label(), 'categories': CATEGORIES, 'allergens': list(engine.ALLERGENS), 'meals': recipe_editor.MEALS, 'tags': recipe_editor.TAGS,
                'canAddIngredient': request.user.has_perm('kitchen.add_ingredient'), 'tools': reverse('admin:recipe_tools', args=['x'])[:-2],
                'recipes': sorted(({'id': r['id'], 'name': r['name'], 'edit': reverse('admin:kitchen_recipe_change', args=[rows[r['id']]]) if r['id'] in rows
                                    else reverse('admin:kitchen_recipe_add') + '?' + urlencode({'copy_from': r['id']})} for r in live), key=lambda r: r['name'].lower()),
            },
            editor_cuisines=sorted({r.get('cuisine') for r in live if r.get('cuisine')}), editor_ai=bool(ai.ai_key()), editor_copying=copying,
            editor_status=dict(Recipe.STATUS)[status], editor_status_key=status, editor_is_live=bool(obj and obj.live), editor_replaces=bool(obj and obj.recipe_id in BUILT_IN),
            editor_can_publish=request.user.is_superuser and self.has_change_permission(request, obj),
            editor_meal_choices=recipe_editor.MEALS, editor_tag_choices=recipe_editor.TAGS)
        return super().render_change_form(request, context, add, change, form_url, obj)

    # ---- the list
    @admin.display(description='kcal / serving')
    def kcal_per_serving(self, obj):
        try:
            return engine.prepare_recipe(obj.to_raw())['nutrition'].get('kcal', '-')
        except (KeyError, ValueError, TypeError):
            return '-'

    @admin.display(boolean=True, description='Live')
    def is_live(self, obj):
        return obj.live is not None

    @admin.display(boolean=True, description='Replaces built-in')
    def replaces_built_in(self, obj):
        return obj.recipe_id in BUILT_IN

    # ---- saving
    def save_model(self, request, obj, form, change):
        obj.status = Recipe.DRAFT  # users keep seeing the published copy until this one is published
        super().save_model(request, obj, form, change)
        if '_publish' not in request.POST and (problems := recipe_editor.problems_of(obj.to_raw())):
            self.message_user(request, 'Saved as a draft. Before publishing: ' + ' '.join(p['text'] for p in problems), messages.WARNING)

    def _after_save(self, request, obj, default):
        """The editor's own buttons: Publish, and Send to review."""
        if '_publish' in request.POST:
            live = publish_recipe(self.admin_site, request, obj)
            return HttpResponseRedirect(reverse('admin:recipe_detail', args=[obj.recipe_id]) if live else reverse('admin:kitchen_recipe_change', args=[obj.pk]))
        if '_review' in request.POST:
            Recipe.objects.filter(pk=obj.pk).update(status=Recipe.REVIEW)
            self.message_user(request, f'"{obj.name}" was sent to review.', messages.SUCCESS)
            return HttpResponseRedirect(reverse('admin:recipe_detail', args=[obj.recipe_id]))
        return default()

    def response_add(self, request, obj, post_url_continue=None):
        return self._after_save(request, obj, lambda: super(RecipeAdmin, self).response_add(request, obj, post_url_continue))

    def response_change(self, request, obj):
        return self._after_save(request, obj, lambda: super(RecipeAdmin, self).response_change(request, obj))

    @admin.action(description='Publish (users see it straight away)')
    def publish(self, request, queryset):
        for recipe in queryset:
            publish_recipe(self.admin_site, request, recipe)

    @admin.action(description='Send to review')
    def send_to_review(self, request, queryset):
        n = queryset.update(status=Recipe.REVIEW)
        self.message_user(request, f'{n} recipe(s) sent to review.')

    @admin.action(description='Move back to draft')
    def back_to_draft(self, request, queryset):
        queryset.update(status=Recipe.DRAFT)


class HiddenRecipeForm(forms.ModelForm):
    recipe_id = forms.ChoiceField(label='Recipe', choices=[])

    class Meta:
        model = HiddenRecipe
        fields = ['recipe_id', 'reason']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        names = {**{k: v['name'] for k, v in BUILT_IN.items()}, **dict(Recipe.objects.values_list('recipe_id', 'name'))}
        self.fields['recipe_id'].choices = sorted(names.items(), key=lambda c: c[1])


@admin.register(HiddenRecipe, site=admin_site)
class HiddenRecipeAdmin(admin.ModelAdmin):
    form = HiddenRecipeForm
    list_display = ['recipe_name', 'recipe_id', 'reason']

    @admin.display(description='Hidden recipe')
    def recipe_name(self, obj):
        return (BUILT_IN.get(obj.recipe_id) or {}).get('name') or obj.recipe_id


# ---------------------------------------------------------------- other content
@admin.register(Ingredient, site=admin_site)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'ingredient_id', 'category', 'kcal', 'protein', 'shelf_days', 'diet']
    search_fields = ['name', 'ingredient_id', 'aliases']
    fieldsets = [
        (None, {'fields': ['ingredient_id', 'name', 'category', 'shelf_days', 'aliases', 'allergens', 'diet']}),
        ('Nutrition per 100 g (optional)', {'fields': ['kcal', 'protein', 'carbs', 'fat', 'fibre'],
                                           'description': 'Fill these in so recipes using this ingredient count its calories. '
                                                          'Look the values up on the pack or in a food table.'}),
        ('Kitchen measures (optional)', {'fields': ['grams_per_cup', 'grams_per_piece'],
                                         'description': 'So "1 cup" or "2" in a recipe can be turned into grams.'}),
    ]

    def save_model(self, request, obj, form, change):
        if not change and obj.ingredient_id in engine.BY_ID and not Ingredient.objects.filter(ingredient_id=obj.ingredient_id).exists():
            self.message_user(request, f'"{obj.ingredient_id}" is already a built-in ingredient. Pick another id.', messages.ERROR)
            return
        super().save_model(request, obj, form, change)


@admin.register(Rescue, site=admin_site)
class RescueAdmin(admin.ModelAdmin):
    list_display = ['title', 'rescue_id']
    search_fields = ['title', 'keywords']


@admin.register(Announcement, site=admin_site)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['text', 'active', 'created_at']
    list_editable = ['active']


@admin.register(Festival, site=admin_site)
class FestivalAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'fast', 'users_see']
    list_filter = ['fast']
    date_hierarchy = 'date'

    @admin.display(description='What users see')
    def users_see(self, obj):
        left = (obj.date - timezone.localdate()).days
        if left < 0:
            return 'Over, so no longer shown'
        when = 'today' if left == 0 else 'tomorrow' if left == 1 else f'in {left} days'
        return f'Plan tab and Dashboard ({when})' if left <= 30 else f'Plan tab ({when}); Dashboard 30 days before'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.date < timezone.localdate():
            self.message_user(request, f'{obj.name} is dated {obj.date}, which has passed, so users will not see it.', messages.WARNING)
        else:
            self.message_user(request, f'Users will see {obj.name} within a minute. Where: {self.users_see(obj)}.')


# ---------------------------------------------------------------- people
class FamilyUserAdmin(UserAdmin):
    """Accounts only. Family data (kitchen, diets, health goals, diary) is never shown here."""
    list_display = ['first_name', 'masked_contact', 'family_size', 'date_joined', 'last_seen', 'is_active', 'is_staff']
    list_filter = ['is_active', 'is_staff']
    search_fields = ['first_name', 'email', 'profile__phone']
    fieldsets = [
        (None, {'fields': ['username', 'password']}),
        ('Person', {'fields': ['first_name', 'email']}),
        ('Access', {'fields': ['is_active', 'is_staff', 'is_superuser'],
                    'description': 'Untick Active to stop someone signing in. They are signed out at once.'}),
        ('Dates', {'fields': ['last_login', 'date_joined']}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('profile', 'profile__household').annotate(
            family_n=Count('profile__household__people'))

    @admin.display(description='Contact')
    def masked_contact(self, obj):
        contact = obj.email or getattr(getattr(obj, 'profile', None), 'phone', None)
        if not contact:
            return '-'
        if '@' in contact:
            user, domain = contact.split('@', 1)
            return f'{user[0]}***@{domain}'
        return f'{contact[:3]}******{contact[-2:]}'

    @admin.display(description='Family size', ordering='family_n')
    def family_size(self, obj):
        return obj.family_n or '-'

    @admin.display(description='Last seen')
    def last_seen(self, obj):
        return getattr(getattr(obj, 'profile', None), 'last_seen', None) or '-'


admin_site.register(User, FamilyUserAdmin)
admin_site.register(Group)


@admin.register(LogEntry, site=admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    """Every change made in this portal: who, what and when. Read-only."""
    list_display = ['action_time', 'user', 'action', 'object_repr', 'change_message']
    list_filter = ['action_flag', 'content_type']
    date_hierarchy = 'action_time'

    @admin.display(description='Action')
    def action(self, obj):
        return {1: 'Added', 2: 'Changed', 3: 'Deleted'}.get(obj.action_flag, '')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


LogEntry._meta.verbose_name_plural = 'Audit log'
