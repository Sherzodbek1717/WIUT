from django import forms
from django.utils import timezone

from . import geo
from .models import Equipment, LoadPosting, LoadType, TruckPosting

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
CITY_ATTRS = {"list": "city-list", "autocomplete": "off", "placeholder": "City, ST"}


def clean_city(value, required=True):
    value = (value or "").strip()
    if not value:
        if required:
            raise forms.ValidationError("Enter a city.")
        return ""
    found = geo.find_city(value)
    if not found:
        raise forms.ValidationError("Pick a city from the list, e.g. “Dallas, TX”.")
    return f"{found[0]}, {found[1]}"


class LoadSearchForm(forms.Form):
    SORTS = [
        ("age", "Age – newest"), ("rpm", "Rate/mile – highest"), ("rate", "Rate – highest"),
        ("dho", "DH-O – closest"), ("trip", "Trip – longest"), ("pickup", "Pickup – soonest"),
    ]

    origin = forms.CharField(widget=forms.TextInput(attrs=CITY_ATTRS))
    dh_o = forms.IntegerField(label="DH-O", initial=100, min_value=0, max_value=500, required=False)
    destination = forms.CharField(required=False, widget=forms.TextInput(attrs={**CITY_ATTRS, "placeholder": "Anywhere"}))
    dh_d = forms.IntegerField(label="DH-D", initial=100, min_value=0, max_value=500, required=False)
    equipment = forms.ChoiceField(choices=[("", "Any equipment")] + Equipment.choices, required=False)
    driver_type = forms.ChoiceField(choices=[("", "All drivers"), ("solo", "Solo"), ("team", "Team")], required=False)
    load_type = forms.ChoiceField(choices=[("", "Full & partial")] + LoadType.choices, required=False)
    date_from = forms.DateField(required=False, widget=DATE)
    date_to = forms.DateField(required=False, widget=DATE)
    max_weight = forms.IntegerField(label="Max lbs", min_value=0, required=False)
    min_rpm = forms.DecimalField(label="Min $/mile", min_value=0, decimal_places=2, required=False)
    sort = forms.ChoiceField(choices=SORTS, required=False)

    def clean_origin(self):
        return clean_city(self.cleaned_data["origin"])

    def clean_destination(self):
        return clean_city(self.cleaned_data["destination"], required=False)

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_to"] < data["date_from"]:
            self.add_error("date_to", "End date is before start date.")
        return data


class TruckSearchForm(forms.Form):
    origin = forms.CharField(widget=forms.TextInput(attrs=CITY_ATTRS))
    dh_o = forms.IntegerField(label="DH-O", initial=150, min_value=0, max_value=500, required=False)
    destination = forms.CharField(required=False, widget=forms.TextInput(attrs={**CITY_ATTRS, "placeholder": "Anywhere"}))
    dh_d = forms.IntegerField(label="DH-D", initial=150, min_value=0, max_value=500, required=False)
    equipment = forms.ChoiceField(choices=[("", "Any equipment")] + Equipment.choices, required=False)
    driver_type = forms.ChoiceField(choices=[("", "All drivers"), ("solo", "Solo"), ("team", "Team")], required=False)
    date_from = forms.DateField(required=False, widget=DATE)
    date_to = forms.DateField(required=False, widget=DATE)

    clean_origin = LoadSearchForm.clean_origin
    clean_destination = LoadSearchForm.clean_destination


class LoadPostingForm(forms.ModelForm):
    origin = forms.CharField(widget=forms.TextInput(attrs=CITY_ATTRS))
    destination = forms.CharField(widget=forms.TextInput(attrs=CITY_ATTRS))

    class Meta:
        model = LoadPosting
        fields = (
            "origin", "destination", "pickup_date", "delivery_date", "equipment", "load_type",
            "team_required", "length_ft", "weight_lbs", "rate", "commodity", "reference",
            "contact_phone", "contact_email", "comments",
        )
        widgets = {"pickup_date": DATE, "delivery_date": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["origin"] = self.instance.origin_label
            self.initial["destination"] = self.instance.destination_label

    clean_origin = LoadSearchForm.clean_origin

    def clean_destination(self):
        return clean_city(self.cleaned_data["destination"])

    def clean(self):
        data = super().clean()
        pickup, delivery = data.get("pickup_date"), data.get("delivery_date")
        if pickup and not self.instance.pk and pickup < timezone.localdate():
            self.add_error("pickup_date", "Pickup date is in the past.")
        if pickup and delivery and delivery < pickup:
            self.add_error("delivery_date", "Delivery is before pickup.")
        if data.get("origin") and data.get("origin") == data.get("destination"):
            self.add_error("destination", "Destination must differ from origin.")
        return data

    def save(self, commit=True):
        posting = super().save(commit=False)
        posting.set_origin(self.cleaned_data["origin"])
        posting.set_destination(self.cleaned_data["destination"])
        if commit:
            posting.save()
        return posting


class TruckPostingForm(forms.ModelForm):
    origin = forms.CharField(label="Truck location", widget=forms.TextInput(attrs=CITY_ATTRS))
    destination = forms.CharField(
        label="Preferred destination", required=False,
        widget=forms.TextInput(attrs={**CITY_ATTRS, "placeholder": "Anywhere"}),
    )

    class Meta:
        model = TruckPosting
        fields = (
            "truck", "origin", "destination", "available_from", "available_to", "equipment", "load_type",
            "team", "length_ft", "max_weight_lbs", "contact_phone", "contact_email", "comments",
        )
        widgets = {"available_from": DATE, "available_to": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].required = False
        self.fields["truck"].help_text = "Optional: link one of your trucks."
        if self.instance.pk:
            self.initial["origin"] = self.instance.origin_label
            self.initial["destination"] = self.instance.destination_city and self.instance.destination_label

    clean_origin = LoadSearchForm.clean_origin
    clean_destination = LoadSearchForm.clean_destination

    def clean(self):
        data = super().clean()
        start, end = data.get("available_from"), data.get("available_to")
        if start and end and end < start:
            self.add_error("available_to", "End date is before start date.")
        return data

    def save(self, commit=True):
        posting = super().save(commit=False)
        posting.set_origin(self.cleaned_data["origin"])
        posting.set_destination(self.cleaned_data["destination"])
        if commit:
            posting.save()
        return posting


class BookForm(forms.Form):
    rate = forms.DecimalField(label="Agreed rate ($)", min_value=1, max_digits=9, decimal_places=2)
    dh_o = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)
