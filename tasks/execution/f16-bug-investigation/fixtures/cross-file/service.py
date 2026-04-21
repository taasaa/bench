"""Service module — still imports the old function name."""
from calculator import calculate_total  # Bug: function was renamed to compute_total


def process_order(items: list[dict]) -> dict:
    """Process an order and return summary."""
    total = calculate_total(items)
    return {"total": total, "item_count": len(items)}


if __name__ == "__main__":
    items = [
        {"name": "widget", "price": 10.0, "qty": 3},
        {"name": "gadget", "price": 25.0, "qty": 1},
    ]
    result = process_order(items)
    print(f"Order total: ${result['total']}")
