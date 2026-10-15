import argparse
import csv
import math
import platform
import statistics
import sys
from array import array
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Import the existing implementation without duplicating the algorithm.
sys.path.insert(0, str(PROJECT_ROOT / "src" / "python"))

from matrix_python import load_input, multiply


def positive_int(value):
    number = int(value)

    if number <= 0:
        raise argparse.ArgumentTypeError("The value must be positive.")

    return number


def main():
    parser = argparse.ArgumentParser(
        description="Preliminary Python kernel timing."
    )
    parser.add_argument("--size", type=positive_int, default=64)
    parser.add_argument("--warmups", type=positive_int, default=3)
    parser.add_argument("--repetitions", type=positive_int, default=5)
    args = parser.parse_args()

    input_path = PROJECT_ROOT / "data" / f"input_n{args.size}.txt"

    # Loading and output allocation are outside the timed region.
    n, a, b = load_input(input_path)

    if n != args.size:
        raise ValueError("Requested size and input dimension differ.")

    c = array("d", [0.0]) * (n * n)

    print(f"Python {platform.python_version()} | n = {n}")
    print(f"Warm-ups: {args.warmups}")
    print(f"Measured repetitions: {args.repetitions}")

    for _ in range(args.warmups):
        multiply(a, b, c, n)

    rows = []
    times_ms = []

    for repetition in range(1, args.repetitions + 1):
        start_ns = perf_counter_ns()
        multiply(a, b, c, n)
        elapsed_ns = perf_counter_ns() - start_ns

        # Consume the result outside the timed region.
        # This checksum does not replace element-by-element validation.
        checksum = math.fsum(c)

        if not math.isfinite(checksum):
            raise ArithmeticError("Non-finite result checksum.")

        times_ms.append(elapsed_ns / 1_000_000)

        rows.append({
            "phase": "pilot",
            "method": "python",
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "input_file": input_path.name,
            "n": n,
            "numeric_type": "float64",
            "loop_order": "ijk",
            "compute_threads": 1,
            "warmups": args.warmups,
            "repetitions": args.repetitions,
            "repetition": repetition,
            "elapsed_ns": elapsed_ns,
            "checksum": checksum,
        })

    # Write and print only after all timed repetitions have finished.
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_path = results_dir / f"pilot_python_n{n}_{run_id}.csv"

    with output_path.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    for index, elapsed_ms in enumerate(times_ms, start=1):
        print(f"Repetition {index}: {elapsed_ms:.3f} ms")

    print(f"Median: {statistics.median(times_ms):.3f} ms")

    if len(times_ms) >= 2:
        q1, _, q3 = statistics.quantiles(
            times_ms, n=4, method="inclusive"
        )
        print(f"IQR: {q3 - q1:.3f} ms")

    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()