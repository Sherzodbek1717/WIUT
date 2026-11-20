from django import template
from django.forms import CheckboxInput, Select
from django.utils import timezone

register = template.Library()

STATUS_COLOURS = {
    "available": "secondary", "dispatched": "primary", "in_transit": "warning",
    "delivered": "success", "on_load": "primary", "off_duty": "secondary",
    "in_use": "primary", "maintenance": "danger",
}
RECOMMENDATION_COLOURS = {"accept": "success", "negotiate": "warning", "reject": "danger"}
HOS_COLOURS = {"feasible": "success", "tight": "warning", "infeasible": "danger", "unknown": "secondary"}


@register.filter
def bootstrap(field):
    """Render a form field's widget with the right Bootstrap class."""
    widget = field.field.widget
    if isinstance(widget, CheckboxInput):
        css = "form-check-input"
    elif isinstance(widget, Select):
        css = "form-select"
    else:
        css = "form-control"
    if field.errors:
        css += " is-invalid"
    return field.as_widget(attrs={"class": css})


@register.filter
def is_checkbox(field):
    return isinstance(field.field.widget, CheckboxInput)


@register.filter
def status_colour(value):
    return STATUS_COLOURS.get(str(value), "secondary")


@register.filter
def recommendation_colour(value):
    return RECOMMENDATION_COLOURS.get(value, "secondary")


@register.filter
def hos_colour(value):
    return HOS_COLOURS.get(value, "secondary")


@register.filter
def age(posted_at):
    """Compact posting age like DAT: 5m, 3h, 2d."""
    seconds = max(0, int((timezone.now() - posted_at).total_seconds()))
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


@register.simple_tag
def sort_url(request, value):
    """Current search URL with a different sort order."""
    params = request.GET.copy()
    params["sort"] = value
    return f"?{params.urlencode()}"
