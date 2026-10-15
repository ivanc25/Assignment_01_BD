import argparse
import math
from array import array
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

ABS_TOL = 1e-12
REL_TOL = 1e-12


def read_values(path):
    """Read the dimension and numeric values from a text file."""
    tokens = path.read_text(encoding="utf-8").split()

    if not tokens:
        raise ValueError(f"Empty file: {path}")

    n = int(tokens[0])

    if n <= 0:
        raise ValueError("Matrix size must be positive.")

    values = array("d", (float(token) for token in tokens[1:]))

    if values.itemsize != 8:
        raise RuntimeError("This implementation requires 64-bit doubles.")

    if not all(math.isfinite(value) for value in values):
        raise ValueError("Matrix values must be finite.")

    return n, values


def load_input(path):
    """Load A and B as flat arrays stored in row-major order."""
    n, values = read_values(path)
    elements = n * n

    if len(values) != 2 * elements:
        raise ValueError(f"Expected {2 * elements} input values.")

    return n, values[:elements], values[elements:]


def load_expected(path):
    """Load one expected result matrix."""
    n, values = read_values(path)

    if len(values) != n * n:
        raise ValueError(f"Expected {n * n} result values.")

    return n, values


def multiply(a, b, c, n):
    """Compute C = A * B using explicit i-j-k loops."""
    for i in range(n):
        for j in range(n):
            total = 0.0

            for k in range(n):
                total += a[i * n + k] * b[k * n + j]

            c[i * n + j] = total


def check_result(actual, expected):
    """Compare every element using absolute and relative tolerances."""
    if len(actual) != len(expected):
        raise AssertionError("Result lengths differ.")

    for index, (actual_value, expected_value) in enumerate(
        zip(actual, expected)
    ):
        if not math.isclose(
            actual_value,
            expected_value,
            rel_tol=REL_TOL,
            abs_tol=ABS_TOL,
        ):
            raise AssertionError(
                f"Mismatch at index {index}: "
                f"got {actual_value}, expected {expected_value}"
            )


def run_tests():
    """Validate the multiplication against four known results."""
    for name in ("known", "identity", "zero", "fractional", "random16", "random32"):
        n, a, b = load_input(DATA_DIR / f"test_{name}.txt")
        expected_n, expected = load_expected(
            DATA_DIR / f"test_{name}_expected.txt"
        )

        if n != expected_n:
            raise AssertionError("Input and expected dimensions differ.")

        c = array("d", [0.0]) * (n * n)
        multiply(a, b, c, n)
        check_result(c, expected)

        print(f"PASS: {name}")

    print("All correctness tests passed.")


def main():
    parser = argparse.ArgumentParser(
        description="Basic matrix multiplication in Python."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run the known-answer correctness tests.",
    )
    args = parser.parse_args()

    if args.test:
        run_tests()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()