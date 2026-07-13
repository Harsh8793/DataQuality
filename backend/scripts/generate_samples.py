"""Generate deliberately-messy demo datasets for a compelling demo.

The data is intentionally dirty (nulls, duplicates, inconsistent casing, bad
emails, whitespace, outliers, mixed types) so quality analysis, cleaning and
PII detection all have dramatic things to surface.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"

_FIRST = ["Ava", "Liam", "Noah", "Emma", "Olivia", "Sophia", "Jackson", "Mia", "Lucas", "Amelia"]
_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
_STATES = ["California", "Texas", "New York", "Florida", "Illinois", "Washington"]
_PRODUCTS = ["Laptop", "Monitor", "Keyboard", "Mouse", "Webcam", "Headset", "Docking Station"]
_COUNTRIES = ["USA", "usa", "United States", "US", "u.s.a.", "United States of America"]
_GENDERS = ["M", "Male", "male", "F", "Female", "female", "m", "f"]


def _messy_email(first: str, last: str) -> str:
    base = f"{first}.{last}".lower()
    roll = random.random()
    if roll < 0.12:
        return f"{base}@@invalid"          # invalid
    if roll < 0.18:
        return f"{base}(at)example.com"    # invalid
    return f"{base}@example.com"


def generate_sales(rows: int = 220, seed: int = 42) -> pd.DataFrame:
    """Generate a messy sales/customers dataset."""
    random.seed(seed)
    records = []
    for i in range(rows):
        first = random.choice(_FIRST)
        last = random.choice(_LAST)
        revenue = round(random.uniform(50, 5000), 2)
        if random.random() < 0.03:
            revenue = round(random.uniform(50000, 200000), 2)  # outliers
        records.append({
            "customer_id": 1000 + i,
            "  Full Name ": f"  {first} {last}  " if random.random() < 0.3 else f"{first} {last}",
            "email": _messy_email(first, last),
            "phone": random.choice(["+1-555-0100", "5550100", "555.010.9999", "call me", "+1 (555) 012-3456"]),
            "state": random.choice(_STATES),
            "country": random.choice(_COUNTRIES),
            "gender": random.choice(_GENDERS),
            "product": random.choice(_PRODUCTS),
            "revenue": revenue if random.random() > 0.08 else None,   # missing values
            "quantity": random.choice([1, 2, 3, 4, 5, "3", "two"]),   # mixed types
            "order_date": random.choice(["2024-01-15", "15/02/2024", "2024/03/20", "not a date", "2024-04-10"]),
            "notes": random.choice(["", "  ", "VIP", "follow up", None]),
        })

    df = pd.DataFrame(records)
    # Inject exact duplicate rows.
    df = pd.concat([df, df.iloc[:12]], ignore_index=True)
    # A constant column (no information).
    df["region"] = "North America"
    return df


def main() -> None:
    """Write all sample datasets to the samples directory."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    sales = generate_sales()
    csv_path = SAMPLES_DIR / "messy_sales.csv"
    sales.to_csv(csv_path, index=False)
    print(f"Wrote {csv_path} ({len(sales)} rows x {sales.shape[1]} cols)")

    # A clean-ish JSON variant to show multi-format support.
    json_path = SAMPLES_DIR / "products.json"
    pd.DataFrame({
        "product": _PRODUCTS,
        "price": [1200, 300, 80, 40, 90, 150, 220],
        "in_stock": [True, True, False, True, False, True, True],
    }).to_json(json_path, orient="records", indent=2)
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
