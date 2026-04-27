"""
Custom Render Engine for Nano Banana
Registers 'Nano Banana' in Blender's Render Engine dropdown.

Architecture:
  F12 → BananaOTRender (pre-captures viewport via opengl) →
  stores path → triggers bpy.ops.render.render →
  NanoBananaRenderEngine.render() picks up stored capture →
  calls Gemini API → loads result

This avoids the render-lock issue where opengl() fails during F12.
"""

import bpy
import threading
import os
import time


# Model name mapping
MODEL_MAP = {
    'NANO_BANANA_2': 'gemini-3.1-flash-image-preview',
    'NANO_BANANA_PRO': 'gemini-3-pro-image-preview',
    'NANO_BANANA': 'gemini-2.5-flash-image',
}

# Module-level storage for pre-captured viewport image
_pre_capture = {
    'path': None,
    'ready': False,
}


class BananaOTRender(bpy.types.Operator):
    """Pre-capture viewport, then trigger F12 render engine"""
    bl_idname = "banana.ai_render"
    bl_label = "AI Render"
    bl_description = "Render using Nano Banana AI"

    def execute(self, context):
        scene = context.scene

        # If not Nano Banana engine, fall through to standard render
        if scene.render.engine != 'NANO_BANANA':
            bpy.ops.render.render('INVOKE_DEFAULT')
            return {'FINISHED'}

        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None
        if not props:
            self.report({'ERROR'}, "Nano Banana properties not found")
            return {'CANCELLED'}

        # Validate beta token
        prefs = context.preferences.addons.get("nano_banana_render")
        has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
        if not has_token:
            self.report({'ERROR'}, "No beta token. Go to Edit → Preferences → Add-ons → Nano Banana")
            return {'CANCELLED'}

        if not scene.camera:
            self.report({'ERROR'}, "No active camera in scene")
            return {'CANCELLED'}

        if not props.prompt.strip() or len(props.prompt.strip()) < 10:
            self.report({'ERROR'}, "Prompt too short (minimum 10 characters)")
            return {'CANCELLED'}

        # --- Step 1: Pre-capture viewport (NO render lock here!) ---
        from . import depth_utils
        depth_renderer = depth_utils.DepthRenderer()

        _pre_capture['ready'] = False
        _pre_capture['path'] = None

        try:
            if props.render_mode == 'DEPTH':
                print("[NANO BANANA] Pre-capturing depth map...")
                path = depth_renderer.render_depth_map_mist(
                    scene, props.mist_start, props.mist_depth, props.mist_falloff
                )
            else:
                print("[NANO BANANA] Pre-capturing EEVEE viewport...")
                path = depth_renderer.render_regular_eevee(scene)

            _pre_capture['path'] = path
            _pre_capture['ready'] = True
            print(f"[NANO BANANA] Pre-capture done: {path}")

        except Exception as e:
            self.report({'ERROR'}, f"Viewport capture failed: {e}")
            try:
                depth_renderer.cleanup_temp_files()
            except Exception:
                pass
            return {'CANCELLED'}

        # --- Step 2: Trigger F12 render (engine picks up stored capture) ---
        bpy.ops.render.render('INVOKE_DEFAULT')

        return {'FINISHED'}


class NanoBananaRenderEngine(bpy.types.RenderEngine):
    """Custom render engine — uses pre-captured viewport data from BananaOTRender"""
    bl_idname = 'NANO_BANANA'
    bl_label = 'Nano Banana'
    bl_use_preview = False
    bl_use_shading_nodes_custom = False
    bl_use_eevee_viewport = True
    bl_use_gpu_context = False

    def render(self, depsgraph):
        """
        Called by Blender after BananaOTRender pre-captured the viewport.
        Reads the stored capture, calls Gemini API, writes result into F12 viewer.
        """
        render_start = time.time()
        scene = depsgraph.scene
        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None

        if self.is_preview:
            return  # Nano Banana does not support rendering material preview spheres

        if not props:
            self.report({'ERROR'}, "Nano Banana properties not found")
            return

        # Check for pre-captured viewport data
        if not _pre_capture.get('ready') or not _pre_capture.get('path'):
            # Called from menu (Render → Render Image) without pre-capture.
            # Return empty result, then schedule our operator to do it properly.
            render_w = int(scene.render.resolution_x * scene.render.resolution_percentage / 100)
            render_h = int(scene.render.resolution_y * scene.render.resolution_percentage / 100)
            result = self.begin_result(0, 0, render_w, render_h)
            self.end_result(result)

            def _trigger_proper_render():
                try:
                    bpy.ops.banana.ai_render()
                except Exception as e:
                    print(f"[NANO BANANA] Auto-trigger failed: {e}")
                return None  # Don't repeat

            bpy.app.timers.register(_trigger_proper_render, first_interval=0.5)
            return

        depth_path = _pre_capture['path']
        _pre_capture['ready'] = False  # Consume

        # Validate beta token
        from . import beta_api

        from . import threading_utils

        render_mode = props.render_mode
        model_name = MODEL_MAP.get(props.ai_model, 'gemini-3.1-flash-image-preview')

        # --- Call via Beta Server ---
        gen_type = 'render_eevee' if render_mode == 'EEVEE' else 'render_depth'
        if render_mode == 'DEPTH':
            self.update_stats("", f"Sending depth map to {model_name}...")
        else:
            self.update_stats("", f"Sending image to {model_name}...")

        reference_path = threading_utils.save_reference_image_temp(scene)

        # Determine dimensions from scene render settings and addon UI property
        render = scene.render
        base_res = int(props.resolution) if hasattr(props, 'resolution') else 1024
        scene_aspect = render.resolution_x / render.resolution_y if render.resolution_y > 0 else 1.0
        
        if scene_aspect >= 1:
            width = base_res
            height = int(base_res / scene_aspect)
        else:
            width = int(base_res * scene_aspect)
            height = base_res

        # Determine token for direct vs server API
        token = ""
        prefs = bpy.context.preferences.addons.get("nano_banana_render")
        if prefs and hasattr(prefs.preferences, "beta_token"):
            token = prefs.preferences.beta_token.strip()

        try:
            if token.startswith("AIza"):
                # ─── Direct Google API Mode ───
                from .gemini_api import GeminiAPI, GeminiAPIError
                
                # Turn off beta UI elements for API key users
                def _update_direct_ui():
                    if hasattr(scene, 'gemini_render'):
                        scene.gemini_render.beta_balance = -1  # Hide balance
                        scene.gemini_render.last_generation_id = 0
                        scene.gemini_render.last_generation_rated = False
                threading_utils.execute_in_main_thread(_update_direct_ui)
                
                self.update_stats("", "Connecting directly to Google API...")
                gemini = GeminiAPI(api_key=token, model=model_name)
                is_color = (render_mode == 'EEVEE')
                image_data, _ = gemini.generate_image(
                    depth_image_path=depth_path,
                    user_prompt=props.prompt,
                    reference_image_path=reference_path,
                    is_color_render=is_color,
                    width=width,
                    height=height
                )
                
            else:
                # ─── Server Mode (Nanode API) ───
                # Build prompt client-side (same logic as direct mode)
                from .gemini_api import GeminiAPI
                is_color = (render_mode == 'EEVEE')
                prompt_builder = GeminiAPI.__new__(GeminiAPI)
                full_prompt = prompt_builder._build_prompt(
                    props.prompt,
                    has_reference=bool(reference_path),
                    is_color_render=is_color
                )
                
                image_data, generation_id, new_balance = beta_api.generate(
                    prompt=full_prompt,
                    model=model_name,
                    input_image_path=depth_path,
                    reference_image_path=reference_path,
                    gen_type=gen_type,
                    width=width,
                    height=height,
                    user_prompt=props.prompt,
                )
    
                # Update balance and generation tracking for rating UI
                def _update_beta_ui():
                    if hasattr(scene, 'gemini_render'):
                        scene.gemini_render.beta_balance = new_balance
                        scene.gemini_render.last_generation_id = int(generation_id) if generation_id else 0
                        scene.gemini_render.last_generation_rated = False
                threading_utils.execute_in_main_thread(_update_beta_ui)

        except beta_api.BetaAPIError as e:
            if e.status_code == 402:
                # Not enough credits — show popup
                try:
                    import json
                    detail = json.loads(e.message) if isinstance(e.message, str) and e.message.startswith('{') else {}
                    credits_needed = detail.get('credits_needed', 0)
                    credits_available = detail.get('credits_available', 0)
                except (ValueError, KeyError):
                    credits_needed = 0
                    credits_available = 0
                
                def _show_popup():
                    try:
                        bpy.ops.banana.show_no_credits_popup(
                            'INVOKE_DEFAULT',
                            credits_needed=credits_needed,
                            credits_available=credits_available
                        )
                    except Exception as ex:
                        print(f"[NANO BANANA] Popup error: {ex}")
                
                threading_utils.execute_in_main_thread(_show_popup)
                self.report({'ERROR'}, f"Not enough credits: need {credits_needed}, have {credits_available}")
            else:
                self.report({'ERROR'}, f"Beta server: {e.message}")
            return
            
        except Exception as e:
            if type(e).__name__ == "GeminiAPIError":
                self.report({'ERROR'}, f"Google API Error: {str(e)}")
            else:
                self.report({'ERROR'}, f"AI generation failed: {str(e)}")
            return
        finally:
            if reference_path:
                try:
                    os.unlink(reference_path)
                except OSError:
                    pass
            from . import depth_utils
            try:
                depth_utils.DepthRenderer().cleanup_temp_files()
            except Exception:
                pass

        if self.test_break():
            return

        # --- Validate image data ---
        if not image_data or len(image_data) < 100:
            self.report({'ERROR'}, f"AI returned empty or invalid image ({len(image_data) if image_data else 0} bytes)")
            return

        # --- Display AI result directly in F12 render buffer ---
        self.update_stats("", "Loading AI result...")

        render_w = int(scene.render.resolution_x * scene.render.resolution_percentage / 100)
        render_h = int(scene.render.resolution_y * scene.render.resolution_percentage / 100)

        self._write_image_to_render_buffer(image_data, render_w, render_h)

        elapsed = time.time() - render_start
        
        def _process_result_main_thread():
            _finalize_render_in_main_thread(image_data, props.prompt, scene, elapsed)

        threading_utils.execute_in_main_thread(_process_result_main_thread)

        self.update_stats("", f"AI render completed in {elapsed:.1f}s")


    def _write_image_to_render_buffer(self, image_data: bytes, render_w: int, render_h: int):
        """Helper to write image directly to Blender F12 buffer."""
        buffer_written = False
        try:
            import io
            try:
                from PIL import Image as PILImage
                pil_img = PILImage.open(io.BytesIO(image_data)).convert('RGBA')
                pil_img = pil_img.resize((render_w, render_h), PILImage.LANCZOS)
                
                raw = pil_img.tobytes()
                pixel_count = render_w * render_h
                pixels = []
                for i in range(pixel_count):
                    offset = i * 4
                    pixels.extend([raw[offset]/255.0, raw[offset+1]/255.0, raw[offset+2]/255.0, raw[offset+3]/255.0])
                
                flipped_pixels = []
                for row in range(render_h - 1, -1, -1):
                    row_start = row * render_w * 4
                    flipped_pixels.extend(pixels[row_start:row_start + render_w * 4])
                
                result = self.begin_result(0, 0, render_w, render_h)
                layer = result.layers[0]
                try:
                    layer.passes["Combined"].rect = [flipped_pixels[i:i+4] for i in range(0, len(flipped_pixels), 4)]
                except Exception:
                    layer.passes["Combined"].rect.foreach_set(flipped_pixels)
                self.end_result(result)
                buffer_written = True
            except ImportError:
                print("[NANO BANANA] PIL not available, using bpy.data.images fallback")
        except Exception as e:
            print(f"[NANO BANANA] Direct buffer write failed: {e}")

        if not buffer_written:
            try:
                result = self.begin_result(0, 0, render_w, render_h)
                self.end_result(result)
            except Exception as e:
                print(f"[NANO BANANA] Error writing fallback to render buffer: {e}")


def _finalize_render_in_main_thread(image_data: bytes, prompt: str, scene, elapsed: float):
    """Helper executed in main thread to load image datablock and swap viewer."""
    import tempfile
    import os
    temp_path = None
    
    try:
        _save_render_to_history(image_data, prompt, scene)
    except Exception as e:
        print(f"[NANO BANANA] History save error: {e}")
        
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(image_data)
            temp_path = f.name

        result_img_name = "Nano Banana Render"
        if result_img_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[result_img_name])

        result_img = bpy.data.images.load(temp_path)
        result_img.name = result_img_name
        result_img.colorspace_settings.name = 'sRGB'
        result_img.pack()

        _pre_capture['result_image'] = result_img_name
    except Exception as e:
        print(f"[NANO BANANA] Error loading AI result into Blender: {e}")
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    if hasattr(scene, 'gemini_render'):
        scene.gemini_render.status_text = f"Done in {elapsed:.1f}s"
        scene.gemini_render.is_rendering = False

    result_img_name = _pre_capture.get('result_image')
    if result_img_name and result_img_name in bpy.data.images:
        ai_img = bpy.data.images[result_img_name]
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    for space in area.spaces:
                        if space.type == 'IMAGE_EDITOR' and getattr(space.image, 'name', '') == 'Render Result':
                            space.image = ai_img
                area.tag_redraw()


def _save_render_to_history(image_data: bytes, user_prompt: str, scene):
    """Save render result to history with packed image data."""
    import tempfile
    import datetime
    import shutil

    if not user_prompt:
        return

    timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    permanent_name = f"AI_Result_{timestamp_str}"

    # Save to permanent location
    permanent_dir = os.path.join(tempfile.gettempdir(), "nano_banana_history")
    os.makedirs(permanent_dir, exist_ok=True)
    permanent_path = os.path.join(permanent_dir, f"{permanent_name}.png")

    with open(permanent_path, 'wb') as f:
        f.write(image_data)

    # Load and pack
    if permanent_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[permanent_name])

    img = bpy.data.images.load(permanent_path)
    img.name = permanent_name
    img.pack()
    img.use_fake_user = True
    print(f"[NANO BANANA] History image packed: {permanent_name}")

    # Add to history
    if hasattr(scene, 'gemini_render'):
        props = scene.gemini_render
        history_item = props.render_history.add()
        history_item.prompt = user_prompt
        history_item.image_name = permanent_name

        if props.use_style_reference and props.style_reference_image:
            history_item.style_reference_used = True
            history_item.style_reference_name = props.style_reference_image.name
        else:
            history_item.style_reference_used = False

        history_item.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_item.thumbnail_name = ""

        while len(props.render_history) > 10:
            oldest = props.render_history[0]
            if oldest.image_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[oldest.image_name])
            props.render_history.remove(0)

        print(f"[NANO BANANA] History saved: {permanent_name}, total: {len(props.render_history)}")


# --- Standard Blender Panels ---
# These are standard panels (Output, Scene, View Layer, etc.) that need
# our engine added to their COMPAT_ENGINES to appear when Nano Banana is selected.

def get_standard_panels():
    """Find standard Blender panels that should be visible with our engine."""
    exclude_panels = {
        # Exclude render-specific panels we don't need (these clutter the UI)
        'RENDER_PT_simplify',
        'RENDER_PT_freestyle',
        'RENDER_PT_color_management_display_settings',
    }

    panels = []
    for attr_name in dir(bpy.types):
        panel = getattr(bpy.types, attr_name, None)
        if panel is None:
            continue
        if not hasattr(panel, 'COMPAT_ENGINES'):
            continue
        if not hasattr(panel, 'bl_context'):
            continue

        # Include panels from all standard Blender tabs EXCEPT the Render tab
        # (Nano Banana provides its own UI for the Render tab)
        bl_context = getattr(panel, 'bl_context', '')
        if bl_context != 'render':
            if hasattr(panel, 'bl_idname') and panel.bl_idname in exclude_panels:
                continue
            # Only include panels that already work with EEVEE
            if 'BLENDER_EEVEE' in panel.COMPAT_ENGINES or 'BLENDER_EEVEE_NEXT' in panel.COMPAT_ENGINES:
                panels.append(panel)

    return panels


# --- Keymap ---
addon_keymaps = []
_registered_panels = []

# Track previous engine to detect switch
_last_engine = [None]


def _on_engine_switch(scene):
    """Initialize viewport when user first switches to Nano Banana engine.
    Sets the viewport shading to match the current render_mode so the
    viewport is never blank on first selection."""
    try:
        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None
        if not props:
            return

        if props.render_mode == 'EEVEE':
            # Regular Render — show Material Preview with Combined pass
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                space.shading.type = 'MATERIAL'
                                if hasattr(space.shading, 'render_pass'):
                                    space.shading.render_pass = 'COMBINED'
                                if hasattr(space.shading, 'use_scene_lights'):
                                    space.shading.use_scene_lights = True
                        area.tag_redraw()
                        return
        else:
            # Depth Map — show Material Preview with Mist pass
            from . import ui_panel
            ui_panel.on_render_mode_change(props, bpy.context)
    except Exception as e:
        print(f"[NANO BANANA] Engine switch viewport init error: {e}")


@bpy.app.handlers.persistent
def _depsgraph_update_handler(scene, depsgraph=None):
    """Detect when render engine changes to NANO_BANANA and initialise viewport."""
    try:
        current = scene.render.engine
        if current != _last_engine[0]:
            prev = _last_engine[0]
            _last_engine[0] = current
            if current == 'NANO_BANANA' and prev is not None:
                # User just switched to our engine — set up viewport
                _on_engine_switch(scene)
    except Exception:
        pass


def register():
    bpy.utils.register_class(NanoBananaRenderEngine)
    bpy.utils.register_class(BananaOTRender)

    # Add our engine to standard Blender panels
    for panel in get_standard_panels():
        if hasattr(panel, 'COMPAT_ENGINES'):
            panel.COMPAT_ENGINES.add('NANO_BANANA')
            _registered_panels.append(panel)

    # Register F12 keymap override
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Screen', space_type='EMPTY')
        kmi = km.keymap_items.new("banana.ai_render", 'F12', 'PRESS')
        addon_keymaps.append((km, kmi))

    # Register engine-switch handler
    if _depsgraph_update_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_update_handler)
    # Seed current engine so we don't trigger on addon load
    try:
        _last_engine[0] = bpy.context.scene.render.engine
    except Exception:
        _last_engine[0] = None


def unregister():
    # Remove engine-switch handler
    if _depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_update_handler)

    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    # Remove our engine from standard panels
    for panel in _registered_panels:
        if hasattr(panel, 'COMPAT_ENGINES'):
            panel.COMPAT_ENGINES.discard('NANO_BANANA')
    _registered_panels.clear()

    bpy.utils.unregister_class(BananaOTRender)
    bpy.utils.unregister_class(NanoBananaRenderEngine)
