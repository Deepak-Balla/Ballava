"""The admin portal at /admin, built on Django's admin.

What admins can do: add and edit recipes (draft -> review -> publish, with safety checks), hide recipes,
add ingredients and Bachao fixes, post announcements, keep the festival calendar, and disable users.
What admins cannot see: any family's kitchen, members, diets, health goals or meal diary.
"""
from collections import Counter
from datetime import timedelta
from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from . import catalog, engine
from .data.recipes import RECIPES
from .models import AiUsage, Announcement, FamilyData, Festival, HiddenRecipe, Household, Ingredient, Recipe, Rescue
from .security import clear_limit, client_ip, limited

BUILT_IN = {r['id']: r for r in RECIPES}
DIETS = {'veg': 'Vegetarian', 'egg': 'Egg', 'nonveg': 'Non-veg'}
SPICE = {1: 'Mild', 2: 'Medium', 3: 'Hot'}


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
        drafts = [(r, engine.validate_recipe(r.to_raw())) for r in Recipe.objects.filter(status=Recipe.DRAFT).order_by('-updated_at')[:6]]
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
            'problems': engine.validate_recipe(row.to_raw()) if row else [],
            'can_change': request.user.has_perm('kitchen.change_recipe') and request.user.has_perm('kitchen.add_recipe'),
            'edit_url': edit_url,
            'hide_url': (reverse('admin:kitchen_hiddenrecipe_add') + '?' + urlencode({'recipe_id': recipe_id}))
            if request.user.has_perm('kitchen.add_hiddenrecipe') else None,
            'hidden_url': reverse('admin:kitchen_hiddenrecipe_delete', args=[hidden.pk]) if hidden else None,
        })

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
    copy_from = forms.ChoiceField(
        required=False, label='Start from a built-in recipe',
        choices=[('', 'No, start empty')] + sorted(((k, v['name']) for k, v in BUILT_IN.items()), key=lambda c: c[1]),
        help_text='Fills in everything from that recipe and keeps its id, so your version replaces it once published.')

    class Meta:
        model = Recipe
        exclude = ['status', 'live']
        widgets = {'ingredients': forms.Textarea(attrs={'rows': 10, 'cols': 70}), 'steps': forms.Textarea(attrs={'rows': 10, 'cols': 70})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields['copy_from']
        else:
            # These are filled in from the built-in recipe when one is chosen, so check them in clean() instead.
            for name in ('recipe_id', 'name', 'meal', 'ingredients', 'steps'):
                self.fields[name].required = False

    def clean(self):
        data = super().clean()
        source = BUILT_IN.get(data.get('copy_from') or '')
        if source:
            data.update(recipe_id=source['id'], name=source['name'], alt=source.get('alt', ''), cuisine=source.get('cuisine', ''),
                        meal=', '.join(source['meal']), time=source['time'], serves=source['serves'], spice=source['spice'],
                        tags=', '.join(source.get('tags', [])), ingredients='\n'.join(source['ing']), steps='\n'.join(source['steps']),
                        prep=source.get('prep', ''), safety=source.get('safety', ''), tip=source.get('tip', ''))
            if Recipe.objects.filter(recipe_id=source['id']).exists():
                raise forms.ValidationError('There is already an edited version of that recipe. Edit that one instead.')
        for name in ('recipe_id', 'name', 'meal', 'ingredients', 'steps'):
            if not data.get(name):
                self.add_error(name, 'This field is required.')
        return data

    def save(self, commit=True):
        for field in ('recipe_id', 'name', 'alt', 'cuisine', 'meal', 'time', 'serves', 'spice', 'tags', 'ingredients', 'steps', 'prep', 'safety', 'tip'):
            if field in self.cleaned_data:
                setattr(self.instance, field, self.cleaned_data[field])
        return super().save(commit)


@admin.register(Recipe, site=admin_site)
class RecipeAdmin(admin.ModelAdmin):
    form = RecipeForm
    list_display = ['name', 'recipe_id', 'cuisine', 'meal', 'time', 'kcal_per_serving', 'status', 'is_live', 'replaces_built_in', 'updated_at']
    list_filter = ['status']
    search_fields = ['name', 'recipe_id', 'cuisine']
    actions = ['send_to_review', 'publish', 'back_to_draft']
    readonly_fields = ['status_note', 'nutrition_preview']

    def get_fieldsets(self, request, obj=None):
        main = ['recipe_id', 'name', 'alt', 'cuisine', 'meal', 'time', 'serves', 'spice', 'tags', 'ingredients', 'steps', 'prep', 'safety', 'tip']
        sets = [(None, {'fields': ['status_note'] + main if obj else main})]
        if obj:
            sets.append(('Calories (worked out from the saved ingredients)', {'fields': ['nutrition_preview']}))
        if not obj:
            sets.insert(0, ('Quick start', {'fields': ['copy_from']}))
        return sets

    def _prepared(self, obj):
        try:
            return engine.prepare_recipe(obj.to_raw())
        except (KeyError, ValueError, TypeError):
            return None

    @admin.display(description='kcal / serving')
    def kcal_per_serving(self, obj):
        r = self._prepared(obj)
        return (r or {}).get('nutrition', {}).get('kcal', '-') if r else '-'

    @admin.display(description='Per serving (approx.)')
    def nutrition_preview(self, obj):
        r = self._prepared(obj)
        n = (r or {}).get('nutrition')
        if not n:
            return '-'
        text = (f"About {n['kcal']} kcal per serving: protein {round(n['protein'])} g, carbs {round(n['carbs'])} g, fat {round(n['fat'])} g, "
                f"fibre {round(n['fibre'])} g. Whole dish about {n['totalKcal']} kcal, serves {n['serves']}.")
        if n['oilTsp']:
            text += f" Includes about {n['oilTsp']} tsp of cooking oil per serving."
        if n['unknown']:
            text += f" Not counted (unknown ingredient): {', '.join(n['unknown'])}."
        return text

    @admin.display(description='Status')
    def status_note(self, obj):
        live = ' Users currently see the last published version.' if obj.live else ' Users do not see it yet.'
        return obj.get_status_display() + '.' + live + ' Use the actions on the recipe list to send it to review or publish it.'

    @admin.display(boolean=True, description='Live')
    def is_live(self, obj):
        return obj.live is not None

    @admin.display(boolean=True, description='Replaces built-in')
    def replaces_built_in(self, obj):
        return obj.recipe_id in BUILT_IN

    def save_model(self, request, obj, form, change):
        obj.status = Recipe.DRAFT  # any edit needs a fresh review; users keep seeing the published copy meanwhile
        super().save_model(request, obj, form, change)
        problems = engine.validate_recipe(obj.to_raw())
        if problems:
            self.message_user(request, 'Saved as a draft. Fix before publishing: ' + '; '.join(problems), messages.WARNING)

    @admin.action(description='Send to review')
    def send_to_review(self, request, queryset):
        n = queryset.update(status=Recipe.REVIEW)
        self.message_user(request, f'{n} recipe(s) sent to review.')

    @admin.action(description='Publish (users see it straight away)')
    def publish(self, request, queryset):
        for recipe in queryset:
            if recipe.status != Recipe.REVIEW:
                self.message_user(request, f'"{recipe.name}" must be sent to review before publishing.', messages.ERROR)
                continue
            problems = engine.validate_recipe(recipe.to_raw())
            if problems:
                self.message_user(request, f'"{recipe.name}" cannot be published: ' + '; '.join(problems), messages.ERROR)
                continue
            recipe.live, recipe.status = recipe.to_raw(), Recipe.PUBLISHED
            recipe.save()
            self.log_change(request, recipe, 'Published')
            self.message_user(request, f'"{recipe.name}" is published. Users see it now.')

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
    list_display = ['name', 'date', 'fast']
    list_filter = ['fast']
    date_hierarchy = 'date'


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
