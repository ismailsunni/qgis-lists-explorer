#!/usr/bin/env bash
# Refresh the local archive mirror and rebuild docs/data/<list>.json.
# Only fetches months that are missing or still open (pipermail rewrites the
# current month, and the previous one for a few days after it rolls over).
set -euo pipefail
cd "$(dirname "$0")/.."

LISTS=("$@")
[ ${#LISTS[@]} -eq 0 ] && LISTS=(qgis-developer qgis-user)

for LIST in "${LISTS[@]}"; do
  BASE="https://lists.osgeo.org/pipermail/$LIST"
  DIR="raw/$LIST"
  mkdir -p "$DIR"

  curl -sS --max-time 60 "$BASE/" \
    | grep -oP '(?<=href=")[^"]*\.txt(\.gz)?(?=")' | sort -u > "$DIR/.index"

  # .txt files are live months; .txt.gz are closed and never change
  comm -13 <(ls "$DIR" | sort) <(grep '\.gz$' "$DIR/.index" | sort) > "$DIR/.todo"
  grep -v '\.gz$' "$DIR/.index" >> "$DIR/.todo"

  echo "$LIST: fetching $(grep -c . "$DIR/.todo" || true) archive(s)…"
  xargs -a "$DIR/.todo" -P 8 -I{} curl -sS --max-time 120 -o "$DIR/{}" "$BASE/{}"
  rm -f "$DIR/.index" "$DIR/.todo"

  python3 scripts/parse.py "$LIST"
done

python3 scripts/stamp.py
