"""Build the shareable HA package without captures or local cache files."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).parent
DESTINATION = ROOT / "releases" / "chery_arrizo8-experimental.zip"
CARD_DESTINATION = ROOT / "releases" / "arrizo8-dashboard-card.zip"
CARD_SOURCES = sorted(path for path in (ROOT / "www" / "arrizo8").rglob("*") if path.is_file())
SOURCES = [
    *sorted((ROOT / "custom_components" / "chery_arrizo8").rglob("*.py")),
    *sorted((ROOT / "custom_components" / "chery_arrizo8").rglob("*.json")),
    *CARD_SOURCES,
    ROOT / "INSTALL.md",
    ROOT / "DASHBOARD.md",
    ROOT / "CARD.md",
]

DESTINATION.parent.mkdir(exist_ok=True)
missing = [source for source in SOURCES if not source.is_file()]
if missing:
    raise SystemExit(f"Missing package files: {missing}")
with ZipFile(DESTINATION, "w", ZIP_DEFLATED) as archive:
    for source in SOURCES:
        archive.write(source, source.relative_to(ROOT))

print(f"Built {DESTINATION.name} with {len(SOURCES)} files")

with ZipFile(CARD_DESTINATION, "w", ZIP_DEFLATED) as archive:
    for source in [*CARD_SOURCES, ROOT / "CARD.md"]:
        archive.write(source, source.relative_to(ROOT))

print(f"Built {CARD_DESTINATION.name} with {len(CARD_SOURCES) + 1} files")
