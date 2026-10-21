import json, os, stat, zipfile, hashlib
from pathlib import Path
root=Path('brz')
output=Path('tmp/merge-wayfinding/followups/scale')
def stats(values):
    values=sorted(values)
    return {'count':len(values),'bytes':sum(values),'min':values[0] if values else 0,'p50':values[(len(values)-1)//2] if values else 0,'p95':values[int((len(values)-1)*.95)] if values else 0,'max':values[-1] if values else 0,'buckets':{label:sum(lo<=x<hi for x in values) for label,lo,hi in [('under64KiB',0,65536),('64KiBto1MiB',65536,1048576),('1MiBto16MiB',1048576,16777216),('16MiBplus',16777216,float('inf'))]}}
records=[]; private_map={}
for ordinal,p in enumerate(sorted(root.iterdir()),1):
    if not (p.is_dir() or p.suffix.lower()=='.brz'): continue
    key=f'input-{ordinal:02d}'; private_map[key]=str(p.resolve())
    if p.is_file():
        with zipfile.ZipFile(p) as z:
            entries=[x for x in z.infolist() if not x.is_dir()]
        sizes=[x.file_size for x in entries]
        # central-directory metadata only, without opening member content
        notes=[x.file_size for x in entries if x.filename.lower().endswith(('.md','.html','.htm','.txt'))]
        other=[x.file_size for x in entries if not x.filename.lower().endswith(('.md','.html','.htm','.txt','.json','.xml'))]
        records.append({'id':key,'kind':'brz-central-directory','archive_bytes':p.stat().st_size,'all_members':stats(sizes),'text_like_members':stats(notes),'nontext_nonmetadata_members':stats(other)})
    else:
        notes=[]; other=[]; config=[]; skipped=0
        for base,dirs,files in os.walk(p,followlinks=False):
            dirs[:]=[d for d in dirs if d not in ('.git','.trash','node_modules','__pycache__') and not (Path(base)/d).is_symlink()]
            for name in files:
                f=Path(base)/name
                if f.is_symlink(): skipped+=1; continue
                n=f.stat().st_size
                if '.obsidian' in f.relative_to(p).parts: config.append(n)
                elif f.suffix.lower()=='.md': notes.append(n)
                else: other.append(n)
        records.append({'id':key,'kind':'retained-directory-stat-only','markdown':stats(notes),'other_regular':stats(other),'obsidian_config':stats(config),'skipped_symlinks':skipped})
(output/'aggregate-inventory.json').write_text(json.dumps(records,indent=2)+'\n')
(output/'private-input-map.json').write_text(json.dumps(private_map,indent=2)+'\n')
print(json.dumps(records,indent=2))
