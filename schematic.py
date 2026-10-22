"""Read/write named Schematica Alpha without losing typed TileEntity NBT."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import struct
import numpy as np
from nbt import Tag,parse,encode,setval

MAX_CELLS=16_000_000
MAX_NBT=256_000_000


def value(tag):
    if tag.kind==10:return {k.decode('utf-8'):value(v) for k,v in tag.data.items()}
    if tag.kind==9:return [value(v) for v in tag.data[1]]
    if tag.kind==8:return tag.data[2:].replace(b'\xc0\x80',b'\0').decode('utf-8',errors='surrogatepass')
    if tag.kind==7:return tag.data[4:]
    if tag.kind in (11,12):return np.frombuffer(tag.data[4:],dtype='>i4' if tag.kind==11 else '>i8')
    return struct.unpack({1:'>b',2:'>h',3:'>i',4:'>q',5:'>f',6:'>d'}[tag.kind],tag.data)[0]


def read(path,registry=None):
    with gzip.open(path,'rb') as f:raw=f.read(MAX_NBT+1)
    if len(raw)>MAX_NBT:raise ValueError('Decompressed NBT exceeds 256 MB')
    _,typed=parse(raw);n=value(typed)
    w,h,l=(n[k] for k in ('Width','Height','Length'));size=w*h*l
    if min(w,h,l)<1 or size>MAX_CELLS:raise ValueError('Invalid or oversized schematic dimensions')
    if len(n['Blocks'])!=size or len(n['Data'])!=size:raise ValueError('Block/Data length mismatch')
    a=np.frombuffer(n['Blocks'],np.uint8).astype(np.uint16)
    named='SchematicaMapping' in n
    if 'AddBlocks' in n:
        extra=np.frombuffer(n['AddBlocks'],np.uint8)
        if len(extra)!=(size+1)//2:raise ValueError('Invalid AddBlocks length')
        # GTNH Schematica uses high nibble first; plain WorldEdit Alpha uses low first.
        a[::2]|=((extra>>4) if named else (extra&15)).astype(np.uint16)<<8
        a[1::2]|=((extra[:size//2]&15) if named else (extra[:size//2]>>4)).astype(np.uint16)<<8
    if named:names={v:k for k,v in n['SchematicaMapping'].items()}
    elif registry is not None:names={int(k):v for k,v in registry.items()}
    else:raise ValueError('Unnamed Alpha requires an explicit --registry JSON; IDs vary between worlds')
    missing=set(map(int,np.unique(a)))-names.keys()
    if missing:raise ValueError('Unmapped block IDs: '+str(sorted(missing)))
    return {'blocks':a.reshape(h,l,w),'metadata':np.frombuffer(n['Data'],np.uint8).reshape(h,l,w),
            'names':names,'tiles':n.get('TileEntities',[]),'typed_nbt':typed}


def write(path,blocks,metadata,palette,tiles=(),origin=(0,0,0)):
    a=np.asarray(blocks);m=np.asarray(metadata)
    if a.ndim!=3 or a.shape!=m.shape or not a.size or a.size>MAX_CELLS:
        raise ValueError('Expected equally shaped Y,Z,X arrays, at most 16 million cells')
    if any(v>32767 for v in a.shape) or int(a.min())<0 or int(a.max())>4095:
        raise ValueError('Named Alpha supports local palette IDs 0..4095; not numeric server IDs')
    if int(m.min())<0 or int(m.max())>255:raise ValueError('Alpha metadata must fit 0..255; preserve higher terrain metadata separately')
    ids=list(palette.values())
    if palette.get('minecraft:air')!=0 or len(ids)!=len(set(ids)) or set(map(int,np.unique(a)))-set(ids):
        raise ValueError('Palette must map names uniquely, include air=0 and every used local ID')
    h,l,w=a.shape;root=Tag(10,{})
    for k,v in [('Width',w),('Height',h),('Length',l)]:setval(root,k,2,v)
    setval(root,'Materials',8,'Alpha');setval(root,'Blocks',7,(a&255).astype(np.uint8).tobytes())
    setval(root,'Data',7,m.astype(np.uint8).tobytes())
    if a.max()>255:
        high=((a.ravel()>>8)&15).astype(np.uint8);extra=high[::2]<<4
        extra[:len(high)//2]|=high[1::2];setval(root,'AddBlocks',7,extra.tobytes())
    mapping=Tag(10,{})
    for name,bid in palette.items():setval(mapping,name,2,bid)
    root.data[b'SchematicaMapping']=mapping
    chosen=copy.deepcopy(list(tiles))
    for t in chosen:
        p=[value(t.data[k]) for k in (b'x',b'y',b'z')]
        if not (0<=p[0]<w and 0<=p[1]<h and 0<=p[2]<l):raise ValueError('TileEntity outside schematic')
    multipart=[t for t in chosen if value(t.data.get(b'id',Tag(8,b'\0\0')))=='savedMultipart']
    root.data[b'TileEntities']=Tag(9,(10,[t for t in chosen if t not in multipart]));root.data[b'Entities']=Tag(9,(10,[]))
    if multipart:root.data[b'GTNHPreviewMultipart']=Tag(9,(10,multipart))
    for axis,v in zip('XYZ',origin):setval(root,'WEOrigin'+axis,3,v);setval(root,'WEOffset'+axis,3,0)
    raw=encode(b'Schematic',root);parse(raw)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(raw,mtime=0))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('schematic',type=Path);p.add_argument('--registry',type=Path)
    args=p.parse_args();s=read(args.schematic,json.loads(args.registry.read_text()) if args.registry else None)
    ids,counts=np.unique(s['blocks'],return_counts=True)
    h,l,w=s['blocks'].shape
    print(json.dumps({'dimensions_xyz':[w,h,l],
        'tile_entities':len(s['tiles']),'palette':{s['names'][int(i)]:int(c) for i,c in zip(ids,counts)}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
