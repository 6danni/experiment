from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple, Sequence, Optional
from firebase_admin import db as rtdb
from app.main.firebase import server_ts, ASSIGN_PATH
from scipy.stats import qmc 

# Discrete levels
RECOMMENDATIONS: Sequence[str] = ["65", "75", "85", "95"]
FREQUENCIES:     Sequence[str] = ["Daily", "Weekly", "Monthly", "Quarterly"]
MISSING_RATES:   Sequence[str] = ["5", "10", "15", "20"]
COVERAGES:       Sequence[str] = ["20", "25", "30", "35"]

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


