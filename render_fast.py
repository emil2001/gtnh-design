"""Approximate full-cube massing preview; not a native block/model verification."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from geometry import NORMALS,CORNERS,color
from schematic import read


def render(path,output,azimuth=115,width=2000,height=1500,registry=None):
    s=read(path,registry);a=s['blocks'];names=s['names']
    palette=np.zeros((max(names)+1,3),np.uint8)
    for bid,name in names.items():palette[bid]=color(name)
    rgb=palette[a]
    for t in s['tiles']:
        if t.get('id')=='gcewing.shape':
            x,y,z=(t[k] for k in ('x','y','z'))
            if 0<=y<a.shape[0] and 0<=z<a.shape[1] and 0<=x<a.shape[2]:rgb[y,z,x]=color(t.get('BaseName','minecraft:stone'))
    air={bid for bid,name in names.items() if name=='minecraft:air'}
    occ=~np.isin(a,list(air));p=np.pad(occ,1);h,l,w=a.shape
    th,ph=np.radians([azimuth,23]);cam=np.array([np.sin(th)*np.cos(ph),np.sin(ph),-np.cos(th)*np.cos(ph)])
    right=np.array([-np.cos(th),0,-np.sin(th)]);up=np.cross(cam,right)
    parts=[];faces=[];colors=[];face_count=0
    for f,(dx,dy,dz) in enumerate(NORMALS):
        if NORMALS[f]@cam<=0:continue
        neigh=p[1+dy:1+dy+h,1+dz:1+dz+l,1+dx:1+dx+w]
        yy,zz,xx=np.where(occ&~neigh);face_count+=len(xx)
        if face_count>2_000_000:raise ValueError('Preview exceeds two million visible faces; use a smaller crop')
        parts.append(np.stack([xx,yy,zz],axis=1));faces.append(np.full(len(xx),f));colors.append(rgb[yy,zz,xx])
    if face_count==0:raise ValueError('Schematic is empty')
    xyz=np.concatenate(parts);fs=np.concatenate(faces);col=np.concatenate(colors)
    pts=xyz[:,None,:]+CORNERS[fs]
    xy=np.stack([pts@right,-pts@up],axis=2);lo=xy.min(axis=(0,1));hi=xy.max(axis=(0,1))
    scale=min((width-80)/(hi[0]-lo[0]),(height-170)/(hi[1]-lo[1]))
    xy=(xy-lo)*scale+[(width-(hi[0]-lo[0])*scale)/2,110]
    light=np.array([.5,.9,.3]);light/=np.linalg.norm(light)
    shades=.48+.52*np.maximum(0,NORMALS@light);col=(col*shades[fs,None]).astype(np.uint8)
    im=Image.new('RGB',(width,height),'#18232b');draw=ImageDraw.Draw(im)
    for i in np.argsort(pts.mean(axis=1)@cam):draw.polygon([tuple(p) for p in xy[i]],fill=tuple(col[i]))
    draw.text((24,20),Path(path).name,font=ImageFont.load_default(size=24),fill='#e9ede9')
    draw.text((24,60),'DRAFT: full cubes and indicative colours; inspect shapes in the native renderer',font=ImageFont.load_default(size=15),fill='#bdc5c6')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);im.save(output)
    return {'output':str(output),'visible_faces':face_count,'full_cube_preview_only':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('schematic',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--azimuth',type=float,default=115);p.add_argument('--width',type=int,default=2000);p.add_argument('--height',type=int,default=1500)
    p.add_argument('--registry',type=Path);a=p.parse_args()
    if not 320<=a.width<=4096 or not 240<=a.height<=4096:p.error('Image size must be 320..4096 by 240..4096')
    print(json.dumps(render(a.schematic,a.output,a.azimuth,a.width,a.height,json.loads(a.registry.read_text()) if a.registry else None)))


if __name__=='__main__':main()
