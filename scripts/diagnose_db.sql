-- sqlite3 -header -column results/archive/paper1_FINAL_DATA_locked_v4_20260913.db < scripts/diagnose_db.sql
.print '== 1. attempt_num base (is first attempt 0 or 1?)'
SELECT MIN(attempt_num) AS min_attempt, MAX(attempt_num) AS max_attempt FROM node_attempts;

.print '== 2. markdown_wrap_revalidation coverage and outcome values'
SELECT COUNT(*) AS rows FROM markdown_wrap_revalidation;
SELECT outcome, compound_category, COUNT(*) AS n
FROM markdown_wrap_revalidation GROUP BY 1, 2 ORDER BY n DESC;

.print '== 3. hand_labels: size, nulls, and which label ground_truth holds'
SELECT COUNT(*) AS n, SUM(ground_truth IS NULL) AS null_gt FROM hand_labels;
SELECT h.attempt_id, h.classifier_label, a.primary_category AS current, h.ground_truth, h.notes
FROM hand_labels h JOIN node_attempts a ON a.id = h.attempt_id
WHERE h.attempt_id IN (987, 2817, 2833, 1208);
SELECT SUM(h.ground_truth = a.primary_category) AS agree_current,
       SUM(h.ground_truth = h.classifier_label) AS agree_stored
FROM hand_labels h JOIN node_attempts a ON a.id = h.attempt_id;

.print '== 4. error_details shape for a length_bound failure (need loc, input, ctx)'
SELECT substr(error_details, 1, 600) AS sample FROM node_attempts
WHERE primary_category = 'length_bound' LIMIT 1;

.print '== 5. dataset / prompt_variant NULLs'
SELECT SUM(dataset IS NULL) AS null_dataset, SUM(prompt_variant IS NULL) AS null_variant FROM runs;

.print '== 6. runs with zero attempts (would inflate pilot run counts)'
SELECT COUNT(*) AS runs_without_attempts FROM runs r
WHERE NOT EXISTS (SELECT 1 FROM node_attempts a WHERE a.run_id = r.run_id);