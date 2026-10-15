import argparse
import json
import subprocess
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent

TIME_LIMIT_S = 120
MEMORY_LIMIT_BYTES = 1024 ** 3
POLL_INTERVAL_S = 0.01


def main():
    parser = argparse.ArgumentParser(
        description="Monitor one preliminary benchmark process."
    )
    parser.add_argument("method", choices=("python", "java", "c"))
    parser.add_argument("--size", type=int, default=64)
    args = parser.parse_args()

    if args.size <= 0:
        parser.error("--size must be positive.")

    input_path = PROJECT_ROOT / "data" / f"input_n{args.size}.txt"

    if not input_path.is_file():
        parser.error(f"Input file not found: {input_path}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = (
        PROJECT_ROOT / "results"
        / f"monitor_{args.method}_n{args.size}_{run_id}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    if args.method == "python":
        command = [
            sys.executable,
            "scripts/benchmark_python.py",
            "--size", str(args.size),
            "--warmups", "3",
            "--repetitions", "5",
        ]
    elif args.method == "java":
        command = [
            "java", "-cp", "src/java", "MatrixJava",
            "--benchmark", str(input_path), "100", "5",
        ]
    else:
        command = [
            str(PROJECT_ROOT / "src" / "c" / "matrix_c.exe"),
            "--benchmark", str(input_path),
            str((run_dir / "timings.csv").relative_to(PROJECT_ROOT)),
        ]

    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"

    samples = []
    status = "running"
    error = None
    return_code = None
    process = None

    print(f"Starting {args.method}, n = {args.size}")
    print("Limits: 120 s, 1024 MiB of resident memory")

    start = time.perf_counter()

    with stdout_path.open("w", encoding="utf-8") as stdout_file, \
            stderr_path.open("w", encoding="utf-8") as stderr_file:
        try:
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            process = psutil.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=stdout_file,
                stderr=stderr_file,
                env=child_env,
            )

            while True:
                # Read memory before checking whether the process has exited.
                try:
                    info = process.memory_info()

                    # Field names may differ between psutil versions.
                    peak = getattr(info, "peak_wset", None)
                    if peak is None:
                        peak = getattr(info, "peak_rss", None)

                    samples.append({
                        "elapsed_s": time.perf_counter() - start,
                        "rss_bytes": info.rss,
                        "os_peak_bytes": peak,
                    })

                    observed = max(info.rss, peak or 0)
                    if observed > MEMORY_LIMIT_BYTES:
                        status = "memory_limit"
                        break

                except psutil.NoSuchProcess:
                    pass

                if process.poll() is not None:
                    status = (
                        "completed" if process.returncode == 0
                        else "process_error"
                    )
                    break

                if time.perf_counter() - start >= TIME_LIMIT_S:
                    status = "timeout"
                    break

                time.sleep(POLL_INTERVAL_S)

        except (OSError, psutil.Error) as exc:
            status = "monitor_error"
            error = str(exc)

        finally:
            if process is not None:
                if process.poll() is None:
                    try:
                        process.kill()
                    except psutil.NoSuchProcess:
                        pass
                return_code = process.wait()

    wall_time_s = time.perf_counter() - start

    sampled_max = max(
        (sample["rss_bytes"] for sample in samples),
        default=None,
    )
    os_peaks = [
        sample["os_peak_bytes"]
        for sample in samples
        if sample["os_peak_bytes"] is not None
    ]
    observed_os_peak = max(os_peaks, default=None)

    summary = {
        "phase": "pilot",
        "method": args.method,
        "n": args.size,
        "command": command,
        "psutil_version": psutil.__version__,
        "status": status,
        "return_code": return_code,
        "error": error,
        "process_wall_time_s": wall_time_s,
        "time_limit_s": TIME_LIMIT_S,
        "memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "requested_poll_interval_s": POLL_INTERVAL_S,
        "memory_sample_count": len(samples),
        "sampled_max_rss_bytes": sampled_max,
        "observed_os_peak_bytes": observed_os_peak,
        "memory_scope": "Child process only; includes loading and runtime",
        "limitation": (
            "Polling may miss the final process interval. "
            "Limits are checked periodically, not enforced by the OS."
        ),
    }

    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "memory_samples.json").write_text(
        json.dumps(samples, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Status: {status}")
    print(f"Process wall time: {wall_time_s:.3f} s")
    print(f"Memory samples: {len(samples)}")

    if sampled_max is not None:
        print(f"Sampled maximum RSS: {sampled_max / 1024**2:.3f} MiB")
    else:
        print("Sampled maximum RSS: unavailable")

    if observed_os_peak is not None:
        print(f"Observed OS peak: {observed_os_peak / 1024**2:.3f} MiB")

    print(f"Monitoring files saved to: {run_dir}")

    if error:
        print(f"Monitoring error: {error}")

    print("\n--- Benchmark output ---")
    print(stdout_path.read_text(encoding="utf-8", errors="replace"))

    stderr_text = stderr_path.read_text(
        encoding="utf-8", errors="replace"
    )
    if stderr_text:
        print("--- Benchmark errors ---")
        print(stderr_text)


if __name__ == "__main__":
    main()