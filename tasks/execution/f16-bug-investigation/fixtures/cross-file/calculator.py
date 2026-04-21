"""Calculator module — function was renamed but caller not updated."""


def compute_total(items: list[dict]) -> float:
    """Compute total price from a list of items.

    This function was renamed from calculate_total to compute_total,
    but the caller in service.py still imports calculate_total.
    """
    return round(sum(item["price"] * item["qty"] for item in items), 2)
