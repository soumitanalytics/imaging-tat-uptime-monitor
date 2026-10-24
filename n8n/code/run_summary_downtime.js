// n8n node: "Run Summary"  (Code node)
// Settings: Mode = "Run Once for All Items", Language = JavaScript
// Connect it to the output of "Validate Downtime", in parallel with the If node.

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
    unknown_equipment: has('Unknown equipment'),
    missing_end_time: has('Missing end time'),
    end_before_start: has('End before start'),
    overlapping_event: has('Overlapping event'),
    unreadable_timestamps: has('Unreadable')
  }
}];
