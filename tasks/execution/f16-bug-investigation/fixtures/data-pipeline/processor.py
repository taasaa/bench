"""Data pipeline processor with a type comparison bug."""
import csv
import json


def process_orders(filepath: str) -> list[dict]:
    """Read orders from CSV, filter adults (age >= 18), return as list.

    Bug: CSV reader returns strings, so row["age"] is a string like "25".
    The comparison row["age"] >= 18 compares string to int, which in
    Python 3 always returns False (TypeError avoided, but comparison is wrong).
    Actually in Python 3, "25" >= 18 raises TypeError... but the real bug
    here is subtler: the code does int(row["age"]) for output but uses
    row["age"] directly for comparison, and in the CSV all ages are numeric
    strings, so the filter never works correctly.

    The fix: use int(row["age"]) in the comparison.
    """
    results = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Bug: comparing string to int
            if row["age"] >= 18:
                results.append({
                    "name": row["name"],
                    "age": int(row["age"]),
                    "total": float(row["total"]),
                })
    return results


def summarize(orders: list[dict]) -> dict:
    """Summarize filtered orders."""
    if not orders:
        return {"count": 0, "total": 0.0}
    return {
        "count": len(orders),
        "total": round(sum(o["total"] for o in orders), 2),
    }


if __name__ == "__main__":
    orders = process_orders("/tmp/data_pipeline_app/orders.csv")
    print(json.dumps(summarize(orders), indent=2))
