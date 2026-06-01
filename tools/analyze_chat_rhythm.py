"""Analyze group chat message frequency to recommend proactive mode thresholds.

Reads messages from data/messages.db, computes message rate distributions
per group, and outputs recommended thresholds for the 5 proactive modes:

    SLEEP / QUIET / CASUAL / LIVELY / BURST

Usage:
    python tools/analyze_chat_rhythm.py [--db data/messages.db] [--window 5]
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Add project root so we can import config if needed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_messages(db_path: str) -> dict[str, list[int]]:
    """Load messages grouped by chat_id, returning list of timestamps per group."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT chat_id, timestamp FROM messages ORDER BY timestamp ASC"
    ).fetchall()
    conn.close()

    groups: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        groups[row["chat_id"]].append(row["timestamp"])
    return dict(groups)


def compute_rates(timestamps: list[int], window_min: int) -> list[float]:
    """Compute message rate (msgs/min) for every sliding window position.

    For each timestamp, count how many messages fall within the next
    `window_min` minutes, yielding the rate at that point in time.
    """
    if len(timestamps) < 2:
        return []

    window_sec = window_min * 60
    rates: list[float] = []
    n = len(timestamps)

    for i, t_start in enumerate(timestamps):
        t_end = t_start + window_sec
        # Count messages in [t_start, t_end)
        count = 1  # at least the message at t_start
        j = i + 1
        while j < n and timestamps[j] < t_end:
            count += 1
            j += 1
        rates.append(count / window_min)

    return rates


def percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile (0-100) of sorted values."""
    if not sorted_values:
        return 0.0
    k = (p / 100.0) * (len(sorted_values) - 1)
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_values):
        return sorted_values[f] + c * (sorted_values[f + 1] - sorted_values[f])
    return sorted_values[f]


def recommend_thresholds(rates: list[float]) -> dict[str, tuple[float, float]]:
    """Recommend mode boundaries from rate distribution.

    Strategy:
      - P0-P60  of rates → SLEEP/QUIET  boundary (most of the time is quiet)
      - P60-P80  of rates → QUIET/CASUAL boundary
      - P80-P93  of rates → CASUAL/LIVELY boundary
      - P93-P99  of rates → LIVELY/BURST  boundary
      - P99+      → BURST

    Returns dict of mode_name -> (min_rate, max_rate).
    """
    if not rates:
        return {}

    s = sorted(rates)
    p50 = percentile(s, 50)
    p60 = percentile(s, 60)
    p80 = percentile(s, 80)
    p93 = percentile(s, 93)
    p99 = percentile(s, 99)

    # Round boundaries to nice numbers
    def _round(v: float) -> float:
        if v < 1:
            return round(v, 1)
        elif v < 10:
            return round(v * 2) / 2  # round to 0.5
        else:
            return round(v)

    quiet  = max(0.3, _round(p50))   # below median = sleep, above = quiet
    casual = max(quiet + 0.5, _round(p80))
    lively = max(casual + 1, _round(p93))
    burst  = max(lively + 2, _round(p99))

    return {
        "SLEEP":  (0.0, quiet),
        "QUIET":  (quiet, casual),
        "CASUAL": (casual, lively),
        "LIVELY": (lively, burst),
        "BURST":  (burst, float("inf")),
    }


def analyze(db_path: str, window_min: int = 5) -> None:
    """Main analysis routine."""
    groups = load_messages(db_path)

    if not groups:
        print("No messages found in database.")
        return

    for chat_id, timestamps in groups.items():
        print(f"\n{'='*60}")
        print(f"Group: {chat_id}")
        print(f"Messages: {len(timestamps)}")

        if len(timestamps) < 2:
            print("  Not enough data (need ≥2 messages)")
            continue

        # Basic stats
        from datetime import datetime
        span_h = (timestamps[-1] - timestamps[0]) / 3600
        avg_rate = len(timestamps) / max(span_h, 0.01) / 60
        print(f"Time span: {span_h:.1f} hours")
        print(f"Global avg rate: {avg_rate:.2f} msgs/min")

        # Rate distribution
        rates = compute_rates(timestamps, window_min)
        s = sorted(rates)
        print(f"\nRate distribution ({window_min}min sliding window):")
        print(f"  Min:    {s[0]:.2f} msgs/min")
        print(f"  P10:    {percentile(s, 10):.2f}")
        print(f"  P25:    {percentile(s, 25):.2f}")
        print(f"  P50:    {percentile(s, 50):.2f}")
        print(f"  P60:    {percentile(s, 60):.2f}")
        print(f"  P75:    {percentile(s, 75):.2f}")
        print(f"  P80:    {percentile(s, 80):.2f}")
        print(f"  P90:    {percentile(s, 90):.2f}")
        print(f"  P93:    {percentile(s, 93):.2f}")
        print(f"  P95:    {percentile(s, 95):.2f}")
        print(f"  P99:    {percentile(s, 99):.2f}")
        print(f"  Max:    {s[-1]:.2f}")

        # Recommended thresholds
        thresholds = recommend_thresholds(rates)
        print(f"\nRecommended mode thresholds:")
        mode_names = {
            "SLEEP": "沉睡 (SLEEP)",
            "QUIET": "冷清 (QUIET)",
            "CASUAL": "闲聊 (CASUAL)",
            "LIVELY": "热闹 (LIVELY)",
            "BURST": "炸了 (BURST)",
        }
        for mode in ["SLEEP", "QUIET", "CASUAL", "LIVELY", "BURST"]:
            lo, hi = thresholds[mode]
            hi_str = f"{hi:.1f}" if hi != float("inf") else "∞"
            print(f"  {mode_names[mode]:20s} {lo:.1f} ~ {hi_str} msgs/min")

        # Distribution histogram (ASCII)
        print(f"\nRate histogram (1 char = ~{max(1, len(rates)//60)} samples):")
        bins = [0] * 20
        max_rate = s[-1]
        for r in rates:
            idx = min(19, int(r / max_rate * 20) if max_rate > 0 else 0)
            # Use log-scale-like binning for better visualization
            if r < 1:
                idx = min(1, int(r * 2))
            elif r < 3:
                idx = 2 + int(r - 1)
            elif r < 6:
                idx = 4 + int((r - 3) / 1.5)
            elif r < 10:
                idx = 6 + int((r - 6) / 2)
            elif r < 20:
                idx = 8 + int((r - 10) / 2.5)
            else:
                idx = 12 + min(7, int((r - 20) / 5))
            idx = max(0, min(19, idx))
            bins[idx] += 1

        bin_labels = [
            "0.0", "0.5", "1.0", "1.5", "2.0", "3.0", "4.5",
            "6.0", "8.0", "10.", "12.", "15.", "20.", "25.",
            "30.", "35.", "40.", "45.", "50.", "50+",
        ]
        max_bin = max(bins) if bins else 1
        bar_width = 50
        for i, (label, count) in enumerate(zip(bin_labels, bins)):
            bar = "#" * max(1, int(count / max_bin * bar_width)) if count else ""
            marker = ""
            for mode in ["SLEEP", "QUIET", "CASUAL", "LIVELY", "BURST"]:
                lo, hi = thresholds[mode]
                lo_f = float(label) if label != "50+" else 51
                hi_f = float(label.replace("+", "")) if "+" in label else lo_f + 0.5
                if lo <= lo_f < hi:
                    marker = f" <-- {mode}"
                    break
            if count:
                print(f"  {label:>4s} |{bar:<50s}| {count:4d}{marker}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze chat rhythm and recommend proactive mode thresholds"
    )
    parser.add_argument(
        "--db", default="data/messages.db",
        help="Path to SQLite database (default: data/messages.db)",
    )
    parser.add_argument(
        "--window", type=int, default=5,
        help="Sliding window size in minutes (default: 5)",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        sys.exit(1)

    analyze(args.db, args.window)


if __name__ == "__main__":
    main()
