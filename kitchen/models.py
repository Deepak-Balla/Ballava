"""Ballava's database tables.

Users sign in with Django's own User model (username = email, or a placeholder for phone-only users).
Everything a family keeps (kitchen, members, plan, diary...) is stored in FamilyData, one row per kind.
Admins never see FamilyData: it is deliberately not shown in the admin portal.
"""
import secrets

from django.conf import settings
from django.db import models

from .data.ingredients import CATEGORIES

INVITE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def new_invite_code():
    return ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(8))


class Household(models.Model):
    name = models.CharField(max_length=80)
    invite_code = models.CharField(max_length=8, unique=True, default=new_invite_code)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    household = models.ForeignKey(Household, null=True, blank=True, on_delete=models.SET_NULL, related_name='people')
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    consent_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)


class FamilyData(models.Model):
    """One piece of a family's data, e.g. key='pantry'. `version` goes up on every save, so two phones
    editing at once can be detected and merged instead of one overwriting the other."""
    KEYS = ['pantry', 'members', 'shopping', 'history', 'aiRecipes', 'filters', 'plan', 'pins', 'prefs', 'savedDishes']
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='data')
    key = models.CharField(max_length=20)
    value = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['household', 'key'], name='one_value_per_key')]


class PhoneCode(models.Model):
    phone = models.CharField(max_length=20, primary_key=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)


class Attempt(models.Model):
    """Counts recent attempts (sign-ins, codes, votes) so guessing and spamming can be slowed down."""
    key = models.CharField(max_length=200, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)


class Poll(models.Model):
    token = models.CharField(max_length=32, primary_key=True)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='polls')
    title = models.CharField(max_length=100)
    date = models.CharField(max_length=10, blank=True)
    slot = models.CharField(max_length=20, default='dinner')
    options = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    closes_at = models.DateTimeField()


class Vote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='votes')
    voter = models.CharField(max_length=64)
    option_id = models.CharField(max_length=40)
    name = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['poll', 'voter'], name='one_vote_per_person')]


class AiUsage(models.Model):
    day = models.DateField()
    who = models.CharField(max_length=64)
    calls = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['day', 'who'], name='one_row_per_day')]


# ---------------------------------------------------------------- admin-managed content
class Recipe(models.Model):
    """A recipe added (or a built-in one changed) by an admin. Users only see it once it is published.
    Editing a published recipe does not change what users see until it is published again."""
    DRAFT, REVIEW, PUBLISHED = 'draft', 'review', 'published'
    STATUS = [(DRAFT, 'Draft'), (REVIEW, 'Waiting for review'), (PUBLISHED, 'Published')]

    recipe_id = models.SlugField('Id', max_length=40, unique=True, help_text='Lowercase letters, numbers and _ only. Use a built-in id to replace that recipe.')
    name = models.CharField(max_length=80)
    alt = models.CharField('Other name', max_length=60, blank=True)
    cuisine = models.CharField(max_length=40, blank=True)
    meal = models.CharField(max_length=80, default='lunch, dinner', help_text='Comma separated: breakfast, lunch, dinner, snack, side, dessert')
    time = models.PositiveIntegerField('Minutes', default=30)
    serves = models.PositiveIntegerField(default=3)
    spice = models.PositiveSmallIntegerField(default=2, choices=[(1, 'Mild'), (2, 'Medium'), (3, 'Hot')])
    tags = models.CharField(max_length=200, blank=True, help_text='Comma separated: gluten-free, diabetic-friendly, high-protein, kid-friendly, tiffin, vrat, quick, sweet, one-pot, leftover')
    ingredients = models.TextField(help_text='One per line, as id:quantity. Add ? after the id for optional, and | between ids for "any of". Example: moong_dal|masoor_dal:1/2 cup')
    steps = models.TextField(help_text='One per line. End a step with |5m for a 5-minute timer, or |3w for 3 cooker whistles.')
    prep = models.CharField('Plan ahead (night before)', max_length=200, blank=True)
    safety = models.CharField('Food safety note', max_length=400, blank=True)
    tip = models.CharField(max_length=400, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=DRAFT)
    live = models.JSONField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @staticmethod
    def _list(text, sep=','):
        return [x.strip() for x in text.split(sep) if x.strip()]

    def to_raw(self):
        """The same compact format as the built-in recipe book."""
        raw = {'id': self.recipe_id, 'name': self.name, 'cuisine': self.cuisine or 'Home style', 'meal': self._list(self.meal),
               'time': self.time, 'serves': self.serves, 'spice': self.spice, 'tags': self._list(self.tags),
               'ing': self._list(self.ingredients, '\n'), 'steps': self._list(self.steps, '\n')}
        for field in ('alt', 'prep', 'safety', 'tip'):
            if getattr(self, field):
                raw[field] = getattr(self, field)
        return raw


class HiddenRecipe(models.Model):
    recipe_id = models.CharField('Recipe', max_length=40, unique=True)
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.recipe_id


class Ingredient(models.Model):
    ingredient_id = models.SlugField('Id', max_length=40, unique=True)
    name = models.CharField(max_length=60)
    category = models.CharField(max_length=30, choices=[(c, c) for c in CATEGORIES])
    shelf_days = models.PositiveIntegerField('Keeps for (days)', null=True, blank=True, help_text='Leave empty if it keeps for months.')
    aliases = models.TextField('Other names', blank=True, help_text='Comma separated, in any language people type.')
    allergens = models.CharField(max_length=100, blank=True, help_text='Comma separated: dairy, gluten, nuts, egg, seafood')
    diet = models.CharField(max_length=6, default='veg', choices=[('veg', 'Vegetarian'), ('egg', 'Egg'), ('nonveg', 'Meat or fish')])
    # Nutrition per 100 g (optional). With these filled in, recipes that use this ingredient count its calories.
    kcal = models.FloatField('Calories (kcal)', null=True, blank=True, help_text='Per 100 g, as it goes into the pot (dry for dals and flours).')
    protein = models.FloatField('Protein (g)', null=True, blank=True)
    carbs = models.FloatField('Carbs (g)', null=True, blank=True)
    fat = models.FloatField('Fat (g)', null=True, blank=True)
    fibre = models.FloatField('Fibre (g)', null=True, blank=True)
    grams_per_cup = models.FloatField('Grams in 1 cup', null=True, blank=True, help_text='A 240 ml cup, filled as usual (chopped, grated, loose).')
    grams_per_piece = models.FloatField('Grams in 1 piece', null=True, blank=True, help_text='One medium item, if it is counted in pieces.')

    def __str__(self):
        return self.name

    def to_raw(self):
        split = lambda s: [x.strip() for x in s.split(',') if x.strip()]  # noqa: E731
        raw = {'id': self.ingredient_id, 'name': self.name, 'category': self.category, 'shelfDays': self.shelf_days,
               'aliases': split(self.aliases), 'allergens': split(self.allergens), 'diet': self.diet}
        if self.kcal is not None:
            raw['nutrition'] = {'kcal': self.kcal, 'protein': self.protein or 0, 'carbs': self.carbs or 0, 'fat': self.fat or 0, 'fibre': self.fibre or 0}
        raw['measures'] = {k: v for k, v in {'cup': self.grams_per_cup, 'piece': self.grams_per_piece}.items() if v}
        return raw


class Rescue(models.Model):
    rescue_id = models.SlugField('Id', max_length=40, unique=True)
    title = models.CharField('Problem', max_length=80)
    keywords = models.CharField('Search words', max_length=300, blank=True)
    fixes = models.TextField(help_text='One fix per line.')
    myth = models.CharField('Myth check', max_length=400, blank=True)

    def __str__(self):
        return self.title

    def to_raw(self):
        raw = {'id': self.rescue_id, 'title': self.title, 'keywords': self.keywords,
               'fixes': [x.strip() for x in self.fixes.splitlines() if x.strip()]}
        if self.myth:
            raw['myth'] = self.myth
        return raw


class Announcement(models.Model):
    text = models.CharField(max_length=240)
    active = models.BooleanField('Show to users', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text


class Festival(models.Model):
    name = models.CharField(max_length=80)
    date = models.DateField(help_text='Dates change every year and vary by region. Check your panchang.')
    fast = models.BooleanField('Fasting day', default=False)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.name} ({self.date})'


class CatalogStamp(models.Model):
    """Goes up whenever admins change content, so every server process reloads the recipe book."""
    value = models.PositiveIntegerField(default=0)
