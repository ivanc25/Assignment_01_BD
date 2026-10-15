"""Analyze controlled matrix benchmarks. Requires matplotlib; raw files are never modified."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median, quantiles
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=root/'results/final')
    parser.add_argument('--output', type=Path, default=root/'results/analysis')
    parser.add_argument('--plots', type=Path, default=root/'plots')
    parser.add_argument('--data', type=Path, default=root/'data')
    args = parser.parse_args()
    groups, hashes, checksums = defaultdict(list), defaultdict(set), defaultdict(set)
    runs, partial = [], []
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    for path in sorted(args.input.glob('*/summary.json')):
        s = json.loads(path.read_text(encoding='utf-8'))
        with (path.parent/'timings.csv').open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        name, n = s['method'], s['n']
        context = path.parent.name
        require(s['phase']=='final' and name in ('python','java','c'), context+': invalid phase/method')
        require(len(rows)==s['samples_saved'], context+': sample count mismatch')
        require(s['warmups']==(100 if name=='java' else 3), context+': unexpected warmups')
        require(s['batch']==max(1,min(4096,(128//n)**3)), context+': unexpected batch')
        require(s['repetitions_requested']==5 and s['timeout_s']==120 and s['memory_budget_bytes']==1024**3, context+': protocol mismatch')
        hashes[n].add(s['input_sha256'])
        values=[]
        for i,r in enumerate(rows,1):
            require(r['method']==name and int(r['n'])==n and r['phase']=='final', context+': row identity mismatch')
            require(r['numeric_type']=='float64' and r['loop_order']=='ijk' and int(r['compute_threads'])==1, context+': kernel mismatch')
            require(int(r['repetition'])==i and int(r['batch'])==s['batch'] and int(r['warmups'])==s['warmups'], context+': row protocol mismatch')
            t=float(r['time_per_multiply_ns'])
            require(math.isfinite(t) and t>0 and math.isclose(t*s['batch'],float(r['total_kernel_ns']),rel_tol=1e-10), context+': invalid timing')
            require(math.isfinite(float(r['checksum'])),context+': invalid checksum')
            checksums[n].add(float(r['checksum']))
            values.append(t/1e6)
            if s['status']!='completed':
                partial.append(dict(run=context,method=name,n=n,status=s['status'],sample=i,time_ms=t/1e6))
        complete=s['status']=='completed'
        require(s['status'] in ('completed','timeout'), context+': unexpected status')
        mid=iqr=None
        if complete:
            require(len(values)==5 and s['return_code']==0 and s['os_peak_at_ready_bytes'] is not None,context+': incomplete successful run')
            mid=median(values)
            q=quantiles(values,n=4,method='inclusive')
            iqr=q[2]-q[0]
            require(math.isclose(mid,s['median_ms'],abs_tol=1e-8) and math.isclose(iqr,s['iqr_ms'],abs_tol=1e-8),context+': summary mismatch')
        run=dict(run=context,method=name,n=n,status=s['status'],samples_saved=len(rows),batch=s['batch'],warmups=s['warmups'],median_ms=mid,iqr_ms=iqr,peak_ready_mib=s['os_peak_at_ready_bytes']/1024**2 if s['os_peak_at_ready_bytes'] is not None else None,observed_peak_mib=s['observed_os_peak_bytes']/1024**2 if s['observed_os_peak_bytes'] is not None else None,process_wall_s=s['process_wall_s'],input_sha256=s['input_sha256'])
        runs.append(run)
        groups[name,n].append(run)
    require(len(runs)==36 and set(groups)=={(m,n) for m in ('python','java','c') for n in (64,128,256,512)},'Expected 36 runs across 12 configurations')
    verified_inputs=[]
    for n, h in hashes.items():
        require(len(h)==1,f'n={n}: inconsistent input hashes')
        require(len(checksums[n])==1,f'n={n}: checksum disagreement')
        file=args.data/f'input_n{n}.txt'
        if file.exists():
            require(hashlib.sha256(file.read_bytes()).hexdigest() in h,f'n={n}: local input hash mismatch')
            verified_inputs.append(n)
    aggregates=[]
    for (name,n),items in sorted(groups.items()):
        require(len(items)==3,f'{name}/{n}: expected 3 independent processes')
        good=[r for r in items if r['status']=='completed']
        a=dict(method=name,n=n,runs=len(items),completed_runs=len(good),timeouts=sum(r['status']=='timeout' for r in items),saved_samples=sum(r['samples_saved'] for r in items))
        for source,prefix in [('median_ms','time_ms'),('peak_ready_mib','peak_mib')]:
            v=[r[source] for r in good]
            for stat,fn in [('median',median),('min',min),('max',max)]:
                a[prefix+'_'+stat]=fn(v) if len(good)==3 else None
        a['time_ns_per_n3']=a['time_ms_median']*1e6/n**3 if len(good)==3 else None
        aggregates.append(a)
    args.output.mkdir(parents=True,exist_ok=True)
    args.plots.mkdir(parents=True,exist_ok=True)
    write_csv(args.output/'runs.csv',runs)
    write_csv(args.output/'configurations.csv',aggregates)
    write_csv(args.output/'timeouts.csv',[r for r in runs if r['status']=='timeout'])
    if partial:
        write_csv(args.output/'partial_samples.csv',partial)
    audit=dict(runs=len(runs),completed=sum(r['status']=='completed' for r in runs),timeouts=sum(r['status']=='timeout' for r in runs),saved_samples=sum(r['samples_saved'] for r in runs),local_inputs_hash_verified=sorted(verified_inputs),checks='Protocol, row counts, timing arithmetic, medians/IQR, shared hashes and checksums validated.',aggregation='Median of three independent process medians; whiskers min/max of these medians, not a confidence interval.',matplotlib_version=matplotlib.__version__)
    (args.output/'validation.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    colors={'python':'#2563eb','java':'#b45309','c':'#15803d'}
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    for kind,title,ylabel in [('time','Matrix multiplication time','Time per multiplication (ms, log scale)'),('memory','Worker process peak resident memory','Peak resident memory (MiB, log scale)'),('normalized','Time normalized by matrix size cubed','Time / n³ (ns, log scale)')]:
        fig,ax=plt.subplots(figsize=(8.4,5.6))
        for method in ('python','java','c'):
            selected=sorted([a for a in aggregates if a['method']==method and a['completed_runs']==3],key=lambda a:a['n'])
            xs=[a['n'] for a in selected]
            prefix='peak_mib' if kind=='memory' else 'time_ms'
            scales=[1e6/a['n']**3 if kind=='normalized' else 1 for a in selected]
            ys=[a[prefix+'_median']*scale for a,scale in zip(selected,scales)]
            low=[(a[prefix+'_median']-a[prefix+'_min'])*scale for a,scale in zip(selected,scales)]
            high=[(a[prefix+'_max']-a[prefix+'_median'])*scale for a,scale in zip(selected,scales)]
            ax.errorbar(xs,ys,yerr=[low,high],marker='o',capsize=5,color=colors[method],label={'python':'Python','java':'Java','c':'C'}[method])
        ax.set_xscale('log',base=2)
        ax.set_yscale('log')
        ax.set_xticks([64,128,256,512],labels=['64','128','256','512'])
        ax.set_xlabel('Matrix dimension n')
        ax.set_ylabel(ylabel)
        ax.set_title(title,pad=14)
        ax.grid(True,which='major',alpha=.2)
        ax.legend()
        note='Points: median across 3 processes. Bars: min–max across processes.\nPython n=512: 3 timeouts (120 s per process); excluded from complete-run estimates.'
        if kind=='memory':
            note+='\nPeak covers startup through READY, including loading, runtime and warm-ups.'
        fig.text(.08,.025,note,fontsize=9,color='#374151')
        fig.tight_layout(rect=(0,.15 if kind=='memory' else .12,1,1))
        fig.savefig(args.plots/f'{kind}.png',dpi=180)
        plt.close(fig)
    print(json.dumps(audit,indent=2))
    for a in aggregates:
        print(a['method'],a['n'],a['time_ms_median'])

if __name__=='__main__':
    main()
