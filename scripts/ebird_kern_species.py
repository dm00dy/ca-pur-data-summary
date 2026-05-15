#!/usr/bin/env python3
"""
Pull all aerial insectivore species recorded at Kern NWR hotspots
and check which have eBird S&T trend data available.
"""

from __future__ import annotations
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ["EBIRD_API_KEY"]

HEADERS = {"X-eBirdApiToken": API_KEY}
BASE = "https://api.ebird.org/v2"

# Kern NWR hotspots
HOTSPOTS = {
    "L628412":  "Kern NWR (main)",
    "L1481043": "Kern NWR—Semitropic Lake",
    "L2520115": "Kern NWR—Lost Hills Rd",
}

# Aerial insectivore families / groups relevant to the grant
AERIAL_INSECTIVORE_FAMILIES = {
    "Swallows and Martins": {
        "cliswa": "Cliff Swallow",
        "treswa": "Tree Swallow",
        "barswa": "Barn Swallow",
        "nrwswa": "Northern Rough-winged Swallow",
        "purmar": "Purple Martin",
        "banswa": "Bank Swallow",
        "vgswa":  "Violet-green Swallow",
    },
    "Swifts": {
        "whtswi": "White-throated Swift",
        "vaswi":  "Vaux's Swift",
        "blkswi": "Black Swift",
        "chimswi": "Chimney Swift",
    },
    "Nighthawks & Nightjars": {
        "comnig": "Common Nighthawk",
        "lesnig": "Lesser Nighthawk",
        "compos": "Common Poorwill",
    },
    "Flycatchers (aerial-sallying)": {
        "weskin": "Western Kingbird",
        "easkin": "Eastern Kingbird",
        "saysph": "Say's Phoebe",
    },
}

# Flatten to code → name
ALL_TARGETS = {}
for grp in AERIAL_INSECTIVORE_FAMILIES.values():
    ALL_TARGETS.update(grp)


def get_hotspot_species(loc_id: str) -> list[str]:
    """All species codes ever recorded at a hotspot."""
    url = f"{BASE}/product/spplist/{loc_id}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()  # flat list of species codes


def main() -> None:
    print("=== Kern NWR Aerial Insectivore Species Inventory ===\n")

    all_seen: set[str] = set()
    for loc_id, name in HOTSPOTS.items():
        try:
            codes = set(get_hotspot_species(loc_id))
        except Exception as e:
            print(f"  {name}: ERROR — {e}")
            continue
        matches = [c for c in codes if c in ALL_TARGETS]
        all_seen |= set(matches)
        print(f"  {name} ({loc_id}): {len(codes)} total species, "
              f"{len(matches)} target aerial insectivores")

    print(f"\nAll aerial insectivores ever recorded at Kern NWR hotspots:")
    for family, birds in AERIAL_INSECTIVORE_FAMILIES.items():
        found = [f"{name} ({code})" for code, name in birds.items() if code in all_seen]
        missing = [f"{name} ({code})" for code, name in birds.items() if code not in all_seen]
        if found:
            print(f"\n  {family}:")
            for b in found:
                print(f"    ✓  {b}")
        if missing:
            for b in missing:
                print(f"    —  {b}  [not recorded]")

    # Print the species codes to use in S&T download attempt
    codes_found = sorted(all_seen)
    print(f"\nSpecies codes for S&T analysis: {codes_found}")


if __name__ == "__main__":
    main()
