"""Month-granularity chronology and conservative availability projections."""
from datetime import datetime, timezone

def parse_date(value: str | None):
    if not value:
        return None, None
    if value in {"infinity", "-infinity"}:
        return None, "nonfinite_date"
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None, "timezone_missing"
        return parsed.astimezone(timezone.utc), None
    except (ValueError, OverflowError):
        return None, "invalid_date"

def time_evidence(kind: str, row: dict) -> dict:
    names = ("Created", "Modified", "StudyingStartDate", "Completed", "BuyingDate")
    raw = {key: row.get(key) or None for key in names if key in row}
    dates, flags = {}, []
    for field, value in raw.items():
        parsed, error = parse_date(value)
        if error:
            flags.append(f"{field}:{error}")
        if parsed:
            dates[field] = parsed
            if parsed.day != 1 or (parsed.hour, parsed.minute, parsed.second) != (12, 0, 0):
                flags.append(f"{field}:unexpected_archive_precision")
    for earlier, later, flag in [("Completed", "Created", "completion_before_creation"),
                                  ("Modified", "Created", "modification_before_creation"),
                                  ("Completed", "StudyingStartDate", "completion_before_study_start")]:
        if earlier in dates and later in dates and dates[earlier] < dates[later]:
            flags.append(flag)
    if kind == "lesson_progress":
        chosen = "Completed" if "Completed" in dates else None
    elif kind == "explicit_rating":
        chosen = max((key for key in ("Created", "Modified") if key in dates),
                     key=lambda key: dates[key], default=None)
    else:
        chosen = next((key for key in ("StudyingStartDate", "Created") if key in dates), None)
    month = dates[chosen].strftime("%Y-%m") if chosen else None
    confidence = "missing" if not month else "uncertain" if flags else "coarse"
    reasons = []
    if kind == "enrollment_state":
        reasons.append("mutable_enrollment_snapshot_not_historical_state")
    if not month:
        reasons.append("missing_event_time")
    if flags:
        reasons.append("uncertain_chronology")
    # Rating uses latest recorded modification, never its earlier creation date
    # with a later value. Lesson completion is admitted only without contradictions.
    available = None
    if not reasons:
        available = max(dates[key] for key in dates if key in {"Created", "Modified", "Completed"}).strftime("%Y-%m")
    return dict(event_time=month, event_time_source=chosen, time_granularity="month" if month else "unknown",
                time_confidence=confidence, raw_dates=raw, available_from_month=available,
                evaluation_eligible=not reasons, evaluation_exclusion_reasons=reasons, quality_flags=flags)

def before_cutoff(observation, cutoff_month: str) -> bool:
    import re
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", cutoff_month):
        raise ValueError("cutoff must be YYYY-MM")
    return (observation.evaluation_eligible and observation.available_from_month is not None
            and observation.available_from_month < cutoff_month)
