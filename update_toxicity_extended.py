#!/usr/bin/env python3
"""
Add bee, chironomid, and avian reproductive NOEC columns to toxicity table.

All values from PPDB (Hertfordshire Pesticide Properties DataBase) unless noted.
Units:
  bee_contact_ld50 / bee_oral_ld50  : μg/bee, Apis mellifera, 48h (worst-case)
  chironomid_ec50                   : μg/L water column (most sensitive acute endpoint
                                      available; see chironomid_endpoint for type)
  avian_noec_repro                  : mg/kg body weight/day, 21-day chronic NOEC

Notable sourcing flags:
  cyfluthrin chironomid             : PPDB reports EC5 (not EC50) — stored as NF
  deltamethrin chironomid           : 24h LC50 (shorter than standard 96h)
  carbofuran / aldicarb chironomid  : 1-day LC50 (PPDB)
  gamma-/bifenthrin chironomid      : 28d NOEC water (no acute available)
  tau-fluvalinate bee               : >12 μg/bee — selectively non-toxic to Apis
  spinosad bee contact              : 0.0036 μg/bee — highly toxic to bees despite
                                      "biopesticide" classification
"""

from pathlib import Path
import mysql.connector

TOX_CSV = Path("toxicity_lookup.csv")

DB_CFG = {
    "host": "localhost", "port": 3366,
    "user": "root", "password": "password",
    "database": "pur_data",
    "charset": "utf8mb4",
    "use_pure": True,
}

P  = "https://sitem.herts.ac.uk/aeru/ppdb/en/Reports/{}.htm"
BP = "https://sitem.herts.ac.uk/aeru/bpdb/Reports/{}.htm"

# (chemname, bee_contact, bee_contact_ceil, bee_oral, bee_oral_ceil, bee_url,
#  chiro_ec50, chiro_ceil, chiro_endpoint, chiro_species, chiro_url,
#  noec, noec_ceil, noec_species, noec_url)
DATA = [
    # ── Pyrethroids ──────────────────────────────────────────────────────────
    ("lambda-cyhalothrin",
     0.038, 0, 0.91,    0, P.format(415),
     1.5,      0, "96h LC50", "Chironomus riparius",  P.format(415),
     3.3,   0, "Anas platyrhynchos (mallard duck)",       P.format(415)),
    ("gamma-cyhalothrin",
     0.005, 0, 4.2,     0, P.format(369),
     0.047,    0, "28d NOEC", "Chironomus riparius",  P.format(369),
     None,  0, None, None),
    ("bifenthrin",
     0.016, 0, 0.1,     0, P.format(78),
     0.32,     0, "28d NOEC", "Chironomus riparius",  P.format(78),
     6.63,  0, "Colinus virginianus (Northern Bobwhite)", P.format(78)),
    ("esfenvalerate",
     0.07,  0, 0.21,    0, P.format(269),
     0.13,     0, "96h LC50", "Chironomus riparius",  P.format(269),
     18.7,  0, "Colinus virginianus (Northern Bobwhite)", P.format(269)),
    ("permethrin",
     0.024, 0, 0.13,    0, P.format(515),
     2.9,      0, "96h LC50", "Chironomus riparius",  P.format(515),
     None,  0, None, None),
    ("cypermethrin",
     0.023, 0, 0.172,   0, P.format(197),
     1.8,      1, "96h LC50", "Chironomus decorus",   P.format(197),
     4.29,  0, "Colinus virginianus (Northern Bobwhite)", P.format(197)),
    ("zeta-cypermethrin",
     0.002, 0, 0.044,   0, P.format(682),
     1.0,      0, "96h LC50", "Chironomus riparius",  P.format(682),
     2.15,  0, "Colinus virginianus (Northern Bobwhite)", P.format(682)),
    ("cyfluthrin",
     0.001, 1, 0.05,    1, P.format(192),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("beta-cyfluthrin",
     0.012, 0, 0.05,    0, P.format(74),
     0.45,     0, "96h LC50", "Chironomus riparius",  P.format(74),
     2.6,   0, "Anas platyrhynchos (mallard duck)",       P.format(74)),
    ("deltamethrin",
     0.0015,1, 0.07,    1, P.format(205),
     39.0,     0, "24h LC50", "Chironomus spp.",      P.format(205),
     55.0,  1, "Colinus virginianus (Northern Bobwhite)", P.format(205)),
    ("fenpropathrin",
     0.05,  1, None,    0, P.format(306),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("tau-fluvalinate",
     12.0,  1, 12.6,    1, P.format(608),
     0.24,     0, "28d NOEC", "Chironomus riparius",  P.format(608),
     70.0,  0, "Colinus virginianus (Northern Bobwhite)", P.format(608)),
    ("tralomethrin",
     0.13,  0, None,    0, P.format(647),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    # ── Organophosphates ─────────────────────────────────────────────────────
    ("chlorpyrifos",
     0.068, 0, 0.15,    0, P.format(154),
     0.024,    0, "96h LC50", "Chironomus riparius",  P.format(154),
     2.885, 0, "Anas platyrhynchos (mallard duck)",       P.format(154)),
    ("malathion",
     0.16,  0, 0.40,    0, P.format(421),
     0.4,      0, "96h LC50", "Chironomus riparius",  P.format(421),
     13.5,  0, "Colinus virginianus (Northern Bobwhite)", P.format(421)),
    ("diazinon",
     0.13,  0, 0.09,    0, P.format(212),
     23.0,     0, "96h LC50", "Chironomus riparius",  P.format(212),
     1.2,   0, "Anas platyrhynchos (mallard duck)",       P.format(212)),
    ("dimethoate",
     0.1,   0, 0.1,     0, P.format(244),
     1.29,     0, "96h LC50", "Chironomus dilutus",   P.format(244),
     1.0,   0, "Colinus virginianus (Northern Bobwhite)", P.format(244)),
    ("acephate",
     1.78,  0, 0.23,    1, P.format(9),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("phosmet",
     0.22,  0, 0.37,    0, P.format(521),
     None,     0, None,       None,                   None,
     7.5,   0, "Colinus virginianus (Northern Bobwhite)", P.format(521)),
    ("methidathion",
     0.13,  1, None,    0, P.format(456),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("naled",
     0.002, 1, None,    0, P.format(480),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("oxydemeton-methyl",
     0.175, 0, 0.2,     0, P.format(501),
     11.0,     0, "48h LC50", "Chironomus riparius",  P.format(501),
     0.97,  0, "Colinus virginianus (Northern Bobwhite)", P.format(501)),
    ("phorate",
     0.32,  0, 0.43,    1, P.format(519),
     81.0,     0, "96h LC50", "Chironomus riparius",  P.format(519),
     None,  0, None, None),
    ("azinphos-methyl",
     0.42,  0, None,    0, P.format(51),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    # ── Restricted neonics ───────────────────────────────────────────────────
    ("imidacloprid",
     0.081, 0, 0.0037,  0, P.format(397),
     55.0,     0, "96h LC50", "Chironomus riparius",  P.format(397),
     9.3,   0, "Colinus virginianus (Northern Bobwhite)", P.format(397)),
    ("clothianidin",
     0.044, 1, 0.004,   1, P.format(171),
     29.0,     0, "96h LC50", "Chironomus riparius",  P.format(171),
     56.8,  0, "Colinus virginianus (Northern Bobwhite)", P.format(171)),
    ("thiamethoxam",
     0.024, 1, 0.005,   1, P.format(631),
     55.3,     0, "96h LC50", "Chironomus dilutus",   P.format(631),
     29.4,  0, "Anas platyrhynchos (mallard duck)",       P.format(631)),
    ("dinotefuran",
     0.047, 1, 0.023,   1, P.format(1195),
     24.0,     0, "96h LC50", "Chironomus dilutus",   P.format(1195),
     None,  0, None, None),
    # ── Other neonics / next-gen systemics ───────────────────────────────────
    ("acetamiprid",
     8.09,  0, 14.53,   0, P.format(11),
     20.0,     0, "96h LC50", "Chironomus riparius",  P.format(11),
     9.5,   0, "Anas platyrhynchos (mallard duck)",       P.format(11)),
    ("thiacloprid",
     38.82, 0, 17.32,   0, P.format(630),
     10.8,     0, "96h LC50", "Chironomus dilutus",   P.format(630),
     3.73,  0, "Anas platyrhynchos (mallard duck)",       P.format(630)),
    ("nitenpyram",
     None,  0, None,    0, P.format(1612),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    ("sulfoxaflor",
     0.379, 0, 0.146,   0, P.format(1669),
     622.0,    0, "96h LC50", "Chironomus dilutus",   P.format(1669),
     25.9,  0, "Anas platyrhynchos (mallard duck)",       P.format(1669)),
    ("flupyradifurone",
     200.0, 1, 1.2,     0, P.format(2620),
     None,     0, None,       None,                   None,
     14.0,  0, "Colinus virginianus (Northern Bobwhite)", P.format(2620)),
    # ── Diamides ─────────────────────────────────────────────────────────────
    ("chlorantraniliprole",
     4.0,   1, 104.1,   1, P.format(1138),
     4.0,      0, "96h LC50", "Chironomus dilutus",   P.format(1138),
     10.1,  0, "Colinus virginianus (Northern Bobwhite)", P.format(1138)),
    ("cyantraniliprole",
     0.0934,1, 0.1055,  1, P.format(1662),
     719000.0, 0, "48h LC50", "Chironomus riparius",  P.format(1662),
     93.2,  0, "Colinus virginianus (Northern Bobwhite)", P.format(1662)),
    ("flubendiamide",
     200.0, 1, 200.0,   1, P.format(1132),
     1188.0,   0, "96h LC50", "Chironomus riparius",  P.format(1132),
     None,  0, None, None),
    ("tetraniliprole",
     None,  0, None,    0, P.format(3190),
     None,     0, None,       None,                   None,
     None,  0, None, None),
    # ── Carbamates ───────────────────────────────────────────────────────────
    ("carbaryl",
     0.14,  1, 0.21,    1, P.format(115),
     130.0,    0, "96h LC50", "Chironomus riparius",  P.format(115),
     30.0,  0, "Anas platyrhynchos (mallard duck)",       P.format(115)),
    ("methomyl",
     0.16,  0, 0.28,    0, P.format(458),
     32.0,     0, "96h LC50", "Chironomus riparius",  P.format(458),
     20.3,  0, "Colinus virginianus (Northern Bobwhite)", P.format(458)),
    ("oxamyl",
     0.47,  0, 0.38,    0, P.format(498),
     350.0,    0, "48h LC50", "Chironomus tentans",   P.format(498),
     1.5,   0, "Anas platyrhynchos (mallard duck)",       P.format(498)),
    ("carbofuran",
     0.036, 0, 0.038,   0, P.format(118),
     16.0,     0, "24h LC50", "Chironomus riparius",  P.format(118),
     None,  0, None, None),
    ("aldicarb",
     0.28,  1, 0.16,    1, P.format(19),
     4.0,      0, "24h LC50", "Chironomus riparius",  P.format(19),
     None,  0, None, None),
    # ── Spinosyns ────────────────────────────────────────────────────────────
    ("spinosad",
     0.0036,0, 0.057,   0, BP.format(596),
     1.6,      0, "28d NOEC", "Chironomus riparius",  BP.format(596),
     68.35, 0, "Anas platyrhynchos (mallard duck)",       BP.format(596)),
    ("spinetoram",
     0.024, 1, 0.14,    1, P.format(1144),
     0.75,     0, "28d NOEC", "Chironomus riparius",  P.format(1144),
     95.0,  0, "Anas platyrhynchos (mallard duck)",       P.format(1144)),
]

# Build lookup dict: chemname -> row (excluding chemname)
LOOKUP = {row[0]: row[1:] for row in DATA}


# ── 1. Update toxicity_lookup.csv ────────────────────────────────────────────

NEW_HEADER_COLS = [
    "bee_contact_ld50_ug_per_bee", "bee_contact_ceiling",
    "bee_oral_ld50_ug_per_bee",    "bee_oral_ceiling",
    "bee_source_url",
    "chironomid_ec50_ug_per_l",    "chironomid_ceiling",
    "chironomid_endpoint",         "chironomid_test_species",
    "chironomid_source_url",
    "avian_noec_repro_bwday",      "avian_noec_ceiling",
    "avian_noec_test_species",     "avian_noec_source_url",
]

def _fmt(v):
    """Format a value for the CSV: None → '', float → repr, else str."""
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v)


def update_csv():
    print("Updating toxicity_lookup.csv ...")
    lines_in = TOX_CSV.read_text(encoding="utf-8").splitlines()
    # Idempotency guard: skip if already updated
    if "bee_contact_ld50_ug_per_bee" in lines_in[0]:
        print("  CSV already has extended columns — skipping")
        return
    out = []
    for i, line in enumerate(lines_in):
        parts = line.rstrip("\n\r").split(",")
        if i == 0:
            # Header: insert new columns before notes (position 10)
            new_header = parts[:10] + NEW_HEADER_COLS + [",".join(parts[10:])]
            out.append(",".join(new_header))
            continue
        if len(parts) < 10:
            out.append(line)
            continue
        chemname = parts[0].strip()
        notes    = ",".join(parts[10:])  # preserve original notes
        ext = LOOKUP.get(chemname)
        if ext is None:
            print(f"  WARNING: {chemname!r} not in DATA dict — inserting blanks")
            new_cols = [""] * len(NEW_HEADER_COLS)
        else:
            new_cols = [_fmt(v) for v in ext]
        out.append(",".join(parts[:10] + new_cols + [notes]))
    TOX_CSV.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  Written {len(out)} lines (header + {len(out)-1} chemicals)")


# ── 2. ALTER TABLE ────────────────────────────────────────────────────────────

NEW_COLUMNS = [
    ("bee_contact_ld50",        "FLOAT"),
    ("bee_contact_ceiling",     "TINYINT(1) DEFAULT 0"),
    ("bee_oral_ld50",           "FLOAT"),
    ("bee_oral_ceiling",        "TINYINT(1) DEFAULT 0"),
    ("bee_source_url",          "VARCHAR(255)"),
    ("chironomid_ec50",         "FLOAT"),
    ("chironomid_ceiling",      "TINYINT(1) DEFAULT 0"),
    ("chironomid_endpoint",     "VARCHAR(40)"),
    ("chironomid_test_species", "VARCHAR(80)"),
    ("chironomid_source_url",   "VARCHAR(255)"),
    ("avian_noec_repro",        "FLOAT"),
    ("avian_noec_ceiling",      "TINYINT(1) DEFAULT 0"),
    ("avian_noec_test_species", "VARCHAR(80)"),
    ("avian_noec_source_url",   "VARCHAR(255)"),
]

def alter_table(conn):
    print("ALTERing toxicity table ...")
    cur = conn.cursor()
    # Check which columns already exist
    cur.execute("SHOW COLUMNS FROM toxicity")
    existing = {row[0] for row in cur.fetchall()}
    added = 0
    for col, coltype in NEW_COLUMNS:
        if col in existing:
            print(f"  {col}: already exists, skipping")
        else:
            cur.execute(f"ALTER TABLE toxicity ADD COLUMN {col} {coltype}")
            print(f"  {col}: added")
            added += 1
    conn.commit()
    cur.close()
    print(f"  {added} columns added")


# ── 3. UPDATE rows ────────────────────────────────────────────────────────────

UPDATE_SQL = """
UPDATE toxicity SET
    bee_contact_ld50        = %s,
    bee_contact_ceiling     = %s,
    bee_oral_ld50           = %s,
    bee_oral_ceiling        = %s,
    bee_source_url          = %s,
    chironomid_ec50         = %s,
    chironomid_ceiling      = %s,
    chironomid_endpoint     = %s,
    chironomid_test_species = %s,
    chironomid_source_url   = %s,
    avian_noec_repro        = %s,
    avian_noec_ceiling      = %s,
    avian_noec_test_species = %s,
    avian_noec_source_url   = %s
WHERE chemname = %s
""".strip()


def update_rows(conn):
    print("Updating toxicity rows ...")
    cur = conn.cursor()
    updated = 0
    not_found = []
    for row in DATA:
        chemname = row[0]
        params   = list(row[1:]) + [chemname]
        cur.execute(UPDATE_SQL, params)
        if cur.rowcount:
            updated += 1
        else:
            not_found.append(chemname)
    conn.commit()
    cur.close()
    print(f"  {updated} rows updated")
    if not_found:
        print(f"  WARNING: not found in DB: {not_found}")


# ── 4. Verify ─────────────────────────────────────────────────────────────────

def verify(conn):
    print("Verifying ...")
    cur = conn.cursor()
    cur.execute("""
        SELECT chemname,
               bee_contact_ld50, bee_oral_ld50,
               chironomid_ec50, avian_noec_repro
        FROM toxicity
        ORDER BY chemname
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"  {'chemname':<25} {'bee_c':>8} {'bee_o':>8} {'chiro':>10} {'noec':>8}")
    for r in rows:
        name, bc, bo, ch, noec = r
        print(f"  {name:<25} {str(bc):>8} {str(bo):>8} {str(ch):>10} {str(noec):>8}")
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    update_csv()

    conn = mysql.connector.connect(**DB_CFG)
    try:
        alter_table(conn)
        update_rows(conn)
        verify(conn)
    finally:
        conn.close()

    print("\nDone.")
