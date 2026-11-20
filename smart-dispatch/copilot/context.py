from django.conf import settings


def branding(request):
    return {"APP_NAME": settings.APP_NAME}
