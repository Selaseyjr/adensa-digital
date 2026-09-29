"""
Exception investigation context service group (P12.3 decomposition).

The operational investigation context projection for one
exception.
"""

from app.repositories import exceptions_repo


def get_exception_context(
    connection,
    exception_id,
):
    """
    Return the operational investigation context for one
    exception, or None when the exception does not exist.

    Projects the existing shared context read into an
    application-facing structure for the UI and any other
    client. Contains no business rules: every field is
    retrieved operational data, including the recorded
    detection description (what happened) and the current
    resolution status.
    """

    context = exceptions_repo.get_exception_operational_context(
        connection,
        exception_id,
    )

    if context is None:
        return None

    return {
        "exception_id": context["exception_id"],
        "shipment_id": context["shipment_id"],
        "order_id": context["order_id"],
        "customer_id": context["customer_id"],
        "customer_name": context["customer_name"],
        "exception_type": context["exception_type"],
        "severity": context["severity"],
        "status": context["resolution_status"],
        "description": context["description"],
        "priority": context["priority"],
        "origin": context["origin"],
        "destination": context["destination"],
        "route": (
            f"{context['origin']} → "
            f"{context['destination']}"
        ),
        "transport_mode": context["transport_mode"],
        "carrier_id": context["carrier_id"],
        "shipment_status": context["shipment_status"],
        "planned_departure": context["planned_departure"],
        "estimated_arrival": context["estimated_arrival"],
        "required_delivery_date": context[
            "required_delivery_date"
        ],
    }
