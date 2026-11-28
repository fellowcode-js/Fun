#!/usr/bin/env python3
"""Convert a glTF binary (.glb) into DOW's runtime model format (.dowm).

Keeps the model exactly as authored: node hierarchy, meshes, base-colour texture (AO multiplied in),
vertex colours and node animations. Used for the original chainsaw hand (assets_src/robot_arm_right.glb).
Usage: python3 tools/glb_to_dowm.py assets_src/robot_arm_right.glb android/app/src/main/assets/robot_arm_right.dowm
"""
import io, json, struct, sys
from PIL import Image

TEX_SIZE = 512

def main(src, dst):
    b = open(src, 'rb').read()
    jl = struct.unpack('<I', b[12:16])[0]; j = json.loads(b[20:20 + jl])
    off = 20 + jl; bl = struct.unpack('<I', b[off:off + 4])[0]; bin_ = b[off + 8: off + 8 + bl]
    comps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
    fmt = {5126: ('f', 4), 5125: ('I', 4), 5123: ('H', 2), 5121: ('B', 1)}

    def acc(i):
        a = j['accessors'][i]; v = j['bufferViews'][a['bufferView']]; c = comps[a['type']]; f, sz = fmt[a['componentType']]
        start = v.get('byteOffset', 0) + a.get('byteOffset', 0); stride = v.get('byteStride', sz * c); out = []
        for k in range(a['count']):
            vals = struct.unpack_from('<' + f * c, bin_, start + k * stride)
            if a.get('normalized') and f in 'BH': vals = tuple(x / (255.0 if f == 'B' else 65535.0) for x in vals)
            out.append(vals)
        return out

    def image(i):
        v = j['bufferViews'][j['images'][i]['bufferView']]; s = v.get('byteOffset', 0)
        return Image.open(io.BytesIO(bin_[s:s + v['byteLength']])).convert('RGBA')

    # materials -> textures (base colour x occlusion, resized for Quest memory)
    mats, texs = [], []
    for m in j.get('materials', []):
        pbr = m.get('pbrMetallicRoughness', {}); col = pbr.get('baseColorFactor', [1, 1, 1, 1]); ti = -1
        if 'baseColorTexture' in pbr:
            img = image(j['textures'][pbr['baseColorTexture']['index']]['source']).resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS)
            if 'occlusionTexture' in m:
                ao = image(j['textures'][m['occlusionTexture']['index']]['source']).resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS).split()[0]
                px, aop = img.load(), ao.load()
                for y in range(TEX_SIZE):
                    for x in range(TEX_SIZE):
                        p = px[x, y]; k = aop[x, y] / 255.0; px[x, y] = (int(p[0] * k), int(p[1] * k), int(p[2] * k), p[3])
            ti = len(texs); texs.append(img)
        mats.append((ti, col, pbr.get('metallicFactor', 1.0), pbr.get('roughnessFactor', 1.0)))

    verts, idx, meshes = bytearray(), [], []
    nverts = 0
    for m in j['meshes']:
        for p in m['primitives'][:1]:
            at = p['attributes']; pos = acc(at['POSITION']); nrm = acc(at['NORMAL']) if 'NORMAL' in at else [(0, 1, 0)] * len(pos)
            uv = acc(at['TEXCOORD_0']) if 'TEXCOORD_0' in at else [(0, 0)] * len(pos)
            col = acc(at['COLOR_0']) if 'COLOR_0' in at else None
            ind = [x[0] for x in acc(p['indices'])] if 'indices' in p else list(range(len(pos)))
            matI = p.get('material', -1); metal = mats[matI][2] if matI >= 0 else 0
            meshes.append((nverts, len(pos), len(idx), len(ind), matI))
            for k in range(len(pos)):
                c = col[k] if col else (1, 1, 1, 1)
                rgba = [max(0, min(255, int(round(c[i] * 255)))) for i in range(3)]
                verts += struct.pack('<8f4B4B', *pos[k], *nrm[k], *uv[k], *rgba, 0, 0, int(metal * 255), 0, 0)
            idx += ind; nverts += len(pos)

    out = bytearray(b'DOWM') + struct.pack('<I', 1)
    nodes = j['nodes']; parent = [-1] * len(nodes)
    for i, n in enumerate(nodes):
        for c in n.get('children', []): parent[c] = i
    out += struct.pack('<I', len(nodes))
    for i, n in enumerate(nodes):
        name = n.get('name', '').encode()[:31].ljust(32, b'\0')
        t = n.get('translation', [0, 0, 0]); r = n.get('rotation', [0, 0, 0, 1]); s = n.get('scale', [1, 1, 1])
        out += name + struct.pack('<ii10f', parent[i], n.get('mesh', -1), *t, *r, *s)
    out += struct.pack('<I', len(meshes))
    for m in meshes: out += struct.pack('<IIIIi', *m)
    out += struct.pack('<I', nverts) + verts
    out += struct.pack('<I', len(idx)) + struct.pack('<%dI' % len(idx), *idx)
    out += struct.pack('<I', len(mats))
    for ti, col, metal, rough in mats: out += struct.pack('<i6f', ti, *col, metal, rough)
    out += struct.pack('<I', len(texs))
    for t in texs: out += struct.pack('<II', *t.size) + t.tobytes()
    anims = j.get('animations', []); out += struct.pack('<I', len(anims))
    for a in anims:
        chans = []; dur = 0
        for c in a['channels']:
            s = a['samplers'][c['sampler']]; times = [x[0] for x in acc(s['input'])]; vals = acc(s['output'])
            path = {'translation': 0, 'rotation': 1, 'scale': 2}.get(c['target']['path'])
            if path is None: continue
            dur = max(dur, times[-1]); chans.append((c['target']['node'], path, times, vals))
        out += a['name'].encode()[:31].ljust(32, b'\0') + struct.pack('<fI', dur, len(chans))
        for node, path, times, vals in chans:
            out += struct.pack('<iII', node, path, len(times)) + struct.pack('<%df' % len(times), *times)
            for v in vals: out += struct.pack('<%df' % len(v), *v)
    open(dst, 'wb').write(out)
    print('%s: %d nodes, %d meshes, %d verts, %d tris, %d textures, %d anims, %.1f MB' % (dst, len(nodes), len(meshes), nverts, len(idx) // 3, len(texs), len(anims), len(out) / 1e6))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
