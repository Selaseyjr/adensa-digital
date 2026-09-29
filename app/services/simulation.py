"""
Data-arrival simulation service group (P12.3 decomposition).

Creates one controlled simulated shipment arrival; the
refresh pipeline runs separately.
"""

from app.simulation import create_simulated_arrival


def run_data_arrival_simulation(connection):
    """
    Create one deterministic simulated shipment arrival.

    The simulation represents new operational data
    arriving: it creates ONLY the arrival records
    (shipment + shipment events) through the simulation
    module and repositories.

    It never creates exceptions, recovery options,
    recommendations or recovery actions, and it never
    calls the operational refresh: detecting and
    processing the arrival is the explicit job of
    run_operational_refresh(), which the user triggers
    separately.

    Returns the arrival summary dictionary from the
    simulation module, or None when the database
    contains no operational data to derive the scenario
    from.
    """

    return create_simulated_arrival(connection)
