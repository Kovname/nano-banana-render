"""
texture_pipeline.py — Core engine for multi-view AI texture generation.

Responsibilities:
  • Mesh preparation (auto UV unwrap)
  • Virtual orthographic camera placement around a model
  • Mist-based depth rendering + flat colour rendering
  • Collage assembly / splitting (pure bpy pixel arrays)
  • Manual UV projection from cameras
  • Projection shader assembly with dot-product masks
  • Final Cycles bake to a single UV texture
"""

import bpy
import math
import os
import tempfile
from mathutils import Vector, Euler

# ── Constants ────────────────────────────────────────────────────

TEMP_PREFIX = "nb_tex_"

PRESET_CUBE    = 'CUBE'
PRESET_RING_8  = 'RING_8'
PRESET_HEMI_10 = 'HEMI_10'


def _look_at_euler(pos_dir: Vector):
    """Compute XYZ Euler for a camera at *pos_dir* looking toward origin."""
    from mathutils import Matrix
    look = (-pos_dir).normalized()
    if abs(look.z) > 0.99:
        up = Vector((0, -1, 0)) if look.z < 0 else Vector((0, 1, 0))
    else:
        up = Vector((0, 0, 1))
    right = look.cross(up).normalized()
    actual_up = right.cross(look).normalized()
    mat = Matrix((
        (right.x, actual_up.x, -look.x),
        (right.y, actual_up.y, -look.y),
        (right.z, actual_up.z, -look.z),
    )).to_3x3()
    return mat.to_euler('XYZ')


def generate_camera_views(preset=PRESET_CUBE, include_top=True,
                          include_bottom=False):
    """Generate camera view definitions for a given preset."""
    views = []
    if preset == PRESET_CUBE:
        views = [
            {'name': 'Front',  'pos_dir': Vector(( 0,  1,  0))},
            {'name': 'Back',   'pos_dir': Vector(( 0, -1,  0))},
            {'name': 'Left',   'pos_dir': Vector((-1,  0,  0))},
            {'name': 'Right',  'pos_dir': Vector(( 1,  0,  0))},
        ]
    elif preset == PRESET_RING_8:
        for i, n in enumerate(['Front', 'FrontRight', 'Right', 'BackRight',
                                'Back', 'BackLeft', 'Left', 'FrontLeft']):
            a = math.radians(i * 45)
            views.append({'name': n, 'pos_dir': Vector((math.sin(a), math.cos(a), 0))})
    elif preset == PRESET_HEMI_10:
        for i, n in enumerate(['Front', 'FrontRight', 'Right', 'BackRight',
                                'Back', 'BackLeft', 'Left', 'FrontLeft']):
            a = math.radians(i * 45)
            views.append({'name': n, 'pos_dir': Vector((math.sin(a), math.cos(a), 0))})
        elev = math.radians(45)
        ce, se = math.cos(elev), math.sin(elev)
        for deg, n in [(0, 'FrontHigh'), (180, 'BackHigh')]:
            a = math.radians(deg)
            views.append({'name': n, 'pos_dir': Vector((math.sin(a)*ce, math.cos(a)*ce, se))})
    if include_top:
        views.append({'name': 'Top', 'pos_dir': Vector((0, 0, 1))})
    if include_bottom:
        views.append({'name': 'Bottom', 'pos_dir': Vector((0, 0, -1))})
    return views


def _name_to_pos_dir(name):
    """Get pos_dir from camera view name (searches all presets)."""
    for preset in (PRESET_CUBE, PRESET_RING_8, PRESET_HEMI_10):
        for v in generate_camera_views(preset, True, True):
            if v['name'] == name:
                return v['pos_dir']
    return None


# ══════════════════════════════════════════════════════════════════
#  1.  MESH PREPARATION
# ══════════════════════════════════════════════════════════════════

def has_uv_map(obj) -> bool:
    if obj.type != 'MESH':
        return False
    return len(obj.data.uv_layers) > 0


def prepare_mesh(obj, auto_uv: bool = True):
    """Ensure the object has a clean UV map."""
    if obj.type != 'MESH':
        raise ValueError(f"Object '{obj.name}' is not a mesh")

    if not auto_uv:
        if not has_uv_map(obj):
            raise RuntimeError(
                f"Object '{obj.name}' has no UV map and Auto UV is disabled"
            )
        return

    print(f"[TEX PIPE] Smart UV Project on '{obj.name}'...")

    prev_mode = obj.mode
    prev_active = bpy.context.view_layer.objects.active

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')

    uv_name = "NB_AutoUV"
    mesh = obj.data
    if uv_name not in mesh.uv_layers:
        mesh.uv_layers.new(name=uv_name)
    mesh.uv_layers[uv_name].active = True

    bpy.ops.uv.smart_project(
        angle_limit=math.radians(66),
        island_margin=0.01,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=True,
    )

    bpy.ops.object.mode_set(mode=prev_mode)
    bpy.context.view_layer.objects.active = prev_active
    print(f"[TEX PIPE] UV done: layer '{uv_name}'")


# ══════════════════════════════════════════════════════════════════
#  2.  CAMERA PLACEMENT
# ══════════════════════════════════════════════════════════════════

def _bbox_world(obj) -> tuple:
    """Return (center, dimensions) of the world-space bounding box."""
    world_verts = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    xs = [v.x for v in world_verts]
    ys = [v.y for v in world_verts]
    zs = [v.z for v in world_verts]

    min_v = Vector((min(xs), min(ys), min(zs)))
    max_v = Vector((max(xs), max(ys), max(zs)))
    return (min_v + max_v) / 2, max_v - min_v


def create_cameras(
    obj,
    preset: str = PRESET_CUBE,
    include_top: bool = True,
    include_bottom: bool = False,
    distance: float = 0.0,
    ortho_scale: float = 0.0,
) -> list:
    """Create orthographic cameras around *obj* using a preset layout."""
    center, dims = _bbox_world(obj)
    diag = dims.length

    used_dist = distance if distance > 0 else diag * 2.0
    used_ortho = ortho_scale if ortho_scale > 0 else max(dims) * 1.15

    views = generate_camera_views(preset, include_top, include_bottom)
    result = []

    for idx, view in enumerate(views):
        name = view['name']
        pos_dir = view['pos_dir']
        cam_name = f"{TEMP_PREFIX}cam_{name}"

        old = bpy.data.objects.get(cam_name)
        if old:
            old_data = old.data
            bpy.data.objects.remove(old, do_unlink=True)
            if old_data and old_data.users == 0:
                bpy.data.cameras.remove(old_data)

        cam_data = bpy.data.cameras.new(cam_name)
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = used_ortho
        cam_data.clip_start = 0.01
        cam_data.clip_end = used_dist * 4

        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        bpy.context.collection.objects.link(cam_obj)

        cam_obj.location = center + pos_dir.normalized() * used_dist
        cam_obj.rotation_euler = _look_at_euler(pos_dir)
        cam_obj.hide_render = True
        cam_obj.hide_viewport = False

        result.append({
            'name': name,
            'camera': cam_obj,
            'pos_dir': pos_dir,
            'index': idx,
        })

    bpy.context.view_layer.update()
    print(f"[TEX PIPE] Created {len(result)} cameras "
          f"(preset={preset}, dist={used_dist:.2f}, ortho={used_ortho:.2f})")
    return result


def update_cameras(distance: float = 0, ortho_scale: float = 0,
                   target_obj=None):
    """Update all existing pipeline cameras with new distance/ortho_scale."""
    if target_obj is None:
        return

    center, dims = _bbox_world(target_obj)
    diag = dims.length

    used_dist = distance if distance > 0 else diag * 2.0
    used_ortho = ortho_scale if ortho_scale > 0 else max(dims) * 1.15

    prefix = TEMP_PREFIX + "cam_"
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(prefix):
            continue
        view_name = obj.name[len(prefix):]
        pos_dir = _name_to_pos_dir(view_name)
        if pos_dir is None:
            continue

        obj.location = center + pos_dir.normalized() * used_dist
        obj.rotation_euler = _look_at_euler(pos_dir)
        obj.data.ortho_scale = used_ortho
        obj.data.clip_end = used_dist * 4

    bpy.context.view_layer.update()


def remove_temp_cameras():
    """Delete all temporary cameras created by the pipeline."""
    to_remove = [o for o in bpy.data.objects if o.name.startswith(TEMP_PREFIX)]
    for obj in to_remove:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            if isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
    print(f"[TEX PIPE] Cleaned up {len(to_remove)} temp objects")


def set_viewport_to_camera(cam_name: str) -> bool:
    """Set the 3D viewport to look through the named camera."""
    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj:
        return False
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    bpy.context.scene.camera = cam_obj
                    space.region_3d.view_perspective = 'CAMERA'
                    area.tag_redraw()
                    return True
    return False


# ══════════════════════════════════════════════════════════════════
#  3.  RENDERING
# ══════════════════════════════════════════════════════════════════

def _eevee_name() -> str:
    """Return the correct Eevee engine identifier for this Blender version."""
    # Blender 4.0-4.x: BLENDER_EEVEE_NEXT,  Blender 3.x/5.0+: BLENDER_EEVEE
    prop = bpy.types.RenderSettings.bl_rna.properties['engine']
    valid = {item.identifier for item in prop.enum_items}
    if 'BLENDER_EEVEE_NEXT' in valid:
        return 'BLENDER_EEVEE_NEXT'
    return 'BLENDER_EEVEE'


def _store_render_settings(scene) -> dict:
    """Snapshot current render/world/compositor settings."""
    render = scene.render
    vl = bpy.context.view_layer
    snap = {
        'engine': render.engine,
        'film_transparent': render.film_transparent,
        'resolution_x': render.resolution_x,
        'resolution_y': render.resolution_y,
        'resolution_percentage': render.resolution_percentage,
        'filepath': render.filepath,
        'file_format': render.image_settings.file_format,
        'color_mode': render.image_settings.color_mode,
        'color_depth': render.image_settings.color_depth,
        'active_camera': scene.camera,
        'use_nodes': scene.use_nodes,
        'use_pass_mist': getattr(vl, 'use_pass_mist', False),
        'use_pass_combined': getattr(vl, 'use_pass_combined', True),
        'view_transform': scene.view_settings.view_transform,
        'look': scene.view_settings.look,
        'exposure': scene.view_settings.exposure,
        'gamma': scene.view_settings.gamma,
    }

    if hasattr(scene, 'eevee'):
        eevee = scene.eevee
        for attr in ('use_shadows', 'use_ssr', 'use_gtao', 'use_bloom'):
            snap[attr] = getattr(eevee, attr, None)

    # Save compositor links (Blender 5.0: scene.node_tree may not exist)
    snap['_comp_links'] = []
    comp_tree = getattr(scene, 'node_tree', None)
    if scene.use_nodes and comp_tree:
        for link in comp_tree.links:
            try:
                snap['_comp_links'].append((
                    link.from_node.name,
                    link.from_socket.name,
                    link.to_node.name,
                    link.to_socket.name,
                ))
            except Exception:
                pass

    return snap


def _restore_render_settings(scene, snap: dict):
    """Restore previously saved render settings."""
    render = scene.render
    render.engine = snap['engine']
    render.film_transparent = snap['film_transparent']
    render.resolution_x = snap['resolution_x']
    render.resolution_y = snap['resolution_y']
    render.resolution_percentage = snap['resolution_percentage']
    render.filepath = snap['filepath']
    render.image_settings.file_format = snap['file_format']
    render.image_settings.color_mode = snap['color_mode']
    render.image_settings.color_depth = snap.get('color_depth', '8')
    scene.camera = snap['active_camera']
    scene.use_nodes = snap.get('use_nodes', False)

    # Restore color management
    if 'view_transform' in snap:
        try:
            scene.view_settings.view_transform = snap['view_transform']
            scene.view_settings.look = snap.get('look', 'None')
            scene.view_settings.exposure = snap.get('exposure', 0.0)
            scene.view_settings.gamma = snap.get('gamma', 1.0)
        except Exception:
            pass

    vl = bpy.context.view_layer
    if hasattr(vl, 'use_pass_mist'):
        vl.use_pass_mist = snap.get('use_pass_mist', False)
    if hasattr(vl, 'use_pass_combined'):
        vl.use_pass_combined = snap.get('use_pass_combined', True)

    if hasattr(scene, 'eevee'):
        eevee = scene.eevee
        for attr in ('use_shadows', 'use_ssr', 'use_gtao', 'use_bloom'):
            if snap.get(attr) is not None:
                try:
                    setattr(eevee, attr, snap[attr])
                except Exception:
                    pass


def setup_flat_render(scene, resolution: int = 1024):
    """Shadow-free flat colour render (for Enhance stage)."""
    render = scene.render
    render.resolution_x = resolution
    render.resolution_y = resolution
    render.resolution_percentage = 100
    render.film_transparent = True
    render.image_settings.file_format = 'PNG'
    render.image_settings.color_mode = 'RGBA'

    try:
        render.engine = 'BLENDER_WORKBENCH'
        
        # Apply Workbench specific rendering defaults
        shading = scene.display.shading
        shading.light = 'MATCAP'
        shading.show_cavity = True
        shading.cavity_type = 'WORLD'
        shading.cavity_ridge_factor = 2.5
        shading.cavity_valley_factor = 1.0
        
        print("[TEX PIPE] Render: Workbench (MatCap + Cavity)")
    except Exception:
        render.engine = _eevee_name()
        if hasattr(scene, 'eevee'):
            for attr in ('use_shadows', 'use_ssr', 'use_gtao'):
                try:
                    setattr(scene.eevee, attr, False)
                except Exception:
                    pass
        print("[TEX PIPE] Flat render: Eevee (shadows off)")


def setup_mist_render(scene, resolution: int = 1024,
                      mist_start: float = 0.1, mist_depth: float = 10.0,
                      mist_falloff: str = 'LINEAR'):
    """Configure scene for mist viewport rendering.

    Enables mist pass and switches engine to Eevee.
    Does NOT override mist_start/depth/falloff or color management —
    those come from the user's current viewport settings so the export
    matches exactly what they see.
    """
    # Cap mist resolution — viewport OpenGL crashes at 4K
    MIST_MAX = 1024
    mist_res = min(resolution, MIST_MAX)
    if mist_res < resolution:
        print(f"[TEX PIPE] Mist resolution capped: {resolution} → {mist_res}")

    render = scene.render
    render.resolution_x = mist_res
    render.resolution_y = mist_res
    render.resolution_percentage = 100
    render.image_settings.file_format = 'PNG'
    render.image_settings.color_mode = 'RGB'
    render.image_settings.color_depth = '8'

    # ── Switch engine to Eevee ──
    for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            scene.render.engine = engine
            print(f"[TEX PIPE] Mist engine: {engine}")
            break
        except TypeError:
            continue

    # Ensure world exists and mist is enabled
    world = scene.world
    if not world:
        world = bpy.data.worlds.new("NB_World")
        scene.world = world

    if hasattr(world, 'mist_settings'):
        world.mist_settings.use_mist = True
        ms = world.mist_settings
        print(f"[TEX PIPE] Mist enabled (keeping user values): "
              f"start={ms.start}, depth={ms.depth}, falloff={ms.falloff}")

    # ── Enable ONLY mist pass, disable combined ──
    view_layer = bpy.context.view_layer
    if hasattr(view_layer, 'use_pass_mist'):
        view_layer.use_pass_mist = True
    if hasattr(view_layer, 'use_pass_combined'):
        view_layer.use_pass_combined = False
        print("[TEX PIPE] Combined pass disabled — pure mist only")


def _get_viewport_context():
    """Find the 3D viewport area and return context override dict."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        region = None
                        for r in area.regions:
                            if r.type == 'WINDOW':
                                region = r
                                break
                        return {
                            'window': window,
                            'screen': window.screen,
                            'scene': bpy.context.scene,
                            'area': area,
                            'region': region,
                            'space_data': space,
                        }
    return None


def render_single_view_mist(scene, camera_obj, output_path: str):
    """Render MIST pass — EXACT same approach as depth_utils._render_viewport_mist.

    1. Switch viewport to camera view
    2. MATERIAL shading + render_pass = MIST
    3. Disable overlays + gizmos
    4. bpy.ops.render.opengl(write_still=True)
    """
    import bpy

    # ── Find 3D viewport ──
    viewport_window = None
    viewport_screen = None
    viewport_area = None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                viewport_window = window
                viewport_screen = window.screen
                viewport_area = area
                break
        if viewport_area:
            break

    if not viewport_area:
        raise RuntimeError("No 3D viewport available for mist render")

    space_data = None
    for space in viewport_area.spaces:
        if space.type == 'VIEW_3D':
            space_data = space
            break

    if not space_data:
        raise RuntimeError("Cannot access viewport settings")

    overlay = space_data.overlay

    # ── Save original state (same fields as depth_utils) ──
    old_cam = scene.camera
    old_filepath = scene.render.filepath
    old_shading_type = space_data.shading.type
    old_render_pass = getattr(space_data.shading, 'render_pass', None)
    old_use_scene_world = getattr(space_data.shading, 'use_scene_world', None)
    old_show_overlays = getattr(overlay, 'show_overlays', None)
    old_show_gizmo = getattr(space_data, 'show_gizmo', None)
    old_show_gizmo_navigate = getattr(space_data, 'show_gizmo_navigate', None)
    old_persp = space_data.region_3d.view_perspective if space_data.region_3d else None

    try:
        # ── Set camera ──
        scene.camera = camera_obj

        # ── Switch viewport to CAMERA VIEW ──
        if space_data.region_3d:
            space_data.region_3d.view_perspective = 'CAMERA'

        # ── MATERIAL shading + MIST pass ──
        space_data.shading.type = 'MATERIAL'
        if hasattr(space_data.shading, 'render_pass'):
            space_data.shading.render_pass = 'MIST'
        if hasattr(space_data.shading, 'use_scene_world'):
            space_data.shading.use_scene_world = True

        # ── Disable ALL overlays + gizmos ──
        if hasattr(overlay, 'show_overlays'):
            overlay.show_overlays = False
        if hasattr(space_data, 'show_gizmo'):
            space_data.show_gizmo = False
        if hasattr(space_data, 'show_gizmo_navigate'):
            space_data.show_gizmo_navigate = False

        # ── Render output settings (same as depth_utils) ──
        scene.render.filepath = output_path
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'

        # ── Execute viewport render (exact same as depth_utils) ──
        override_context = {
            'window': viewport_window,
            'screen': viewport_screen,
            'scene': scene,
            'area': viewport_area,
            'region': viewport_area.regions[-1],
            'space_data': space_data,
        }

        with bpy.context.temp_override(**override_context):
            bpy.ops.render.opengl(write_still=True)

        print(f"[TEX PIPE] Mist rendered: {output_path}")

    finally:
        # ── Restore everything (same order as depth_utils) ──
        if old_render_pass is not None and hasattr(space_data.shading, 'render_pass'):
            space_data.shading.render_pass = old_render_pass
        if old_shading_type:
            space_data.shading.type = old_shading_type
        if old_use_scene_world is not None and hasattr(space_data.shading, 'use_scene_world'):
            space_data.shading.use_scene_world = old_use_scene_world
        if old_show_overlays is not None and hasattr(overlay, 'show_overlays'):
            overlay.show_overlays = old_show_overlays
        if old_show_gizmo is not None and hasattr(space_data, 'show_gizmo'):
            space_data.show_gizmo = old_show_gizmo
        if old_show_gizmo_navigate is not None and hasattr(space_data, 'show_gizmo_navigate'):
            space_data.show_gizmo_navigate = old_show_gizmo_navigate
        if old_persp is not None and space_data.region_3d:
            space_data.region_3d.view_perspective = old_persp
        scene.camera = old_cam
        scene.render.filepath = old_filepath

    return output_path


def render_single_view(scene, camera_obj, output_path: str):
    """Normal Eevee/Workbench render from *camera_obj*."""
    scene.camera = camera_obj
    camera_obj.hide_render = False
    scene.render.filepath = output_path

    bpy.ops.render.render(write_still=True)

    camera_obj.hide_render = True
    print(f"[TEX PIPE] Rendered: {output_path}")
    return output_path


def render_all_views(scene, cameras: list, output_dir: str,
                     render_type: str = "mist") -> list:
    """Render all camera views. Returns list of file paths.

    render_type:
      'mist'   — viewport mist pass (depth maps)
      'color'  — normal Eevee/Workbench render
    """
    paths = []
    for cam_info in cameras:
        name = cam_info['name']
        filename = f"{TEMP_PREFIX}{render_type}_{name}.png"
        out_path = os.path.join(output_dir, filename)

        if render_type == "mist":
            render_single_view_mist(scene, cam_info['camera'], out_path)
        else:
            render_single_view(scene, cam_info['camera'], out_path)

        paths.append(out_path)
    return paths


# ══════════════════════════════════════════════════════════════════
#  4.  COLLAGE ASSEMBLY & SPLITTING
#      ALL FUNCTIONS MUST RUN IN MAIN THREAD (bpy.data.images).
# ══════════════════════════════════════════════════════════════════

def create_collage(image_paths: list, tile_size: int = 1024) -> str:
    """Stitch square images into a grid collage.

    Grid size is computed automatically from the number of images.
    Returns the saved collage file path.
    """
    import math as _m
    n = len(image_paths)
    cols = _m.ceil(_m.sqrt(n))
    rows = _m.ceil(n / cols)
    coll_w = tile_size * cols
    coll_h = tile_size * rows

    collage = bpy.data.images.new(
        f"{TEMP_PREFIX}collage", coll_w, coll_h, alpha=True
    )
    pixels = [0.0] * (coll_w * coll_h * 4)

    for idx, path in enumerate(image_paths):
        if idx >= cols * rows:
            break

        col = idx % cols
        row = idx // cols

        src = bpy.data.images.load(path, check_existing=False)
        src.colorspace_settings.name = 'Non-Color'
        src.scale(tile_size, tile_size)
        src_pixels = list(src.pixels)

        x_off = col * tile_size
        y_off = (rows - 1 - row) * tile_size  # bottom-up

        for y in range(tile_size):
            src_start = y * tile_size * 4
            src_end = src_start + tile_size * 4
            dst_y = y_off + y
            dst_start = (dst_y * coll_w + x_off) * 4
            dst_end = dst_start + tile_size * 4
            pixels[dst_start:dst_end] = src_pixels[src_start:src_end]

        bpy.data.images.remove(src)

    collage.pixels = pixels

    out_path = os.path.join(tempfile.gettempdir(), f"{TEMP_PREFIX}collage.png")
    collage.filepath_raw = out_path
    collage.file_format = 'PNG'
    collage.save()
    bpy.data.images.remove(collage)

    print(f"[TEX PIPE] Collage saved: {out_path} ({len(image_paths)} tiles)")
    return out_path


def split_collage(collage_path: str, num_tiles: int,
                  tile_size: int = 1024) -> list:
    """Split a grid collage into individual tiles. Returns file paths."""
    import math as _m
    cols = _m.ceil(_m.sqrt(num_tiles))
    rows = _m.ceil(num_tiles / cols)

    src = bpy.data.images.load(collage_path, check_existing=False)
    src.scale(cols * tile_size, rows * tile_size)
    src_pixels = list(src.pixels)

    out_dir = tempfile.mkdtemp(prefix=TEMP_PREFIX)
    paths = []

    for idx in range(min(num_tiles, cols * rows)):
        col = idx % cols
        row = idx // cols

        tile = bpy.data.images.new(
            f"{TEMP_PREFIX}tile_{idx}", tile_size, tile_size, alpha=True
        )
        tile_pixels = [0.0] * (tile_size * tile_size * 4)

        x_off = col * tile_size
        y_off = (rows - 1 - row) * tile_size

        for y in range(tile_size):
            src_y = y_off + y
            src_start = (src_y * cols * tile_size + x_off) * 4
            src_end = src_start + tile_size * 4
            dst_start = y * tile_size * 4
            dst_end = dst_start + tile_size * 4
            tile_pixels[dst_start:dst_end] = src_pixels[src_start:src_end]

        tile.pixels = tile_pixels

        out_path = os.path.join(out_dir, f"tile_{idx}.png")
        tile.filepath_raw = out_path
        tile.file_format = 'PNG'
        tile.save()
        bpy.data.images.remove(tile)

        paths.append(out_path)

    bpy.data.images.remove(src)
    print(f"[TEX PIPE] Collage split into {len(paths)} tiles")
    return paths


def mask_with_depth(texture_paths: list, depth_paths: list) -> list:
    """Force AI textures to match depth map silhouettes pixel-perfectly.

    For each texture tile, the corresponding depth map is used as a mask:
    - Where depth > 0 (object): keep the AI texture
    - Where depth == 0 (background): force pure black

    This eliminates any silhouette deviations the AI introduced.
    Returns the same paths (files are modified in-place).
    """
    if len(texture_paths) != len(depth_paths):
        print(f"[TEX PIPE] mask_with_depth: mismatch "
              f"({len(texture_paths)} tex vs {len(depth_paths)} depth)")
        return texture_paths

    for tex_path, depth_path in zip(texture_paths, depth_paths):
        tex_img = bpy.data.images.load(tex_path, check_existing=False)
        depth_img = bpy.data.images.load(depth_path, check_existing=False)

        tw, th = tex_img.size[0], tex_img.size[1]
        dw, dh = depth_img.size[0], depth_img.size[1]

        # Scale depth to match texture if needed
        if dw != tw or dh != th:
            depth_img.scale(tw, th)

        tex_px = list(tex_img.pixels)
        depth_px = list(depth_img.pixels)
        total = tw * th

        for i in range(total):
            # Depth pixel luminance (any channel — they're grayscale)
            d = depth_px[i * 4]  # R channel
            if d < 0.01:
                # Background — force black
                tex_px[i * 4 + 0] = 0.0
                tex_px[i * 4 + 1] = 0.0
                tex_px[i * 4 + 2] = 0.0
                tex_px[i * 4 + 3] = 1.0

        tex_img.pixels = tex_px
        tex_img.filepath_raw = tex_path
        tex_img.file_format = 'PNG'
        tex_img.save()

        bpy.data.images.remove(tex_img)
        bpy.data.images.remove(depth_img)

    print(f"[TEX PIPE] Masked {len(texture_paths)} textures with depth maps")
    return texture_paths


# ══════════════════════════════════════════════════════════════════
#  5.  UV PROJECTION & TEXTURE SHADER ASSEMBLY
# ══════════════════════════════════════════════════════════════════

def _project_uvs_from_camera(obj, cam_obj, uv_layer_name: str):
    """Project UVs using Blender's project_from_view (exact camera match).

    Falls back to manual orthographic math if the viewport isn't available
    (e.g. running headless or from a background thread callback).
    """
    mesh = obj.data
    mesh.uv_layers[uv_layer_name].active = True

    scene = bpy.context.scene
    old_cam = scene.camera
    scene.camera = cam_obj

    success = False

    try:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        for area in bpy.context.screen.areas:
            if area.type != 'VIEW_3D':
                continue

            # Switch viewport to camera
            r3d = None
            old_persp = 'PERSP'
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    r3d = space.region_3d
                    old_persp = r3d.view_perspective
                    r3d.view_perspective = 'CAMERA'
                    break

            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.uv.project_from_view(
                            camera_bounds=True,
                            correct_aspect=True,
                            scale_to_bounds=False,
                        )
                    success = True
                    break

            # Restore viewport
            if r3d:
                r3d.view_perspective = old_persp
            break

        bpy.ops.object.mode_set(mode='OBJECT')

    except Exception as e:
        print(f"[TEX PIPE] project_from_view failed: {e}")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    scene.camera = old_cam

    if success:
        print(f"[TEX PIPE] UV projected (view): {uv_layer_name}")
    else:
        print(f"[TEX PIPE] Fallback to manual: {uv_layer_name}")
        _manual_ortho_project(obj, cam_obj, uv_layer_name)


def _manual_ortho_project(obj, cam_obj, uv_layer_name: str):
    """Manual orthographic UV projection — exact same math as project_from_view."""
    mesh = obj.data
    cam_data = cam_obj.data

    bpy.context.view_layer.update()

    cam_inv = cam_obj.matrix_world.inverted()
    obj_mat = obj.matrix_world
    ortho_scale = cam_data.ortho_scale

    uv_layer = mesh.uv_layers[uv_layer_name]

    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            vert_idx = mesh.loops[loop_idx].vertex_index
            world_pos = obj_mat @ mesh.vertices[vert_idx].co
            cam_pos = cam_inv @ world_pos

            u = cam_pos.x / ortho_scale + 0.5
            v = cam_pos.y / ortho_scale + 0.5

            uv_layer.data[loop_idx].uv = (u, v)


# ─── Node Group builder ─────────────────────────────────────────

def _build_projection_group(cameras: list, texture_paths: list):
    """Build a ShaderNodeTree group for multi-view projection.

    Uses Geometry.Position + hardcoded camera axis dot products for UV
    computation. NO external object references — all camera matrices are
    baked as constant values into the shader nodes.

    Blending: normalized weight blending (weights sum to 1.0) ensures
    smooth, seam-free transitions for complex models like characters.
    """
    PRIMARY_NAMES = {'Front', 'Back', 'Left', 'Right', 'Top', 'Bottom'}

    group_name = "NB_Texture_Projection"
    old = bpy.data.node_groups.get(group_name)
    if old:
        bpy.data.node_groups.remove(old)
    group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

    try:
        group.interface.new_socket(
            'Color', in_out='OUTPUT', socket_type='NodeSocketColor'
        )
    except AttributeError:
        group.outputs.new('NodeSocketColor', 'Color')

    nodes = group.nodes
    links = group.links

    group_out = nodes.new('NodeGroupOutput')
    group_out.location = (1600, 0)

    # ── Shared Geometry node (Position + Normal) ──
    geom = nodes.new('ShaderNodeNewGeometry')
    geom.location = (-2000, 0)
    geom.label = "Geometry (shared)"

    # Layout constants
    ROW_H = 550
    COL_UV     = -1600
    COL_UV2    = -1350
    COL_COMB   = -1100
    COL_TEX    = -800
    COL_MASK   = -1350
    COL_RAMP   = -1000
    COL_WMUL   = -400
    COL_WSUM   = 0
    COL_FINAL  = 400

    hues = [
        (0.28, 0.34, 0.48), (0.28, 0.44, 0.38),
        (0.38, 0.34, 0.48), (0.44, 0.38, 0.28),
        (0.28, 0.42, 0.28), (0.44, 0.28, 0.38),
    ]

    # ═══════════════════════════════════════════════════════════
    # Stage 1: Create texture + raw weight per camera
    # ═══════════════════════════════════════════════════════════
    cam_data = []   # list of (color_output, weight_output, view_name)

    for idx, (cam_info, tex_path) in enumerate(zip(cameras, texture_paths)):
        view_name = cam_info['name']
        cam_obj = cam_info['camera']
        ortho = cam_obj.data.ortho_scale

        # ── Extract camera axes + position ──
        mat_w = cam_obj.matrix_world
        cam_right = mat_w.to_3x3() @ Vector((1, 0, 0))
        cam_up    = mat_w.to_3x3() @ Vector((0, 1, 0))
        cam_pos   = mat_w.translation

        # Precompute projection constants:
        #   u = dot(world_pos, cam_right/ortho) + offset_u
        #   v = dot(world_pos, cam_up/ortho)    + offset_v
        u_dir = cam_right / ortho
        u_off = -cam_pos.dot(cam_right) / ortho + 0.5
        v_dir = cam_up / ortho
        v_off = -cam_pos.dot(cam_up) / ortho + 0.5

        row_y = -idx * ROW_H

        frame = nodes.new('NodeFrame')
        frame.label = view_name
        frame.use_custom_color = True
        frame.color = hues[idx % len(hues)]
        frame.label_size = 18

        # ── UV via dot products (hardcoded constants) ──
        dot_u = nodes.new('ShaderNodeVectorMath')
        dot_u.operation = 'DOT_PRODUCT'
        dot_u.label = f"U {view_name}"
        dot_u.location = (COL_UV, row_y)
        dot_u.parent = frame
        links.new(geom.outputs['Position'], dot_u.inputs[0])
        dot_u.inputs[1].default_value = (u_dir.x, u_dir.y, u_dir.z)

        add_u = nodes.new('ShaderNodeMath')
        add_u.operation = 'ADD'
        add_u.label = f"U+ {view_name}"
        add_u.location = (COL_UV2, row_y)
        add_u.parent = frame
        links.new(dot_u.outputs['Value'], add_u.inputs[0])
        add_u.inputs[1].default_value = u_off

        dot_v = nodes.new('ShaderNodeVectorMath')
        dot_v.operation = 'DOT_PRODUCT'
        dot_v.label = f"V {view_name}"
        dot_v.location = (COL_UV, row_y - 100)
        dot_v.parent = frame
        links.new(geom.outputs['Position'], dot_v.inputs[0])
        dot_v.inputs[1].default_value = (v_dir.x, v_dir.y, v_dir.z)

        add_v = nodes.new('ShaderNodeMath')
        add_v.operation = 'ADD'
        add_v.label = f"V+ {view_name}"
        add_v.location = (COL_UV2, row_y - 100)
        add_v.parent = frame
        links.new(dot_v.outputs['Value'], add_v.inputs[0])
        add_v.inputs[1].default_value = v_off

        combine = nodes.new('ShaderNodeCombineXYZ')
        combine.label = f"UV {view_name}"
        combine.location = (COL_COMB, row_y - 50)
        combine.parent = frame
        links.new(add_u.outputs['Value'], combine.inputs['X'])
        links.new(add_v.outputs['Value'], combine.inputs['Y'])
        combine.inputs['Z'].default_value = 0.0

        # ── Image Texture ──
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.label = f"Tex {view_name}"
        tex_node.location = (COL_TEX, row_y - 50)
        tex_node.width = 220
        tex_node.parent = frame
        img = bpy.data.images.load(tex_path, check_existing=False)
        img.name = f"NB_Tex_{view_name}"
        tex_node.image = img
        links.new(combine.outputs['Vector'], tex_node.inputs['Vector'])

        # ── Facing mask: raw weight = max(0, dot(normal, cam_dir))^N ──
        # Front/Back get lower power (broader coverage) + priority boost
        # to reduce face/detail distortion from side camera bleeding
        PRIORITY_VIEWS = {'Front', 'Back'}
        pos_dir = cam_info.get('pos_dir') or _name_to_pos_dir(view_name)
        if pos_dir is None:
            pos_dir = Vector((0, 0, 1))

        mask_dot = nodes.new('ShaderNodeVectorMath')
        mask_dot.operation = 'DOT_PRODUCT'
        mask_dot.label = f"Face {view_name}"
        mask_dot.location = (COL_MASK, row_y - 220)
        mask_dot.parent = frame
        links.new(geom.outputs['Normal'], mask_dot.inputs[0])
        mask_dot.inputs[1].default_value = (
            pos_dir.x, pos_dir.y, pos_dir.z
        )

        # Clamp negative (backfacing → 0)
        clamp = nodes.new('ShaderNodeMath')
        clamp.operation = 'MAXIMUM'
        clamp.label = f"Clamp"
        clamp.location = (COL_RAMP, row_y - 220)
        clamp.parent = frame
        clamp.hide = True
        links.new(mask_dot.outputs['Value'], clamp.inputs[0])
        clamp.inputs[1].default_value = 0.0

        # Power: Front/Back = 1.5 (broad), others = 3.0 (tight)
        pw = 1.5 if view_name in PRIORITY_VIEWS else 3.0
        power = nodes.new('ShaderNodeMath')
        power.operation = 'POWER'
        power.label = f"^{pw}"
        power.location = (COL_RAMP + 180, row_y - 220)
        power.parent = frame
        power.hide = True
        links.new(clamp.outputs['Value'], power.inputs[0])
        power.inputs[1].default_value = pw

        # Priority boost: Front/Back × 2.0 for dominance
        weight_out = power.outputs['Value']
        if view_name in PRIORITY_VIEWS:
            boost = nodes.new('ShaderNodeMath')
            boost.operation = 'MULTIPLY'
            boost.label = f"Boost ×2"
            boost.location = (COL_RAMP + 360, row_y - 220)
            boost.parent = frame
            boost.hide = True
            links.new(power.outputs['Value'], boost.inputs[0])
            boost.inputs[1].default_value = 2.0
            weight_out = boost.outputs['Value']

        cam_data.append({
            'color': tex_node.outputs['Color'],
            'weight': weight_out,
            'name': view_name,
            'row_y': row_y,
            'frame': frame,
        })

    # ═══════════════════════════════════════════════════════════
    # Stage 2: Normalized weight blending (weights sum to 1.0)
    #   Eliminates seams — each point has smooth, balanced weights
    # ═══════════════════════════════════════════════════════════

    # Sum all weights
    if len(cam_data) == 1:
        weight_sum = cam_data[0]['weight']
    else:
        weight_sum = cam_data[0]['weight']
        for i in range(1, len(cam_data)):
            add_w = nodes.new('ShaderNodeMath')
            add_w.operation = 'ADD'
            add_w.label = f"Σ w{i}"
            add_w.location = (COL_WSUM, -i * 80)
            links.new(weight_sum, add_w.inputs[0])
            links.new(cam_data[i]['weight'], add_w.inputs[1])
            weight_sum = add_w.outputs['Value']

    # Prevent division by zero
    safe_sum = nodes.new('ShaderNodeMath')
    safe_sum.operation = 'MAXIMUM'
    safe_sum.label = "Safe÷"
    safe_sum.location = (COL_WSUM + 200, 0)
    links.new(weight_sum, safe_sum.inputs[0])
    safe_sum.inputs[1].default_value = 0.001

    # Weighted sum: Σ (w_i / sum) * color_i
    prev_color = None
    for i, cd in enumerate(cam_data):
        row_y = cd['row_y']

        # Normalize: w_i / sum
        div = nodes.new('ShaderNodeMath')
        div.operation = 'DIVIDE'
        div.label = f"Norm {cd['name']}"
        div.location = (COL_WMUL, row_y - 200)
        links.new(cd['weight'], div.inputs[0])
        links.new(safe_sum.outputs['Value'], div.inputs[1])

        # Mix with accumulated color
        if bpy.app.version >= (4, 0, 0):
            mix = nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.blend_type = 'MIX'
            mix.clamp_factor = True
            mix.label = f"Blend {cd['name']}"
            mix.location = (COL_FINAL, row_y)
            links.new(div.outputs['Value'], mix.inputs['Factor'])
            if prev_color is None:
                mix.inputs[6].default_value = (0, 0, 0, 1)
            else:
                links.new(prev_color, mix.inputs[6])
            links.new(cd['color'], mix.inputs[7])
            prev_color = mix.outputs[2]
        else:
            mix = nodes.new('ShaderNodeMixRGB')
            mix.blend_type = 'MIX'
            mix.label = f"Blend {cd['name']}"
            mix.location = (COL_FINAL, row_y)
            links.new(div.outputs['Value'], mix.inputs['Fac'])
            if prev_color is None:
                mix.inputs['Color1'].default_value = (0, 0, 0, 1)
            else:
                links.new(prev_color, mix.inputs['Color1'])
            links.new(cd['color'], mix.inputs['Color2'])
            prev_color = mix.outputs['Color']

    if prev_color:
        links.new(prev_color, group_out.inputs[0])

    print(f"[TEX PIPE] Node group '{group_name}': {len(cameras)} cameras "
          f"(hardcoded projection, normalized blending)")
    return group


# ─── Main entry point ───────────────────────────────────────────

def project_textures(obj, cameras: list, texture_paths: list):
    """Create a multi-projection material.

    Uses Geometry.Position + hardcoded camera constants (NOT TexCoord.Object).
    All projection math is baked as shader node constants — zero external
    object references, guaranteed correct in all Blender versions.
    """
    if len(texture_paths) != len(cameras):
        raise ValueError(
            f"Mismatch: {len(cameras)} cameras vs "
            f"{len(texture_paths)} textures"
        )

    bpy.context.view_layer.update()

    # Build self-contained projection node group
    group = _build_projection_group(cameras, texture_paths)

    # Create clean material
    mat_name = "NB_Projected"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    output_node = tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (500, 0)

    principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (200, 0)
    tree.links.new(
        principled.outputs['BSDF'], output_node.inputs['Surface']
    )

    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = group
    group_node.name = "Texture Projection"
    group_node.label = "AI Texture Projection"
    group_node.location = (-100, 0)
    group_node.width = 200
    tree.links.new(
        group_node.outputs['Color'], principled.inputs['Base Color']
    )

    obj.data.materials.clear()
    obj.data.materials.append(mat)
    print(f"[TEX PIPE] Material assigned: {len(cameras)} cameras "
          f"(hardcoded projection, no object references)")


# ══════════════════════════════════════════════════════════════════
#  6.  TEXTURE BAKING
# ══════════════════════════════════════════════════════════════════

def bake_final(obj, resolution: int = 4096) -> str:
    """Bake projection material into a single UV texture."""
    scene = bpy.context.scene
    snap = _store_render_settings(scene)

    try:
        scene.render.engine = 'CYCLES'
        if hasattr(scene, 'cycles'):
            scene.cycles.device = 'GPU' if _has_gpu() else 'CPU'
            scene.cycles.samples = 16

        bake_img_name = "NB_Baked_Albedo"
        if bake_img_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[bake_img_name])
        bake_img = bpy.data.images.new(
            bake_img_name, resolution, resolution, alpha=False
        )

        mesh = obj.data
        if "NB_AutoUV" in mesh.uv_layers:
            mesh.uv_layers["NB_AutoUV"].active = True
            mesh.uv_layers["NB_AutoUV"].active_render = True

        mat = obj.data.materials[0] if obj.data.materials else None
        if not mat or not mat.use_nodes:
            raise RuntimeError("No valid material on object")

        tree = mat.node_tree
        bake_node = tree.nodes.new('ShaderNodeTexImage')
        bake_node.name = "NB_BakeTarget"
        bake_node.image = bake_img
        bake_node.location = (1600, 0)

        for n in tree.nodes:
            n.select = False
        bake_node.select = True
        tree.nodes.active = bake_node

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        bpy.ops.object.bake(
            type='DIFFUSE',
            pass_filter={'COLOR'},
            margin=16,
            margin_type='EXTEND',
        )

        out_dir = os.path.join(tempfile.gettempdir(), "nano_banana_baked")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{bake_img_name}.png")

        bake_img.filepath_raw = out_path
        bake_img.file_format = 'PNG'
        bake_img.save()

        _replace_with_baked_material(obj, bake_img)
        print(f"[TEX PIPE] Baked texture: {out_path}")
        return out_path

    finally:
        _restore_render_settings(scene, snap)


def _replace_with_baked_material(obj, bake_img):
    mat_name = "NB_Baked_Material"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)
    principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (300, 0)
    tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.location = (0, 0)
    tex.image = bake_img
    tree.links.new(tex.outputs['Color'], principled.inputs['Base Color'])

    obj.data.materials.clear()
    obj.data.materials.append(mat)


def _has_gpu() -> bool:
    try:
        prefs = bpy.context.preferences.addons.get('cycles')
        if prefs:
            return bool(
                prefs.preferences.get_devices_for_type('CUDA')
                or prefs.preferences.get_devices_for_type('OPTIX')
                or prefs.preferences.get_devices_for_type('HIP')
            )
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════
#  7.  CLEANUP
# ══════════════════════════════════════════════════════════════════

def cleanup_temp_data():
    """Remove all temporary images, materials, UV layers, and cameras."""
    for img in list(bpy.data.images):
        if img.name.startswith(TEMP_PREFIX) or img.name.startswith("NB_Tex_"):
            bpy.data.images.remove(img)

    for mat in list(bpy.data.materials):
        if mat.name.startswith("NB_"):
            bpy.data.materials.remove(mat)

    for mesh in bpy.data.meshes:
        to_remove = [
            uv for uv in mesh.uv_layers if uv.name.startswith("NB_Proj_")
        ]
        for uv in to_remove:
            mesh.uv_layers.remove(uv)

    remove_temp_cameras()
    print("[TEX PIPE] Full cleanup complete")
