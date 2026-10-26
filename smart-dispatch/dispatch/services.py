"""Dispatch workflow rules: assigning loads and moving them through their stages.

Driver and truck statuses are only changed here, so they stay in step with
the loads they are working.
"""

from django.db import transaction
from django.utils import timezone

from .models import Assignment, Driver, Load, Truck

S = Load.Status

# Status changes a dispatcher can make directly. Available -> Dispatched happens
# only through assign_load, because a dispatched load needs a driver and a truck.
ALLOWED_TRANSITIONS = {
    S.AVAILABLE: set(),
    S.DISPATCHED: {S.AVAILABLE, S.IN_TRANSIT},
    S.IN_TRANSIT: {S.DISPATCHED, S.DELIVERED},
    S.DELIVERED: set(),
}


class DispatchError(Exception):
    pass


def _release(assignment):
    assignment.active = False
    assignment.save(update_fields=["active"])
    Driver.objects.filter(pk=assignment.driver_id, status=Driver.Status.ON_LOAD).update(
        status=Driver.Status.AVAILABLE
    )
    Truck.objects.filter(pk=assignment.truck_id, status=Truck.Status.IN_USE).update(
        status=Truck.Status.AVAILABLE
    )


@transaction.atomic
def assign_load(load, driver, truck, user=None):
    load = Load.objects.select_for_update().get(pk=load.pk)
    if load.status not in (S.AVAILABLE, S.DISPATCHED):
        raise DispatchError("Only available or dispatched loads can be (re)assigned.")

    current = load.assignments.filter(active=True).first()
    driver = Driver.objects.select_for_update().get(pk=driver.pk)
    truck = Truck.objects.select_for_update().get(pk=truck.pk)
    keeps_driver = current is not None and current.driver_id == driver.pk
    keeps_truck = current is not None and current.truck_id == truck.pk
    if not keeps_driver and driver.status != Driver.Status.AVAILABLE:
        raise DispatchError(f"{driver} is {driver.get_status_display().lower()}.")
    if not keeps_truck and truck.status != Truck.Status.AVAILABLE:
        raise DispatchError(f"Truck {truck.unit_number} is {truck.get_status_display().lower()}.")

    if current:
        _release(current)
    assignment = Assignment.objects.create(load=load, driver=driver, truck=truck, assigned_by=user)
    Driver.objects.filter(pk=driver.pk).update(status=Driver.Status.ON_LOAD)
    Truck.objects.filter(pk=truck.pk).update(status=Truck.Status.IN_USE)
    load.status = S.DISPATCHED
    load.save(update_fields=["status"])
    return assignment


@transaction.atomic
def change_status(load, new_status):
    if new_status not in S.values:
        raise DispatchError("Unknown status.")
    load = Load.objects.select_for_update().get(pk=load.pk)
    if new_status not in ALLOWED_TRANSITIONS[load.status]:
        raise DispatchError(
            f"Cannot move a load from {load.get_status_display()} to {S(new_status).label}."
        )

    current = load.assignments.filter(active=True).first()
    if new_status == S.AVAILABLE and current:
        _release(current)
    if new_status == S.DELIVERED:
        load.delivered_at = timezone.now()
        if current:
            # Keep the assignment as history but free the driver and truck.
            Driver.objects.filter(pk=current.driver_id).update(status=Driver.Status.AVAILABLE)
            Truck.objects.filter(pk=current.truck_id).update(status=Truck.Status.AVAILABLE)

    load.status = new_status
    load.save(update_fields=["status", "delivered_at"])
    return load
