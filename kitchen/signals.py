"""When admins change recipes, ingredients, fixes, announcements or festivals, tell every server process."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Announcement, Festival, HiddenRecipe, Ingredient, Recipe, Rescue

WATCHED = (Recipe, HiddenRecipe, Ingredient, Rescue, Announcement, Festival)


@receiver(post_save)
@receiver(post_delete)
def content_changed(sender, **kwargs):
    if sender in WATCHED:
        from .catalog import bump
        bump()
