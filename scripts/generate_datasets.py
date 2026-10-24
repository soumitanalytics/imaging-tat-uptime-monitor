"""Generate synthetic imaging-department datasets for the n8n + Power BI project.

Creates three files in ../data:
  equipment_master.csv  - 8 imaging units (the lookup list for valid EquipmentIDs)
  study_log.csv         - one row per imaging study (scan time, report time, ...)
  downtime_log.csv      - one row per equipment downtime event

Deliberately planted problems are documented in ../docs/answer_key.md and listed
row by row in ../docs/answer_key_details.csv.

All data is synthetic. No real patients, staff or hospital. Seeded for reproducibility.
Run from the repo root:  python scripts/generate_datasets.py
"""
import csv
import os
import random
from datetime import datetime, timedelta

SEED = 2026
random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
DOCS_DIR = os.path.join(HERE, "..", "docs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)

START = datetime(2026, 7, 1)
END = datetime(2026, 10, 1)          # exclusive
N_STUDIES = 600

EQUIPMENT = [
    ("XR-01", "X-Ray", "Room 1"), ("XR-02", "X-Ray", "Room 2"),
    ("CT-01", "CT", "Room 3"),    ("CT-02", "CT", "Room 4"),
    ("MR-01", "MRI", "Room 5"),   ("MR-02", "MRI", "Room 6"),
    ("US-01", "Ultrasound", "Room 7"), ("US-02", "Ultrasound", "Room 8"),
]
MOD_UNITS = {}
for eid, mod, _ in EQUIPMENT:
    MOD_UNITS.setdefault(mod, []).append(eid)

TECHNICIANS = [f"TECH-{i:02d}" for i in range(1, 7)]

FMT_ISO = "%Y-%m-%d %H:%M"
FMT_DMY = "%d/%m/%Y %H:%M"
FMT_MDY = "%m-%d-%Y %I:%M %p"

BAD_EQUIP_STUDY = ["XR-09", "CT-03", "MR-03", "US-07", "CT01", "XR-1"]
BAD_EQUIP_DT = ["XR-09", "CT-03", "MR-03"]
VARIANTS = {
    "X-Ray": ["xray", "X Ray", "x-ray", "XRAY"],
    "CT": ["CT Scan", "ct", "Ct "],
    "MRI": ["mri", "MRI ", "Mri"],
    "Ultrasound": ["USG", "ultrasound", "Ultra Sound"],
}

planted = []   # (dataset, id, rule)


def rd(dt):
    return dt.replace(second=0, microsecond=0)


def pick_fmt():
    r = random.random()
    return FMT_ISO if r < 0.5 else FMT_DMY if r < 0.8 else FMT_MDY


def shift_of(hour):
    return "Day" if 7 <= hour < 15 else "Evening" if 15 <= hour < 23 else "Night"


# ---------------------------------------------------------------- downtime (true events)
REASONS_GENERAL = [
    ("Scheduled maintenance", (2, 6), 0.30), ("Calibration", (1, 3), 0.15),
    ("Software update", (1, 4), 0.15), ("Hardware fault", (6, 48), 0.25),
    ("Power outage", (1, 5), 0.10),
]
REASON_MRI_EXTRA = ("Cooling system issue", (24, 72), 0.10)

events = []
for eid, mod, _ in EQUIPMENT:
    reasons = REASONS_GENERAL + ([REASON_MRI_EXTRA] if mod == "MRI" else [])
    cursor = START
    while True:
        cursor += timedelta(days=random.randint(6, 16), hours=random.randint(0, 23),
                            minutes=random.randint(0, 59))
        reason, (lo, hi), _w = random.choices(reasons, weights=[r[2] for r in reasons])[0]
        start = rd(cursor)
        end = rd(start + timedelta(hours=random.uniform(lo, hi)))
        if end >= END:
            break
        events.append(dict(equip=eid, start=start, end=end, reason=reason, tag=None))
        cursor = end

# plant 3 overlapping events: a short event nested inside a long one (different equipment each)
cands = [e for e in events if (e["end"] - e["start"]) >= timedelta(hours=4)]
random.shuffle(cands)
bases, used = [], set()
for e in cands:
    if e["equip"] in used:
        continue
    bases.append(e)
    used.add(e["equip"])
    if len(bases) == 3:
        break
for b in bases:
    dur = b["end"] - b["start"]
    s = rd(b["start"] + dur * 0.25)
    e2 = rd(s + min(timedelta(hours=2), dur * 0.5))
    events.append(dict(equip=b["equip"], start=s, end=e2,
                       reason=random.choice(["Software update", "Calibration"]), tag="overlap"))
    b["tag"] = "overlap_base"

events.sort(key=lambda e: e["start"])
for i, e in enumerate(events, 1):
    e["id"] = f"DT-{i:04d}"

by_equip = {}
for e in events:
    by_equip.setdefault(e["equip"], []).append(e)


def is_down(eq, t):
    return any(e["start"] <= t < e["end"] for e in by_equip.get(eq, []))


def after_down(eq, t):
    return any(e["end"] <= t < e["end"] + timedelta(hours=24) for e in by_equip.get(eq, []))


# ---------------------------------------------------------------- studies (true values)
MODS = ["X-Ray", "Ultrasound", "CT", "MRI"]
MOD_W = [0.40, 0.25, 0.22, 0.13]
TAT = {"X-Ray": (25, 10, 8), "Ultrasound": (40, 15, 15), "CT": (60, 25, 20), "MRI": (110, 40, 30)}


def rand_scan_time():
    day = random.randrange((END - START).days)
    band = random.choices(["day", "eve", "night"], weights=[0.70, 0.25, 0.05])[0]
    hour = (random.randint(7, 14) if band == "day" else random.randint(15, 22) if band == "eve"
            else random.choice([23, 0, 1, 2, 3, 4, 5, 6]))
    return START + timedelta(days=day, hours=hour, minutes=random.randint(0, 59))


studies = []
for _ in range(N_STUDIES):
    mod = random.choices(MODS, weights=MOD_W)[0]
    for _attempt in range(100):
        eq = random.choice(MOD_UNITS[mod])
        t = rand_scan_time()
        if not is_down(eq, t):
            break
    else:
        raise RuntimeError("could not place study")
    mean, sd, mn = TAT[mod]
    tat = max(mn, random.gauss(mean, sd))
    if shift_of(t.hour) == "Night":
        tat *= 1.5
    if eq == "MR-02":
        tat *= 1.25
    if after_down(eq, t):
        tat *= 1.4
    studies.append(dict(mod=mod, eq=eq, scan=t, report=t + timedelta(minutes=int(round(tat))),
                        tech=random.choice(TECHNICIANS), pt=f"PT-{random.randint(10000, 99999)}"))
studies.sort(key=lambda s: s["scan"])
for i, s in enumerate(studies, 1):
    s["id"] = f"ST-{i:06d}"
    s["eq_out"], s["tech_out"], s["mod_out"] = s["eq"], s["tech"], s["mod"]
    s["report_out"] = s["report"]

# ---------------------------------------------------------------- plant study errors (disjoint rows)
idx = list(range(N_STUDIES))
random.shuffle(idx)
dup_src, rbs, unk, mt, mr = idx[0:8], idx[8:18], idx[18:27], idx[27:39], idx[39:45]

for i in rbs:
    s = studies[i]
    s["report_out"] = s["scan"] - timedelta(minutes=random.randint(5, 120))
    planted.append(("study", s["id"], "report_before_scan"))
for i in unk:
    s = studies[i]
    s["eq_out"] = random.choice(BAD_EQUIP_STUDY)
    planted.append(("study", s["id"], "unknown_equipment"))
for i in mt:
    studies[i]["tech_out"] = ""
    planted.append(("study", studies[i]["id"], "missing_technician"))
for i in mr:
    studies[i]["report_out"] = None
    planted.append(("study", studies[i]["id"], "missing_report_time"))
for i in random.sample(range(N_STUDIES), 40):
    s = studies[i]
    s["mod_out"] = random.choice(VARIANTS[s["mod"]])
    planted.append(("study", s["id"], "modality_variant"))
for i in dup_src:
    planted.append(("study", studies[i]["id"], "duplicate_studyid"))

rows = []
for s in studies:
    f = pick_fmt()
    rows.append([s["id"], s["pt"], s["mod_out"], s["eq_out"], s["tech_out"],
                 s["scan"].strftime(f),
                 "" if s["report_out"] is None else s["report_out"].strftime(f)])
keyed = [(float(i), r) for i, r in enumerate(rows)]
for i in dup_src:
    keyed.append((i + random.uniform(0.01, 25), list(rows[i])))   # exact extra copy, later in file
keyed.sort(key=lambda kr: kr[0])

with open(os.path.join(DATA_DIR, "study_log.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["StudyID", "PatientRef", "Modality", "EquipmentID", "TechnicianID", "ScanTime", "ReportTime"])
    w.writerows([r for _, r in keyed])

# ---------------------------------------------------------------- plant downtime errors (disjoint rows)
pool = [e for e in events if e["tag"] is None]
random.shuffle(pool)
ebs, dunk, dmiss = pool[0:4], pool[4:7], pool[7:10]
for e in events:
    e["eq_out"] = e["equip"]
    e["start_out"], e["end_out"] = e["start"], e["end"]
    if e["tag"] == "overlap":
        planted.append(("downtime", e["id"], "overlap"))
for e in ebs:
    e["start_out"], e["end_out"] = e["end"], e["start"]       # swapped: end before start
    planted.append(("downtime", e["id"], "end_before_start"))
for e in dunk:
    e["eq_out"] = random.choice(BAD_EQUIP_DT)
    planted.append(("downtime", e["id"], "unknown_equipment"))
for e in dmiss:
    e["end_out"] = None
    planted.append(("downtime", e["id"], "missing_end_time"))

with open(os.path.join(DATA_DIR, "downtime_log.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["DowntimeID", "EquipmentID", "StartTime", "EndTime", "Reason"])
    for e in events:
        f = pick_fmt()
        w.writerow([e["id"], e["eq_out"], e["start_out"].strftime(f),
                    "" if e["end_out"] is None else e["end_out"].strftime(f), e["reason"]])

with open(os.path.join(DATA_DIR, "equipment_master.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["EquipmentID", "Modality", "Room"])
    w.writerows(EQUIPMENT)

with open(os.path.join(DOCS_DIR, "answer_key_details.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["dataset", "id", "rule"])
    w.writerows(sorted(planted))

print("studies in file:", len(keyed), "| downtime events in file:", len(events))
