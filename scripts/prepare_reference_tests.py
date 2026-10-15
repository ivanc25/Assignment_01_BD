import json
from pathlib import Path

import numpy as np

from generate_inputs import write_case, write_expected


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def main():
    reference_cases = []

    for n in (16, 32):
        input_path = DATA_DIR / f"input_n{n}.txt"

        # Read the same input file used by the student implementations.
        with input_path.open("r", encoding="utf-8") as file:
            file_n = int(file.readline())
            values = np.loadtxt(file, dtype=np.float64)

        if file_n != n or values.shape != (2 * n, n):
            raise ValueError(f"Unexpected input format: {input_path}")

        a = values[:n, :]
        b = values[n:, :]

        # NumPy is used only as an independent correctness reference.
        expected = a @ b

        if not np.isfinite(expected).all():
            raise ValueError("The reference contains non-finite values.")

        name = f"random{n}"

        write_case(
            DATA_DIR / f"test_{name}.txt",
            a.tolist(),
            b.tolist(),
        )
        write_expected(
            DATA_DIR / f"test_{name}_expected.txt",
            expected.tolist(),
        )

        reference_cases.append({
            "name": name,
            "source_input": input_path.name,
            "n": n,
            "reference": "numpy.matmul",
        })

        print(f"Created reference test: {name} ({n} x {n})")

    metadata = {
        "numpy_version": np.__version__,
        "numeric_type": "float64",
        "purpose": "Correctness validation only; not a benchmark method",
        "cases": reference_cases,
    }

    (DATA_DIR / "reference_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Reference test preparation completed.")


if __name__ == "__main__":
    main()