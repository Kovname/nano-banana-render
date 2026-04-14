"""
texture_operators.py — Blender operators for the AI texturing pipeline.

Operators:
  • BANANA_OT_init_tex_cameras    — Create cameras around mesh
  • BANANA_OT_update_tex_cameras  — Update camera distance/scale
  • BANANA_OT_preview_tex_camera  — Look through a specific camera
  • BANANA_OT_texture_draft       — Draft generation (mist collage → API → project)
  • BANANA_OT_texture_enhance     — Per-view enhancement with depth
  • BANANA_OT_cleanup_tex         — Remove all temp pipeline data
"""

import bpy
import os
import tempfile
import threading
import time
from bpy.types import Operator
from bpy.props import IntProperty, StringProperty

from . import texture_pipeline as pipe
from . import beta_api
from .threading_utils import execute_in_main_thread
from .render_engine import MODEL_MAP


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────

COST_GRID = {
    'flash': {'1024': 10, '2048': 15, '4096': 60},
    'pro':   {'1024': 30, '2048': 45, '4096': 60},
}


def _get_cost(props) -> int:
    tier = 'pro' if props.ai_model == 'NANO_BANANA_PRO' else 'flash'
    res = getattr(props, 'tex_resolution', '1024')
    return COST_GRID.get(tier, COST_GRID['pro']).get(res, 30)


def _get_token() -> str:
    prefs = bpy.context.preferences.addons.get("nano_banana_render")
    if prefs and hasattr(prefs.preferences, "beta_token"):
        return prefs.preferences.beta_token.strip()
    return ""


def _is_direct_api() -> bool:
    return _get_token().startswith("AIza")


def _call_api_depth(prompt: str, model_name: str, depth_image_path: str,
                    reference_image_path: str = None,
                    width: int = 1024, height: int = 1024):
    """Send a DEPTH MAP image to the AI for texture generation.

    Routes to direct Google API or Nanode server.
    Returns: (image_bytes, generation_id, new_balance)
    """
    token = _get_token()

    if token.startswith("AIza"):
        from .gemini_api import GeminiAPI
        gemini = GeminiAPI(api_key=token, model=model_name)
        image_data, _ = gemini.generate_image(
            depth_image_path=depth_image_path,
            user_prompt=prompt,
            reference_image_path=reference_image_path,
            is_color_render=False,
            width=width,
            height=height,
        )
        return image_data, 0, -1

    else:
        image_data, generation_id, new_balance = beta_api.generate(
            prompt=prompt,
            model=model_name,
            input_image_path=depth_image_path,
            reference_image_path=reference_image_path,
            gen_type="texture_draft",
            width=width,
            height=height,
        )
        return image_data, generation_id, new_balance


def _call_api_enhance(prompt: str, model_name: str,
                      color_path: str, depth_path: str,
                      ref_path: str = None,
                      width: int = 1024, height: int = 1024):
    """Send a COLOR render + DEPTH MAP for enhancement.

    The colour image is the base to improve; depth map provides geometry.
    Returns: (image_bytes, generation_id, new_balance)
    """
    token = _get_token()

    if token.startswith("AIza"):
        from .gemini_api import GeminiAPI
        gemini = GeminiAPI(api_key=token, model=model_name)
        # For enhancement: send colour render as depth_image_path (main input),
        # and use the depth map as reference for geometry guidance.
        image_data, _ = gemini.generate_image(
            depth_image_path=color_path,
            user_prompt=prompt,
            reference_image_path=depth_path,
            is_color_render=True,  # colour-based enhancement
            width=width,
            height=height,
        )
        return image_data, 0, -1

    else:
        image_data, generation_id, new_balance = beta_api.generate(
            prompt=prompt,
            model=model_name,
            input_image_path=color_path,
            reference_image_path=depth_path,
            gen_type="texture_enhance",
            width=width,
            height=height,
        )
        return image_data, generation_id, new_balance


def _collect_cameras(props) -> list:
    """Gather existing temp cameras by scanning scene objects."""
    prefix = pipe.TEMP_PREFIX + "cam_"
    cameras = []
    for idx, obj in enumerate(sorted(
        (o for o in bpy.data.objects if o.name.startswith(prefix)),
        key=lambda o: o.name
    )):
        name = obj.name[len(prefix):]
        pos_dir = pipe._name_to_pos_dir(name)
        cameras.append({
            'name': name,
            'camera': obj,
            'pos_dir': pos_dir,
            'index': idx,
        })
    return cameras


def _get_gemini_dimensions(cols: int, rows: int, resolution: int) -> tuple[int, int]:
    import math
    gcd = math.gcd(cols, rows)
    w_ratio = cols // gcd
    h_ratio = rows // gcd
    ratio = f"{w_ratio}:{h_ratio}"

    idx = 0
    if resolution >= 2048: idx = 1
    if resolution >= 4096: idx = 2

    dims = {
        "1:1": [(1024,1024), (2048,2048), (4096,4096)],
        "4:3": [(1200,896), (2400,1792), (4800,3584)],
        "3:4": [(896,1200), (1792,2400), (3584,4800)],
        "3:2": [(1264,848), (2528,1696), (5056,3392)],
        "2:3": [(848,1264), (1696,2528), (3392,5056)],
        "5:4": [(1152,928), (2304,1856), (4608,3712)],
        "4:5": [(928,1152), (1856,2304), (3712,4608)],
        "16:9": [(1376,768), (2752,1536), (5504,3072)],
        "9:16": [(768,1376), (1536,2752), (3072,5504)],
        "4:1": [(2048,512), (4096,1024), (8192,2048)],
        "1:4": [(512,2048), (1024,4096), (2048,8192)],
        "8:1": [(3072,384), (6144,768), (12288,1536)],
        "1:8": [(384,3072), (768,6144), (1536,12288)],
    }
    if ratio in dims:
        return dims[ratio][idx]
    
    return (cols * resolution, rows * resolution)


def _update_status(scene, text: str):
    def _upd():
        if hasattr(scene, 'gemini_render'):
            scene.gemini_render.tex_status = text
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type in ('VIEW_3D', 'PROPERTIES'):
                        area.tag_redraw()
    execute_in_main_thread(_upd)


def _set_processing(scene, val: bool):
    def _upd():
        if hasattr(scene, 'gemini_render'):
            scene.gemini_render.tex_is_processing = val
    execute_in_main_thread(_upd)


def _wait_for(box, label: str, timeout: int = 300):
    """Block until box[0] is not None (or is an Exception)."""
    elapsed = 0
    while box[0] is None and elapsed < timeout:
        time.sleep(0.2)
        elapsed += 0.2
    if isinstance(box[0], Exception):
        raise box[0]
    if box[0] is None:
        raise RuntimeError(f"{label} timed out (>{timeout}s)")


# ──────────────────────────────────────────────────────────────────
#  Operator: Init Cameras
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_init_tex_cameras(Operator):
    """Create orthographic cameras around the selected mesh"""
    bl_idname = "banana.init_tex_cameras"
    bl_label = "Init Cameras"
    bl_description = "Place virtual cameras around the selected mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None
                and context.active_object.type == 'MESH'
                and context.mode == 'OBJECT')

    def execute(self, context):
        obj = context.active_object
        props = context.scene.gemini_render

        pipe.remove_temp_cameras()

        cameras = pipe.create_cameras(
            obj,
            preset=props.tex_camera_preset,
            include_top=props.tex_include_top,
            include_bottom=props.tex_include_bottom,
            distance=props.tex_cam_distance,
            ortho_scale=props.tex_cam_ortho_scale,
        )

        props.tex_camera_count = len(cameras)
        props.tex_status = f"Cameras ready ({len(cameras)} views)"
        self.report({'INFO'}, f"Created {len(cameras)} cameras")
        return {'FINISHED'}


# ──────────────────────────────────────────────────────────────────
#  Operator: Update Cameras (distance / ortho_scale)
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_update_tex_cameras(Operator):
    """Update camera positions and ortho scale"""
    bl_idname = "banana.update_tex_cameras"
    bl_label = "Update Cameras"
    bl_description = "Re-position cameras using current Distance / Ortho Scale"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None
                and context.active_object.type == 'MESH'
                and any(o.name.startswith(pipe.TEMP_PREFIX + "cam_")
                        for o in bpy.data.objects))

    def execute(self, context):
        obj = context.active_object
        props = context.scene.gemini_render

        pipe.update_cameras(
            distance=props.tex_cam_distance,
            ortho_scale=props.tex_cam_ortho_scale,
            target_obj=obj,
        )

        self.report({'INFO'}, "Cameras updated")
        return {'FINISHED'}


# ──────────────────────────────────────────────────────────────────
#  Operator: Preview Camera
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_preview_tex_camera(Operator):
    """Look through a specific pipeline camera"""
    bl_idname = "banana.preview_tex_camera"
    bl_label = "Preview Camera"
    bl_description = "Set the viewport to this camera view"

    camera_name: StringProperty(name="Camera Name", default="")

    def execute(self, context):
        full_name = f"{pipe.TEMP_PREFIX}cam_{self.camera_name}"
        ok = pipe.set_viewport_to_camera(full_name)
        if ok:
            self.report({'INFO'}, f"Viewing: {self.camera_name}")
        else:
            self.report({'WARNING'}, f"Camera '{self.camera_name}' not found")
        return {'FINISHED'}


# ──────────────────────────────────────────────────────────────────
#  Operator: Draft Generation (mist collage → AI → project)
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_texture_draft(Operator):
    """Generate a draft texture from mist/depth collage"""
    bl_idname = "banana.texture_draft"
    bl_label = "Generate Draft"
    bl_description = (
        "Render mist/depth views, assemble collage, send to AI, "
        "split result and project textures onto the model"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        props = getattr(context.scene, 'gemini_render', None)
        if not obj or obj.type != 'MESH' or context.mode != 'OBJECT':
            return False
        if not props or props.tex_is_processing:
            return False
        return any(o.name.startswith(pipe.TEMP_PREFIX + "cam_")
                   for o in bpy.data.objects)

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        props = scene.gemini_render

        if not _get_token():
            self.report({'ERROR'}, "No API key configured")
            return {'CANCELLED'}
        if not props.tex_prompt.strip() or len(props.tex_prompt.strip()) < 5:
            self.report({'ERROR'}, "Prompt too short")
            return {'CANCELLED'}

        try:
            pipe.prepare_mesh(obj, auto_uv=props.tex_auto_uv)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        props.tex_is_processing = True
        props.tex_status = "Starting draft generation..."

        cameras = _collect_cameras(props)
        if not cameras:
            props.tex_is_processing = False
            self.report({'ERROR'}, "No cameras. Click 'Init Cameras' first.")
            return {'CANCELLED'}

        # Save reference image to temp file if provided
        ref_path = None
        if props.tex_reference_image:
            ref_img = props.tex_reference_image
            import tempfile as _tf
            ref_dir = _tf.mkdtemp(prefix=pipe.TEMP_PREFIX)
            ref_path = os.path.join(ref_dir, "style_reference.png")
            orig_fp = ref_img.filepath_raw
            orig_fmt = ref_img.file_format
            try:
                ref_img.filepath_raw = ref_path
                ref_img.file_format = 'PNG'
                ref_img.save()
            finally:
                ref_img.filepath_raw = orig_fp
                ref_img.file_format = orig_fmt
            print(f"[TEX PIPE] Style reference saved: {ref_path}")

        t = threading.Thread(
            target=self._run_draft,
            args=(scene, obj.name, cameras, props.tex_prompt,
                  int(props.tex_resolution), props.ai_model,
                  props.tex_depth_start, props.tex_depth_depth,
                  props.mist_falloff, ref_path, props.tex_render_mode),
            daemon=True,
        )
        t.start()
        return {'FINISHED'}

    @staticmethod
    def _run_draft(scene, obj_name, cameras, prompt, resolution,
                   ai_model, mist_start, mist_depth, mist_falloff,
                   reference_path=None, render_mode='MIST'):
        try:
            tmp_dir = tempfile.mkdtemp(prefix=pipe.TEMP_PREFIX)

            # ─── Step 1: Render MIST views (main thread) ───
            _update_status(scene, "Rendering depth (mist) views...")
            r = [None]

            def _do_mist_render():
                try:
                    snap = pipe._store_render_settings(scene)
                    try:
                        if render_mode == 'MIST':
                            pipe.setup_mist_render(
                                scene, resolution,
                                mist_start, mist_depth, mist_falloff,
                            )
                            paths = pipe.render_all_views(
                                scene, cameras, tmp_dir, "mist"
                            )
                        else:
                            pipe.setup_flat_render(scene, resolution)
                            paths = pipe.render_all_views(
                                scene, cameras, tmp_dir, "color"
                            )
                        r[0] = paths
                    finally:
                        pipe._restore_render_settings(scene, snap)
                except Exception as e:
                    r[0] = e

            execute_in_main_thread(_do_mist_render)
            _wait_for(r, "Mist render")
            mist_paths = r[0]

            # ─── Step 2: Assemble collage (main thread) ───
            _update_status(scene, "Building depth collage...")
            c = [None]

            def _do_collage():
                try:
                    # Collage tiles match mist resolution (capped at 1024)
                    mist_tile = min(resolution, 1024)
                    c[0] = pipe.create_collage(mist_paths, mist_tile)
                except Exception as e:
                    c[0] = e

            execute_in_main_thread(_do_collage)
            _wait_for(c, "Collage")
            collage_path = c[0]

            # ─── Step 3: API call (bg thread OK) ───
            _update_status(scene, "Sending depth collage to AI...")

            model_name = MODEL_MAP.get(
                ai_model, 'gemini-3.1-flash-image-preview'
            )
            num = len(cameras)
            names = ", ".join(cam['name'] for cam in cameras)

            import math as _m
            grid_cols = _m.ceil(_m.sqrt(num))
            grid_rows = _m.ceil(num / grid_cols)

            ref_instruction = ""
            if reference_path:
                ref_instruction = (
                    f"6. A STYLE REFERENCE image is attached separately. "
                    f"Use it ONLY as art direction — extract the colour "
                    f"palette, material finish, and artistic feel from it. "
                    f"Do NOT copy any shapes, objects, or content from the "
                    f"reference — it is purely for visual style guidance.\n"
                )

            input_type = "depth map (mist/Z-pass)" if render_mode == 'MIST' else "flat untextured base"
            input_term = "depth map" if render_mode == 'MIST' else "base image"

            # Build a prompt that tells the AI exactly what it's looking at
            full_prompt = (
                f"You are a 3D texture artist. I am giving you a {input_type} "
                f"sprite sheet of a 3D model rendered across {grid_cols} columns "
                f"by {grid_rows} rows.\n\n"
                f"VIEWS (left-to-right, top-to-bottom): {names}.\n"
                f"IMPORTANT: All tiles show the EXACT SAME 3D object "
                f"photographed from different angles. The object does NOT "
                f"move or change between views — only the camera rotates. "
                f"Every surface detail (eyes, buttons, markings, patterns) "
                f"must be consistent across ALL views.\n\n"
                f"YOUR TASK: Paint realistic surface textures onto every "
                f"tile of this sprite sheet, replacing grayscale depth "
                f"with full-colour material based on this description:\n"
                f"\"{prompt}\"\n\n"
                f"CRITICAL RULES — FOLLOW EXACTLY:\n"
                f"1. TRACE THE DEPTH MAP PRECISELY. Every contour, edge, "
                f"and surface detail in the depth map defines the exact "
                f"shape. Paint textures WITHIN these contours. Do NOT "
                f"extend, shrink, shift, or modify any shape.\n"
                f"2. Do NOT reinterpret the 3D form. No turning heads, "
                f"no moving eyes, no repositioning limbs, no adding "
                f"features. The depth map IS the ground truth geometry.\n"
                f"3. Output the EXACT same {grid_cols}×{grid_rows} grid — "
                f"same tile count, same positions, same silhouettes.\n"
                f"4. CROSS-VIEW CONSISTENCY: A marking visible in the "
                f"Front view must appear at the correct position in the "
                f"Right, Back, and Left views. Think in 3D.\n"
                f"5. FLAT UNIFORM LIGHTING: Use perfectly even, ambient "
                f"lighting with NO directional shadows, NO specular "
                f"highlights, NO light variation between views. Every "
                f"view must have identical brightness and lighting.\n"
                f"6. Keep background areas pure black.\n"
                f"7. Output at the same resolution as the input image.\n"
                f"{ref_instruction}"
            )

            req_w, req_h = _get_gemini_dimensions(grid_cols, grid_rows, resolution)

            image_data, gen_id, new_balance = _call_api_depth(
                prompt=full_prompt,
                model_name=model_name,
                depth_image_path=collage_path,
                reference_image_path=reference_path,
                width=req_w,
                height=req_h,
            )

            # Update balance
            if new_balance >= 0:
                def _upd():
                    p = scene.gemini_render
                    p.beta_balance = new_balance
                    p.last_generation_id = gen_id or 0
                    p.last_generation_rated = False
                execute_in_main_thread(_upd)

            # ─── Step 4: Save AI result ───
            result_path = os.path.join(tmp_dir, "ai_result_collage.png")
            with open(result_path, 'wb') as f:
                f.write(image_data)

            # ─── Step 5: Split + project (main thread) ───
            _update_status(scene, "Splitting & projecting textures...")
            p = [None]

            def _do_project():
                try:
                    mist_tile = min(resolution, 1024)
                    tiles = pipe.split_collage(
                        result_path, num, mist_tile
                    )

                    # Split depth collage too and mask textures
                    depth_tiles = pipe.split_collage(
                        collage_path, num, mist_tile
                    )
                    pipe.mask_with_depth(tiles, depth_tiles)

                    obj = bpy.data.objects.get(obj_name)
                    if not obj:
                        raise RuntimeError(f"Object '{obj_name}' gone")

                    cams = _collect_cameras(scene.gemini_render)
                    pipe.project_textures(obj, cams, tiles)

                    scene.gemini_render.tex_has_draft = True
                    scene.gemini_render.tex_is_processing = False
                    scene.gemini_render.tex_status = "Draft applied ✓"
                    p[0] = True
                except Exception as e:
                    p[0] = e
                    scene.gemini_render.tex_is_processing = False
                    scene.gemini_render.tex_status = f"Error: {e}"

            execute_in_main_thread(_do_project)

        except beta_api.BetaAPIError as e:
            _update_status(scene, f"API Error: {e.message}")
            _set_processing(scene, False)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _update_status(scene, f"Error: {str(e)}")
            _set_processing(scene, False)


# ──────────────────────────────────────────────────────────────────
#  Operator: Enhance (per-view with depth)
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_texture_enhance(Operator):
    """Enhance each camera view individually with depth guidance"""
    bl_idname = "banana.texture_enhance"
    bl_label = "Enhance Details"
    bl_description = (
        "Improve each view using colour + depth renders "
        "for consistent high-quality textures"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, 'gemini_render', None)
        if not props:
            return False
        return (props.tex_has_draft
                and not props.tex_is_processing
                and context.active_object is not None
                and context.active_object.type == 'MESH')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        props = context.scene.gemini_render
        n = len(_collect_cameras(props))
        cost = _get_cost(props)
        total = n * cost

        layout.label(text="⚠️ Enhance: multiple API requests", icon='INFO')
        layout.separator()
        layout.label(text=f"Requests: {n}  ×  {cost} credits  =  {total}")

        if props.beta_balance >= 0:
            layout.separator()
            layout.label(text=f"Your balance: {props.beta_balance} credits")
            if props.beta_balance < total:
                row = layout.row()
                row.alert = True
                row.label(text="Not enough credits!", icon='ERROR')

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        props = scene.gemini_render

        n = len(_collect_cameras(props))
        total = _get_cost(props) * n

        if props.beta_balance >= 0 and props.beta_balance < total:
            self.report(
                {'ERROR'},
                f"Need {total} credits, have {props.beta_balance}"
            )
            return {'CANCELLED'}

        props.tex_is_processing = True
        props.tex_status = "Starting enhancement..."

        cameras = _collect_cameras(props)
        if not cameras:
            props.tex_is_processing = False
            self.report({'ERROR'}, "No cameras found")
            return {'CANCELLED'}

        # Save reference image to temp file if provided
        ref_path = None
        if props.tex_reference_image:
            ref_img = props.tex_reference_image
            import tempfile as _tf
            ref_dir = _tf.mkdtemp(prefix=pipe.TEMP_PREFIX)
            ref_path = os.path.join(ref_dir, "style_reference.png")
            orig_fp = ref_img.filepath_raw
            orig_fmt = ref_img.file_format
            try:
                ref_img.filepath_raw = ref_path
                ref_img.file_format = 'PNG'
                ref_img.save()
            finally:
                ref_img.filepath_raw = orig_fp
                ref_img.file_format = orig_fmt

        t = threading.Thread(
            target=self._run_enhance,
            args=(scene, obj.name, cameras, props.tex_prompt,
                  int(props.tex_resolution), props.ai_model,
                  props.tex_depth_start, props.tex_depth_depth,
                  props.mist_falloff, ref_path, props.tex_render_mode),
            daemon=True,
        )
        t.start()
        return {'FINISHED'}

    @staticmethod
    def _run_enhance(scene, obj_name, cameras, prompt, resolution,
                     ai_model, mist_start, mist_depth, mist_falloff,
                     reference_path=None, render_mode='MIST'):
        try:
            tmp_dir = tempfile.mkdtemp(prefix=pipe.TEMP_PREFIX)
            model_name = MODEL_MAP.get(
                ai_model, 'gemini-3.1-flash-image-preview'
            )
            total = len(cameras)

            # ── Step 1: Render all colour + mist views (main thread) ──
            _update_status(scene, "Rendering colour + depth views...")
            r = [None]

            def _do_renders():
                try:
                    snap = pipe._store_render_settings(scene)
                    try:
                        results = {}

                        # Mist renders (viewport approach) - only if MIST mode
                        if render_mode == 'MIST':
                            pipe.setup_mist_render(
                                scene, resolution,
                                mist_start, mist_depth, mist_falloff,
                            )
                            for cam_info in cameras:
                                d_path = os.path.join(
                                    tmp_dir,
                                    f"enh_depth_{cam_info['name']}.png"
                                )
                                pipe.render_single_view_mist(
                                    scene, cam_info['camera'], d_path
                                )
                                results.setdefault(
                                    cam_info['name'], {}
                                )['depth'] = d_path

                        # Colour renders (flat render)
                        pipe.setup_flat_render(scene, resolution)
                        for cam_info in cameras:
                            c_path = os.path.join(
                                tmp_dir,
                                f"enh_color_{cam_info['name']}.png"
                            )
                            pipe.render_single_view(
                                scene, cam_info['camera'], c_path
                            )
                            results.setdefault(cam_info['name'], {})['color'] = c_path

                        r[0] = results
                    finally:
                        pipe._restore_render_settings(scene, snap)
                except Exception as e:
                    r[0] = e

            execute_in_main_thread(_do_renders)
            _wait_for(r, "Renders")
            render_results = r[0]

            # ── Step 2: Parallel API calls ──
            _update_status(scene, f"Enhancing {total} views (parallel)...")

            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _enhance_one(cam_info):
                cam_name = cam_info['name']
                paths = render_results[cam_name]
                color_path = paths['color']

                # Upload base color
                import google.generativeai as genai
                images = []
                current_img = genai.upload_file(color_path)
                images.append(current_img)
                pipe.track_upload(current_img)

                depth_img = None
                if render_mode == 'MIST' and 'depth' in paths:
                    depth_img = genai.upload_file(paths['depth'])
                    images.append(depth_img)
                    pipe.track_upload(depth_img)

                if reference_path and os.path.exists(reference_path):
                    ref_img = genai.upload_file(reference_path)
                    images.append(ref_img)
                    pipe.track_upload(ref_img)

                ref_instruction = ""
                if reference_path:
                    ref_instruction = (
                        f"- A STYLE REFERENCE image is attached. Use it ONLY "
                        f"for colour palette and artistic feel — do NOT copy "
                        f"any shapes or objects from it\n"
                    )

                if render_mode == 'MIST':
                    enh_prompt = (
                        f"You are a 3D texture artist enhancing a "
                        f"{cam_name} orthographic view of a 3D model.\n\n"
                        f"IMAGE 1: Current basic texture (low quality).\n"
                        f"IMAGE 2: Depth map (white = near, black = far).\n\n"
                        f"TASK: Repaint this view with high-quality, detailed "
                        f"surface textures matching this description:\n"
                        f"\"{prompt}\"\n\n"
                        f"STRICT RULES:\n"
                        f"- The depth map is an ABSOLUTE MASK. Your output MUST "
                        f"match the silhouette PIXEL-PERFECTLY. Do NOT move, "
                        f"rotate, or change ANY part of the shape.\n"
                        f"- Do NOT add creative changes — no turning heads, "
                        f"no moving eyes/limbs, no changing the pose. The 3D "
                        f"geometry is FIXED and IMMUTABLE.\n"
                        f"- FLAT UNIFORM LIGHTING: Use perfectly even ambient "
                        f"lighting. NO directional shadows, NO specular "
                        f"highlights. Pure flat albedo texture only.\n"
                        f"- Add realistic material detail: scratches, wear, "
                        f"color variation, surface imperfections.\n"
                        f"- Use the depth map ONLY to understand 3D form — "
                        f"do NOT include depth overlay in your output.\n"
                        f"- Keep background pure black.\n"
                        f"- Output same resolution as input.\n"
                        f"{ref_instruction}"
                    )
                else:
                    enh_prompt = (
                        f"You are a 3D texture artist enhancing a "
                        f"{cam_name} orthographic view of a 3D model.\n\n"
                        f"IMAGE 1: Current texture / base model.\n\n"
                        f"TASK: Repaint this view with high-quality, detailed "
                        f"surface textures matching this description:\n"
                        f"\"{prompt}\"\n\n"
                        f"STRICT RULES:\n"
                        f"- The input image is an ABSOLUTE MASK. Your output MUST "
                        f"match the silhouette PIXEL-PERFECTLY. Do NOT move, "
                        f"rotate, or change ANY part of the shape.\n"
                        f"- Do NOT add creative changes — no turning heads, "
                        f"no moving eyes/limbs, no changing the pose. The 3D "
                        f"geometry is FIXED and IMMUTABLE.\n"
                        f"- FLAT UNIFORM LIGHTING: Use perfectly even ambient "
                        f"lighting. NO directional shadows, NO specular "
                        f"highlights. Pure flat albedo texture only.\n"
                        f"- Add realistic material detail: scratches, wear, "
                        f"color variation, surface imperfections.\n"
                        f"- Keep background pure black.\n"
                        f"- Output same resolution as input.\n"
                        f"{ref_instruction}"
                    )

                image_data, gen_id, new_balance = _call_api_enhance(
                    prompt=enh_prompt,
                    model_name=model_name,
                    color_path=color_path,
                    depth_path=paths.get('depth'),
                    ref_path=reference_path,
                    width=resolution,
                    height=resolution,
                )

                enh_path = os.path.join(
                    tmp_dir, f"enhanced_{cam_name}.png"
                )
                with open(enh_path, 'wb') as f:
                    f.write(image_data)

                return cam_name, enh_path, gen_id, new_balance

            enhanced_paths = []
            cam_order = [c['name'] for c in cameras]

            with ThreadPoolExecutor(max_workers=min(total, 4)) as pool:
                futures = {
                    pool.submit(_enhance_one, cam): cam
                    for cam in cameras
                }
                name_to_path = {}
                for future in as_completed(futures):
                    cam_name, enh_path, gen_id, new_balance = future.result()
                    name_to_path[cam_name] = enh_path
                    _update_status(
                        scene,
                        f"Enhanced {len(name_to_path)}/{total}: {cam_name}"
                    )
                    if new_balance >= 0:
                        def _upd(_b=new_balance, _g=gen_id):
                            p = scene.gemini_render
                            p.beta_balance = _b
                            p.last_generation_id = _g or 0
                        execute_in_main_thread(_upd)

            # Keep camera order
            enhanced_paths = [name_to_path[n] for n in cam_order]

            # ── Step 3: Re-project + bake (main thread) ──
            _update_status(scene, "Projecting enhanced textures & baking...")

            def _do_final():
                try:
                    obj = bpy.data.objects.get(obj_name)
                    if not obj:
                        raise RuntimeError(f"Object '{obj_name}' gone")

                    cams = _collect_cameras(scene.gemini_render)

                    # Mask enhanced textures with depth maps
                    depth_order = [
                        render_results[n]['depth'] for n in cam_order
                    ]
                    pipe.mask_with_depth(enhanced_paths, depth_order)

                    pipe.project_textures(obj, cams, enhanced_paths)

                    bake_res = int(scene.gemini_render.tex_resolution)
                    pipe.bake_final(obj, bake_res)

                    scene.gemini_render.tex_is_processing = False
                    scene.gemini_render.tex_status = "Enhancement complete ✓"
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    scene.gemini_render.tex_is_processing = False
                    scene.gemini_render.tex_status = f"Error: {e}"

            execute_in_main_thread(_do_final)

        except beta_api.BetaAPIError as e:
            _update_status(scene, f"API Error: {e.message}")
            _set_processing(scene, False)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _update_status(scene, f"Error: {str(e)}")
            _set_processing(scene, False)


# ──────────────────────────────────────────────────────────────────
#  Operator: Cleanup
# ──────────────────────────────────────────────────────────────────

class BANANA_OT_cleanup_tex(Operator):
    """Remove all temporary texturing data"""
    bl_idname = "banana.cleanup_tex"
    bl_label = "Cleanup Texturing"
    bl_description = "Remove all temporary cameras, images and materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        pipe.cleanup_temp_data()

        props = context.scene.gemini_render
        props.tex_has_draft = False
        props.tex_is_processing = False
        props.tex_camera_count = 0
        props.tex_status = "Cleaned up"

        self.report({'INFO'}, "Texturing data cleaned up")
        return {'FINISHED'}


class BANANA_OT_clear_tex_reference(Operator):
    """Clear the selected style reference image"""
    bl_idname = "banana.clear_tex_reference"
    bl_label = "Clear Reference"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.gemini_render.tex_reference_image = None
        return {'FINISHED'}


class BANANA_OT_load_tex_reference(Operator):
    """Load a style reference image from disk"""
    bl_idname = "banana.load_tex_reference"
    bl_label = "Load Style Reference"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif;*.webp",
        options={'HIDDEN'},
    )

    def execute(self, context):
        if not self.filepath:
            return {'CANCELLED'}
        img = bpy.data.images.load(self.filepath, check_existing=True)
        context.scene.gemini_render.tex_reference_image = img
        self.report({'INFO'}, f"Loaded reference: {img.name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# ── Registration list ──
texture_operator_classes = (
    BANANA_OT_init_tex_cameras,
    BANANA_OT_update_tex_cameras,
    BANANA_OT_preview_tex_camera,
    BANANA_OT_texture_draft,
    BANANA_OT_texture_enhance,
    BANANA_OT_cleanup_tex,
    BANANA_OT_clear_tex_reference,
    BANANA_OT_load_tex_reference,
)
