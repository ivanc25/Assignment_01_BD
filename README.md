# Assignment 1 — Matrix Multiplication

**Ivan Giacomo Colella** · BIG DATA · ULPGC · 2026–2027

Comparison of basic dense matrix multiplication in **Python, Java and C**, using explicit i–j–k loops, flat row-major arrays and 64-bit floating-point values.

## Contents

- `src/`: implementations in the three languages.
- `scripts/`: input generation, correctness checks, benchmarks and analysis.
- `data/`: shared inputs, expected outputs and metadata.
- `results/final/`: original measurements, including timeouts.
- `results/analysis/`: summary tables and validation results.
- `plots/`: runtime, memory and scaling figures.
- `report/Assignment01_Report.pdf`: full research report.

## Requirements

The complete benchmark requires **Windows**, Python 3.13.5, JDK 21 and GCC. Recorded versions: Temurin 21.0.12.1 and GCC 16.2.0 (UCRT64). Run commands from the project root, preferably in a Python virtual environment.

```powershell
python -m pip install numpy==2.5.4 psutil==7.2.2 matplotlib==3.10.8
```

## Reproduce tables and plots

The original measurements are included. No new benchmark is needed:

```powershell
python scripts/analyze_results.py
```

## Build and test

```powershell
javac src/java/MatrixJava.java
gcc -std=c11 -O2 -ffp-contract=off -Wall -Wextra src/c/matrix_c.c -o src/c/matrix_c.exe -lm
python src/python/matrix_python.py --test
java -cp src/java MatrixJava --test data
.\src\c\matrix_c.exe --test data
```

All implementations passed six correctness tests. NumPy provides reference results only; it is not used in the measured kernels. To regenerate the supplied inputs and reference tests:

```powershell
python scripts/generate_inputs.py
python scripts/prepare_reference_tests.py
```

## Benchmark protocol and results

Final sizes: **64, 128, 256 and 512**. Each configuration uses three independent processes and five measured samples per process. Warm-ups: Python/C 3, Java 100. At n=64, each sample averages eight individually timed calls; otherwise it contains one call. Budgets: **120 s per process and 1024 MiB resident memory**.

| n | Python (ms) | Java (ms) | C (ms) |
|---:|---:|---:|---:|
| 64 | 50.200 | 0.403 | 0.275 |
| 128 | 306.723 | 2.176 | 1.929 |
| 256 | 2411.224 | 27.624 | 24.818 |
| 512 | Timeout in 3/3 runs | 315.729 | 220.900 |

Values are medians of the three process medians. Plot bars show their minimum–maximum range, not confidence intervals. Timing covers the multiplication kernel; memory is the worker's cumulative resident peak from startup through READY, including loading and warm-up.

**33 of 36 processes completed.** Python n=512 partial samples are retained separately and excluded from complete-run estimates. A timeout concerns the whole process, not one multiplication. Conclusions apply to the tested implementations and hardware.

## Collect new measurements

For a small check, run `python scripts/run_controlled.py python --size 64`; replace `python` with `java` or `c` to test the other workers. The default output phase is `validation`.

For a new full campaign, use a separate project copy and preserve the supplied `results/final/` under another name before running:

```powershell
$orders = @("python,java,c", "java,c,python", "c,python,java")
foreach ($n in @(64,128,256,512)) {
    foreach ($order in $orders) {
        foreach ($method in $order.Split(",")) {
            python scripts/run_controlled.py $method --size $n --phase final
        }
    }
}
python scripts/analyze_results.py
```

Do not mix new runs with the original final dataset: analysis expects exactly 36 processes. Earlier pilot and validation records are not included in final analysis.
