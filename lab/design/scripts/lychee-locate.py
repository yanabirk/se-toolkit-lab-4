"""Post-process lychee --format json output to add file:line locations.
"""

import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel


class _Status(BaseModel):
    text: str


class _LinkError(BaseModel):
    url: str
    status: _Status


class _LycheeOutput(BaseModel):
    error_map: dict[str, list[_LinkError]] = {}


def find_location(filepath: str, url: str) -> tuple[int, int] | None:
    # lychee normalizes relative file links to absolute file:// URLs.
    # Reconstruct a searchable pattern from just the basename + fragment.
    if url.startswith("file://"):
        path_part = re.sub(r"^file://", "", url)
        basename = path_part.split("/")[-1]  # e.g. "task-1.md#6-authorize-in-swagger-ui"
        pattern = re.compile(re.escape(basename))
    else:
        pattern = re.compile(re.escape(url.rstrip("/")))

    try:
        with open(filepath) as f:
            for i, line in enumerate(f, 1):
                m = pattern.search(line)
                if m:
                    start = m.start()
                    # Adjust for a relative path prefix (e.g. "./" or "../") that
                    # precedes the basename but was stripped when we split on "/".
                    prefix_match = re.search(r'(?:\.\.?/)+$', line[:start])
                    if prefix_match:
                        start = prefix_match.start()
                    return i, start + 1
    except (OSError, UnicodeDecodeError):
        pass
    return None


raw = sys.stdin.read()
# lychee sometimes emits the JSON block twice; take the first complete object
raw_obj, _ = json.JSONDecoder().raw_decode(raw.lstrip())
data = _LycheeOutput.model_validate(raw_obj)

if not data.error_map:
    print("No broken links found.")
    sys.exit(0)

for filepath, errors in data.error_map.items():
    try:
        relpath = Path(filepath).relative_to(Path.cwd())
    except ValueError:
        relpath = Path(filepath)
    for error in errors:
        loc = find_location(filepath, error.url)
        location = f"{relpath}:{loc[0]}:{loc[1]}" if loc else str(relpath)
        print(f"{location}: [ERROR] {error.url}")
        print(f"  {error.status.text}")

sys.exit(1)
