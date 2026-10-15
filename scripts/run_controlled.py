"""Controlled Windows benchmark. Default phase is validation, not final."""
import argparse
import csv
import hashlib
import json
import math
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('method', choices=['python', 'java', 'c'])
    parser.add_argument('--size', type=int, default=64)
    parser.add_argument('--phase', choices=['validation', 'final'], default='validation')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This monitor requires Windows OS peak-memory counters.')
    if args.size <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('Size and timeout must be positive and finite.')
    source = ROOT / 'data' / f'input_n{args.size}.txt'
    if not source.is_file():
        parser.error(f'Missing input: {source}')
    warmups = 100 if args.method == 'java' else 3
    batch = max(1, min(4096, (128 // args.size) ** 3))
    repetitions = 5
    budget = 1024 ** 3
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder = ROOT / 'results' / args.phase / f'{args.method}_n{args.size}_{run_id}'
    folder.mkdir(parents=True)
    tail = [str(source), str(warmups), str(repetitions), str(batch)]
    if args.method == 'python':
        command = [sys.executable, '-u', str(ROOT/'scripts/worker_python.py'), *tail]
    elif args.method == 'java':
        command = ['java', '-cp', str(ROOT/'src/java'), 'MatrixJava', '--stream', *tail]
    else:
        command = [str(ROOT/'src/c/matrix_c.exe'), '--stream', *tail]
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    messages = queue.Queue()
    rows = []
    peak = None
    ready_peak = None
    status = 'running'
    error = None
    proc = None
    released = False
    sample_count = 0
    protocol_seconds = None
    fields = ['phase', 'method', 'n', 'numeric_type', 'loop_order', 'compute_threads',
              'warmups', 'repetition', 'batch', 'total_kernel_ns', 'time_per_multiply_ns', 'checksum']
    start = time.perf_counter()
    print(f'{args.phase}: {args.method}, n={args.size}, warmups={warmups}, batch={batch}', flush=True)
    with (folder/'timings.csv').open('w', newline='', encoding='utf-8') as tf, \
         (folder/'memory_samples.csv').open('w', newline='', encoding='utf-8') as mf, \
         (folder/'stdout.txt').open('w', encoding='utf-8') as log, \
         (folder/'stderr.txt').open('w', encoding='utf-8') as err:
        writer = csv.DictWriter(tf, fieldnames=fields)
        writer.writeheader(); tf.flush()
        memory = csv.writer(mf)
        memory.writerow(['elapsed_s', 'rss_bytes', 'os_peak_bytes'])
        def snapshot():
            nonlocal peak, sample_count
            info = proc.memory_info()
            value = getattr(info, 'peak_wset', getattr(info, 'peak_rss', None))
            if value is None:
                raise RuntimeError('OS peak counter unavailable; do not substitute sampled RSS.')
            peak = max(peak or 0, value)
            sample_count += 1
            memory.writerow([time.perf_counter()-start, info.rss, value])
            return value
        try:
            proc = psutil.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=err, text=True,
                                encoding='utf-8', bufsize=1)
            def read_output():
                try:
                    for line in proc.stdout:
                        messages.put(line)
                finally:
                    messages.put(None)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            while True:
                try:
                    snapshot()
                except psutil.NoSuchProcess:
                    pass
                if peak is not None and peak > budget:
                    status = 'memory_limit'; break
                if time.perf_counter()-start >= args.timeout:
                    status = 'timeout'; break
                try:
                    line = messages.get(timeout=0.01)
                except queue.Empty:
                    continue
                if line is None:
                    code = proc.wait(timeout=5)
                    status = 'completed' if released and len(rows)==repetitions and code==0 else 'process_error'
                    break
                log.write(line); log.flush()
                parts = line.strip().split('\t')
                if parts[0] == 'SAMPLE':
                    rep, count = int(parts[1]), int(parts[2])
                    elapsed, checksum = float(parts[3]), float(parts[4])
                    if (len(parts)!=5 or rep != len(rows)+1 or count != batch
                        or rep > repetitions or elapsed <= 0
                        or not math.isfinite(elapsed) or not math.isfinite(checksum)):
                        raise ValueError('Invalid sample from worker')
                    row = dict(zip(fields, [args.phase, args.method, args.size, 'float64', 'ijk', 1,
                               warmups, rep, batch, elapsed, elapsed/batch, checksum]))
                    writer.writerow(row); tf.flush()
                    rows.append(row)
                    print(f'  sample {rep}/{repetitions}: {elapsed/batch/1e6:.3f} ms', flush=True)
                elif parts == ['READY']:
                    if released or len(rows) != repetitions:
                        raise ValueError('Unexpected READY')
                    ready_peak = snapshot()
                    protocol_seconds = time.perf_counter()-start
                    if ready_peak > budget:
                        status = 'memory_limit'; break
                    proc.stdin.write('RELEASE\n'); proc.stdin.flush()
                    released = True
                else:
                    raise ValueError(f'Unexpected worker output: {line!r}')
        except Exception as exc:
            status = 'monitor_error'; error = str(exc)
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
                if 'reader' in locals():
                    reader.join(timeout=2)
                for pipe in (proc.stdin, proc.stdout):
                    if pipe:
                        pipe.close()
    summary = {
        'phase': args.phase, 'method': args.method, 'n': args.size, 'status': status,
        'error': error, 'return_code': proc.returncode if proc else None,
        'command': command, 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'warmups': warmups, 'repetitions_requested': repetitions, 'samples_saved': len(rows),
        'batch': batch, 'timeout_s': args.timeout, 'memory_budget_bytes': budget,
        'process_wall_s': time.perf_counter()-start, 'protocol_until_ready_s': protocol_seconds,
        'os_peak_at_ready_bytes': ready_peak, 'observed_os_peak_bytes': peak,
        'memory_sample_count': sample_count, 'psutil_version': psutil.__version__,
        'memory_scope': 'Worker process from startup to READY; includes loading, runtime, warmups and output. Excludes monitor and post-RELEASE shutdown.',
        'timing_scope': 'Sum of individually timed kernel calls divided by batch; result consumption and CSV writes excluded. Timer overhead remains.',
        'limits': 'Polling-based soft limits; timeout runs have incomplete memory coverage and partial samples, not a complete configuration.'
    }
    if status == 'completed':
        times = [r['time_per_multiply_ns']/1e6 for r in rows]
        q1, _, q3 = statistics.quantiles(times, n=4, method='inclusive')
        summary.update(median_ms=statistics.median(times), iqr_ms=q3-q1)
        print(f'Median: {summary["median_ms"]:.3f} ms | IQR: {summary["iqr_ms"]:.3f} ms')
    (folder/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(f'Status: {status} | Samples saved: {len(rows)}/{repetitions}')
    if ready_peak is not None:
        print(f'OS peak at READY: {ready_peak/1024**2:.3f} MiB')
    if error:
        print(error)
    print(f'Files: {folder.relative_to(ROOT)}')
    if status != 'completed':
        print((folder/'stderr.txt').read_text(encoding='utf-8', errors='replace'))
        sys.exit(1)


if __name__ == '__main__':
    main()
