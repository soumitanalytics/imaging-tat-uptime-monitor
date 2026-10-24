// n8n node: "Validate Studies"  (Code node)
// Settings: Mode = "Run Once for All Items", Language = JavaScript
//
// Receives ALL study rows at once (needed for duplicate detection), tags each row
// with every problem found, normalises modality names, converts the three timestamp
// formats to YYYY-MM-DD HH:MM and calculates turnaround time (TAT) in minutes.
// Rows are never deleted here: each row leaves with the reason it failed.

// Hardcoded for the prototype. In production, check against the equipment master table.
const VALID_EQUIPMENT = ['XR-01', 'XR-02', 'CT-01', 'CT-02', 'MR-01', 'MR-02', 'US-01', 'US-02'];
const CANONICAL = ['X-Ray', 'CT', 'MRI', 'Ultrasound'];
// key = lower-case value with spaces and hyphens removed
const MODALITY_MAP = { xray: 'X-Ray', ct: 'CT', ctscan: 'CT', mri: 'MRI', usg: 'Ultrasound', ultrasound: 'Ultrasound' };

function pad(n) { return String(n).padStart(2, '0'); }

// Returns { ms, text } or null if the value is blank, in an unknown format, or not a real date/time.
function parseTs(value) {
  const s = (value === undefined || value === null) ? '' : String(value).trim();
  let y, mo, d, h, mi, m;
  if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/))) {            // 2026-07-14 09:30
    y = +m[1]; mo = +m[2]; d = +m[3]; h = +m[4]; mi = +m[5];
  } else if ((m = s.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/))) {   // 14/07/2026 09:30  (day first)
    d = +m[1]; mo = +m[2]; y = +m[3]; h = +m[4]; mi = +m[5];
  } else if ((m = s.match(/^(\d{2})-(\d{2})-(\d{4}) (\d{1,2}):(\d{2}) (AM|PM)$/i))) { // 07-14-2026 09:30 AM (month first)
    mo = +m[1]; d = +m[2]; y = +m[3]; mi = +m[5];
    const h12 = +m[4];
    if (h12 < 1 || h12 > 12) return null;
    h = h12 % 12;
    if (m[6].toUpperCase() === 'PM') h += 12;
  } else {
    return null;
  }
  const ms = Date.UTC(y, mo - 1, d, h, mi);
  const t = new Date(ms);
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d ||
      t.getUTCHours() !== h || t.getUTCMinutes() !== mi) return null;   // e.g. 31/02 or 25:00
  return { ms, text: y + '-' + pad(mo) + '-' + pad(d) + ' ' + pad(h) + ':' + pad(mi) };
}

const seen = new Set();
const out = [];

for (const item of $input.all()) {
  const row = item.json;
  const issues = [];

  // RULE 1: duplicate StudyID (flag the second and later occurrences)
  const id = String(row.StudyID === undefined ? '' : row.StudyID).trim();
  if (seen.has(id)) issues.push('Duplicate StudyID');
  seen.add(id);

  // RULE 2: unknown equipment
  const eq = String(row.EquipmentID === undefined ? '' : row.EquipmentID).trim();
  if (!VALID_EQUIPMENT.includes(eq)) issues.push('Unknown equipment: ' + (eq || '(blank)'));

  // RULE 3: missing technician (n8n drops blank CSV cells, so the field may be undefined)
  if (!row.TechnicianID || String(row.TechnicianID).trim() === '') issues.push('Missing technician');

  // RULE 4 and 5: timestamps
  const scan = parseTs(row.ScanTime);
  if (!scan) issues.push('Unreadable scan time: ' + String(row.ScanTime));
  const reportRaw = (row.ReportTime === undefined || row.ReportTime === null) ? '' : String(row.ReportTime).trim();
  let report = null;
  if (reportRaw === '') {
    issues.push('Missing report time');
  } else {
    report = parseTs(reportRaw);
    if (!report) issues.push('Unreadable report time: ' + reportRaw);
    else if (scan && report.ms < scan.ms) issues.push('Report before scan');
  }

  // NORMALISE (not a rejection): modality names
  const rawModality = (row.Modality === undefined || row.Modality === null) ? '' : String(row.Modality);
  const wasVariant = !CANONICAL.includes(rawModality);
  const modalityClean = MODALITY_MAP[rawModality.toLowerCase().replace(/[\s-]/g, '')] || null;
  if (!modalityClean) issues.push('Unknown modality: ' + (rawModality || '(blank)'));

  const isValid = issues.length === 0;
  out.push({
    json: {
      ...row,
      Modality_clean: modalityClean,
      ScanTime_clean: scan ? scan.text : null,
      ReportTime_clean: report ? report.text : null,
      TAT_minutes: (isValid && scan && report) ? Math.round((report.ms - scan.ms) / 60000) : null,
      modality_normalised: wasVariant,
      issues: issues.join('; '),
      issue_count: issues.length,
      is_valid: isValid
    }
  });
}

return out;
