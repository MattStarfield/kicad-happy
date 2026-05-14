#!/usr/bin/env python3
"""Translate client-provided BOM and Pick & Place files to JLCPCB upload format.

JLCPCB expects:
  - BOM CSV columns: Comment, Designator, Footprint, LCSC Part #
    (extra columns are preserved but ignored by JLC's parser; we keep MPN,
     Manufacturer, Quantity, Notes for human review)
  - CPL CSV columns: Designator, Mid X, Mid Y, Layer (T/B), Rotation
    (coords in mm; this script converts mils -> mm automatically)

Supports:
  - BOM input: .xlsx (Altium/Gener8-style with alternate-mfg rows), .csv
  - P&P input: Altium-style mil CSV (auto-detects header row past metadata block),
               KiCad-style mm CSV (F.Cu/B.Cu layer names also mapped)

Usage:
  python3 translate_bom_pnp.py bom <input.xlsx|.csv> -o <output.csv>
  python3 translate_bom_pnp.py pnp <input.csv> -o <output.csv>

Library use:
  from translate_bom_pnp import translate_bom, translate_pnp
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any


# ---------- BOM translation ----------

BOM_DES_FIELDS = ("Designator", "Ref Des", "RefDes", "Reference", "References")
BOM_VAL_FIELDS = ("Comment", "Description", "Value", "Comments")
BOM_FP_FIELDS = ("Footprint", "Package")
BOM_MPN_FIELDS = ("Mfg PN", "MPN", "Manufacturer Part Number", "Manufacturer PN", "Mfr PN", "Part Number")
BOM_MFG_FIELDS = ("Mfg", "Manufacturer", "Mfr")
BOM_QTY_FIELDS = ("Quantity", "Qty", "Quantity Total")
BOM_IDX_FIELDS = ("Index", "Item")
BOM_LCSC_FIELDS = ("LCSC", "LCSC Part #", "LCSC Part Number", "LCSC#", "JLCPCB Part Number")
BOM_NOTES_FIELDS = ("Notes", "BOM Notes", "Comments", "Remarks")

DNP_MARKERS = ("NO STUFF", "NOSTUFF", "DNP", "DO NOT POPULATE", "DO NOT PLACE", "DNI", "NOLOAD")
PCB_MARKERS = ("PCB,", "BARE PCB", "PCB-")


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _find_col(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    lower = [_norm(h).lower() for h in headers]
    for cand in candidates:
        cl = cand.lower()
        for i, h in enumerate(lower):
            if h == cl:
                return i
    # loose contains
    for cand in candidates:
        cl = cand.lower()
        for i, h in enumerate(lower):
            if cl in h:
                return i
    return None


def _read_xlsx_rows(path: Path) -> list[list[Any]]:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        raise RuntimeError("openpyxl required for .xlsx input. Install: pip install openpyxl")
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.values]


def _read_csv_rows(path: Path) -> list[list[Any]]:
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.reader(f))


def _find_header_row(rows: list[list[Any]]) -> int:
    """Find the first row that looks like a BOM header (has Designator/Ref Des AND another known column)."""
    for i, row in enumerate(rows[:20]):
        cells = [_norm(c).lower() for c in row]
        has_des = any(d.lower() in cells for d in BOM_DES_FIELDS)
        has_other = any(v.lower() in cells for v in BOM_VAL_FIELDS + BOM_FP_FIELDS + BOM_MPN_FIELDS)
        if has_des and has_other:
            return i
    raise ValueError("Could not find BOM header row (no Designator/Ref Des column found)")


def translate_bom(input_path: Path, output_path: Path) -> dict:
    """Translate any BOM into JLCPCB upload format. Returns summary stats."""
    path = Path(input_path)
    if path.suffix.lower() == ".xlsx":
        rows = _read_xlsx_rows(path)
    else:
        rows = _read_csv_rows(path)
    header_idx = _find_header_row(rows)
    hdr = [_norm(c) for c in rows[header_idx]]

    col_idx = _find_col(hdr, BOM_IDX_FIELDS)
    col_qty = _find_col(hdr, BOM_QTY_FIELDS)
    col_des = _find_col(hdr, BOM_DES_FIELDS)
    col_val = _find_col(hdr, BOM_VAL_FIELDS)
    col_fp = _find_col(hdr, BOM_FP_FIELDS)
    col_mpn = _find_col(hdr, BOM_MPN_FIELDS)
    col_mfg = _find_col(hdr, BOM_MFG_FIELDS)
    col_lcsc = _find_col(hdr, BOM_LCSC_FIELDS)
    col_notes = _find_col(hdr, BOM_NOTES_FIELDS)
    if col_des is None or (col_val is None and col_fp is None):
        raise ValueError(f"BOM missing required columns. Found: {hdr}")

    def cell(row: list[Any], idx: int | None) -> str:
        if idx is None or idx >= len(row):
            return ""
        return _norm(row[idx])

    out_rows: list[dict[str, str]] = []
    stats = {"input_rows": 0, "output_rows": 0, "skipped_pcb": 0, "skipped_dnp": 0, "no_mpn": 0}
    current: dict[str, Any] | None = None

    for row in rows[header_idx + 1:]:
        if not row or not any(_norm(c) for c in row):
            continue
        idx_val = cell(row, col_idx) if col_idx is not None else ""
        des_val = cell(row, col_des)
        val_val = cell(row, col_val)
        fp_val = cell(row, col_fp)
        mpn_val = cell(row, col_mpn)
        mfg_val = cell(row, col_mfg)
        qty_val = cell(row, col_qty)
        lcsc_val = cell(row, col_lcsc)
        notes_val = cell(row, col_notes)

        is_continuation = col_idx is not None and not idx_val and not des_val and (mpn_val or mfg_val)
        if is_continuation and current is not None:
            current.setdefault("alt_mpns", []).append(mpn_val)
            current.setdefault("alt_mfgs", []).append(mfg_val)
            continue

        if current is not None:
            out_rows.append(_finalize_bom_row(current, stats))
        stats["input_rows"] += 1

        upper_desc = val_val.upper()
        if any(m in upper_desc for m in PCB_MARKERS) or upper_desc.strip() == "PCB":
            stats["skipped_pcb"] += 1
            current = None
            continue
        if any(m in upper_desc for m in DNP_MARKERS):
            stats["skipped_dnp"] += 1
            current = None
            continue

        current = {
            "designator": des_val,
            "comment": val_val,
            "footprint": fp_val,
            "mpn": mpn_val,
            "manufacturer": mfg_val,
            "quantity": qty_val,
            "lcsc": lcsc_val,
            "notes": notes_val,
            "alt_mpns": [],
            "alt_mfgs": [],
        }

    if current is not None:
        out_rows.append(_finalize_bom_row(current, stats))
    stats["output_rows"] = len(out_rows)

    out_path = Path(output_path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Comment", "Designator", "Footprint", "LCSC Part #",
            "MPN", "Manufacturer", "Quantity", "Notes",
        ])
        w.writeheader()
        w.writerows(out_rows)
    stats["output_path"] = str(out_path)
    return stats


def _finalize_bom_row(current: dict, stats: dict) -> dict[str, str]:
    if not current.get("mpn"):
        stats["no_mpn"] += 1
    return {
        "Comment": current.get("comment") or "",
        "Designator": current.get("designator") or "",
        "Footprint": current.get("footprint") or "",
        "LCSC Part #": current.get("lcsc") or "",
        "MPN": current.get("mpn") or "",
        "Manufacturer": current.get("manufacturer") or "",
        "Quantity": current.get("quantity") or "",
        "Notes": current.get("notes") or "",
    }


# ---------- P&P translation ----------

PNP_DES_FIELDS = ("Designator", "Ref", "Reference", "RefDes")
PNP_X_FIELDS = ("Center-X(mil)", "Center-X(mm)", "Mid X", "PosX", "Center-X", "X")
PNP_Y_FIELDS = ("Center-Y(mil)", "Center-Y(mm)", "Mid Y", "PosY", "Center-Y", "Y")
PNP_LAYER_FIELDS = ("Layer", "Side", "TB")
PNP_ROT_FIELDS = ("Rotation", "Rot", "Angle")


def _find_pnp_header_row(rows: list[list[Any]]) -> int:
    for i, row in enumerate(rows[:30]):
        cells = [_norm(c).lower() for c in row]
        has_des = any(d.lower() in cells for d in PNP_DES_FIELDS)
        has_xy = (any(x.lower() in cells for x in PNP_X_FIELDS) and any(y.lower() in cells for y in PNP_Y_FIELDS))
        if has_des and has_xy:
            return i
    raise ValueError("Could not find P&P header row (no Designator + X/Y columns found)")


def _coord_to_mm(s: str, units_hint: str | None) -> str:
    """Convert a coordinate string to mm-formatted string with 'mm' suffix."""
    s = _norm(s)
    if not s:
        return s
    # If string already has units appended, parse it
    m = re.match(r"^(-?[\d.]+)\s*(mm|mil|inch|in|cm)?$", s, re.IGNORECASE)
    if not m:
        return s
    val = float(m.group(1))
    unit = (m.group(2) or units_hint or "").lower()
    if unit in ("mil",):
        val_mm = val * 0.0254
    elif unit in ("inch", "in"):
        val_mm = val * 25.4
    elif unit in ("cm",):
        val_mm = val * 10
    else:
        val_mm = val  # assume mm
    return f"{val_mm:.4f}mm"


LAYER_MAP_TOP = ("toplayer", "top", "f.cu", "front", "t")
LAYER_MAP_BOT = ("bottomlayer", "bottom", "b.cu", "back", "b")


def _normalize_layer(s: str) -> str:
    s_norm = _norm(s).lower()
    if s_norm in LAYER_MAP_TOP:
        return "T"
    if s_norm in LAYER_MAP_BOT:
        return "B"
    return s.strip()  # passthrough if unknown


def translate_pnp(input_path: Path, output_path: Path) -> dict:
    rows = _read_csv_rows(Path(input_path))
    header_idx = _find_pnp_header_row(rows)
    hdr = [_norm(c) for c in rows[header_idx]]
    col_des = _find_col(hdr, PNP_DES_FIELDS)
    col_x = _find_col(hdr, PNP_X_FIELDS)
    col_y = _find_col(hdr, PNP_Y_FIELDS)
    col_layer = _find_col(hdr, PNP_LAYER_FIELDS)
    col_rot = _find_col(hdr, PNP_ROT_FIELDS)
    if None in (col_des, col_x, col_y, col_layer, col_rot):
        raise ValueError(f"P&P missing required columns. Found: {hdr}")

    # Detect units from column header
    units_hint = None
    for h in hdr:
        hl = h.lower()
        if "(mil)" in hl:
            units_hint = "mil"
            break
        if "(mm)" in hl:
            units_hint = "mm"
            break
        if "(inch)" in hl:
            units_hint = "inch"
            break

    stats = {"input_rows": 0, "output_rows": 0, "top_count": 0, "bot_count": 0}
    out_rows: list[dict[str, str]] = []
    for row in rows[header_idx + 1:]:
        if not row or not any(_norm(c) for c in row):
            continue
        des = _norm(row[col_des]) if col_des < len(row) else ""
        if not des or des.startswith("="):
            continue
        stats["input_rows"] += 1
        x = _norm(row[col_x]) if col_x < len(row) else ""
        y = _norm(row[col_y]) if col_y < len(row) else ""
        layer = _norm(row[col_layer]) if col_layer < len(row) else ""
        rot = _norm(row[col_rot]) if col_rot < len(row) else ""

        normalized_layer = _normalize_layer(layer)
        if normalized_layer == "T":
            stats["top_count"] += 1
        elif normalized_layer == "B":
            stats["bot_count"] += 1
        out_rows.append({
            "Designator": des,
            "Mid X": _coord_to_mm(x, units_hint),
            "Mid Y": _coord_to_mm(y, units_hint),
            "Layer": normalized_layer,
            "Rotation": rot,
        })

    out_path = Path(output_path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writeheader()
        w.writerows(out_rows)
    stats["output_rows"] = len(out_rows)
    stats["units_detected"] = units_hint or "(none, assumed mm)"
    stats["output_path"] = str(out_path)
    return stats


# ---------- CLI ----------

def _cli():
    p = argparse.ArgumentParser(description="Translate client BOM/P&P files to JLCPCB format")
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("bom", help="Translate a BOM (xlsx/csv) to JLCPCB-format CSV")
    pb.add_argument("input")
    pb.add_argument("-o", "--output", required=True)
    pp = sub.add_parser("pnp", help="Translate a Pick&Place CSV to JLCPCB CPL")
    pp.add_argument("input")
    pp.add_argument("-o", "--output", required=True)
    args = p.parse_args()
    if args.cmd == "bom":
        stats = translate_bom(Path(args.input), Path(args.output))
    elif args.cmd == "pnp":
        stats = translate_pnp(Path(args.input), Path(args.output))
    import json
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    _cli()
