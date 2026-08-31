#!/usr/bin/env python3
import pprint
import subprocess

import pkg_resources

dupes = [
    d for d in pkg_resources.working_set if d.key in ("app", "coordinate-recorder")
]
pprint.pprint([(d.key, d.location) for d in dupes])

# Also check pip list

result = subprocess.run(["pip", "list"], capture_output=True, text=True)
print("\n--- pip list (filtered) ---")
for line in result.stdout.split("\n"):
    if "app" in line.lower() or "coordinate" in line.lower():
        print(line)
