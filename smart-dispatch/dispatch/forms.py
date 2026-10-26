from django import forms

from .models import Broker, Driver, Load, Truck

DATETIME_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class BrokerForm(forms.ModelForm):
    class Meta:
        model = Broker
        fields = ("name", "mc_number", "contact_email", "contact_phone")


class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ("first_name", "last_name", "phone", "status")

    def clean_status(self):
        status = self.cleaned_data["status"]
        on_load = self.instance.pk and self.instance.status == Driver.Status.ON_LOAD
        if (status == Driver.Status.ON_LOAD) != bool(on_load):
            raise forms.ValidationError("“On load” is set by assigning or delivering a load.")
        return status


class TruckForm(forms.ModelForm):
    class Meta:
        model = Truck
        fields = ("unit_number", "truck_type", "status")

    def clean_status(self):
        status = self.cleaned_data["status"]
        in_use = self.instance.pk and self.instance.status == Truck.Status.IN_USE
        if (status == Truck.Status.IN_USE) != bool(in_use):
            raise forms.ValidationError("“In use” is set by assigning or delivering a load.")
        return status


class LoadForm(forms.ModelForm):
    """Load offer details. Also feeds the decision engine before the load is booked."""

    driver_hours_available = forms.FloatField(
        label="Driver hours left in 70-hour cycle",
        required=False, min_value=0, max_value=70,
        help_text="Optional. Used only for the hours-of-service check; not saved.",
    )

    class Meta:
        model = Load
        fields = (
            "reference", "broker",
            "origin_city", "origin_state", "destination_city", "destination_state",
            "pickup_at", "delivery_at",
            "rate", "loaded_miles", "deadhead_miles",
            "commodity", "weight_lbs",
        )
        widgets = {"pickup_at": DATETIME_WIDGET, "delivery_at": DATETIME_WIDGET}

    def clean(self):
        cleaned = super().clean()
        pickup, delivery = cleaned.get("pickup_at"), cleaned.get("delivery_at")
        if pickup and delivery and delivery <= pickup:
            self.add_error("delivery_at", "Delivery must be after pickup.")
        return cleaned


class AssignForm(forms.Form):
    driver = forms.ModelChoiceField(queryset=Driver.objects.none())
    truck = forms.ModelChoiceField(queryset=Truck.objects.none())

    def __init__(self, *args, load=None, **kwargs):
        super().__init__(*args, **kwargs)
        current = load.active_assignment if load else None
        drivers = Driver.objects.filter(status=Driver.Status.AVAILABLE)
        trucks = Truck.objects.filter(status=Truck.Status.AVAILABLE)
        if current:
            drivers = drivers | Driver.objects.filter(pk=current.driver_id)
            trucks = trucks | Truck.objects.filter(pk=current.truck_id)
            self.initial.setdefault("driver", current.driver_id)
            self.initial.setdefault("truck", current.truck_id)
        self.fields["driver"].queryset = drivers.distinct()
        self.fields["truck"].queryset = trucks.distinct()
