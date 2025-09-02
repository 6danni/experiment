# app/utils/metrics.py
import random
from firebase_admin import db as rtdb

def choose_and_increment_one(path: str, candidate_ids: list[str]) -> str:
    """
    Generic RTDB transactional chooser:
    - initializes missing counters to 0
    - chooses among min-count IDs with random tiebreak
    - increments chosen ID atomically
    """
    chosen = {"id": None}
    counts_ref = rtdb.reference(path)

    def txn(curr):
        curr = curr or {}
        for cid in candidate_ids:
            curr.setdefault(cid, 0)
        min_count = min(curr[cid] for cid in candidate_ids)
        pool = [cid for cid in candidate_ids if curr[cid] == min_count]
        cid = random.choice(pool)
        curr[cid] += 1
        chosen["id"] = cid
        return curr

    counts_ref.transaction(txn)
    return chosen["id"]
