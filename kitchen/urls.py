"""Addresses under /api/ that the phone app calls."""
from django.http import JsonResponse
from django.urls import path, re_path

from . import api

urlpatterns = [
    path('health', api.health),
    path('catalog', api.catalog_view),
    # accounts
    path('auth/config', api.config_view),
    path('auth/signup', api.signup),
    path('auth/login', api.login_view),
    path('auth/otp/request', api.otp_request),
    path('auth/otp/verify', api.otp_verify),
    path('auth/logout', api.logout_view),
    path('me', api.me),
    path('state', api.state),
    path('household/join', api.join_household),
    path('household/rename', api.rename_household),
    path('account/export', api.export_account),
    path('account/delete', api.delete_account),
    path('polls', api.create_poll),
    path('polls/<str:token>', api.get_poll),
    path('polls/<str:token>/vote', api.cast_vote),
    # the brain
    path('parse', api.parse_view),
    path('suggest', api.suggest_view),
    path('chat', api.chat_view),
    path('rescue', api.rescue_view),
    path('brain/home', api.home),
    path('brain/plan', api.plan_week),
    path('brain/swap', api.swap),
    path('brain/recommend', api.recommend_view),
    path('brain/plan-info', api.plan_info),
    path('brain/recipe', api.recipe_info),
    path('brain/dashboard', api.dashboard_view),
    path('brain/calories', api.calories_view),
    path('brain/ask', api.ask),
    # AI Chef
    path('ai/invent', api.ai_invent),
    path('ai/scan', api.ai_scan),
    path('ai/chat', api.ai_chat),
    path('ai/estimate', api.ai_estimate),
    re_path(r'^.*$', lambda request: JsonResponse({'error': 'Unknown API route'}, status=404)),
]
