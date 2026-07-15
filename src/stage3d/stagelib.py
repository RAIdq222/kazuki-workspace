# -*- coding: utf-8 -*-
"""美術ボード3Dステージ化の共通ヘルパー (bpy)."""
import math
import os
import sys

import bpy

_mats = {}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()


def mat(name, color, rough=0.65, emit=0.0, alpha=1.0, emit_color=None):
    key = f"m_{name}"
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emit > 0:
        bsdf.inputs["Emission Color"].default_value = (*(emit_color or color), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
    _mats[key] = m
    return m


def mat_image(name, img_path, rough=0.9, blend="CLIP", emit=0.0, uv_scale=None):
    """画像テクスチャ(アルファ付き)マテリアル。リーフカード・張りぼて用."""
    key = f"m_{name}"
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.abspath(img_path))
    if uv_scale:
        # UVタイル: Mappingノードのscale (glTFでは KHR_texture_transform に変換される)
        uvn = nt.nodes.new("ShaderNodeUVMap")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (uv_scale[0], uv_scale[1], 1)
        nt.links.new(uvn.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        tex.extension = "REPEAT"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if blend != "OPAQUE":
        # 不透明素材でアルファを繋ぐと glTF が alphaMode=BLEND になり
        # ビューワー側で半透明扱いされてしまうため、抜きが必要な時だけ繋ぐ
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if emit > 0:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit
    try:
        m.blend_method = blend  # glTFのalphaMode(MASK/BLEND)に反映される
        if blend == "CLIP":
            m.alpha_threshold = 0.3
    except AttributeError:
        pass
    _mats[key] = m
    return m


def _obj(o, name, material):
    o.name = name
    if material:
        o.data.materials.append(material)
    return o


def box(name, sx, sy, sz, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    return _obj(o, name, material)


def cyl(name, r, depth, loc, material, rot=(0, 0, 0), verts=16, r2=None):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts,
                                            location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r2, depth=depth, vertices=verts,
                                        location=loc, rotation=rot)
    return _obj(bpy.context.object, name, material)


def sphere(name, r, loc, material, scale=(1, 1, 1), smooth=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=18, ring_count=12)
    o = bpy.context.object
    o.scale = scale
    if smooth:
        bpy.ops.object.shade_smooth()
    return _obj(o, name, material)


def torus(name, r, r_minor, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=r_minor,
                                     location=loc, rotation=rot,
                                     major_segments=24, minor_segments=10)
    bpy.ops.object.shade_smooth()
    return _obj(bpy.context.object, name, material)


def plane(name, sx, sy, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (sx, sy, 1)
    return _obj(o, name, material)


def add_camera(name, loc, look_at, lens=24):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_end = 500.0  # 遠景の山などが既定の100mで切れないように
    o = bpy.data.objects.new(name, cam)
    o.location = loc
    d = (look_at[0] - loc[0], look_at[1] - loc[1], look_at[2] - loc[2])
    rot_z = math.atan2(d[1], d[0]) - math.pi / 2
    rot_x = math.atan2(math.hypot(d[0], d[1]), -d[2])
    o.rotation_euler = (rot_x, 0, rot_z)
    bpy.context.collection.objects.link(o)
    return o


def area_light(name, loc, rot, size, energy, color=(1, 1, 1), size_y=None):
    d = bpy.data.lights.new(name, type="AREA")
    d.energy = energy
    d.color = color
    if size_y:
        d.shape = "RECTANGLE"
        d.size = size
        d.size_y = size_y
    else:
        d.size = size
    o = bpy.data.objects.new(name, d)
    o.location = loc
    o.rotation_euler = rot
    bpy.context.collection.objects.link(o)
    return o


def sun_light(name, rot, energy, color=(1, 1, 1), angle_deg=5.0):
    d = bpy.data.lights.new(name, type="SUN")
    d.energy = energy
    d.color = color
    d.angle = math.radians(angle_deg)
    o = bpy.data.objects.new(name, d)
    o.rotation_euler = rot
    bpy.context.collection.objects.link(o)
    return o


def set_world(color, strength=1.0):
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def render_cli(cams, argv=None, default_res="1280x830", view_transform="AgX",
               exposure=0.9):
    """--views/--samples/--res/--out/--blend/--tag を処理してレンダリング."""
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--views", default=",".join(cams.keys()))
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", default=default_res)
    ap.add_argument("--out", default="work/renders")
    ap.add_argument("--blend", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--style", default="color", choices=["color", "gray", "line"],
                    help="color=通常 / gray=グレーモデル / line=線画(Freestyle)")
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = ap.parse_args(argv)

    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    w, h = (int(v) for v in args.res.split("x"))
    scn.render.resolution_x = w
    scn.render.resolution_y = h
    scn.cycles.samples = args.samples
    scn.cycles.use_denoising = True
    scn.cycles.device = "CPU"
    scn.view_settings.view_transform = view_transform
    if view_transform == "AgX":
        scn.view_settings.look = "AgX - Base Contrast"
    scn.view_settings.exposure = exposure

    # ---- 出力スタイル切替 (グレーモデル / 線画) ----
    if args.style == "gray":
        gm = bpy.data.materials.new("m_override_gray")
        gm.use_nodes = True
        b = gm.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1)
        b.inputs["Roughness"].default_value = 0.85
        bpy.context.view_layer.material_override = gm
    elif args.style == "line":
        wm_ = bpy.data.materials.new("m_override_white")
        wm_.use_nodes = True
        b = wm_.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (1, 1, 1, 1)
        b.inputs["Emission Color"].default_value = (1, 1, 1, 1)
        b.inputs["Emission Strength"].default_value = 1.0
        bpy.context.view_layer.material_override = wm_
        set_world((1, 1, 1), strength=1.0)
        scn.render.use_freestyle = True
        scn.render.line_thickness = 1.4
        fs = bpy.context.view_layer.freestyle_settings
        ls = fs.linesets.new("lineart")
        ls.select_silhouette = True
        ls.select_border = True
        ls.select_crease = True
        fs.crease_angle = math.radians(134)
        scn.view_settings.view_transform = "Standard"
        scn.view_settings.exposure = 0.0

    os.makedirs(args.out, exist_ok=True)
    for v in args.views.split(","):
        scn.camera = cams[v.strip()]
        scn.render.filepath = os.path.join(args.out, f"view{v.strip()}{args.tag}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scn.render.filepath)
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend))
        print("saved", args.blend)


# ---- プロシージャルマテリアル (blender-shader-nodesスキル準拠) ----
# glTFには変換できないため、fallback色をカスタムプロパティに保存しておき、
# build_viewer.export_glb がGLB用にその色へ落とす。

def _proc_base(name, color, rough):
    key = f"m_{name}"
    if key in _mats:
        return None, None
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    m["fallback"] = list(color)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    _mats[key] = m
    return m, bsdf


def mat_wood(name, color, rough=0.55, scale=3.0, along="Y", strength=0.35):
    """木目: Wave Texture をノイズで歪ませ ColorRamp で濃淡 + バンプ."""
    m, bsdf = _proc_base(name, color, rough)
    if m is None:
        return _mats[f"m_{name}"]
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.bands_direction = "X" if along == "X" else "Y"
    wave.inputs["Scale"].default_value = 1.6
    wave.inputs["Distortion"].default_value = 3.5
    wave.inputs["Detail"].default_value = 2.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo = [max(0.0, c * (1 - strength)) for c in color]
    hi = [min(1.0, c * (1 + strength * 0.7)) for c in color]
    ramp.color_ramp.elements[0].color = (*lo, 1)
    ramp.color_ramp.elements[1].color = (*hi, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mat_plaster(name, color, rough=0.9, scale=8.0, strength=0.16):
    """漆喰・土壁: 大小ノイズの重ねで色ムラ + 細かいバンプ."""
    m, bsdf = _proc_base(name, color, rough)
    if m is None:
        return _mats[f"m_{name}"]
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = scale * 0.4
    n1.inputs["Detail"].default_value = 4.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo = [max(0.0, c * (1 - strength)) for c in color]
    hi = [min(1.0, c * (1 + strength)) for c in color]
    ramp.color_ramp.elements[0].color = (*lo, 1)
    ramp.color_ramp.elements[1].color = (*hi, 1)
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = scale * 6
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mat_cloth(name, color, rough=0.95, scale=90.0, drape_scale=1.2):
    """布: 細かい織り目バンプ + 縦ドレープの明暗 (幕・布掛け用)."""
    m, bsdf = _proc_base(name, color, rough)
    if m is None:
        return _mats[f"m_{name}"]
    nt = m.node_tree
    bsdf.inputs["Sheen Weight"].default_value = 0.4
    tc = nt.nodes.new("ShaderNodeTexCoord")
    # 縦ドレープ: X方向のWaveで柔らかい明暗
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = drape_scale
    wave.inputs["Distortion"].default_value = 1.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo = [max(0.0, c * 0.78) for c in color]
    hi = [min(1.0, c * 1.10) for c in color]
    ramp.color_ramp.elements[0].color = (*lo, 1)
    ramp.color_ramp.elements[1].color = (*hi, 1)
    weave = nt.nodes.new("ShaderNodeTexNoise")
    weave.inputs["Scale"].default_value = scale
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], weave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(weave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m
