# app/services/comparison.py
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple, Sequence, Optional
from firebase_admin import db as rtdb
from app.main.firebase import server_ts, ASSIGN_PATH, PARTIC_PATH
from scipy.stats import qmc 

# Discrete levels
RECOMMENDATIONS: Sequence[str] = ["95", "85", "75", "65"]
FREQUENCIES:     Sequence[str] = ["Daily", "Weekly", "Monthly", "Quarterly"]
MISSING_RATES:   Sequence[str] = ["5", "10", "15", "20"]
COVERAGES:       Sequence[str] = ["35", "30", "25", "20"]

CriteriaLevels = Dict[str, Sequence[str]]
LEVELS: CriteriaLevels = {
    "recommendation": RECOMMENDATIONS,
    "frequency":      FREQUENCIES,
    "missing":        MISSING_RATES,
    "coverage":       COVERAGES,
}

SCENARIO_TO_CRITERION = {
    "s1": "recommendation",
    "s2": "coverage",
    "s3": "frequency",
    "s4": "missing",
}

def _sobol_samples(n: int, d: int) -> List[List[float]]:
    """
    Return n x d samples in [0,1).
    Uses scipy.stats.qmc.Sobol if available; otherwise falls back to a small Halton generator.
    """
    sampler = qmc.Sobol(d=d, scramble=True)
    pow2 = 1 << (n - 1).bit_length()
    X = sampler.random_base2(m=int(math.log2(pow2)))
    if pow2 > n:
        # Randomly subsample to n while preserving spread
        idx = list(range(pow2))
        random.shuffle(idx)
        idx = idx[:n]
        X = X[idx]
    return X.tolist()


# def _map_to_levels(samples: List[List[float]], levels: CriteriaLevels) -> List[Dict[str, str]]:
#     """
#     Map each sample in [0,1)^d to a dict picking one level per criterion by stratified binning.
#     """
#     keys = list(levels.keys())
#     out: List[Dict[str, str]] = []
#     for x in samples:
#         row: Dict[str, str] = {}
#         for j, key in enumerate(keys):
#             vals = levels[key]
#             # stratified bin index
#             idx = min(int(math.floor(x[j] * len(vals))), len(vals) - 1)
#             row[key] = vals[idx]
#         out.append(row)
#     return out

# def _generate_sobol_datasets(n: int) -> List[Dict[str, str]]:
#     """
#     Produce n datasets with minimal correlation across criteria via low-discrepancy sampling.
#     """
#     d = len(LEVELS)
#     samples = _sobol_samples(n, d)
#     return _map_to_levels(samples, LEVELS)

CONTINUOUS_RANGES: Dict[str, Tuple[float, float]] = {
    "recommendation": (95.0, 65.0),  # percent points
    "coverage": (35.0, 20.0),        # percent points
    "missing": (5.0, 20.0),          # percent points
    "frequency": (1.0, 90.0),        # days (1=Daily, ~7=Weekly, ~30=Monthly, ~90=Quarterly)
}

def _generate_sobol_continuous(
    n: int,
    ranges: Dict[str, Tuple[float, float]] = CONTINUOUS_RANGES
) -> List[Dict[str, float]]:
    """
    Produce n datasets as continuous values within the provided [lo, hi] ranges
    using low-discrepancy Sobol samples.
    """
    keys = list(ranges.keys())
    d = len(keys)
    samples = _sobol_samples(n, d)
    out: List[Dict[str, float]] = []
    for x in samples:
        row: Dict[str, float] = {}
        for j, key in enumerate(keys):
            lo, hi = ranges[key]
            val = lo + x[j] * (hi - lo)
            row[key] = round(val, 2)
        out.append(row)
    return out


def _comparison_pairs(
    target_key: str,
    n: int,
    use_low_discrepancy: bool,
    rng: Optional[random.Random] = None,
    include_self_pairs: bool = True,
) -> List[Tuple[Dict[str, str], Dict[str, str]]]:
    """
    Build pairs that cover all (A_level, B_level) combinations for the given `criterion`
    exactly once (order randomized). Other criteria are populated as they are now:
      - low-discrepancy when use_low_discrepancy=True
      - random otherwise
    The resulting list is trimmed to length n.
    """
    rng = rng or random.Random()

    # Validate criterion
    if target_key not in LEVELS:
        raise ValueError(f"Unknown criterion '{target_key}'. Must be one of: {list(LEVELS)}")

    crit_levels = LEVELS[target_key]

    # All A×B combos for this criterion (optionally excluding identical pairs)
    combos: List[Tuple[str, str]] = []
    for a in crit_levels:
        for b in crit_levels:
            if include_self_pairs or a != b:
                combos.append((a, b))

    # Shuffle required combos
    rng.shuffle(combos)

    # Prepare endpoints for the other criteria (one dataset per side)
    endpoints_required = 2 * len(combos)
    if use_low_discrepancy:
        endpoints = _generate_sobol_continuous(endpoints_required)
    else:
        endpoints = [_rand_dataset() for _ in range(endpoints_required)]

    # Overwrite ONLY the targeted criterion on each endpoint to match the combo
    pairs: List[Tuple[Dict[str, str], Dict[str, str]]] = []
    ei = 0
    for a_level, b_level in combos:
        a = dict(endpoints[ei]);   ei += 1
        b = dict(endpoints[ei]);   ei += 1
        a[target_key] = a_level
        b[target_key] = b_level
        pairs.append((a, b))
    if len(pairs) >= n:
        return pairs[:n]
    out = list(pairs)
    i = 0
    while len(out) < n:
        out.append(pairs[i % len(pairs)])
        i += 1
    return out


# def _all_level_pairs(levels: Sequence[str], include_self: bool = True) -> List[Tuple[str, str]]:
#     pairs: List[Tuple[str, str]] = []
#     for a in levels:
#         for b in levels:
#             if include_self or a != b:
#                 pairs.append((a, b))
#     return pairs

# def _pair_datasets_for_target(
#     datasets: List[Dict[str, str]],
#     target_key: str,
#     include_self_pairs: bool = True,
#     rng: Optional[random.Random] = None,
# ) -> List[Tuple[Dict[str, str], Dict[str, str]]]:
#     """
#     Build A/B pairs so that for the target_key we cover each (level_A, level_B) combination at least once.
#     Other criteria are implicitly diverse because datasets came from low-discrepancy sampling.
#     """
#     rng = rng or random.Random()
#     target_levels = LEVELS[target_key]
#     needed = _all_level_pairs(target_levels, include_self_pairs)
#     rng.shuffle(needed)

#     # Index datasets by their target level for quick matching
#     buckets: Dict[str, List[Dict[str, str]]] = {lvl: [] for lvl in target_levels}
#     for d in datasets:
#         buckets[d[target_key]].append(d)

#     # To avoid reusing the exact same dataset too often, shuffle buckets
#     for v in buckets.values():
#         rng.shuffle(v)

#     pairs: List[Tuple[Dict[str, str], Dict[str, str]]] = []
#     # Greedy coverage of the required target pairs
#     for (a_lvl, b_lvl) in needed:
#         if not buckets[a_lvl]:
#             # If bucket empty, borrow from the largest bucket
#             largest = max(buckets.items(), key=lambda kv: len(kv[1]))[0]
#             a = buckets[largest].pop() if buckets[largest] else rng.choice(datasets)
#         else:
#             a = buckets[a_lvl].pop()

#         if not buckets[b_lvl]:
#             largest = max(buckets.items(), key=lambda kv: len(kv[1]))[0]
#             b = buckets[largest].pop() if buckets[largest] else rng.choice(datasets)
#         else:
#             b = buckets[b_lvl].pop()

#         pairs.append((a, b))

#     # If leftover datasets remain, optionally extend pairs by cycling through target pairs
#     leftovers = [d for v in buckets.values() for d in v]
#     rng.shuffle(leftovers)
#     i = 0
#     while i < len(leftovers) - 1:
#         a, b = leftovers[i], leftovers[i + 1]
#         pairs.append((a, b))
#         i += 2

#     return pairs


def _rand_dataset(force_rec: str | None = None) -> Dict[str, str]:
    # Kept for compatibility; not used in Sobol path.
    return {
        "recommendation": force_rec if force_rec else random.choice(RECOMMENDATIONS),
        "frequency": random.choice(FREQUENCIES),
        "missing": random.choice(MISSING_RATES),
        "coverage": random.choice(COVERAGES),
    }


def ensure_comparison_trials(
    pid: str,
    scenario_id: str,
    n: int = 16,
    use_low_discrepancy: bool = True,
    include_self_pairs: bool = True,
) -> None:
    """
    Idempotently create comparison trials under {ASSIGN_PATH}/{pid}/comparison_trials.

    If `use_low_discrepancy` is True (default), we:
      - For known scenarios (in SCENARIO_TO_CRITERION): cover all (A_level, B_level)
        combinations for the target criterion, diversifying others.
      - For other scenarios: generate continuous endpoints within configured ranges.
    """
    base = f"{ASSIGN_PATH}/{pid}/comparison_trials"
    if rtdb.reference(base).get():
        return

    trials: Dict[str, Dict[str, Any]] = {}
    rng = random.Random()
    
    if str(scenario_id) in SCENARIO_TO_CRITERION:
        print("get scenario id" + scenario_id)
        pairs = _comparison_pairs(
            target_key=SCENARIO_TO_CRITERION[str(scenario_id)],
            n=n,
            use_low_discrepancy=use_low_discrepancy,
            rng=rng,
            include_self_pairs=include_self_pairs,
        )
        print(pairs)
    else:
        print("error")
        # endpoints_required = 2 * n
        # if use_low_discrepancy:
        #     endpoints = _generate_sobol_continuous(endpoints_required)
        # else:
        #     endpoints = []
        #     for _ in range(endpoints_required):
        #         sample: Dict[str, float] = {}
        #         for k, (lo, hi) in CONTINUOUS_RANGES.items():
        #             sample[k] = lo + rng.random() * (hi - lo)
        #         endpoints.append(sample)
        # pairs = []
        # for i in range(0, endpoints_required, 2):
        #     a = dict(endpoints[i])
        #     b = dict(endpoints[i + 1])
        #     pairs.append((a, b))

    for i, (opt_a, opt_b) in enumerate(pairs, start=1):
        trials[str(i)] = {
            "scenario_id": scenario_id,
            "option_a": dict(opt_a),
            "option_b": dict(opt_b),
            "ts": server_ts(),
        }
    print()
    rtdb.reference(base).update(trials)
    rtdb.reference(f"{ASSIGN_PATH}/{pid}/last_comparison_trial").set(0)