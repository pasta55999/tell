from tell.analysis.rules import (
    advertising,
    concentration,
    data_quality,
    inventory,
    profitability,
    refunds,
    revenue,
    seasonality,
)

MODULES = [revenue, profitability, refunds, advertising, concentration, inventory, seasonality, data_quality]

__all__ = ["MODULES"]
