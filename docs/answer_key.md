# Answer key: Imaging TAT and Equipment Uptime datasets

All data is synthetic. Read parts 1 to 4 before you build the n8n validation. **Part 5 holds reference results: keep it closed until your Power BI measures are written**, then use it to reconcile your numbers.

Row-by-row detail of every planted problem is in `answer_key_details.csv`. Run `python scripts/verify_answer_key.py` to re-check that the CSVs and this key agree.

## 1. The files

| File | Rows | Columns |
|---|---|---|
| `equipment_master.csv` | 8 | EquipmentID, Modality, Room |
| `study_log.csv` | 608 | StudyID, PatientRef, Modality, EquipmentID, TechnicianID, ScanTime, ReportTime |
| `downtime_log.csv` | 57 | DowntimeID, EquipmentID, StartTime, EndTime, Reason |

Period covered: 1 July 2026 to 30 September 2026 (92 days).

## 2. Validation rules to implement in n8n

**Study log**

| Rule | Definition | Action |
|---|---|---|
| `duplicate_studyid` | StudyID already seen earlier in the file (the repeat is an exact copy) | flag the second and later occurrences |
| `unknown_equipment` | EquipmentID not in `equipment_master.csv` | flag |
| `missing_technician` | TechnicianID blank | flag |
| `missing_report_time` | ReportTime blank | flag |
| `report_before_scan` | ReportTime earlier than ScanTime | flag |
| `modality_variant` | Modality is not exactly `X-Ray`, `CT`, `MRI` or `Ultrasound` | normalise, do not reject |

**Downtime log**

| Rule | Definition | Action |
|---|---|---|
| `unknown_equipment` | EquipmentID not in the master list | flag |
| `missing_end_time` | EndTime blank | flag |
| `end_before_start` | EndTime earlier than StartTime | flag |
| `overlap` | Event starts before the previous valid event on the same equipment has ended (sort by StartTime per equipment) | flag the later event |

Evaluate `overlap` only on rows that passed the other three downtime checks.

## 3. Expected counts

**Study log:** 608 rows in file, **45 flagged**, **563 clean**. In this dataset every flagged row has exactly one rejection reason, so the reasons add up to the flagged total.

| Rule | Rows |
|---|---|
| duplicate_studyid | 8 |
| unknown_equipment | 9 |
| missing_technician | 12 |
| missing_report_time | 6 |
| report_before_scan | 10 |
| **Total flagged** | 45 |
| modality_variant (normalised, not rejected) | 40 |

**Downtime log:** 57 rows in file, **13 flagged**, **44 clean**.

| Rule | Rows |
|---|---|
| unknown_equipment | 3 |
| missing_end_time | 3 |
| end_before_start | 4 |
| overlap | 3 |
| **Total flagged** | 13 |

If your n8n counts differ from these, find the rule that differs before you touch Power BI.

## 4. Normalisation and timestamps

**Modality.** Lowercase the value, remove spaces and hyphens, then map:

| Cleaned value | Canonical modality |
|---|---|
| xray | X-Ray |
| ct, ctscan | CT |
| mri | MRI |
| usg, ultrasound | Ultrasound |

**Timestamps.** Both log files mix three formats, and every value parses with one of them:

| Format | Example | How to recognise it |
|---|---|---|
| YYYY-MM-DD HH:MM | 2026-07-14 09:30 | year first, 24-hour clock |
| DD/MM/YYYY HH:MM | 14/07/2026 09:30 | slashes, 24-hour clock |
| MM-DD-YYYY HH:MM AM/PM | 07-14-2026 09:30 AM | dashes with year last, AM/PM |

Assumption: the separator tells you the order (slashes are day first, dashes with the year last are month first). A real file would not tell you, so confirm the convention with the data owner. Convert everything to `YYYY-MM-DD HH:MM` before calculating anything.

## 5. Reference results (spoilers)

These were measured on the **clean** rows only: 563 studies and 44 downtime events, modality names normalised. TAT is ReportTime minus ScanTime, in minutes. Shifts are by scan time: Day 07:00 to 14:59, Evening 15:00 to 22:59, Night 23:00 to 06:59.

Overall average TAT: **53.4 min** across 563 studies.

| Modality | Studies | Avg TAT (min) |
|---|---|---|
| X-Ray | 247 | 26.7 |
| Ultrasound | 131 | 44.1 |
| CT | 113 | 68.8 |
| MRI | 72 | 137.8 |

| Shift | Studies | Avg TAT (min) |
|---|---|---|
| Day | 399 | 48.7 |
| Evening | 131 | 60.9 |
| Night | 33 | 80.8 |

**Effects built into the data** (so you can check your dashboard finds them):
- Night-shift studies take about 1.5 times as long. No Evening effect was built in. Evening still looks slower than Day in the raw numbers, partly because it has a larger share of CT studies and partly through random variation, so do not read it as a real Evening effect. Compare within a modality before drawing conclusions.
- MR-02 is about 25% slower than MR-01: average TAT 150.0 vs 116.2 min.
- Studies in the 24 hours after a downtime event ends on the same unit take about 1.4 times as long: 70.7 min (34 studies) vs 52.3 min (529 studies). This raw comparison mixes modalities, so it is only a rough check.

**Downtime** (clean events only, period of 2,208 hours = 92 days x 24 h). Total downtime: **667.4 hours**.

| Equipment | Downtime hours | Uptime % |
|---|---|---|
| CT-01 | 88.4 | 96.0 |
| CT-02 | 41.4 | 98.1 |
| MR-01 | 163.2 | 92.6 |
| MR-02 | 94.8 | 95.7 |
| US-01 | 140.3 | 93.6 |
| US-02 | 29.1 | 98.7 |
| XR-01 | 55.4 | 97.5 |
| XR-02 | 54.8 | 97.5 |

Your numbers will differ if you include flagged rows or treat blank end times as "still down", so write down which choice you made.
