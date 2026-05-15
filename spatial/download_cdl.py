#!/usr/bin/env python3
"""
Standalone CDL downloader — run this yourself in a terminal.

Downloads USDA Cropland Data Layer GeoTIFFs for California from NASS CropScape.
Files are ~1 GB each; NASS drops connections at ~130 MB so the script reconnects
with HTTP Range headers until each file is complete (~9 reconnects per year).

Usage:
    python download_cdl.py                        # all years 2015-2023
    python download_cdl.py --years 2020 2021      # specific years
    python download_cdl.py --force                # re-download even if cached

Output: data/cdl/cdl_{year}_ca.tif
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# ---------------------------------------------------------------------------

CDL_DIR   = Path("data/cdl")
CDL_WCS   = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile"
CA_BBOX   = (-2_110_000, 1_480_000, -1_160_000, 2_490_000)   # EPSG:5070
YEARS_ALL = list(range(2015, 2024))

# ---------------------------------------------------------------------------

def get_nass_url(year: int) -> str:
    xmin, ymin, xmax, ymax = CA_BBOX
    for attempt in range(1, 6):
        try:
            print(f"  requesting download URL from NASS (attempt {attempt}) ...", flush=True)
            r = requests.get(
                CDL_WCS,
                params={
                    "year": year,
                    "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                    "format": "GeoTIFF",
                    "crs": "EPSG:5070",
                },
                timeout=300,
            )
            r.raise_for_status()
            root = ET.fromstring(r.text)
            url_el = root.find(".//{*}returnURL")
            if url_el is None:
                url_el = root.find("returnURL")
            if url_el is None or not (url_el.text or "").strip():
                raise RuntimeError(f"no returnURL in response: {r.text[:300]}")
            return url_el.text.strip()
        except Exception as exc:
            if attempt < 5:
                wait = 15 * attempt
                print(f"  failed ({exc}); retrying in {wait}s ...", flush=True)
                time.sleep(wait)
            else:
                raise RuntimeError(f"could not get NASS URL for {year}: {exc}") from exc


def download_year(year: int, force: bool = False) -> None:
    CDL_DIR.mkdir(parents=True, exist_ok=True)
    out = CDL_DIR / f"cdl_{year}_ca.tif"

    if out.exists() and not force:
        try:
            import rasterio
            import numpy as np
            with rasterio.open(out) as src:
                # Read a tile near the bottom of the file — catches truncated downloads
                # that have valid headers but missing pixel data
                w = rasterio.windows.Window(src.width // 2, src.height - 100, 100, 100)
                src.read(1, window=w)
            print(f"CDL {year}: already complete ({out.stat().st_size / 1e6:.0f} MB) — skipping")
            return
        except Exception:
            print(f"CDL {year}: existing file is truncated — deleting and restarting")
            out.unlink()

    file_url = get_nass_url(year)
    print(f"  URL: {file_url}", flush=True)

    written = 0
    for attempt in range(1, 21):   # up to 20 reconnects; 20 × 130 MB > 1066 MB
        headers = {"Range": f"bytes={written}-"} if written else {}
        mode    = "ab" if written else "wb"
        if written:
            print(f"  resuming from {written / 1e6:.0f} MB (reconnect {attempt}) ...", flush=True)
        try:
            with requests.get(file_url, stream=True, timeout=3600, headers=headers) as resp:
                if resp.status_code == 416:
                    break   # server says we already have everything
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0)) + written
                with open(out, mode) as f:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = 100 * written / total
                            print(f"\r  {written / 1e6:.0f} / {total / 1e6:.0f} MB  ({pct:.0f}%)",
                                  end="", flush=True)
            break   # completed without error
        except Exception as exc:
            written = out.stat().st_size if out.exists() else 0
            if attempt < 20:
                print(f"\n  connection dropped at {written / 1e6:.0f} MB ({exc}); reconnecting in 15s ...",
                      flush=True)
                time.sleep(15)
            else:
                print(f"\n  gave up after 20 attempts", flush=True)
                sys.exit(1)

    # Final validation — read a pixel tile near the bottom to catch truncation
    print(flush=True)
    try:
        import rasterio
        with rasterio.open(out) as src:
            w = rasterio.windows.Window(src.width // 2, src.height - 100, 100, 100)
            src.read(1, window=w)
        print(f"CDL {year}: complete and valid ({out.stat().st_size / 1e6:.0f} MB) → {out}")
    except Exception as exc:
        print(f"CDL {year}: WARNING — file is truncated ({exc}); re-run with --force")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Download USDA CDL rasters for California")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS_ALL,
                        metavar="YEAR", help="years to download (default: 2015-2023)")
    parser.add_argument("--force", action="store_true",
                        help="re-download even if cached file looks valid")
    args = parser.parse_args()

    print(f"Downloading CDL for {len(args.years)} year(s): {args.years}")
    print(f"Output directory: {CDL_DIR.resolve()}\n")

    failed = []
    for year in args.years:
        print(f"--- {year} ---")
        try:
            download_year(year, force=args.force)
        except Exception as exc:
            print(f"CDL {year}: FAILED — {exc}")
            failed.append(year)
        print()

    if failed:
        print(f"Failed years: {failed}")
        sys.exit(1)
    else:
        print("All years complete.")


if __name__ == "__main__":
    main()
