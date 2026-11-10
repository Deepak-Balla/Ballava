"""Small safety helpers: rate limits, phone numbers and one-time sign-in codes."""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

import urllib.parse
import urllib.request
from base64 import b64encode

from django.conf import settings
from django.utils import timezone

from .models import Attempt, PhoneCode

log = logging.getLogger('kitchen')


class ApiError(Exception):
    """An error to show the user, with an HTTP status code."""

    def __init__(self, status, message, payload=None):
        super().__init__(message)
        self.status, self.message, self.payload = status, message, payload


def limited(key, max_hits, window_seconds):
    """True when `key` has been used `max_hits` times in the window. Otherwise counts this use."""
    since = timezone.now() - timedelta(seconds=window_seconds)
    if Attempt.objects.filter(key=key, at__gte=since).count() >= max_hits:
        return True
    Attempt.objects.create(key=key)
    if secrets.randbelow(200) == 0:  # tidy up old rows now and then
        Attempt.objects.filter(at__lt=timezone.now() - timedelta(days=1)).delete()
    return False


def clear_limit(key):
    Attempt.objects.filter(key=key).delete()


def client_ip(request):
    return request.META.get('REMOTE_ADDR', 'x')


# ---------------------------------------------------------------- phone sign-in
def normalize_phone(raw):
    s = re.sub(r'[\s()-]', '', str(raw or ''))
    if re.fullmatch(r'[6-9]\d{9}', s):
        return '+91' + s
    if re.fullmatch(r'\+[1-9]\d{7,14}', s):
        return s
    return None


def twilio_ready():
    import os
    return all(os.environ.get(k) for k in ('TWILIO_SID', 'TWILIO_TOKEN', 'TWILIO_FROM'))


def auth_config():
    return {'phone': twilio_ready() or settings.OTP_DEV_MODE, 'devOtp': settings.OTP_DEV_MODE and not twilio_ready()}


def _code_hash(phone, code):
    return hashlib.sha256(f'{phone}{code}'.encode()).hexdigest()


def send_sms(phone, text):
    import os
    sid, token = os.environ['TWILIO_SID'], os.environ['TWILIO_TOKEN']
    req = urllib.request.Request(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
        data=urllib.parse.urlencode({'To': phone, 'From': os.environ['TWILIO_FROM'], 'Body': text}).encode(),
        headers={'Authorization': 'Basic ' + b64encode(f'{sid}:{token}'.encode()).decode()}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as err:  # noqa: BLE001  any failure means the code did not go out
        log.warning('SMS failed: %s', err)
        raise ApiError(502, 'We could not send the code. Please try again.') from err


def request_code(raw_phone, ip):
    phone = normalize_phone(raw_phone)
    if not phone:
        raise ApiError(400, 'Please enter a valid mobile number.')
    if not auth_config()['phone']:
        raise ApiError(503, 'Phone sign-in is not set up on this server yet. Please use email.')
    if limited('otp:' + phone, 5, 3600) or limited('otpip:' + ip, 20, 3600):
        raise ApiError(429, 'Too many codes requested. Please try again later.')
    code = f'{secrets.randbelow(900000) + 100000}'
    PhoneCode.objects.update_or_create(phone=phone, defaults={
        'code_hash': _code_hash(phone, code), 'expires_at': timezone.now() + timedelta(minutes=10), 'attempts': 0})
    if twilio_ready():
        send_sms(phone, f'Your Ballava code is {code}. It expires in 10 minutes.')
        return {'sent': True}
    log.info('Dev sign-in code for %s: %s', phone, code)
    return {'sent': True, 'devCode': code}


def check_code(raw_phone, code):
    phone = normalize_phone(raw_phone)
    row = PhoneCode.objects.filter(phone=phone).first() if phone else None
    if not row or row.expires_at < timezone.now():
        raise ApiError(400, 'That code has expired. Please ask for a new one.')
    if row.attempts >= 5:
        row.delete()
        raise ApiError(429, 'Too many wrong tries. Please ask for a new code.')
    if not hmac.compare_digest(_code_hash(phone, str(code or '')), row.code_hash):
        row.attempts += 1
        row.save(update_fields=['attempts'])
        raise ApiError(400, 'That code is not right. Please check and try again.')
    return phone
