"""Opt-in real GTNH check: import recovery, complex models/NBT and same-PID iteration."""
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import uuid
import numpy as np
from PIL import Image
from example_scene import make
from nbt import parse,encode,setval
from settings import ROOT,RUNTIME,RENDERS
from render_fast import render as draft


def main():
    run='verify-'+uuid.uuid4().hex[:8];scratch=RUNTIME/'checks'/run;scratch.mkdir(parents=True)
    source=make(scratch/'iteration.schematic')
    name,nbt=parse(gzip.decompress(source.read_bytes()))
    def save(n):source.write_bytes(gzip.compress(encode(name,n),mtime=0))
    def native(label,error=None):
        job=run+'-'+label
        proc=subprocess.run([sys.executable,str(ROOT/'render_native.py'),str(source),'--id',job],capture_output=True,text=True,timeout=1000)
        out=RENDERS/job
        if not (out/'result.json').exists():raise RuntimeError('Native process failed before a job report: '+proc.stderr[-3000:])
        result=json.loads((out/'result.json').read_text())
        if error:
            assert proc.returncode!=0 and result['status']=='failed' and error in result['error'],result
            assert not (RUNTIME/'native/worker-request.json').exists()
            print('PASS explicit missing-block error; queue released',flush=True)
            return out,result
        assert proc.returncode==0,proc.stderr
        assert result['status']=='complete' and result['gl_error']==0 and not result['renderer_messages'],result
        assert result['background_worker'] and result['window_hidden'] and not result['mouse_relative_mode'],result
        assert result['tile_entities']==8 and len(result['images'])==6,result
        for filename in result['images']:
            a=np.asarray(Image.open(out/filename));assert np.any(a!=a[0,0],axis=2).sum()>10000
        print('PASS',label,'six native views; eight TileEntities retained; hidden window',flush=True)
        return out,result
    invalid=copy.deepcopy(nbt)
    mapping=invalid.data[b'SchematicaMapping'].data
    mapping[b'preview_missing:stonebrick']=mapping.pop(b'minecraft:stonebrick')
    save(invalid);native('missing','Blocks missing from this client')
    save(nbt);before,br=native('before')
    changed=copy.deepcopy(nbt)
    for tile in changed.data[b'TileEntities'].data[1][2:6]:setval(tile,'BaseName',8,'minecraft:gold_block')
    metadata=bytearray(changed.data[b'Data'].data);metadata[4+(1*15+2)*25+1]=4;changed.data[b'Data'].data=bytes(metadata)
    save(changed);after,ar=native('after');assert br['worker_pid']==ar['worker_pid']
    diff={}
    for filename in ar['images']:
        diff[filename]=int(np.any(np.asarray(Image.open(before/filename))!=np.asarray(Image.open(after/filename)),axis=2).sum())
    assert diff['iso-ne.png']>1000,diff
    fast=draft(source,scratch/'draft.png')
    result={'status':'passed','worker_pid':ar['worker_pid'],'before':str(before),'after':str(after),
            'changed_pixels':diff,'fast_preview':fast,'window_hidden':True,'tile_entities':8}
    (RUNTIME/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS same-path geometry/material iteration and fast preview',flush=True)


if __name__=='__main__':main()
