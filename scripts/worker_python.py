"""Streaming benchmark worker; run through run_controlled.py."""
import sys
import math
from array import array
from pathlib import Path
from time import perf_counter_ns
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'python'))
from matrix_python import load_input, multiply


def main():
    path, warmups, repetitions, batch = sys.argv[1:]
    warmups, repetitions, batch = map(int, (warmups, repetitions, batch))
    if min(warmups, repetitions, batch) < 1:
        raise ValueError('Counts must be positive')
    n, a, b = load_input(Path(path))
    c = array('d', [0.0]) * (n*n)
    for _ in range(warmups):
        multiply(a, b, c, n)
    for rep in range(1, repetitions + 1):
        elapsed = 0
        for _ in range(batch):
            start = perf_counter_ns()
            multiply(a, b, c, n)
            elapsed += perf_counter_ns() - start
            checksum = math.fsum(c)
            if not math.isfinite(checksum):
                raise ValueError('Non-finite result')
        print(f'SAMPLE\t{rep}\t{batch}\t{elapsed}\t{checksum}', flush=True)
    # Keep arrays alive until the parent has read the OS peak counter.
    print('READY', flush=True)
    if input() != 'RELEASE':
        raise RuntimeError('Missing monitor acknowledgement')


if __name__ == '__main__':
    main()
