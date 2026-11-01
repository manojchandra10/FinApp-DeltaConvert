def calculate_trust_label(pred_pct: float, actual_pct: float) -> str:
    """
    Compares predicted vs actual next-day change.

    A day where the market barely moved (under 0.05%) is labelled neutral
    rather than a hit or a miss: at that magnitude the direction is noise,
    and counting it either way flatters or punishes the model unfairly.
    """
    if abs(actual_pct) < 0.0005:
        return "Flat Day (Neutral)"

    same_direction = (pred_pct > 0 and actual_pct > 0) or (pred_pct < 0 and actual_pct < 0)

    if not same_direction:
        return "Direction Missed"

    diff = abs(pred_pct - actual_pct)

    if diff < 0.0015:
        return "Direction Matched (Close)"

    if abs(actual_pct) > abs(pred_pct):
        return "Direction Matched (Undershot)"

    return "Direction Matched (Overshot)"
