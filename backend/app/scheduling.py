from collections import Counter
import pandas as pd

HARD_RULES = ["no_overlapping_shifts", "no_approved_leave_overlap", "required_skill_present"]

def evaluate_assignments(assignments: pd.DataFrame) -> dict:
    """Evaluate the generated baseline schedule. Returns explainable counts, not a black-box score."""
    if assignments.empty:
        return {"assignment_count": 0, "overlap_conflicts": 0, "overtime_assignments": 0, "coverage_gaps": 0, "hard_rules": HARD_RULES}
    df = assignments.copy()
    df["start_at"] = pd.to_datetime(df["start_at"])
    df["end_at"] = pd.to_datetime(df["end_at"])
    overlaps = 0
    for _, group in df.sort_values("start_at").groupby("employee_id"):
        prev_end = None
        for row in group.itertuples():
            if prev_end is not None and row.start_at < prev_end:
                overlaps += 1
            prev_end = max(prev_end, row.end_at) if prev_end is not None else row.end_at
    overtime = int((df.get("weekly_hours_after_assignment", pd.Series([0] * len(df))) > 48).sum())
    gaps = int(df.get("coverage_gap", pd.Series([False] * len(df))).astype(bool).sum())
    return {"assignment_count": int(len(df)), "overlap_conflicts": overlaps, "overtime_assignments": overtime, "coverage_gaps": gaps, "hard_rules": HARD_RULES}
