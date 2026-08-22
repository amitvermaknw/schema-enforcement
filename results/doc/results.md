### python3 scripts/run_crux.py --model gpt-4o --n 20

Loading 20 HotpotQA samples...
Model: gpt-4o | max_retries=3 | inputs=20
Logging to: results/experiments.db

[1/20] Were Scott Derrickson and Ed Wood of the same nationality?...
    [OK] tokens=1550+382 repairs=0 lat=4.381s
[2/20] What government position was held by the woman who portrayed Corliss A...
    [OK] tokens=1610+429 repairs=0 lat=4.187s
[3/20] What science fantasy young adult series, told in first person, has a s...
    [OK] tokens=2568+601 repairs=1 lat=6.449s
[4/20] Are the Laleli Mosque and Esma Sultan Mansion located in the same neig...
    [OK] tokens=2503+605 repairs=1 lat=5.541s
[5/20] The director of the romantic comedy "Big Stone Gap" is based in what N...
    [OK] tokens=2451+528 repairs=1 lat=5.809s
[6/20] 2014 S/S is the debut album of a South Korean boy group that was forme...
    [OK] tokens=2370+482 repairs=1 lat=4.19s
[7/20] Who was known by his stage name Aladin and helped organizations improv...
    [OK] tokens=1554+344 repairs=0 lat=3.24s
[8/20] The arena where the Lewiston Maineiacs played their home games can sea...
    [OK] tokens=2495+568 repairs=1 lat=6.275s
[9/20] Who is older, Annie Morton or Terry Richardson?...
    [OK] tokens=1505+296 repairs=0 lat=4.804s
[10/20] Are Local H and For Against both from the United States?...
    [OK] tokens=2423+554 repairs=1 lat=5.521s
[11/20] What is the name of the fight song of the university whose main campus...
    [OK] tokens=2454+478 repairs=1 lat=5.76s
[12/20] What screenwriter with credits for "Evolution" co-wrote a film starrin...
    [OK] tokens=1605+437 repairs=0 lat=4.164s
[13/20] What year did Guns N Roses perform a promo for a movie starring Arnold...
    [OK] tokens=2594+622 repairs=1 lat=6.444s
[14/20] Are Random House Tower and 888 7th Avenue both used for real estate?...
    [OK] tokens=3283+720 repairs=2 lat=7.857s
[15/20] The football manager who recruited David Beckham managed Manchester Un...
    [OK] tokens=2433+535 repairs=1 lat=6.007s
[16/20] Brown State Fishing Lake is in a country that has a population of how ...
    [OK] tokens=1529+316 repairs=0 lat=3.547s
[17/20] The Vermont Catamounts men's soccer team currently competes in a confe...
    [OK] tokens=1642+443 repairs=0 lat=4.79s
[18/20] Are Giuseppe Verdi and Ambroise Thomas both Opera composers ?...
    [OK] tokens=1567+417 repairs=0 lat=4.209s
[19/20] Roger O. Egeberg was Assistant Secretary for Health and Scientific Aff...
    [OK] tokens=2586+573 repairs=1 lat=5.856s
[20/20] Which writer was from England, Henry Roth or Robert Erskine Childers?...
    [OK] tokens=1619+491 repairs=0 lat=5.218s
------------------------------------------------------------
Model=gpt-4o: 20/20 succeeded, 12 total repairs, 52162 total tokens

Next: run for another model, then `python scripts/analyze_crux.py`
Mac-mini:schema-enforcement-paper amitvermaknw$ python3 scripts/analyze_crux.py
========================================================================
PER-MODEL FAILURE RATES
========================================================================
Model                                      Attempts   Failures     Rate
------------------------------------------------------------------------
gpt-4o                                           72         12   16.7%
gpt-4o-mini                                      69          9   13.0%

========================================================================
FAILURE TAXONOMY (counts of failures by category, per model)
========================================================================
Category                              gpt-4o         gpt-4o-mini
----------------------------------------------------------------
enum_violation                             1                   0
length_bound                               0                   1
missing_field                              9                   1
regex_pattern                              2                   7

========================================================================
FAILURE DISTRIBUTION (share of each model's failures, normalized)
========================================================================
Category                              gpt-4o         gpt-4o-mini
----------------------------------------------------------------
enum_violation                         8.3%                0.0% 
length_bound                           0.0%               11.1% 
missing_field                         75.0%               11.1% 
regex_pattern                         16.7%               77.8% 

========================================================================
VERDICT
========================================================================
Comparing failure distributions across 2 models.
Higher divergence = failure modes differ more across models = paper thesis holds.

  gpt-4o vs gpt-4o-mini:
    max category divergence: 63.9% on 'missing_field'
    top-3 diverging categories: missing_field(63.9%), regex_pattern(61.1%), length_bound(11.1%)

Overall max divergence across all pairs: 63.9%

Failure distributions differ MEANINGFULLY across models.
The paper's thesis is supported: failure modes shift across model tiers.
Proceed to Week 3 (add paradigm 2, then full matrix).