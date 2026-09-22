# Review-3 audit

DB: `results/archive/paper1_FINAL_DATA_locked_v4_20260913.db`  sha256 `d0f406f00882dadb4c0aa0b1bea3a4a77b562c80ec46f19fe7d6ad7d4ebfbeb4`  generated 2026-09-16T05:05:07.309848+00:00

## 0. Schema

- `hand_labels` (144 rows): id, attempt_id, classifier_label, ground_truth, notes, labeled_at
- `markdown_wrap_revalidation` (789 rows): attempt_id, model, schema_tier, node_name, outcome, compound_category, compound_errors
- `node_attempts` (4396 rows): id, run_id, node_name, attempt_num, raw_output, input_tokens, output_tokens, validation_ok, primary_category, all_categories, error_details, resolved_model_version
- `node_runs` (3096 rows): run_id, node_name, input_tokens, output_tokens, num_repairs, latency_sec, success, final_error
- `runs` (1040 rows): run_id, timestamp, paradigm, topology, schema_tier, model, max_retries, question, final_answer, graph_success, total_input_tokens, total_output_tokens, total_repairs, total_latency_sec, dataset, prompt_variant
- `sqlite_sequence` (2 rows): name, seq

Resolved: {'attempt_pk': 'id', 'node': 'node_name', 'raw': 'raw_output', 'reval_key': 'attempt_id', 'reval_outcome': 'outcome'}

## B1 run-node pairs without exactly one attempt_num=0 (all data)

```sql
SELECT COUNT(*) n_bad FROM (SELECT run_id,node_name,SUM(attempt_num=0) k FROM node_attempts GROUP BY 1,2) WHERE k<>1
```

| n_bad |
|---|
| 0 |

## B1b breakdown of k (first attempts per run-node)

```sql
SELECT k, COUNT(*) FROM (SELECT run_id,node_name,SUM(attempt_num=0) k FROM node_attempts GROUP BY 1,2) GROUP BY k
```

| k | COUNT(*) |
|---|---|
| 1 | 3096 |

## B2 validity by attempt_num × primary_category, Haiku baseline

```sql
SELECT a.attempt_num, COUNT(*) n, SUM(a.validation_ok) valid, a.primary_category FROM node_attempts a JOIN runs r USING(run_id) WHERE r.model LIKE 'claude-haiku-4-5%' AND r.prompt_variant='baseline' GROUP BY 1,4 ORDER BY 1,2 DESC
```

| attempt_num | n | valid | primary_category |
|---|---|---|---|
| 0 | 475 | 0 | markdown_wrap |
| 1 | 240 | 240 |  |
| 1 | 165 | 0 | markdown_wrap |
| 1 | 48 | 0 | length_bound |
| 1 | 22 | 0 | regex_pattern |
| 2 | 144 | 0 | length_bound |
| 2 | 91 | 91 |  |
| 3 | 120 | 120 |  |
| 3 | 24 | 0 | length_bound |

## B3 attempt_num contiguity: run-nodes where max(attempt_num)+1 != count or min != 0

```sql
SELECT COUNT(*) FROM (SELECT run_id,node_name,MIN(attempt_num) mn,MAX(attempt_num) mx,COUNT(*) c FROM node_attempts GROUP BY 1,2) WHERE mn<>0 OR mx+1<>c
```

| COUNT(*) |
|---|
| 0 |

## B4 attempts logged after a valid attempt in the same run-node (should be 0)

```sql
SELECT COUNT(*) FROM node_attempts a JOIN node_attempts b ON a.run_id=b.run_id AND a.node_name=b.node_name AND b.attempt_num>a.attempt_num WHERE a.validation_ok=1
```

| COUNT(*) |
|---|
| 0 |

## B5 flag consistency: NULL validation_ok; valid with category; invalid without category

```sql
SELECT SUM(validation_ok IS NULL) null_ok, SUM(validation_ok=1 AND primary_category IS NOT NULL) valid_with_cat, SUM(validation_ok=0 AND primary_category IS NULL) invalid_no_cat, SUM(validation_ok=1 AND error_details IS NOT NULL AND error_details NOT IN ('','[]','null')) valid_with_errors, SUM(validation_ok=0 AND (error_details IS NULL OR error_details IN ('','[]','null'))) invalid_no_errors FROM node_attempts
```

| null_ok | valid_with_cat | invalid_no_cat | valid_with_errors | invalid_no_errors |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |

## B6 first-attempt validity by model (baseline), all nodes

```sql
SELECT r.model, COUNT(*) reached, SUM(a.validation_ok) valid, ROUND(AVG(a.validation_ok),4) rate FROM node_attempts a JOIN runs r USING(run_id) WHERE a.attempt_num=0 AND r.prompt_variant='baseline' GROUP BY 1 ORDER BY 4
```

| model | reached | valid | rate |
|---|---|---|---|
| claude-haiku-4-5-20251001 | 475 | 0 | 0.0 |
| claude-sonnet-5 | 246 | 187 | 0.7602 |
| gpt-4o | 210 | 170 | 0.8095 |
| gpt-4o-mini | 225 | 190 | 0.8444 |
| claude-sonnet-4-6 | 450 | 400 | 0.8889 |
| claude-opus-4-8 | 252 | 240 | 0.9524 |
| gpt-5.6-terra | 402 | 384 | 0.9552 |
| gpt-5.6-luna | 261 | 250 | 0.9579 |
| gpt-5.6-sol | 396 | 382 | 0.9646 |

## B7 Haiku first attempts by collection date × dataset (batch uniformity)

```sql
SELECT substr(r.timestamp,1,10) day, r.dataset, COUNT(*) first_attempts, SUM(a.validation_ok) valid FROM node_attempts a JOIN runs r USING(run_id) WHERE r.model LIKE 'claude-haiku-4-5%' AND r.prompt_variant='baseline' AND a.attempt_num=0 GROUP BY 1,2 ORDER BY 1
```

| day | dataset | first_attempts | valid |
|---|---|---|---|
| 2026-08-09 | hotpotqa | 147 | 0 |
| 2026-08-22 | hotpotqa | 148 | 0 |
| 2026-08-23 | financebench | 51 | 0 |
| 2026-08-26 | financebench | 36 | 0 |
| 2026-08-28 | hotpotqa | 93 | 0 |

## B8 Haiku (baseline) attempts per run-node: distribution of attempt counts and final validity

```sql
SELECT c attempts, SUM(ok) ended_valid, COUNT(*) run_nodes FROM (SELECT a.run_id,a.node_name,COUNT(*) c,MAX(a.validation_ok) ok FROM node_attempts a JOIN runs r USING(run_id) WHERE r.model LIKE 'claude-haiku-4-5%' AND r.prompt_variant='baseline' GROUP BY 1,2) GROUP BY 1
```

| attempts | ended_valid | run_nodes |
|---|---|---|
| 2 | 240 | 240 |
| 3 | 91 | 91 |
| 4 | 120 | 144 |

## B9 run completion vs answer-node validity (baseline), mismatches by model

```sql
SELECT r.model, COUNT(*) runs, SUM(r.graph_success=1) completed, SUM(r.graph_success IS NULL) null_flag, SUM((r.graph_success=1) <> COALESCE(x.ans_ok,0)) mismatch FROM runs r LEFT JOIN (SELECT run_id, MAX(validation_ok) ans_ok FROM node_attempts WHERE node_name='answer' GROUP BY 1) x USING(run_id) WHERE r.prompt_variant='baseline' GROUP BY 1
```

| model | runs | completed | null_flag | mismatch |
|---|---|---|---|---|
| claude-haiku-4-5-20251001 | 166 | 142 | 0 | 0 |
| claude-opus-4-8 | 84 | 84 | 0 | 0 |
| claude-sonnet-4-6 | 150 | 150 | 0 | 0 |
| claude-sonnet-5 | 82 | 82 | 0 | 0 |
| gpt-4o | 70 | 70 | 0 | 0 |
| gpt-4o-mini | 75 | 74 | 0 | 0 |
| gpt-5.6-luna | 87 | 87 | 0 | 0 |
| gpt-5.6-sol | 132 | 132 | 0 | 0 |
| gpt-5.6-terra | 134 | 134 | 0 | 0 |

## B10 runs per cell by prompt_variant (manifest bug check)

```sql
SELECT model, schema_tier, dataset, prompt_variant, COUNT(*) runs, COUNT(DISTINCT question) questions, MIN(timestamp) first, MAX(timestamp) last FROM runs GROUP BY 1,2,3,4 ORDER BY 1,2,3,4
```

| model | schema_tier | dataset | prompt_variant | runs | questions | first | last |
|---|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | medium | financebench | baseline | 32 | 18 | 2026-08-23T01:33:34.143837+00:00 | 2026-08-26T04:32:50.990798+00:00 |
| claude-haiku-4-5-20251001 | medium | hotpotqa | aggressive | 30 | 30 | 2026-08-28T04:22:28.873387+00:00 | 2026-08-28T04:30:03.842742+00:00 |
| claude-haiku-4-5-20251001 | medium | hotpotqa | baseline | 134 | 50 | 2026-08-09T23:02:27.871565+00:00 | 2026-08-28T04:21:24.057316+00:00 |
| claude-haiku-4-5-20251001 | medium | hotpotqa | few_shot | 30 | 30 | 2026-08-28T04:30:54.333234+00:00 | 2026-08-28T04:38:10.749909+00:00 |
| claude-opus-4-8 | medium | financebench | baseline | 30 | 30 | 2026-08-26T05:27:09.638327+00:00 | 2026-08-26T05:33:38.050191+00:00 |
| claude-opus-4-8 | medium | hotpotqa | baseline | 54 | 50 | 2026-08-22T22:23:35.507207+00:00 | 2026-08-23T00:59:23.000945+00:00 |
| claude-sonnet-4-6 | medium | hotpotqa | baseline | 50 | 50 | 2026-08-09T23:17:01.576142+00:00 | 2026-08-09T23:28:28.896391+00:00 |
| claude-sonnet-4-6 | medium_v2 | hotpotqa | baseline | 100 | 50 | 2026-08-10T00:55:59.845879+00:00 | 2026-08-11T05:09:48.107032+00:00 |
| claude-sonnet-5 | medium | financebench | baseline | 30 | 30 | 2026-08-26T05:17:44.161761+00:00 | 2026-08-26T05:26:25.504089+00:00 |
| claude-sonnet-5 | medium | hotpotqa | baseline | 52 | 50 | 2026-08-22T22:41:54.893141+00:00 | 2026-08-23T00:50:50.556882+00:00 |
| gpt-4o | medium | hotpotqa | baseline | 70 | 50 | 2026-08-09T03:26:24.158274+00:00 | 2026-08-09T23:01:04.718166+00:00 |
| gpt-4o-mini | medium | financebench | baseline | 5 | 5 | 2026-08-22T04:48:36.942771+00:00 | 2026-08-22T04:49:18.442224+00:00 |
| gpt-4o-mini | medium | hotpotqa | baseline | 70 | 50 | 2026-08-09T02:57:23.103349+00:00 | 2026-08-09T22:55:41.850343+00:00 |
| gpt-5.6-luna | medium | financebench | baseline | 30 | 30 | 2026-08-23T01:02:03.683513+00:00 | 2026-08-23T01:07:49.904823+00:00 |
| gpt-5.6-luna | medium | hotpotqa | baseline | 55 | 50 | 2026-08-22T05:24:10.922809+00:00 | 2026-08-22T23:02:07.837213+00:00 |
| gpt-5.6-luna | medium_v3_loose_regex | hotpotqa | baseline | 2 | 2 | 2026-08-27T06:00:30.975387+00:00 | 2026-08-27T06:00:40.787854+00:00 |
| gpt-5.6-sol | medium | financebench | baseline | 30 | 30 | 2026-08-23T01:18:40.705907+00:00 | 2026-08-23T01:26:21.174352+00:00 |
| gpt-5.6-sol | medium | hotpotqa | baseline | 52 | 50 | 2026-08-22T22:22:07.688267+00:00 | 2026-08-22T23:24:08.181913+00:00 |
| gpt-5.6-sol | medium_v3_loose_regex | hotpotqa | baseline | 50 | 50 | 2026-08-27T06:02:28.332079+00:00 | 2026-08-27T06:14:24.128872+00:00 |
| gpt-5.6-terra | medium | financebench | baseline | 30 | 30 | 2026-08-23T01:10:23.658793+00:00 | 2026-08-23T01:13:51.909093+00:00 |
| gpt-5.6-terra | medium | hotpotqa | baseline | 54 | 50 | 2026-08-22T21:23:07.425942+00:00 | 2026-08-22T23:08:36.961972+00:00 |
| gpt-5.6-terra | medium_v3_loose_regex | hotpotqa | baseline | 50 | 50 | 2026-08-27T06:14:50.344681+00:00 | 2026-08-27T06:22:04.325618+00:00 |

## B11 resolved_model_version by requested model

```sql
SELECT r.model, COALESCE(a.resolved_model_version,'<null>') returned, COUNT(*) FROM node_attempts a JOIN runs r USING(run_id) GROUP BY 1,2 ORDER BY 1,2
```

| model | returned | COUNT(*) |
|---|---|---|
| claude-haiku-4-5-20251001 | claude-haiku-4-5-20251001 | 1694 |
| claude-opus-4-8 | claude-opus-4-8 | 265 |
| claude-sonnet-4-6 | claude-sonnet-4-6 | 502 |
| claude-sonnet-5 | claude-sonnet-5 | 313 |
| gpt-4o | <null> | 72 |
| gpt-4o | gpt-4o-2024-08-06 | 178 |
| gpt-4o-mini | <null> | 69 |
| gpt-4o-mini | gpt-4o-mini-2024-07-18 | 201 |
| gpt-5.6-luna | gpt-5.6-luna | 272 |
| gpt-5.6-sol | gpt-5.6-sol | 410 |
| gpt-5.6-terra | gpt-5.6-terra | 420 |

## B12 Haiku first attempts: raw opener (classifier-independent)

| node | opener | n |
|---|---|---|
| answer | fence | 143 |
| gather | fence | 166 |
| identify | fence | 166 |

### B12b three first-attempt samples (first 160 chars)

- 493 identify: ````json⏎{⏎  "entities": [⏎    {⏎      "name": "Scott Derrickson",⏎      "entity_type": "person",⏎      "canonical_id": "scott_derrickson"⏎    },⏎    {⏎      "na`
- 495 gather: ````json⏎{⏎  "facts": [⏎    {⏎      "entity_id": "scott_derrickson",⏎      "fact": "Scott Derrickson is an American film director and screenwriter born in Denver`
- 499 identify: ````json⏎{⏎  "entities": [⏎    {⏎      "name": "Corliss Archer",⏎      "entity_type": "person",⏎      "canonical_id": "corliss_archer"⏎    },⏎    {⏎      "name":`

### B12c Haiku: fence rate by attempt_num (does retry feedback suppress fences?)

| attempt_num | n | valid | fenced |
|---|---|---|---|
| 0 | 475 | 0 | 475 |
| 1 | 475 | 240 | 165 |
| 2 | 235 | 91 | 0 |
| 3 | 144 | 120 | 0 |
