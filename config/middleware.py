from django.http import HttpResponse


class HealthCheck:
    """/healthz says "ok" before anything else runs, so a hosting service can check the app is up whatever address or
    protocol it uses. It looks at nothing and tells nothing. (/api/health is the fuller one: it also reads the database.)"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/healthz':
            return HttpResponse('ok', content_type='text/plain')
        return self.get_response(request)
