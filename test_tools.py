"""Offline tests: named IDs, strict NBT, draft output and admission without GTNH."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib
import numpy as np
from PIL import Image
from schematic import read,write
from render_fast import render
from nbt import Tag,encode,setval
from world_crop import chunk
import worker

ROOT=Path(__file__).resolve().parent


class ToolsTest(unittest.TestCase):
    def test_named_high_palette_and_metadata_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.schematic';a=np.array([[[0,256,4095]]],np.uint16);m=np.array([[[0,5,255]]],np.uint16)
            write(p,a,m,{'minecraft:air':0,'test:one':256,'test:two':4095})
            s=read(p);np.testing.assert_array_equal(a,s['blocks']);np.testing.assert_array_equal(m,s['metadata'])

    def test_inspection_uses_xyz_not_reversed_array_axes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.schematic';write(p,np.ones((2,3,5),np.uint16),np.zeros((2,3,5),np.uint16),{'minecraft:air':0,'minecraft:stone':1})
            result=subprocess.run([sys.executable,str(ROOT/'schematic.py'),str(p)],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout)['dimensions_xyz'],[5,2,3])

    def test_fast_has_visible_geometry_and_explicit_approximation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.schematic';out=Path(d)/'a.png'
            write(p,np.ones((2,3,5),np.uint16),np.zeros((2,3,5),np.uint16),{'minecraft:air':0,'minecraft:stone':1})
            result=render(p,out,width=640,height=480)
            self.assertTrue(result['full_cube_preview_only']);self.assertGreater(result['visible_faces'],0)
            pixels=np.asarray(Image.open(out));self.assertGreater(np.any(pixels!=pixels[0,0],axis=2).sum(),1000)

    def test_empty_and_invalid_palette_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.schematic';zero=np.zeros((1,1,1),np.uint16)
            with self.assertRaises(ValueError):write(p,zero+1,zero,{'minecraft:air':0})
            write(p,zero,zero,{'minecraft:air':0})
            with self.assertRaises(ValueError):render(p,Path(d)/'out.png')

    def test_anvil_chunk_read_and_decompression_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Tag(10,{});level=Tag(10,{});root.data[b'Level']=level
            setval(level,'xPos',3,0);setval(level,'zPos',3,0)
            raw=encode(b'',root);payload=zlib.compress(raw)
            region=Path(d)/'region';region.mkdir()
            header=bytearray(8192);header[:4]=(2*256+1).to_bytes(4,'big')
            (region/'r.0.0.mca').write_bytes(header+(len(payload)+1).to_bytes(4,'big')+b'\x02'+payload)
            data,_=chunk(Path(d),0,0,0);self.assertEqual((data['xPos'],data['zPos']),(0,0))
            with patch('world_crop.MAX_NBT',10),self.assertRaisesRegex(ValueError,'Oversized'):
                chunk(Path(d),0,0,0)

    def test_worker_refuses_another_toolkit_owner(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state';state.mkdir();(state/'background-agent.jar').touch()
            instance=Path(d)/'instance';instance.mkdir()
            (instance/'renderer-instance.json').write_text(json.dumps({'source':d,'toolkit':'/another/clone'}))
            with patch.object(worker,'HERE',state),patch.object(worker,'load',return_value={'source':Path(d),'instance':instance}),patch.object(worker,'bindings'):
                with self.assertRaisesRegex(RuntimeError,'another toolkit'):worker.prepare()

    def test_busy_worker_rejected_without_local_config_or_java(self):
        (ROOT/'runtime').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime') as d:
            p=Path(d)/'test.schematic';p.write_bytes(b'input validated before native import')
            with (Path(d)/'worker-render.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                program="""
import sys
from pathlib import Path
sys.path.insert(0,sys.argv.pop(1))
import render_native
render_native.HERE=Path(sys.argv.pop(1))
render_native.worker.start=lambda deadline:sys.exit('worker started despite held lock')
render_native.main()
"""
                proc=subprocess.run([sys.executable,'-c',program,str(ROOT),d,str(p)],capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,2,proc.stderr);self.assertIn('renderer is busy',proc.stderr)


if __name__=='__main__':unittest.main()
