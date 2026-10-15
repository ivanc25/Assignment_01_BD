import json
import random
from pathlib import Path


# Resolve paths relative to this script, not the terminal directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

SIZES = [16, 32, 64, 128, 256, 512]
BASE_SEED = 42
MIN_VALUE = -5
MAX_VALUE = 5


def write_case(path, matrix_a, matrix_b):
    """Write n, then the rows of A, then the rows of B."""
    n = len(matrix_a)

    assert n > 0
    assert len(matrix_b) == n
    assert all(len(row) == n for row in matrix_a)
    assert all(len(row) == n for row in matrix_b)

    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(f"{n}\n")

        for matrix in (matrix_a, matrix_b):
            for row in matrix:
                file.write(" ".join(format(value, ".17g") for value in row))
                file.write("\n")


def write_expected(path, matrix):
    """Write the expected result separately from the input."""
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(f"{len(matrix)}\n")

        for row in matrix:
            file.write(" ".join(format(value, ".17g") for value in row))
            file.write("\n")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Expected results are specified independently of the future algorithms.
    test_cases = [
        (
            "known",
            [[1.0, 2.0], [3.0, 4.0]],
            [[5.0, 6.0], [7.0, 8.0]],
            [[19.0, 22.0], [43.0, 50.0]],
        ),
        (
            "identity",
            [[2.0, -3.0], [4.0, 5.0]],
            [[1.0, 0.0], [0.0, 1.0]],
            [[2.0, -3.0], [4.0, 5.0]],
        ),
        (
            "zero",
            [[2.0, -3.0], [4.0, 5.0]],
            [[0.0, 0.0], [0.0, 0.0]],
            [[0.0, 0.0], [0.0, 0.0]],
        ),
        (
            "fractional",
            [[0.5, -1.0], [1.5, 2.0]],
            [[2.0, 0.25], [-0.5, 1.0]],
            [[1.5, -0.875], [2.0, 2.375]],
        ),
    ]

    for name, matrix_a, matrix_b, expected in test_cases:
        write_case(DATA_DIR / f"test_{name}.txt", matrix_a, matrix_b)
        write_expected(DATA_DIR / f"test_{name}_expected.txt", expected)
        print(f"Created correctness test: {name}")

    datasets = []

    for n in SIZES:
        # A separate seed per size makes generation independent of size order.
        seed = BASE_SEED + n
        rng = random.Random(seed)

        matrix_a = [
            [float(rng.randint(MIN_VALUE, MAX_VALUE)) for _ in range(n)]
            for _ in range(n)
        ]
        matrix_b = [
            [float(rng.randint(MIN_VALUE, MAX_VALUE)) for _ in range(n)]
            for _ in range(n)
        ]

        filename = f"input_n{n}.txt"
        write_case(DATA_DIR / filename, matrix_a, matrix_b)

        datasets.append({
            "file": filename,
            "n": n,
            "seed": seed,
        })

        print(f"Created benchmark input: {filename}")

    metadata = {
        "generator": "Python random.Random (Mersenne Twister)",
        "base_seed": BASE_SEED,
        "seed_rule": "base_seed + n; generate A first, then B, row by row",
        "sampling": "randint, inclusive bounds",
        "value_range": [MIN_VALUE, MAX_VALUE],
        "numeric_type": "float64",
        "input_format": "Text: n on first line, then n rows of A and n rows of B",
        "datasets": datasets,
    }

    metadata_path = DATA_DIR / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Created metadata.json")
    print("Input generation completed.")


if __name__ == "__main__":
    main()