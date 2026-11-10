"""The admin portal at /admin, built on Django's admin.

What admins can do: add and edit recipes (draft -> review -> publish, with safety checks), hide recipes,
add ingredients and Bachao fixes, post announcements, keep the festival calendar, and disable users.
What admins cannot see: any family's kitchen, members, diets, health goals or meal diary.
"""
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone

from . import engine
from .data.recipes import RECIPES
from .models import AiUsage, Announcement, FamilyData, Festival, HiddenRecipe, Household, Ingredient, Recipe, Rescue
from .security import clear_limit, client_ip, limited

BUILT_IN = {r['id']: r for r in RECIPES}


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

    def index(self, request, extra_context=None):
        week_ago = timezone.now() - timedelta(days=7)
        month_ago = timezone.localdate() - timedelta(days=29)
        meals = sum(len(v) for v in FamilyData.objects.filter(key='history').values_list('value', flat=True) if isinstance(v, list))
        stats = [
            ('Users', User.objects.filter(is_staff=False).count()),
            ('Active in 7 days', User.objects.filter(is_staff=False, profile__last_seen__gte=week_ago).count()),
            ('Families', Household.objects.count()),
            ('Meals logged', meals),
            ('Built-in recipes', len(RECIPES)),
            ('Custom recipes live', Recipe.objects.exclude(live=None).count()),
            ('Waiting for review', Recipe.objects.filter(status=Recipe.REVIEW).count()),
            ('AI calls, 30 days', AiUsage.objects.filter(day__gte=month_ago).aggregate(n=Sum('calls'))['n'] or 0),
        ]
        return super().index(request, {'ballava_stats': stats, **(extra_context or {})})


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
    list_display = ['name', 'recipe_id', 'status', 'is_live', 'replaces_built_in', 'updated_at']
    list_filter = ['status']
    search_fields = ['name', 'recipe_id', 'cuisine']
    actions = ['send_to_review', 'publish', 'back_to_draft']
    readonly_fields = ['status_note']

    def get_fieldsets(self, request, obj=None):
        main = ['recipe_id', 'name', 'alt', 'cuisine', 'meal', 'time', 'serves', 'spice', 'tags', 'ingredients', 'steps', 'prep', 'safety', 'tip']
        sets = [(None, {'fields': ['status_note'] + main if obj else main})]
        if not obj:
            sets.insert(0, ('Quick start', {'fields': ['copy_from']}))
        return sets

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
    list_display = ['name', 'ingredient_id', 'category', 'shelf_days', 'diet']
    search_fields = ['name', 'ingredient_id', 'aliases']

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
