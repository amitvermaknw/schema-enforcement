"""Synthetic DB matching the documented schema; not real data."""
import sqlite3, random, json, sys
random.seed(1)
db=sys.argv[1]; con=sqlite3.connect(db)
con.executescript("""
CREATE TABLE runs(run_id INTEGER PRIMARY KEY, model TEXT, schema_tier TEXT, dataset TEXT, prompt_variant TEXT,
 question TEXT, timestamp TEXT, graph_success INTEGER);
CREATE TABLE node_attempts(attempt_id INTEGER PRIMARY KEY, run_id INT, node_name TEXT, attempt_num INT,
 validation_ok INT, primary_category TEXT, all_categories TEXT, error_details TEXT, resolved_model_version TEXT,
 output_tokens INT, raw_output TEXT);
CREATE TABLE markdown_wrap_revalidation(attempt_id INT, outcome TEXT);
""")
cfg=[("claude-haiku-4-5-20251001","medium","hotpotqa","baseline",134,0.0),
     ("claude-haiku-4-5-20251001","medium","hotpotqa","few_shot",30,0.3),
     ("claude-haiku-4-5-20251001","medium","financebench","baseline",32,0.0),
     ("claude-sonnet-5","medium","hotpotqa","baseline",52,0.8),
     ("claude-sonnet-5","medium","financebench","baseline",30,0.8),
     ("gpt-4o-mini","medium","financebench","baseline",5,0.8),
     ("gpt-5.6-sol","medium","hotpotqa","baseline",52,0.95)]
rid=0; aid=0
for m,t,d,v,n,p0 in cfg:
    for i in range(n):
        rid+=1; q=f"{d}-q{i%50}"
        ok_run=1
        for node in ("identify","gather","answer"):
            done=False
            for k in range(4):
                aid+=1
                p = p0 if k==0 else 0.7
                ok = random.random()<p
                cat=None; raw='{"x":1}'
                if not ok:
                    if m.startswith("claude"): cat="markdown_wrap"; raw="```json\n{}\n```"
                    else: cat=random.choice(["regex_pattern","length_bound"])
                con.execute("INSERT INTO node_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (aid,rid,node,k,int(ok),cat,None,None if ok else '[{"type":"x"}]',
                     None if (m.startswith("gpt-4o") and rid%3==0) else m, 100, raw))
                if cat=="markdown_wrap":
                    con.execute("INSERT INTO markdown_wrap_revalidation VALUES(?,?)",(aid,random.choice(["pure_formatting","compound_length_bound"])))
                if ok: done=True; break
            if not done: ok_run=0; break
        con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",(rid,m,t,d,v,q,f"2026-08-{10+i%5:02d}T12:{i%60:02d}:00",ok_run))
con.commit()