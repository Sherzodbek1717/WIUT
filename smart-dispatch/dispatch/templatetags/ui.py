from django import template
from django.forms import CheckboxInput, Select

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
