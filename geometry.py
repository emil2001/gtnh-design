"""Indicative voxel colours and XYZ face conventions."""
import numpy as np

NORMALS = np.array([(0,0,-1),(0,0,1),(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)])
CORNERS = np.array([
    [(0,1,0),(1,1,0),(1,0,0),(0,0,0)],
    [(1,1,1),(0,1,1),(0,0,1),(1,0,1)],
    [(1,1,0),(1,1,1),(1,0,1),(1,0,0)],
    [(0,1,1),(0,1,0),(0,0,0),(0,0,1)],
    [(0,1,1),(1,1,1),(1,1,0),(0,1,0)],
    [(0,0,0),(1,0,0),(1,0,1),(0,0,1)],
],dtype=np.int16)


def color(name):
    n = name.lower()
    if n == 'minecraft:air': return (27, 36, 45)
    if any(v in n for v in ['water', 'river']): return (48, 108, 146)
    if 'lava' in n: return (236, 105, 35)
    if any(v in n for v in ['leaves', 'bamboo', 'sapling', 'plant', 'grass', 'flower', 'vine', 'crop', 'lily']): return (89, 128, 65)
    if any(v in n for v in ['log', 'wood', 'planks', 'fence', 'chest', 'bookshelf']): return (154, 112, 70)
    if any(v in n for v in ['snow', 'quartz', 'marble']): return (216, 220, 211)
    if 'glass' in n: return (107, 172, 186)
    if any(v in n for v in ['sand', 'limestone']): return (199, 186, 148)
    if 'dirt' in n: return (143, 111, 80)
    if 'clay' in n: return (156, 120, 97)
    if 'brick' in n: return (153, 151, 141)
    if 'gravel' in n: return (128, 128, 126)
    if any(v in n for v in ['stone', 'ore', 'basalt', 'bedrock', 'granite']): return (151, 145, 133)
    if any(v in n for v in ['torch', 'glow', 'lamp']): return (232, 190, 92)
    return (133, 150, 160)
