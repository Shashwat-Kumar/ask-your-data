"""Generate the synthetic sample dataset (seeded). No real business data."""
import random, csv, datetime as dt
random.seed(42)
cities = ["Mumbai", "Pune", "Bengaluru", "Delhi", "Chennai", "Hyderabad"]
products = ["Tea", "Coffee", "Snacks", "Juice"]
channels = ["Store", "Online"]
rows = []
for m in range(12):
    month = dt.date(2025, 1 + m, 1)
    for c in cities:
        for p in products:
            for ch in channels:
                base = random.randint(20, 60)
                if c == "Pune" and m >= 8: base = int(base * 0.55)   # planted drop for the demo
                units = base * (2 if ch == "Online" else 1)
                price = {"Tea": 120, "Coffee": 260, "Snacks": 80, "Juice": 150}[p]
                rows.append([month.isoformat(), c, p, ch, units, units * price])
with open("data/sample_sales.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["order_month", "city", "product", "channel", "units", "revenue"]); w.writerows(rows)
print(len(rows), "rows")
