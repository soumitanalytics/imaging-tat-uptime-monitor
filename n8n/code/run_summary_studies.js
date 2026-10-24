// n8n node: "Run Summary"  (Code node)
// Settings: Mode = "Run Once for All Items", Language = JavaScript
// Connect it to the output of "Validate Studies", in parallel with the If node.
// Produces ONE summary item per run.

const rows = $input.all().map(i => i.json);
const total = rows.length;
const clean = rows.filter(r => r.is_valid).length;
const has = (text) => rows.filter(r => (r.issues || '').includes(text)).length;

return [{
  json: {
    run_time: new Date().toISOString(),
    rows_received: total,
    rows_clean: clean,
    rows_flagged: total - clean,
    pct_clean: total ? Math.round((clean / total) * 1000) / 10 : 0,
    duplicate_studyid: has('Duplicate StudyID'),
    unknown_equipment: has('Unknown equipment'),
    missing_technician: has('Missing technician'),
    missing_report_time: has('Missing report time'),
    report_before_scan: has('Report before scan'),
    unreadable_timestamps: has('Unreadable'),
    unknown_modality: has('Unknown modality'),
    modality_normalised: rows.filter(r => r.modality_normalised).length
  }
}];
