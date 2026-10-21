"""Bounded synthetic whole-vault measurement for issue #252; no production imports."""
from __future__ import annotations
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[3]
OUTPUT = PROJECT / 'tmp/merge-wayfinding/followups/scale'
FROZEN = '273233fb4020ceb156ed6b3ab33785adcedfdda9'
LIMIT_SECONDS = 720

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf8')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def summary(content):
    return {'files':len(content), 'bytes':sum(map(len,content.values())),
            'inventory_sha256':sha(json.dumps({p:[len(b),sha(b)] for p,b in sorted(content.items())},sort_keys=True).encode())}

def allocation(path):
    if os.name != 'nt':
        return path.stat().st_blocks * 512
    high=ctypes.c_ulong(0)
    func=ctypes.windll.kernel32.GetCompressedFileSizeW
    func.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
    func.restype=ctypes.c_ulong
    low=func(str(path),ctypes.byref(high))
    if low == 0xffffffff and ctypes.GetLastError():
        raise OSError('GetCompressedFileSizeW failed')
    return (high.value << 32) + low

def storage(repo, git):
    paths=[p for p in (repo/'.git').rglob('*') if p.is_file()]
    loose=[p for p in (repo/'.git/objects').glob('[0-9a-f][0-9a-f]/*') if p.is_file()]
    return {'git_file_logical_bytes':sum(p.stat().st_size for p in paths),
            'git_file_allocated_bytes':sum(allocation(p) for p in paths),
            'loose_object_logical_bytes':sum(p.stat().st_size for p in loose),
            'loose_object_allocated_bytes':sum(allocation(p) for p in loose),
            'loose_object_files':len(loose),'count_objects_v':git(repo,'count-objects','-v').decode(),
            'allocation_method':'NTFS GetCompressedFileSizeW file streams; excludes directory/MFT metadata'}

def note(i, related=True):
    head=f'---\nid: {i:08d}\n---\n# Synthetic {"incoming" if related else "unrelated author"} note {i}\n'.encode()
    return (head + (b'Bounded synthetic authored prose, local links and context.\r\n' * 50))[:2048]

def fixture():
    sizes=[32768]*40 + [344428]*611 + [8388608]*11 + [17329582]*3
    sizes[651] += 952177
    source={f'Imports/notes/{i:04d}.md':note(i) for i in range(740)}
    for i,n in enumerate(sizes):
        source[f'Imports/attachments/{i:04d}.bin']=hashlib.shake_256(f'synthetic binary {i}'.encode()).digest(n)
    vault=dict(source)
    p='Imports/notes/0000.md'
    vault[p]=source[p][:-28]+b'Local authored current bytes\n'
    vault.update({f'Journal/notes/{i:04d}.md':note(i,False) for i in range(318)})
    vault.update({f'Journal/files/{i:04d}.bin':hashlib.shake_256(f'unrelated binary {i}'.encode()).digest(1048576) for i in range(20)})
    for i,n in enumerate([2,264,264,264,696,5738,2]):
        vault[f'.obsidian/config-{i}.json']=(b'{}'+b' '*n)[:n]
    changed=dict(source)
    changed['Imports/notes/0001.md']=source['Imports/notes/0001.md'][:-14]+b'Incoming edit\n'
    changed['Imports/attachments/0664.bin']=hashlib.shake_256(b'synthetic changed binary 664').digest(17329582)
    result=dict(vault)
    result.update({p:changed[p] for p in ['Imports/notes/0001.md','Imports/attachments/0664.bin']})
    return source,vault,changed,result

def main():
    started=time.perf_counter()
    run=OUTPUT/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    dump(run/'PROTOTYPE-OWNED.json',{'issue':252,'frozen':FROZEN})
    frozen=subprocess.run(['git','show',FROZEN+':prototypes/editable-vault-wayfinder/git/experiment.py'],capture_output=True,check=True).stdout
    frozen_path=run/'frozen-experiment.py'; frozen_path.write_bytes(frozen)
    spec=importlib.util.spec_from_file_location('frozen_scale',frozen_path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.OUTPUT=OUTPUT
    calls=[]; original_git=module.git
    def timed_git(repo,*args,**kwargs):
        if time.perf_counter()-started > LIMIT_SECONDS:
            raise TimeoutError('Declared 720-second measurement boundary reached')
        t=time.perf_counter()
        try:return original_git(repo,*args,**kwargs)
        finally:calls.append({'command':list(args),'seconds':round(time.perf_counter()-t,6)})
    module.git=timed_git
    source,vault,changed,result=fixture()
    expected={'source_initial':summary(source),'vault_initial':summary(vault),'source_changed':summary(changed),'vault_changed':summary(result),
      'attachment_bytes':356971839,'changed_binary_bytes':17329582,
      'raw_unique_payload_blobs_across_source_and_vault_revisions':1753,
      'extra_independent_user_blobs':2,'operation_manifest_blobs':1,
      'final_blob_objects':1756,'final_tree_objects':22,'final_commit_objects':6,'final_total_objects':1784,
      'vault_changed_additional_payload_blobs':2,'unchanged_vault_payloads_reused':1748,
      'expected_user_state_unchanged':True,'expected_files_match_approved_result':True,
      'expected_all_objects_reachable':True,'no_pack_no_gc':True,'wall_bound_seconds':LIMIT_SECONDS}
    dump(run/'expected-before-run.json',expected)
    print('RUN '+str(run),flush=True)
    print('EXPECTED '+json.dumps(expected),flush=True)
    results={'expected':expected,'frozen_commit':FROZEN,'frozen_source_sha256':sha(frozen),
      'author_source_sha256':sha(Path(__file__).read_bytes()),'python':sys.executable,'python_version':sys.version,
      'platform':platform.platform(),'git_executable':shutil.which('git'),'measurements':{}}
    repo=module.initialize(run,'vault',seeded=False)
    try:
        module.put(repo,'Imports/notes/0000.md',b'Independent user base\n')
        module.git(repo,'add','Imports/notes/0000.md'); module.git(repo,'commit','-m','Independent synthetic user history')
        module.git(repo,'branch','independent-branch'); module.git(repo,'tag','independent-tag')
        module.git(repo,'remote','add','origin','https://example.invalid/never-contacted.git')
        module.put(repo,'Imports/notes/0000.md',b'Staged user draft\n'); module.git(repo,'add','Imports/notes/0000.md')
        for p,b in vault.items():module.put(repo,p,b)
        baseline_user=module.user_state(repo)
        results['git_version']=module.git(repo,'--version').decode().strip()
        results['initial_user_state']=baseline_user
        results['storage_initial']=storage(repo,module.git)
        ids={}
        for label,content,ref,parents in [
          ('source_initial',source,module.NS+'source',()),
          ('vault_initial',vault,module.NS+'vault',()),
          ('source_changed',changed,module.NS+'source',()),
          ('vault_changed',result,module.NS+'accepted',None)]:
            t=time.perf_counter(); call_start=len(calls)
            ids[label]=module.snapshot(repo,content,ref,parents if parents is not None else [ids['vault_initial']])
            elapsed=time.perf_counter()-t
            results['measurements'][label]={'elapsed_seconds':round(elapsed,6),'git_processes':len(calls)-call_start,
                'input':summary(content),'commit':ids[label],'storage':storage(repo,module.git)}
            dump(run/'partial-results.json',results)
            print(label+' '+str(round(elapsed,3))+'s',flush=True)
        manifest={'version':1,'status':'applied','pre':ids['vault_initial'],'result':ids['vault_changed'],
          'source':ids['source_changed'],'format':1,'policy':'controlled ordinary/raw bytes',
          'review':'synthetic approved whole change','rows':{}}
        module.persist(repo,manifest)
        for p in ['Imports/notes/0001.md','Imports/attachments/0664.bin']:module.put(repo,p,result[p])
        final_user=module.user_state(repo)
        observed_files=module.files(repo)
        all_objects=module.git(repo,'cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
        counts={kind:sum(line.split()[1]==kind for line in all_objects) for kind in ['blob','tree','commit']}
        reachable={line.split()[0] for line in module.git(repo,'rev-list','--objects','--all').decode().splitlines()}
        objects={line.split()[0] for line in all_objects}
        object_ids={p:hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() for p,b in result.items()}
        # Every expected payload is independently read back through batch raw blob output.
        batch=module.git(repo,'cat-file','--batch',data=('\n'.join(object_ids.values())+'\n').encode())
        offset=0; raw_ok=True
        for p,b in result.items():
            end=batch.index(b'\n',offset); header=batch[offset:end].decode().split(); n=int(header[2]); offset=end+1
            raw_ok=raw_ok and header[0]==object_ids[p] and batch[offset:offset+n]==b
            offset+=n+1
        results.update({'final_user_state':final_user,'final_inventory':summary(observed_files),'object_counts':counts,
          'all_object_count':len(objects),'reachable_object_count':len(reachable),'unreachable_object_count':len(objects-reachable),
          'final_storage':storage(repo,module.git),'converter_refs':module.refs(repo),
          'checks':{'literal_counts_match':counts=={'blob':1756,'tree':22,'commit':6},
            'all_objects_reachable':objects==reachable,'user_state_unchanged':baseline_user==final_user,
            'approved_working_bytes_exact':observed_files==result,'all_result_blobs_raw_exact':raw_ok,
            'source_history_excludes_unrelated_authored':len(module.git(repo,'ls-tree','-r','--name-only',ids['source_changed']).decode().splitlines())==1405,
            'required_commits_reachable':all(oid in reachable for oid in ids.values())}})
        results['total_elapsed_seconds']=round(time.perf_counter()-started,6)
        results['verdict']='PASS' if all(results['checks'].values()) else 'FAIL'
    except Exception as exc:
        results['verdict']='INCOMPLETE'; results['exception']=repr(exc)
        results['total_elapsed_seconds']=round(time.perf_counter()-started,6)
    dump(run/'commands.json',calls)
    dump(run/'results.json',results)
    print('RESULT '+results['verdict']+' '+str(run/'results.json'),flush=True)
    return 0 if results['verdict']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
