"""Minecraft/EndlessIDs section decoding; source arrays use Y,Z,X order."""
import numpy as np

def nibble_array(data):
    packed = np.frombuffer(data, dtype=np.uint8)
    if len(packed) != 2048:
        raise ValueError('Invalid section nibble array')
    result = np.empty(4096, dtype=np.uint32)
    result[0::2], result[1::2] = packed & 15, packed >> 4
    return result


def decode_section(section):
    # EndlessIDs 1.7.4: B1 + B2Low<<8 + B2High<<12 + B3<<16.
    if 'Blocks16' in section:
        ids = np.frombuffer(section['Blocks16'], dtype='>u2').astype(np.uint32)
    else:
        ids = np.frombuffer(section['Blocks'], dtype=np.uint8).astype(np.uint32)
        for name, shift in [('Add', 8), ('BlocksB2Hi', 12)]:
            if name in section:
                ids |= nibble_array(section[name]) << shift
        if 'BlocksB3' in section:
            ids |= np.frombuffer(section['BlocksB3'], dtype=np.uint8).astype(np.uint32) << 16
    if 'Data16' in section:
        meta = np.frombuffer(section['Data16'], dtype='>u2').astype(np.uint16)
    else:
        meta = nibble_array(section['Data'])
        if 'Data1High' in section:
            meta |= nibble_array(section['Data1High']) << 4
        if 'Data2' in section:
            meta |= np.frombuffer(section['Data2'], dtype=np.uint8).astype(np.uint32) << 8
        meta = meta.astype(np.uint16)
    if ids.size != 4096 or meta.size != 4096:
        raise ValueError('Invalid section size')
    return ids.reshape(16, 16, 16), meta.reshape(16, 16, 16)
