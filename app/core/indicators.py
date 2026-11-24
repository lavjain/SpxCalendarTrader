"""Small indicators on a list of closes. No web imports."""


def simple_moving_average(closes, window):
    """Mean of the last `window` closes, or None when there are fewer than that."""
    if window < 1 or len(closes) < window:
        return None
    return sum(closes[-window:]) / window
