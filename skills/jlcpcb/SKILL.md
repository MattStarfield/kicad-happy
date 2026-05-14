---
name: jlcpcb
description: JLCPCB PCB fabrication and assembly — Open Platform API (signed HMAC-SHA256), instant quoting, order tracking, component lookup, BOM/CPL translation from any client format. Use with KiCad for JLCPCB manufacturing. Use this skill when the user mentions JLCPCB, wants to order PCBs or assembled boards, needs prototype bare PCBs and stencils, wants to know JLCPCB design rules and capabilities, is asking about PCB manufacturing costs or turnaround times, wants to translate a client BOM/Pick&Place file to JLCPCB upload format, or needs component lookup against JLCPCB's library. For gerber/CPL export, stencil ordering, and BOM management, see the `bom` skill.
---

# JLCPCB — PCB Fabrication & Assembly

JLCPCB is a PCB fabrication and assembly service based in Shenzhen, China. It is a sister company to LCSC Electronics (common ownership) — they share the same parts library.

**Typical usage**: Order bare prototype PCBs + framed stencil from JLCPCB during prototyping (parts sourced separately from DigiKey/Mouser, hand-assembled in lab). For production runs (100s qty), order fully assembled boards from JLCPCB using LCSC parts. PCBWay is an alternative assembler. For component searching, see the `lcsc` skill. For BOM management, gerber/CPL export, and stencil ordering, see the `bom` skill.

## How to use this skill — the `jlcpcb-cli` tool

Matt has an approved JLCPCB Open Platform API account. A working CLI is on PATH at `~/.local/bin/jlcpcb-cli` (wraps `~/scripts/jlcpcb-api/jlcpcb_cli.py`).

**Always reach for `jlcpcb-cli` first** for anything programmatic against JLCPCB. Fall back to Playwright only for PCBA workflows (assembly is NOT exposed via the API).

```
jlcpcb-cli auth verify              # confirm credentials + which API scopes are active
jlcpcb-cli component C14663         # look up an LCSC C-number
jlcpcb-cli component-search 100nF   # search public component library
jlcpcb-cli private-stock            # list consigned (private) component inventory
jlcpcb-cli pcb quote <fileId> --layers 8 --qty 10 --finish ENIG --thickness 1.6
jlcpcb-cli pcb audit <fileId>       # parsed Gerber info (dimensions, preview)
jlcpcb-cli pcb order detail <batchNum>
jlcpcb-cli pcb order wip <batchNum>
jlcpcb-cli bom translate <input.xlsx|.csv> -o <output.csv>
jlcpcb-cli pnp translate <input.csv> -o <output-cpl.csv>
```

Default output is human-readable tables. **For programmatic / LLM consumption always pass `--json`** to get parseable output.

### Credentials & auth

- Credentials live at `~/.config/jlcpcb/credentials.json` (mode 0600). NEVER print them, commit them, or paste them into conversation.
- The shell auto-loader at `~/.bashrc.d/87-jlcpcb-api.sh` exports `JLCPCB_APP_ID`, `JLCPCB_ACCESS_KEY`, `JLCPCB_SECRET_KEY` into every new shell so subprocesses see them.
- Auth scheme: HMAC-SHA256 signed requests with `Authorization: JOP appid=...,accesskey=...,nonce=...,timestamp=...,signature=...` per JLCPCB's API docs.

### Known gotcha — per-API permission scopes

Even with valid credentials, each API category (PCB / Parts / Stencil / 3D) must be enabled in the developer console. Until enabled, endpoints return `403 "API insufficient permissions, access denied"`. **The CLI catches this specifically** and prints what to do:

> Sign in at https://api.jlcpcb.com → Manage Apps → Permission Setting, toggle on the relevant scope, wait for status to flip from `Reviewing` to `Active`.

### Hard limit — PCBA is NOT in the public API

The JLCPCB Open Platform API covers: **bare PCB quoting/ordering, Stencil, 3D Printing, Components**. It does **NOT** include PCB **Assembly** (PCBA) quoting or ordering. The published endpoint catalog (api.jlcpcb.com/docs/api-list) confirms this.

For PCBA workflows we use Playwright against `cart.jlcpcb.com/quote` with the user's logged-in browser session. Reference implementation in conversation history of geltech project, 2026-05-13.

### Endpoint catalog (base: `https://open.jlcpcb.com`)

All POST unless noted. Prefix: `/overseas/openapi/`.

**PCB**: `pcb/calculate` (quote) · `pcb/create` (order) · `pcb/order/detail` · `pcb/audit/get` (Gerber parse) · `pcb/wip/get` (production status) · `pcb/uploadGerber` (multipart) · `pcb/uploadBlindViaHoleImg` · `pcb/getImpedanceTemplateSettingList` · `pcb/getSteelPriceConfig` (GET).

**Components**: `component/getComponentDetailByCode` (by C-number) · `component/getComponentLibraryList` (paginated) · `component/getPrivateComponentLibrary` (consigned inventory) · `component/getComponentInfos`.

**3D Printing**: `tdp/api/{calculate,upload,order/{create,list,detail,process},file/result}`.

### Standard PCBA quote workflow — the MANDATORY steps

When a client provides BOM and Pick & Place files for a PCBA quote (in any format — Altium .xlsx, KiCad CSV, OrCAD, etc.), follow ALL of these steps. None are optional.

#### Step 1: Translate BOM first (gives you the canonical Designator set)

```bash
jlcpcb-cli bom translate "Client BOM.xlsx" -o "Client BOM-jlc-formatted.csv"
```

#### Step 2: Translate Pick & Place, **always passing `--bom`** so the CPL is filtered

```bash
jlcpcb-cli pnp translate "Client Pick & Place.csv" \
  -o "Client Pick & Place-jlc-formatted.csv" \
  --bom "Client BOM-jlc-formatted.csv"
```

**ALWAYS pass `--bom`.** Without it, the CPL will include placements for mounting holes (`MH*`), fiducials, unstuffed test points (TP Pads), and `NO STUFF` components — none of which exist in the BOM. JLCPCB's matcher rejects the upload with **"CPL does not match BOM"** when CPL has orphan designators. The `--bom` filter drops these and guarantees perfect designator parity.

Verify parity before handing off the files:

```bash
python3 -c "
import csv
b = set(); c = set()
for r in csv.DictReader(open('Client BOM-jlc-formatted.csv')):
    for d in r['Designator'].split(','):
        if d.strip(): b.add(d.strip())
for r in csv.DictReader(open('Client Pick & Place-jlc-formatted.csv')):
    if r['Designator'].strip(): c.add(r['Designator'].strip())
print(f'BOM: {len(b)}  CPL: {len(c)}  CPL-orphans: {len(c-b)}  BOM-only: {len(b-c)}')
"
```

CPL-orphans should be **0**. BOM-only is fine (those are joined refdes lists in the BOM that map to multiple stuffed positions in CPL).

#### Step 3 (MANDATORY): Tabulate consigned-parts cost as part of the quote

JLCPCB only assembles parts they can source from their LCSC library. Any part on the BOM that is NOT in LCSC stock (or is in stock but the client requires the exact MPN that LCSC doesn't carry) must be **procured by you and shipped to JLCPCB** for consigned assembly. **The cost of those parts MUST appear in the project quote**, even though the client doesn't pay JLCPCB for them — they pay you (or DigiKey/Mouser/element14) for the parts plus shipping. Break the consigned-parts subtotal out separately from the JLCPCB PCBA quote so the client sees both line items.

Algorithm:

1. For each line in the translated BOM, look up the MPN in LCSC's library:

    ```bash
    jlcpcb-cli component <C-number> --json     # if you already have a C-number
    jlcpcb-cli component-search "<MPN>" --json  # search by manufacturer part number
    ```

    For free / no-auth lookup of MPN→C-number mapping, use the community jlcsearch API (see the `lcsc` skill).

2. Classify each BOM line as:
   - **Basic** (JLC sources, free) — `basic` flag in JLC response
   - **Extended** (JLC sources, $3 setup fee) — `basic == 0`, in stock
   - **Consigned** (you ship to JLC) — not in LCSC library, or LCSC stock = 0, or client requires exact MPN that LCSC doesn't have

3. For every Consigned line, query DigiKey / Mouser / element14 / direct manufacturer for the per-unit price at the build quantity (× boards × +20% spares is typical). Use the `digikey`, `mouser`, or `element14` skills.

4. Build the consigned-parts cost table — one row per Consigned MPN:

    | MPN | Qty/board | Boards | +Spares | Total qty | Source | Unit price | Extended | Notes |
    |---|---|---|---|---|---|---|---|---|

5. **Include the consigned-parts subtotal in the project quote**, formatted as:

    ```
    Project Quote
      JLCPCB Bare PCB                              $XXX.XX
      JLCPCB PCBA labor + extended-part fees       $XXX.XX
      JLCPCB Shipping (DHL DDP)                    $XX.XX
      ---
      Consigned-parts procurement (you ship):      $XXX.XX
        (broken-out table follows — see "consigned-parts cost" subsection)
      Shipping to JLCPCB (DHL international)       $XX.XX
      ---
      All-in landed cost                           $X,XXX.XX
    ```

The client must see the consigned-parts cost or the quote is incomplete. Even though JLCPCB doesn't invoice for those parts, the client is still spending real money on them.

### Translator behavior summary

| Concern | Handled |
|---|---|
| Multi-row alternate-manufacturer entries in xlsx | Collapses to primary MPN, alternates noted |
| mil → mm coordinate conversion | Auto-detected from header (`Center-X(mil)`, `(mm)`, `(inch)`) |
| Layer name normalization | TopLayer/Top/F.Cu → T; BottomLayer/Bottom/B.Cu → B |
| PCB / NO STUFF / DNP row filtering in BOM | Excluded automatically |
| CPL-vs-BOM designator orphan filtering | Use `--bom <path>` on `pnp translate` (MANDATORY) |
| Column auto-mapping (Designator/Ref Des/Reference, etc.) | `BOM_*_FIELDS` and `PNP_*_FIELDS` tuples in the translator |

Output:
- **BOM CSV**: `Comment, Designator, Footprint, LCSC Part #` (plus MPN/Manufacturer/Quantity/Notes for review)
- **CPL CSV**: `Designator, Mid X (mm), Mid Y (mm), Layer (T|B), Rotation`

If a client uses an unusual format that the translator doesn't auto-detect, edit `~/.claude/skills/jlcpcb/scripts/translate_bom_pnp.py` to add the new column name to the relevant `*_FIELDS` tuple. Then commit the improvement upstream to `MattStarfield/kicad-happy`.

### Discovery references

- Memory entry: `~/.claude/projects/-mnt-netshare-git-geltech/memory/reference_jlcpcb_api.md` (geltech-specific notes)
- Skill scripts: `~/.claude/skills/jlcpcb/scripts/translate_bom_pnp.py`
- Library: `~/scripts/jlcpcb-api/jlcpcb_client.py` (importable)
- CLI: `~/.local/bin/jlcpcb-cli` (wrapper) and `~/scripts/jlcpcb-api/jlcpcb_cli.py` (implementation)
- Reference Python SDK (for endpoint discovery): https://github.com/i2cjak/jlcpcb_api

## Related Skills

| Skill | Purpose |
|-------|---------|
| `kicad` | Read/analyze KiCad project files, DFM scoring against JLCPCB capabilities |
| `bom` | BOM management, gerber/CPL export, stencil ordering |
| `digikey` | Search DigiKey (prototype sourcing, primary — also preferred for datasheet downloads via API) |
| `mouser` | Search Mouser (prototype sourcing, secondary) |
| `lcsc` | Search LCSC (production sourcing — JLCPCB uses LCSC parts library) |
| `pcbway` | Alternative PCB fabrication & assembly |

## Assembly Parts Library

### Part Categories

| Category | Description | Assembly Fee |
|----------|-------------|--------------|
| **Basic** | ~698 common parts (resistors, caps, diodes, etc.) pre-loaded on pick-and-place machines | No extra fee |
| **Preferred Extended** | Frequently used extended parts | No feeder loading fee (Economic assembly) |
| **Extended** | 300k+ less common parts loaded on demand | $3 per unique extended part |

### LCSC Part Numbers

Every assembly component is identified by an **LCSC Part Number** (`Cxxxxx`, e.g., `C14663`). This is the definitive identifier for BOM matching. See the `lcsc` skill for searching parts.

### Parts Search (JLCPCB-Specific)

- Parts library: `https://jlcpcb.com/parts/componentSearch?searchTxt=<query>`
- Basic parts only: `https://jlcpcb.com/parts/basic_parts`

## BOM Format for Assembly

JLCPCB accepts CSV, XLS, or XLSX BOMs with these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `Comment` / `Value` | Yes | Component value (e.g., 100nF, 10k) |
| `Designator` | Yes | Reference designators, comma-separated (e.g., C1,C2,C5) |
| `Footprint` | Yes | Package/footprint name |
| `LCSC Part #` | Recommended | LCSC part number (Cxxxxx) — guarantees exact match |

The column header for LCSC numbers must be exactly **"LCSC Part #"** or **"LCSC Part Number"** — typos cause upload failures.

### KiCad BOM Export for JLCPCB

1. In KiCad schematic editor, add an `LCSC` field to each symbol with the LCSC part number
2. Export BOM as CSV with columns: Reference, Value, Footprint, LCSC
3. Rename columns to match JLCPCB's expected format:
   - `Reference` -> `Designator`
   - `Value` -> `Comment`
   - `Footprint` -> `Footprint`
   - `LCSC` -> `LCSC Part #`

For gerber export settings, CPL format, and stencil ordering, see the `bom` skill.

## JLCPCB Official API (Approval Required)

Apply at `https://api.jlcpcb.com`. Access is gated — requires review based on order history and business profile.

Available APIs (once approved):
- **Components API** — real-time pricing, inventory, component specs
- **PCB API** — upload gerbers, get quotes, place orders, track status
- **Stencil API** — stencil quoting and ordering
- **3D Printing API** — SLA/MJF/SLM/FDM ordering

## PCB Design Rules (JLCPCB Capabilities)

### Standard PCB (1-2 layers)

| Parameter | Minimum |
|-----------|---------|
| Trace width | 0.127mm (5mil) |
| Trace spacing | 0.127mm (5mil) |
| Via diameter | 0.45mm |
| Via drill | 0.2mm |
| Annular ring | 0.125mm |
| Min hole size | 0.2mm |
| Board thickness | 0.4-2.4mm (default 1.6mm) |
| Min board size | 6x6mm |
| Max board size | 500x400mm (2-layer) |

### Multi-layer (4+ layers)

| Parameter | Minimum |
|-----------|---------|
| Trace width | 0.09mm (3.5mil) |
| Trace spacing | 0.09mm (3.5mil) |
| Via diameter | 0.25mm |
| Via drill | 0.15mm |
| Board thickness | 0.6-2.4mm |

### Importing DRU into KiCad

If you have a JLCPCB `.kicad_dru` design rules file, import it in KiCad Board Editor > Board Setup > Design Rules > Import Settings.

## Assembly Constraints

### Economic vs Standard Assembly

| Feature | Economic | Standard |
|---------|----------|----------|
| Sides | Top only | Top + Bottom |
| Component types | SMD only | SMD + through-hole |
| Min component size | 0201 | 01005 |
| Fine-pitch BGA/QFP | Down to 0.5mm pitch | Down to 0.4mm pitch |
| Turnaround | ~3-5 days | ~3-5 days |
| Extended part fee | $3 per unique part | $3 per unique part |

### General Constraints

- **Minimum order**: 5 PCBs for assembly
- **Unique parts limit**: No hard limit, but each extended part adds $3
- **Basic parts**: No extra fee, pre-loaded on machines

## Rotation Offsets

JLCPCB's pick-and-place uses different rotation conventions than KiCad for some footprints. Common offsets:

| Footprint Family | Typical Offset |
|-----------------|----------------|
| SOT-23, SOT-23-5, SOT-23-6 | +180° |
| SOT-223 | +180° |
| SOIC-8, SOIC-16 | +90° or +270° |
| QFN (all sizes) | +90° |
| SMA/SMB/SMC diodes | +180° |
| USB-C connectors | Varies — check datasheet |

To fix rotation issues:
1. Add rotation corrections directly in the CPL file before uploading (adjust the Rotation column)
2. For custom footprints, verify pin 1 orientation matches JLCPCB expectations
3. JLCPCB's review step catches major errors, but subtle 180° rotations on symmetric parts (caps, resistors) may slip through
4. After first assembly order, note any rotation corrections needed and apply them to future CPL exports

## Ordering Workflow

### Prototype Order (Bare PCB + Stencil)

1. **Export gerbers** from KiCad (see `bom` skill for export settings)
2. Upload gerbers to `https://cart.jlcpcb.com/quote` — configure layers, thickness, color, qty
3. Add a **framed stencil** to the cart (uses paste layers from your gerbers)
4. Order — PCBs and stencil typically arrive in ~1 week

### Production Order (Assembled Boards)

1. **Export gerbers** from KiCad (see `bom` skill for export settings)
2. **Export BOM** as CSV with LCSC part numbers (format above)
3. **Export CPL** (placement file) as CSV (see `bom` skill for format)
4. Upload gerbers to `https://cart.jlcpcb.com/quote` — configure layers, thickness, color, qty
5. Enable "PCB Assembly", select Economic or Standard
6. Upload BOM and CPL files
7. Review part matching — fix any unmatched parts by searching LCSC numbers
8. Confirm and order

## Tips

- **Prefer Basic parts** — no extra fee, always in stock, faster assembly
- **Check stock before ordering** — extended parts can go out of stock; use the `lcsc` skill to search
- **Panel by JLCPCB** — for small boards, let JLCPCB panelize (cheaper) vs custom panels
- **Lead-free solder** — default is leaded (HASL); select lead-free HASL or ENIG if needed
- **Impedance control** — available for multi-layer boards, specify stackup in order notes
- **Castellated holes** — supported, enable in order options
- **V-cuts and mouse bites** — supported for panel separation
- **Silkscreen minimum** — 0.8mm height, 0.15mm line width for readable text
- **Edge clearance** — keep copper >=0.3mm from board edge (0.5mm recommended)
