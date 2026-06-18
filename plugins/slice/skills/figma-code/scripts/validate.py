#!/usr/bin/env python3
import argparse
import json
import pathlib
import re

import numpy as np
from PIL import Image


def stringify(v):
    if isinstance(v, str):
        return v
    return json.dumps(v)


# Record a value difference with its path and both sides, a missing for a path only in a, and an extra for a path only in b.
def walk(a, b, path, differences, a_dir, b_dir):
    # Walk a and b together by the same path comparing every key and value both ways, excluding box and the screenshot path.
    if isinstance(a, dict) and isinstance(b, dict):
        # For every frame compare the a and b screenshot images and record the percent pixel difference at the frame path.
        if a.get("type") == "FRAME" and b.get("type") == "FRAME":
            ima = Image.open(a_dir / a["screenshot"]).convert("RGB")
            imb = Image.open(b_dir / b["screenshot"]).convert("RGB").resize(ima.size)
            diff = round(np.abs(np.asarray(ima, float) - np.asarray(imb, float)).mean() / 255 * 100, 2)
            differences.append({"path": path, "kind": "screenshot", "percent": diff})

        all_keys = set(a.keys()) | set(b.keys())
        skip = {"box", "screenshot"}
        for key in all_keys:
            if key in skip:
                continue
            child_path = path + "/" + key if path else key
            if key in a and key in b:
                walk(a[key], b[key], child_path, differences, a_dir, b_dir)
            elif key in a:
                # Record a missing for a path only in a.
                differences.append({"path": child_path, "kind": "missing", "a": stringify(a[key])})
            else:
                # Record an extra for a path only in b.
                differences.append({"path": child_path, "kind": "extra", "b": stringify(b[key])})

    elif isinstance(a, list) and isinstance(b, list):
        longer = max(len(a), len(b))
        for i in range(longer):
            child_path = path + "/" + str(i)
            if i < len(a) and i < len(b):
                walk(a[i], b[i], child_path, differences, a_dir, b_dir)
            elif i < len(a):
                # Record a missing for a path only in a.
                differences.append({"path": child_path, "kind": "missing", "a": stringify(a[i])})
            else:
                # Record an extra for a path only in b.
                differences.append({"path": child_path, "kind": "extra", "b": stringify(b[i])})

    else:
        # Record a value difference with its path and both sides.
        if a != b:
            differences.append({"path": path, "kind": "value", "a": stringify(a), "b": stringify(b)})


def main():
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description="Compare two design documents and their reference images",
        epilog="Examples:\n  python3 validate.py --a /path/to/fig/1-2.json --b /path/to/cln/1-2.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--a", type=str, required=True, help="The path to the first design document")
    parser.add_argument("--b", type=str, required=True, help="The path to the second design document")
    args = parser.parse_args()
    if args.a is not None and not re.match(r"^/", args.a):
        parser.error("--a must match ^/")
    if args.b is not None and not re.match(r"^/", args.b):
        parser.error("--b must match ^/")

    # Read the two design documents a and b as json.
    a = json.loads(pathlib.Path(args.a).read_text())
    b = json.loads(pathlib.Path(args.b).read_text())

    a_dir = pathlib.Path(args.a).parent
    b_dir = pathlib.Path(args.b).parent

    differences = []

    # Walk a and b together by the same path comparing every key and value both ways, excluding box and the screenshot path.
    walk(a, b, "", differences, a_dir, b_dir)

    # Print an object with a differences array holding all the records.
    print(json.dumps({"differences": differences}))


if __name__ == "__main__":
    main()
