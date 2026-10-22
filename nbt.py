"""Lossless typed Minecraft NBT; no world writes or game dependencies."""
from dataclasses import dataclass
from io import BytesIO
import struct

@dataclass
class Tag:
    kind: int
    data: object


def parse(raw):
    f = BytesIO(raw)

    def take(n):
        if not 0 <= n <= len(raw):
            raise ValueError('Invalid NBT length')
        b = f.read(n)
        if len(b) != n:
            raise ValueError('Truncated NBT')
        return b

    def number(fmt):
        return struct.unpack(fmt, take(struct.calcsize(fmt)))[0]

    def name():
        return take(number('>H'))

    def payload(kind, depth=0):
        if depth > 128:
            raise ValueError('Excessive nesting')
        if kind in (1, 2, 3, 4, 5, 6):
            return Tag(kind, take({1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}[kind]))
        if kind in (7, 11, 12):
            count = number('>i')
            return Tag(kind, struct.pack('>i', count) + take(count * {7: 1, 11: 4, 12: 8}[kind]))
        if kind == 8:
            value = name()
            return Tag(kind, struct.pack('>H', len(value)) + value)
        if kind == 9:
            child, count = number('>B'), number('>i')
            if not 0 <= count <= len(raw) or child == 0 and count:
                raise ValueError('Invalid NBT list')
            return Tag(kind, (child, [payload(child, depth + 1) for _ in range(count)]))
        if kind == 10:
            values = {}
            while (child := number('>B')):
                key = name()
                if key in values:
                    raise ValueError('Duplicate tag')
                values[key] = payload(child, depth + 1)
            return Tag(kind, values)
        raise ValueError(f'Unknown NBT type {kind}')

    kind = number('>B')
    if kind != 10:
        raise ValueError('Expected compound root')
    rootname, node = name(), payload(kind)
    if f.read():
        raise ValueError('Trailing NBT data')
    assert encode(rootname, node) == raw, 'Lossless NBT round trip failed'
    return rootname, node


def body(tag):
    if tag.kind == 10:
        return b''.join(bytes([v.kind]) + struct.pack('>H', len(k)) + k + body(v)
                        for k, v in tag.data.items()) + b'\0'
    if tag.kind == 9:
        child, values = tag.data
        assert all(v.kind == child for v in values)
        return bytes([child]) + struct.pack('>i', len(values)) + b''.join(map(body, values))
    return tag.data


def encode(name, tag):
    return bytes([tag.kind]) + struct.pack('>H', len(name)) + name + body(tag)


def setval(compound, name, kind, value):
    if kind in (1, 2, 3, 4, 5, 6):
        raw = struct.pack({1: '>b', 2: '>h', 3: '>i', 4: '>q', 5: '>f', 6: '>d'}[kind], value)
    elif kind == 8:
        raw = value.encode('utf-8')
        raw = struct.pack('>H', len(raw)) + raw
    elif kind == 7:
        raw = struct.pack('>i', len(value)) + value
    else:
        raise ValueError(kind)
    compound.data[name.encode()] = Tag(kind, raw)
