"""Generate a tiny, synthetic block-model fixture; no world or player data."""
import argparse
from pathlib import Path
import numpy as np
from nbt import Tag,setval
from schematic import write


def make(path):
    a=np.zeros((6,15,25),np.uint16);m=np.zeros_like(a);palette={'minecraft:air':0};tiles=[]
    def put(x,y,z,name,meta=0,tile=None):
        if name not in palette:palette[name]=len(palette)
        a[y,z,x]=palette[name];m[y,z,x]=meta
        if tile is not None:
            for k,v in zip(('x','y','z'),(x,y,z)):setval(tile,k,3,v)
            tiles.append(tile)
    def tile(name):
        t=Tag(10,{});setval(t,'id',8,name);return t
    for z0 in (1,9):
        for x0 in (1,7,13,19):
            for z in range(z0,z0+4):
                for x in range(x0,x0+4):put(x,0,z,'minecraft:stonebrick')
    for x,meta in [(1,0),(2,1),(3,4)]:put(x,1,2,'etfuturum:deepslate_brick_stairs',meta)
    put(1,1,4,'minecraft:wooden_slab');put(3,1,4,'minecraft:wooden_slab',8)
    for x,z in [(7,2),(8,2),(9,2),(9,3),(9,4)]:put(x,1,z,'minecraft:fence')
    for x,z in [(13,2),(14,2),(15,2),(15,3),(15,4)]:put(x,1,z,'minecraft:glass_pane')
    for x in [19,20]:
        t=tile('Chest');t.data[b'Items']=Tag(9,(10,[]));put(x,1,2,'minecraft:chest',3,t)
    for shape,x,z in [(0,1,10),(10,3,10),(15,1,12),(77,3,12)]:
        t=tile('gcewing.shape')
        for k,kind,v in [('Shape',3,shape),('BaseName',8,'minecraft:stonebrick'),('BaseData',3,0),('turn',1,0),('side',1,0)]:setval(t,k,kind,v)
        put(x,1,z,'ArchitectureCraft:shape',tile=t)
    for x,name,shape in [(7,'CarpentersBlocks:blockCarpentersSlope',10),(9,'CarpentersBlocks:blockCarpentersStairs',9)]:
        t=tile('TileEntityCarpentersBlock');setval(t,'cbMetadata',3,shape);setval(t,'cbDesign',8,'')
        attr=Tag(10,{})
        for k,kind,v in [('cbUniqueId',8,'minecraft:stonebrick'),('cbAttribute',1,6),('Damage',2,0),('Count',1,1),('id',2,98)]:setval(attr,k,kind,v)
        t.data[b'cbAttrList']=Tag(9,(10,[attr]));put(x,1,10,name,tile=t)
    for x in (13,14,15,16):
        for z in (9,10,11,12):put(x,1,z,'minecraft:glass' if x in (13,16) or z in (9,12) else 'minecraft:water')
    for x,z in [(19,10),(20,10),(21,10),(21,11),(21,12)]:put(x,1,z,'minecraft:iron_bars')
    put(22,1,9,'chisel:glowstone',9)
    write(path,a,m,palette,tiles)
    return Path(path)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'runtime/example.schematic')
    print(make(p.parse_args().output))
