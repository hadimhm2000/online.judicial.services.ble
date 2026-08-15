import json
from pathlib import Path

input_file = Path("all_units.json")
output_file = Path("units_compact.json")

keep_fields = [
    "Id",
    "ParentUnitId",
    "ParentId",
    "UnitName",
    "Code",
    "UnitNo",
    "UnitType",
    "HasChildUnit",
    "HasSelectUnit",
    "Depth",
    "Path",
]

if not input_file.exists():
    raise FileNotFoundError(f"Cannot find {input_file.resolve()}")

with input_file.open("r", encoding="utf-8") as f:
    data = json.load(f)

compact = []

for item in data:
    row = {}
    for key in keep_fields:
        row[key] = item.get(key)
    compact.append(row)

with output_file.open("w", encoding="utf-8") as f:
    json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

print("DONE")
print("Input rows:", len(data))
print("Output file:", output_file.resolve())
print("Output size MB:", round(output_file.stat().st_size / 1024 / 1024, 2))
