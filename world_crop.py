"""Read a local 1.7.10 Anvil crop into a named schematic; never write the source save."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import zlib
import numpy as np
from nbt import Tag,parse,encode,setval
from schematic import value,write,MAX_CELLS,MAX_NBT
from world_decode import decode_section


def chunk(world,cx,cz,dimension):
    folder=world if dimension==0 else world/f'DIM{dimension}'
    path=folder/'region'/f'r.{cx//32}.{cz//32}.mca'
    with path.open('rb') as f:
        f.seek(4*((cz%32)*32+cx%32));location=int.from_bytes(f.read(4),'big');sector=location>>8;sectors=location&255
        if sector<2 or sectors<1:raise ValueError(f'Missing source chunk {cx},{cz}; do not invent terrain')
        f.seek(sector*4096);length=int.from_bytes(f.read(4),'big')
        if not 1<length<=sectors*4096-4:raise ValueError('Invalid Anvil chunk length')
        codec=f.read(1)[0];raw=f.read(length-1)
    if len(raw)!=length-1:raise ValueError('Truncated Anvil payload')
    if codec in (1,2):
        decoder=zlib.decompressobj(31 if codec==1 else 15)
        raw=decoder.decompress(raw,MAX_NBT+1)
        if len(raw)>MAX_NBT:raise ValueError('Oversized Anvil NBT')
        if not decoder.eof:raise ValueError('Truncated compressed Anvil NBT')
    elif codec!=3:raise ValueError('Unsupported Anvil compression')
    if len(raw)>MAX_NBT:raise ValueError('Oversized Anvil NBT')
    _,typed=parse(raw);level=typed.data[b'Level'];n=value(level)
    if (n['xPos'],n['zPos'])!=(cx,cz):raise ValueError('Chunk coordinate mismatch')
    return n,level


def crop(world,bounds,output,dimension=0):
    world=Path(world).resolve(strict=True);output=Path(output).resolve()
    if output.is_relative_to(world):raise ValueError('Output must be outside the source save')
    x0,y0,z0,x1,y1,z1=bounds;w=x1-x0+1;h=y1-y0+1;l=z1-z0+1
    if min(w,h,l)<1 or not 0<=y0<=y1<=255 or w*h*l>MAX_CELLS:raise ValueError('Invalid or oversized crop')
    with gzip.open(world/'level.dat','rb') as f:raw=f.read(MAX_NBT+1)
    if len(raw)>MAX_NBT:raise ValueError('Oversized level.dat')
    registry=value(parse(raw)[1])['FML']['ItemData']
    registry={p['V']:p['K'][1:] for p in registry if p['K'].startswith('\x01')}
    a=np.zeros((h,l,w),np.uint32);m=np.zeros_like(a,np.uint16);tiles=[]
    for cz in range(z0//16,z1//16+1):
        for cx in range(x0//16,x1//16+1):
            n,typed=chunk(world,cx,cz,dimension);seen=set()
            for section in n['Sections']:
                sy=section['Y'];bottom=sy*16
                if sy not in range(16) or sy in seen:raise ValueError('Invalid section height')
                seen.add(sy)
                low=max(y0,bottom);high=min(y1+1,bottom+16)
                if low>=high:continue
                ids,meta=decode_section(section)
                xx=max(x0,cx*16);xx1=min(x1+1,cx*16+16);zz=max(z0,cz*16);zz1=min(z1+1,cz*16+16)
                source=np.s_[low-bottom:high-bottom,zz-cz*16:zz1-cz*16,xx-cx*16:xx1-cx*16]
                target=np.s_[low-y0:high-y0,zz-z0:zz1-z0,xx-x0:xx1-x0]
                a[target]=ids[source];m[target]=meta[source]
            for t in typed.data.get(b'TileEntities',Tag(9,(10,[]))).data[1]:
                x,y,z=(value(t.data[k]) for k in (b'x',b'y',b'z'))
                if x0<=x<=x1 and y0<=y<=y1 and z0<=z<=z1 and a[y-y0,z-z0,x-x0]:
                    t=copy.deepcopy(t)
                    for k,v in zip(('x','y','z'),(x-x0,y-y0,z-z0)):setval(t,k,3,v)
                    tiles.append(t)
    unique=np.unique(a)
    if len(unique)>4096 or any(int(i) not in registry for i in unique):raise ValueError('Missing/oversized block registry')
    if 0 not in unique:unique=np.insert(unique,0,0)
    palette={registry[int(bid)]:local for local,bid in enumerate(unique)}
    write(output,np.searchsorted(unique,a).astype(np.uint16),(m&255),palette,tiles,(x0,y0,z0))
    extended=np.flatnonzero(m.ravel()>255)
    if len(extended):
        name,t=parse(gzip.decompress(output.read_bytes()));audit=Tag(10,{})
        for index in extended:setval(audit,str(int(index)),3,int(m.ravel()[index]))
        t.data[b'GTNHPreviewMetadata']=audit;output.write_bytes(gzip.compress(encode(name,t),mtime=0))
    return {'output':str(output),'bounds_xyz':bounds,'dimension':dimension,'tile_entities_including_multipart':len(tiles),
            'metadata_above_alpha_range':len(extended),'source_modified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--world',required=True,type=Path)
    p.add_argument('--bounds',required=True,type=int,nargs=6,metavar=('X0','Y0','Z0','X1','Y1','Z1'))
    p.add_argument('--output',required=True,type=Path);p.add_argument('--dimension',type=int,default=0)
    args=p.parse_args();print(json.dumps(crop(args.world,args.bounds,args.output,args.dimension)))
