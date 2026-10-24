"""Independently re-checks the generated CSVs against the answer key.

It re-reads the CSV files from disk, applies the validation rules from docs/answer_key.md
from scratch (without using any generator internals), and compares the result with
docs/answer_key_details.csv. Run from the repo root:  python scripts/verify_answer_key.py
"""
import csv
import os
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
DOCS = os.path.join(HERE, "..", "docs")

FORMATS = ["%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%m-%d-%Y %I:%M %p"]
CANON = {"X-Ray", "CT", "MRI", "Ultrasound"}
NORM = {"xray": "X-Ray", "ct": "CT", "ctscan": "CT", "mri": "MRI", "usg": "Ultrasound", "ultrasound": "Ultrasound"}
PERIOD_HOURS = 92 * 24


def parse_ts(s):
    s = (s or "").strip()
    for f in FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def normalise_modality(m):
    return NORM[m.lower().replace(" ", "").replace("-", "")]


def shift_of(h):
    return "Day" if 7 <= h < 15 else "Evening" if 15 <= h < 23 else "Night"


def read(name):
    with open(os.path.join(DATA, name), newline="") as fh:
        return list(csv.DictReader(fh))


def check():
    master = {r["EquipmentID"] for r in read("equipment_master.csv")}
    studies, downtime = read("study_log.csv"), read("downtime_log.csv")
    flags = []          # (dataset, id, rule)

    # ---- studies
    seen, clean_studies, variant_rows = set(), [], 0
    for r in studies:
        rules, sid = [], r["StudyID"]
        if sid in seen:
            rules.append("duplicate_studyid")
        seen.add(sid)
        if r["EquipmentID"].strip() not in master:
            rules.append("unknown_equipment")
        if not r["TechnicianID"].strip():
            rules.append("missing_technician")
        scan = parse_ts(r["ScanTime"])
        assert scan is not None, f"unparseable scan time in {sid}"
        if not r["ReportTime"].strip():
            rules.append("missing_report_time")
            rep = None
        else:
            rep = parse_ts(r["ReportTime"])
            assert rep is not None, f"unparseable report time in {sid}"
            if rep < scan:
                rules.append("report_before_scan")
        if r["Modality"] not in CANON:
            variant_rows += 1
            flags.append(("study", sid, "modality_variant"))
        for rule in rules:
            flags.append(("study", sid, rule))
        if not rules:
            clean_studies.append(dict(id=sid, mod=normalise_modality(r["Modality"]), eq=r["EquipmentID"],
                                      scan=scan, tat=(rep - scan).total_seconds() / 60))

    # ---- downtime
    valid = []
    for r in downtime:
        rules = []
        if r["EquipmentID"].strip() not in master:
            rules.append("unknown_equipment")
        st = parse_ts(r["StartTime"])
        assert st is not None
        if not r["EndTime"].strip():
            rules.append("missing_end_time")
            en = None
        else:
            en = parse_ts(r["EndTime"])
            assert en is not None
            if en < st:
                rules.append("end_before_start")
        for rule in rules:
            flags.append(("downtime", r["DowntimeID"], rule))
        if not rules:
            valid.append(dict(id=r["DowntimeID"], eq=r["EquipmentID"], start=st, end=en))
    clean_dt = []
    by_eq = {}
    for e in valid:
        by_eq.setdefault(e["eq"], []).append(e)
    for eq, evs in by_eq.items():
        prev_end = None
        for e in sorted(evs, key=lambda x: x["start"]):
            if prev_end is not None and e["start"] < prev_end:
                flags.append(("downtime", e["id"], "overlap"))
            else:
                clean_dt.append(e)
                prev_end = e["end"]
    return dict(flags=flags, studies=studies, downtime=downtime, clean_studies=clean_studies,
                clean_dt=clean_dt, variant_rows=variant_rows, master=sorted(master))


def reference_stats(res):
    cs, cd = res["clean_studies"], res["clean_dt"]
    by_eq = {}
    for e in cd:
        by_eq.setdefault(e["eq"], []).append(e)

    def post(s):
        return any(e["end"] <= s["scan"] < e["end"] + timedelta(hours=24) for e in by_eq.get(s["eq"], []))

    def mean(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 1) if xs else None

    out = {"overall": mean(s["tat"] for s in cs), "n": len(cs)}
    out["by_modality"] = {m: (mean(s["tat"] for s in cs if s["mod"] == m), sum(1 for s in cs if s["mod"] == m))
                          for m in ["X-Ray", "Ultrasound", "CT", "MRI"]}
    out["by_shift"] = {sh: (mean(s["tat"] for s in cs if shift_of(s["scan"].hour) == sh),
                            sum(1 for s in cs if shift_of(s["scan"].hour) == sh))
                       for sh in ["Day", "Evening", "Night"]}
    out["mr"] = {eq: mean(s["tat"] for s in cs if s["eq"] == eq) for eq in ["MR-01", "MR-02"]}
    out["post_down"] = (mean(s["tat"] for s in cs if post(s)), sum(1 for s in cs if post(s)))
    out["not_post_down"] = (mean(s["tat"] for s in cs if not post(s)), sum(1 for s in cs if not post(s)))
    hrs = {}
    for e in cd:
        hrs[e["eq"]] = hrs.get(e["eq"], 0) + (e["end"] - e["start"]).total_seconds() / 3600
    out["downtime_hours"] = {eq: round(h, 1) for eq, h in sorted(hrs.items())}
    out["total_downtime_hours"] = round(sum(hrs.values()), 1)
    out["uptime_pct"] = {eq: round(100 * (1 - h / PERIOD_HOURS), 1) for eq, h in sorted(hrs.items())}
    return out


if __name__ == "__main__":
    res = check()
    mine = set(res["flags"])
    with open(os.path.join(DOCS, "answer_key_details.csv"), newline="") as fh:
        planted = {(r["dataset"], r["id"], r["rule"]) for r in csv.DictReader(fh)}
    print("rows: studies", len(res["studies"]), "| downtime", len(res["downtime"]))
    print("flags found by independent check:", len(mine), "| planted:", len(planted))
    print("MISSING from check:", sorted(planted - mine))
    print("EXTRA in check:    ", sorted(mine - planted))
    print("MATCH" if mine == planted else "MISMATCH")
