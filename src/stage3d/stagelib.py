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


def mat_image(name, img_path, rough=0.9, blend="CLIP", emit=0.0):
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
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
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

    os.makedirs(args.out, exist_ok=True)
    for v in args.views.split(","):
        scn.camera = cams[v.strip()]
        scn.render.filepath = os.path.join(args.out, f"view{v.strip()}{args.tag}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scn.render.filepath)
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend))
        print("saved", args.blend)
