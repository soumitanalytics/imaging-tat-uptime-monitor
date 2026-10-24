// n8n node: "Validate Downtime"  (Code node)
// Settings: Mode = "Run Once for All Items", Language = JavaScript
//
// Receives ALL downtime events at once (the overlap rule compares events on the same
// machine, so it needs to see every row). Tags each row with every problem found and
// converts the three timestamp formats to YYYY-MM-DD HH:MM. Rows are never deleted.

// Hardcoded for the prototype. In production, check against the equipment master table.
const VALID_EQUIPMENT = ['XR-01', 'XR-02', 'CT-01', 'CT-02', 'MR-01', 'MR-02', 'US-01', 'US-02'];

function pad(n) { return String(n).padStart(2, '0'); }

// Returns { ms, text } or null if the value is blank, in an unknown format, or not a real date/time.
function parseTs(value) {
  const s = (value === undefined || value === null) ? '' : String(value).trim();
  let y, mo, d, h, mi, m;
  if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/))) {            // 2026-07-14 09:30
    y = +m[1]; mo = +m[2]; d = +m[3]; h = +m[4]; mi = +m[5];
  } else if ((m = s.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/))) {   // 14/07/2026 09:30 (day first)
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
      t.getUTCHours() !== h || t.getUTCMinutes() !== mi) return null;
  return { ms, text: y + '-' + pad(mo) + '-' + pad(d) + ' ' + pad(h) + ':' + pad(mi) };
}

// PASS 1: row-by-row checks
const records = $input.all().map(item => {
  const row = item.json;
  const issues = [];

  // RULE 1: unknown equipment
  const eq = String(row.EquipmentID === undefined ? '' : row.EquipmentID).trim();
  if (!VALID_EQUIPMENT.includes(eq)) issues.push('Unknown equipment: ' + (eq || '(blank)'));

  // RULES 2 and 3: timestamps (n8n drops blank CSV cells, so EndTime may be undefined)
  const start = parseTs(row.StartTime);
  if (!start) issues.push('Unreadable start time: ' + String(row.StartTime));
  const endRaw = (row.EndTime === undefined || row.EndTime === null) ? '' : String(row.EndTime).trim();
  let end = null;
  if (endRaw === '') {
    issues.push('Missing end time');
  } else {
    end = parseTs(endRaw);
    if (!end) issues.push('Unreadable end time: ' + endRaw);
    else if (start && end.ms < start.ms) issues.push('End before start');
  }
  return { row, eq, start, end, issues };
});

// PASS 2: overlap check, only on rows that passed pass 1.
// Per machine, sort by start time. An event that starts before the previous valid
// event has ended is flagged (the later one).
const byEquipment = {};
for (const r of records) {
  if (r.issues.length === 0) (byEquipment[r.eq] = byEquipment[r.eq] || []).push(r);
}
for (const eq of Object.keys(byEquipment)) {
  const list = byEquipment[eq].sort((a, b) => a.start.ms - b.start.ms);
  let prevEnd = null;
  for (const r of list) {
    if (prevEnd !== null && r.start.ms < prevEnd) r.issues.push('Overlapping event on ' + eq);
    else prevEnd = r.end.ms;
  }
}

return records.map(r => {
  const isValid = r.issues.length === 0;
  return {
    json: {
      ...r.row,
      StartTime_clean: r.start ? r.start.text : null,
      EndTime_clean: r.end ? r.end.text : null,
      Duration_hours: isValid ? Math.round(((r.end.ms - r.start.ms) / 3600000) * 100) / 100 : null,
      issues: r.issues.join('; '),
      issue_count: r.issues.length,
      is_valid: isValid
    }
  };
});
