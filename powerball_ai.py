
"""
DOC'S POWERBALL AI LAB
Historical Research & Walk-Forward Backtesting
Version 1.0

Python standard library only.
No API keys or pip installation required.

Outputs:
  data/powerball_history.csv
  data/data_audit.json
  data/backtest_results.csv
  data/model_comparison.json
  data/latest_research.json

Research only. Lottery draws are random.
Historical patterns do not guarantee future results.
"""

import csv
import io
import json
import math
import random
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ARCHIVE_URL = (
    "https://raw.githubusercontent.com/"
    "jt2002/Data-Science-for-Powerball/"
    "master/powerball_numbers_since_1992.csv"
)

NY_URL = "https://data.ny.gov/resource/d6yy-54nr.json"

OUTPUT = Path("data")
OUTPUT.mkdir(exist_ok=True)

RANDOM_SEED = 20261010
BACKTEST_DRAWS = 150
MIN_TRAINING_DRAWS = 100
RANDOM_TRIALS = 100

# Current Powerball format.
CURRENT_WHITE_MAX = 69
CURRENT_RED_MAX = 26
CURRENT_FORMAT_START = date(2015, 10, 7)


def download(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DocsPowerballAILab/1.0"}
    )
    with urllib.request.urlopen(
        request, timeout=45
    ) as response:
        return response.read().decode("utf-8-sig")


def parse_date(value):
    if isinstance(value, date):
        return value

    text = str(value).strip()

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
    ):
        try:
            return datetime.strptime(
                text[:10], fmt
            ).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date: {text}")


def normalize_record(draw_date, numbers, source):
    d = parse_date(draw_date)
    balls = [int(x) for x in numbers]

    if len(balls) != 6:
        raise ValueError("Expected six numbers")

    white = balls[:5]
    red = balls[5]

    if (
        len(set(white)) != 5
        or min(white) < 1
        or red < 1
    ):
        raise ValueError("Invalid or duplicate balls")

    # Validate current-era records using known limits.
    if d >= CURRENT_FORMAT_START:
        if max(white) > 69 or red > 26:
            raise ValueError("Invalid current-format balls")
    else:
        # Preliminary safety bounds for historical data.
        # Exact older-era rules require separate verification.
        if max(white) > 69 or red > 45:
            raise ValueError("Outside historical safety bounds")

    return {
        "date": d.isoformat(),
        "white": sorted(white),
        "powerball": red,
        "source": source,
    }


def load_archive():
    print("Downloading historical archive...")

    content = download(ARCHIVE_URL)
    rows = list(csv.reader(io.StringIO(content)))

    if not rows:
        raise ValueError("Historical archive is empty")

    header = [
        str(x).strip().lower()
        for x in rows[0]
    ]

    expected = [
        "drawdate", "ball1", "ball2",
        "ball3", "ball4", "ball5",
        "powerball"
    ]

    if header[:7] != expected:
        raise ValueError(
            "Unexpected archive columns: "
            + repr(header)
        )

    records = []
    rejected = []

    for row_number, row in enumerate(
        rows[1:], start=2
    ):
        try:
            if len(row) < 7:
                raise ValueError("Too few columns")

            records.append(
                normalize_record(
                    row[0],
                    row[1:7],
                    "Historical CSV"
                )
            )
        except Exception as exc:
            rejected.append({
                "row": row_number,
                "error": str(exc),
            })

    return records, rejected


def load_new_york():
    print("Downloading New York drawing records...")

    records = []
    rejected = []
    limit = 1000
    offset = 0

    while True:
        query = urllib.parse.urlencode({
            "$limit": limit,
            "$offset": offset,
            "$order": "draw_date ASC",
        })

        page = json.loads(
            download(NY_URL + "?" + query)
        )

        if not isinstance(page, list):
            raise ValueError("Unexpected NY API response")

        for item in page:
            try:
                numbers = re.findall(
                    r"\d+",
                    str(item.get(
                        "winning_numbers", ""
                    ))
                )

                records.append(
                    normalize_record(
                        item["draw_date"],
                        numbers,
                        "NY State Open Data"
                    )
                )
            except Exception as exc:
                rejected.append({
                    "date": item.get("draw_date"),
                    "error": str(exc),
                })

        print(
            f"  NY records received: "
            f"{offset + len(page)}"
        )

        if len(page) < limit:
            break

        offset += limit

        if offset >= 100000:
            raise RuntimeError(
                "NY pagination safety limit reached"
            )

    return records, rejected


def merge_history(archive, ny_records):
    merged = {}
    conflicts = []
    matches = 0

    for record in archive + ny_records:
        key = record["date"]

        if key not in merged:
            merged[key] = record
            continue

        old = merged[key]

        same = (
            old["white"] == record["white"]
            and old["powerball"]
            == record["powerball"]
        )

        if same:
            matches += 1

            if record["source"] == "NY State Open Data":
                merged[key] = record
        else:
            conflicts.append({
                "date": key,
                "existing": old,
                "incoming": record,
            })

    history = sorted(
        merged.values(),
        key=lambda r: r["date"]
    )

    return history, conflicts, matches


def save_json(path, obj):
    with open(
        OUTPUT / path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            obj,
            file,
            indent=2,
            ensure_ascii=False
        )


def save_history(history):
    with open(
        OUTPUT / "powerball_history.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "draw_date",
            "white_1", "white_2",
            "white_3", "white_4",
            "white_5", "powerball",
            "source"
        ])

        for r in history:
            writer.writerow([
                r["date"],
                *r["white"],
                r["powerball"],
                r["source"]
            ])


def audit_data(history, archive, ny, rejected,
               conflicts, matches):
    earliest = history[0]["date"] if history else None
    latest = history[-1]["date"] if history else None

    audit = {
        "archive_records": len(archive),
        "new_york_records": len(ny),
        "unique_drawings": len(history),
        "matching_overlaps": matches,
        "conflict_count": len(conflicts),
        "rejected_count": len(rejected),
        "earliest_date": earliest,
        "latest_date": latest,
        "conflicts": conflicts[:50],
        "rejected": rejected[:50],
        "coverage_status": (
            "NOT VERIFIED - scheduled drawing "
            "date completeness requires "
            "independent verification"
        ),
        "historical_rules_status": (
            "NOT VERIFIED for all pre-2015 eras"
        ),
    }

    save_json("data_audit.json", audit)
    return audit


def generate_weighted(history, rng):
    """
    Frequency-based research candidate.

    Counts prior appearances, then samples
    without replacement.

    This is a hypothesis to test, not a
    demonstrated prediction advantage.
    """

    white_counts = Counter()
    red_counts = Counter()

    for record in history:
        white_counts.update(record["white"])
        red_counts[record["powerball"]] += 1

    available = list(range(1, 70))
    chosen = []

    for _ in range(5):
        weights = [
            white_counts[n] + 1
            for n in available
        ]

        selected = rng.choices(
            available,
            weights=weights,
            k=1
        )[0]

        chosen.append(selected)
        available.remove(selected)

    red_options = list(range(1, 27))
    red_weights = [
        red_counts[n] + 1
        for n in red_options
    ]

    red = rng.choices(
        red_options,
        weights=red_weights,
        k=1
    )[0]

    return sorted(chosen), red


def generate_random(rng):
    return (
        sorted(rng.sample(range(1, 70), 5)),
        rng.randint(1, 26)
    )


def score_pick(pick, actual):
    white, red = pick

    return {
        "white_matches": len(
            set(white) & set(actual["white"])
        ),
        "powerball_match": int(
            red == actual["powerball"]
        )
    }


def run_backtest(history):
    """
    Walk-forward evaluation.

    Only uses past drawings for each prediction.
    Tests current-format draws only.
    """

    eligible = [
        i for i, r in enumerate(history)
        if parse_date(r["date"])
        >= CURRENT_FORMAT_START
        and i >= MIN_TRAINING_DRAWS
    ]

    eligible = eligible[-BACKTEST_DRAWS:]

    if not eligible:
        raise ValueError(
            "No eligible current-format test draws"
        )

    rng = random.Random(RANDOM_SEED)
    results = []

    for i in eligible:
        actual = history[i]

        # Training includes only earlier draws
        # under the same 2015+ game format.
        training = [
            r for r in history[:i]
            if parse_date(r["date"])
            >= CURRENT_FORMAT_START
        ]

        if len(training) < MIN_TRAINING_DRAWS:
            continue

        model_pick = generate_weighted(
            training, rng
        )

        model_score = score_pick(
            model_pick, actual
        )

        random_scores = [
            score_pick(
                generate_random(rng),
                actual
            )
            for _ in range(RANDOM_TRIALS)
        ]

        random_white_avg = statistics.mean(
            s["white_matches"]
            for s in random_scores
        )

        random_red_rate = statistics.mean(
            s["powerball_match"]
            for s in random_scores
        )

        results.append({
            "draw_date": actual["date"],
            "model_white": " ".join(
                map(str, model_pick[0])
            ),
            "model_powerball": model_pick[1],
            "model_white_matches":
                model_score["white_matches"],
            "model_powerball_match":
                model_score["powerball_match"],
            "random_white_average":
                round(random_white_avg, 4),
            "random_powerball_rate":
                round(random_red_rate, 4),
        })

    if not results:
        raise ValueError(
            "Not enough current-format training data"
        )

    path = OUTPUT / "backtest_results.csv"

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0].keys())
        )
        writer.writeheader()
        writer.writerows(results)

    model_white = statistics.mean(
        r["model_white_matches"]
        for r in results
    )

    random_white = statistics.mean(
        r["random_white_average"]
        for r in results
    )

    model_red = statistics.mean(
        r["model_powerball_match"]
        for r in results
    )

    random_red = statistics.mean(
        r["random_powerball_rate"]
        for r in results
    )

    comparison = {
        "model": "Historical Frequency v1",
        "evaluation": "Walk-forward",
        "tested_drawings": len(results),
        "random_trials_per_draw": RANDOM_TRIALS,
        "model_avg_white_matches":
            round(model_white, 4),
        "random_avg_white_matches":
            round(random_white, 4),
        "model_powerball_hit_rate":
            round(model_red, 4),
        "random_powerball_hit_rate":
            round(random_red, 4),
        "theoretical_random_white_average":
            round(25 / 69, 4),
        "theoretical_random_red_hit_rate":
            round(1 / 26, 4),
        "model_minus_random_white":
            round(model_white - random_white, 4),
        "model_minus_random_red":
            round(model_red - random_red, 4),
        "conclusion": (
            "Exploratory results only. "
            "No predictive advantage established. "
            "Statistical uncertainty and additional "
            "out-of-sample validation are required."
        ),
    }

    save_json(
        "model_comparison.json",
        comparison
    )

    return comparison


def create_latest_research(history):
    current = [
        r for r in history
        if parse_date(r["date"])
        >= CURRENT_FORMAT_START
    ]

    rng = random.Random(RANDOM_SEED + 1)

    model_pick = generate_weighted(
        current, rng
    )

    random_pick = generate_random(rng)

    research = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "latest_known_draw": history[-1]["date"],
        "historical_frequency_candidate": {
            "white": model_pick[0],
            "powerball": model_pick[1],
        },
        "random_baseline_candidate": {
            "white": random_pick[0],
            "powerball": random_pick[1],
        },
        "warning": (
            "Research combinations only. "
            "Neither has a demonstrated "
            "advantage in a random lottery."
        ),
    }

    save_json(
        "latest_research.json",
        research
    )

    return research


def main():
    print("=" * 55)
    print("DOC'S POWERBALL AI LAB")
    print("HISTORICAL DATA + RESEARCH ENGINE")
    print("=" * 55)

    try:
        archive, archive_rejected = load_archive()
        ny, ny_rejected = load_new_york()
    except Exception as exc:
        print("SOURCE DOWNLOAD FAILED:", exc)
        print(
            "Check the archive URL and source "
            "availability. No results were generated."
        )
        raise

    history, conflicts, matches = merge_history(
        archive, ny
    )

    audit = audit_data(
        history,
        archive,
        ny,
        archive_rejected + ny_rejected,
        conflicts,
        matches
    )

    print("\nDATA AUDIT")
    print("Historical records:", len(archive))
    print("NY records:", len(ny))
    print("Unique drawings:", len(history))
    print("Matching overlaps:", matches)
    print("Conflicts:", len(conflicts))
    print(
        "Rejected:",
        len(archive_rejected) + len(ny_rejected)
    )
    print("Earliest:", audit["earliest_date"])
    print("Latest:", audit["latest_date"])

    # Stop rather than train on unresolved conflicts
    # or rejected records.
    if conflicts or archive_rejected or ny_rejected:
        raise RuntimeError(
            "Data audit requires review. "
            "See data/data_audit.json. "
            "Backtesting stopped."
        )

    if not history:
        raise RuntimeError("No history available")

    save_history(history)

    print("\nRUNNING WALK-FORWARD BACKTEST...")

    comparison = run_backtest(history)

    print(
        json.dumps(comparison, indent=2)
    )

    research = create_latest_research(history)

    print("\nLATEST RESEARCH CANDIDATES")
    print(
        json.dumps(research, indent=2)
    )

    print("\nENGINE RUN COMPLETE")
    print("Output folder: data/")


if __name__ == "__main__":
    main()
