"""
Image Editor panel for post-render editing with AI
Supports mask-based inpainting, style changes, and iterative refinement
"""

import bpy
import os
import time
from typing import Optional
from bpy.types import Panel, PropertyGroup, Operator
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty, PointerProperty, EnumProperty

class EditHistoryItem(PropertyGroup):
    """Single edit in the session history"""
    
    prompt: StringProperty(
        name="Edit Prompt",
        description="Prompt used for this edit",
        default=""
    )
    
    image_name: StringProperty(
        name="Image Name",
        description="Name of image in bpy.data.images",
        default=""
    )
    
    timestamp: StringProperty(
        name="Timestamp",
        description="When this edit was made",
        default=""
    )
    
    has_mask: BoolProperty(
        name="Has Mask",
        description="Whether this edit used a mask",
        default=False
    )

class ImageEditorProperties(PropertyGroup):
    """Properties for Image Editor panel - stored in WindowManager for session persistence"""
    
    # Current edit prompt
    edit_prompt: StringProperty(
        name="Edit Prompt",
        description="Describe what you want to change in the image",
        default="",
        maxlen=500
    )
    
    # AI Model selection
    ai_model: EnumProperty(
        name="Model",
        description="Select which AI model to use for editing",
        items=[
            ('NANO_BANANA_2', "Nano Banana 2", "gemini-3.1-flash-image-preview — Fast, balanced quality"),
            ('NANO_BANANA_PRO', "Nano Banana Pro", "gemini-3-pro-image-preview — Highest quality, slower"),
            ('NANO_BANANA', "Nano Banana", "gemini-2.5-flash-image — Basic, fastest (1K only)"),
        ],
        default='NANO_BANANA_PRO',
    )
    
    # Session history (kept in memory only - not saved in blend file)
    edit_history: CollectionProperty(
        type=EditHistoryItem,
        name="Edit History"
    )
    
    history_index: IntProperty(
        name="History Index",
        default=-1
    )
    
    # Current image being edited
    active_image: StringProperty(
        name="Active Image",
        description="Name of image currently being edited",
        default=""
    )
    
    # Original render context (to preserve settings)
    original_prompt: StringProperty(
        name="Original Prompt",
        description="Original prompt from initial render",
        default=""
    )
    
    # Style reference for editing
    use_reference_image: BoolProperty(
        name="Use Reference Image",
        description="Add objects or people from reference image to your scene",
        default=False
    )
    
    reference_image: PointerProperty(
        type=bpy.types.Image,
        name="Reference Image",
        description="Image containing object/person to add (works with inpainting to place at specific location)"
    )
    
    # Inpainting mode
    use_inpainting: BoolProperty(
        name="Use Inpainting",
        description="Draw what you want AI to create (inpainting)",
        default=False
    )
    
    # Paint brush settings
    brush_size: bpy.props.IntProperty(
        name="Brush Size",
        description="Size of paint brush for masking",
        default=50,
        min=1,
        max=500,
        update=lambda self, context: update_brush_settings(self, context)
    )
    
    brush_color: bpy.props.FloatVectorProperty(
        name="Brush Color",
        description="Color for painting mask (white = edit area)",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=lambda self, context: update_brush_settings(self, context)
    )
    
    # UI state
    show_history: BoolProperty(
        name="Show History",
        description="Show edit history",
        default=False
    )
    
    # Status
    is_editing: BoolProperty(
        name="Is Editing",
        description="Whether AI edit is in progress",
        default=False
    )
    
    # Resolution selection for editing (aspect ratio preserved from input)
    resolution: bpy.props.EnumProperty(
        name="Resolution",
        description="Choose output resolution (aspect ratio preserved from input)",
        items=[
            ('AUTO', "Auto (Match Input)", "Keep original resolution and aspect ratio"),
            ('1024', "1K Base", "Scale to 1K base (preserves aspect ratio)"),
            ('2048', "2K Base", "Scale to 2K base (preserves aspect ratio)"),
            ('4096', "4K Base", "Scale to 4K base (preserves aspect ratio)"),
        ],
        default='AUTO',
    )
    
    # Status
    status_text: StringProperty(
        name="Status",
        description="Current operation status",
        default="Ready to edit"
    )


class BANANA_PT_image_editor_panel(Panel):
    """Main Image Editor panel for AI post-processing"""
    bl_label = "Nanode AI Editor"
    bl_idname = "BANANA_PT_image_editor_panel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Nanode AI Editor"
    
    @classmethod
    def poll(cls, context):
        """Only show if there's an image in the editor"""
        sima = context.space_data
        return sima and sima.image is not None
    
    def draw(self, context):
        layout = self.layout
        sima = context.space_data
        image = sima.image
        props = context.window_manager.nano_banana_editor
        
        # Image info
        box = layout.box()
        box.label(text=f"🖼️ {image.name}", icon='IMAGE_DATA')
        box.label(text=f"📏 {image.size[0]}x{image.size[1]}", icon='EMPTY_DATA')
        
        # Model selection
        box.prop(props, "ai_model", text="Model")
        
        # ─── Beta Token Status (Shared with 3D Viewport) ───
        scene_props = context.scene.gemini_render
        prefs = context.preferences.addons.get("nano_banana_render")
        has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
        
        if not has_token:
            row = layout.row()
            row.alert = True
            row.operator("banana.google_login", text="Login with Google", icon='URL')
        else:
            # ─── Cost per render ───
            model_tier = 'pro' if props.ai_model == 'NANO_BANANA_PRO' else 'flash'
            cost_grid = {
                'flash': {'1024': 10, '2048': 15, '4096': 60, 'AUTO': 10},
                'pro':   {'1024': 30, '2048': 45, '4096': 60, 'AUTO': 30},
            }
            res = getattr(props, 'resolution', '1024')
            cost = cost_grid.get(model_tier, cost_grid['pro']).get(res, 30)
            row = box.row()
            row.scale_y = 0.8
            row.label(text=f"Cost: {cost} credits per render")
            
            row = box.row(align=True)
            if scene_props.beta_balance >= 0:
                row.label(text=f"Credits: {scene_props.beta_balance}")
            else:
                row.label(text="Credits: ...")
            row.operator("banana.refresh_balance", text="", icon='FILE_REFRESH')
            op = row.operator("wm.url_open", text="Buy Credits", icon='PLUS')
            op.url = "https://nanode.tech/pricing/"
            
            # ─── Rating buttons (after render) ────────────────
            if scene_props.last_generation_id > 0 and not scene_props.last_generation_rated:
                rate_box = box.box()
                rate_box.label(text="Rate this result:", icon='QUESTION')
                row = rate_box.row(align=True)
                op_like = row.operator("banana.rate_generation", text="👍 Good")
                op_like.rating = "like"
                op_dislike = row.operator("banana.rate_generation", text="👎 Bad")
                op_dislike.rating = "dislike"
            
            # ─── Feedback section ─────────────────────────────
            if scene_props.show_feedback:
                fb_box = box.box()
                if scene_props.has_submitted_feedback:
                    fb_box.label(text="Leave additional feedback (no bonus):", icon='INFO')
                else:
                    fb_box.label(text="Leave feedback (min. 50 chars) for +50 generations!", icon='INFO')
                fb_box.prop(scene_props, "feedback_text", text="")
                row = fb_box.row()
                row.enabled = len(scene_props.feedback_text.strip()) >= 50
                row.operator("banana.send_feedback", text="Submit Feedback", icon='CHECKMARK')
            else:
                row = box.row()
                if scene_props.has_submitted_feedback:
                    row.operator("banana.toggle_feedback", text="Thanks for your Feedback!", icon='CHECKMARK')
                else:
                    row.operator("banana.toggle_feedback", text="Leave Feedback (+50 Credits)", icon='OUTLINER_OB_LIGHT')
        
        # Convert Render Result button
        if image.type == 'RENDER_RESULT':
            box.separator()
            box.label(text="⚠️ Render Result is read-only", icon='INFO')
            row = box.row()
            row.scale_y = 1.2
            row.operator("nano_banana.convert_render_result", text="Convert to Editable", icon='IMAGE_RGB')
        
        # Resolution selection
        box.label(text="Output Resolution:", icon='FULLSCREEN_ENTER')
        box.prop(props, "resolution", text="")
        
        # Warn if 2K/4K selected with Nano Banana
        if props.ai_model == 'NANO_BANANA' and props.resolution in ('2048', '4096'):
            row = box.row()
            row.alert = True
            row.label(text="Nano Banana supports 1K only", icon='ERROR')
        
        # Edit prompt
        layout.separator()
        box = layout.box()
        box.label(text="Edit Instructions:", icon='TEXT')
        box.prop(props, "edit_prompt", text="")
        
        # Inpainting mode
        layout.separator()
        box = layout.box()
        row = box.row()
        row.prop(props, "use_inpainting", text="✏️ Inpainting", toggle=True)
        
        if props.use_inpainting:
            sima = context.space_data
            is_paint_mode = sima and sima.mode == 'PAINT'
            
            # Draw button
            row = box.row()
            row.scale_y = 1.5
            
            if is_paint_mode:
                row.operator("nano_banana.apply_inpaint", text="Apply Drawing", icon='NONE')
            else:
                row.operator("nano_banana.switch_to_paint", text="Draw", icon='NONE')
            
            # Brush settings (only active when in paint mode)
            settings_box = box.box()
            settings_box.label(text="Brush Settings:")
            settings_box.enabled = is_paint_mode
            col = settings_box.column(align=True)
            col.prop(props, "brush_size")
            col.prop(props, "brush_color", text="Color")
        
        # Reference Image section (add objects/people)
        layout.separator()
        box = layout.box()
        row = box.row()
        row.prop(props, "use_reference_image", text="📷 Reference Image", toggle=True)
        
        if props.use_reference_image:
            # Use prop_search to select from existing images without switching
            row = box.row(align=True)
            row.prop_search(props, "reference_image", bpy.data, "images", text="", icon='IMAGE_DATA')
            
            # Custom load button that doesn't switch Image Editor
            load_op = row.operator("nano_banana.load_reference_image", text="", icon='FILEBROWSER')
            
            # Unlink button
            if props.reference_image:
                unlink_op = row.operator("nano_banana.unlink_reference_image", text="", icon='X')
            
            if props.reference_image:
                box.label(text=f"✓ {props.reference_image.name}", icon='CHECKMARK')
                
                # Show hint - inpainting is optional
                if props.use_inpainting:
                    box.label(text="Draw WHERE (optional)", icon='INFO')
                else:
                    box.label(text="Describe what/where to add", icon='INFO')
            else:
                box.label(text="Click 📂 to load", icon='INFO')
        
        # Main action buttons (skip if inpainting - has own button)
        if not props.use_inpainting:
            layout.separator()
            col = layout.column(align=True)
            col.scale_y = 1.8
            
            if props.is_editing:
                col.enabled = False
                col.operator("nano_banana.apply_edit", text="🔄 Processing...", icon='TIME')
            else:
                if props.edit_prompt.strip() or props.use_reference_image:
                    col.operator("nano_banana.apply_edit", text="✨ Apply AI Edit", icon='BRUSH_DATA')
                else:
                    col.enabled = False
                    col.operator("nano_banana.apply_edit", text="Enter prompt", icon='INFO')
        
        # Render button for inpainting
        if props.use_inpainting:
            layout.separator()
            col = layout.column(align=True)
            col.scale_y = 1.8
            
            if props.is_editing:
                col.enabled = False
                col.operator("nano_banana.apply_edit", text="🔄 Processing...", icon='TIME')
            else:
                if props.edit_prompt.strip():
                    col.operator("nano_banana.apply_edit", text="Render", icon='NONE')
                else:
                    col.enabled = False
                    col.operator("nano_banana.apply_edit", text="Enter prompt first", icon='INFO')
        
        # Quick actions
        layout.separator()
        box = layout.box()
        box.label(text="Finalize & Adjust:", icon='IMAGE_RGB')
        col = box.column(align=True)
        col.scale_y = 1.3
        col.operator("nano_banana.finalize_composite", text="Finalize Composite")
        
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("nano_banana.rerender_image", text="Re-render", icon='FILE_REFRESH')
        
        # Status
        layout.separator()
        box = layout.box()
        box.label(text=props.status_text, icon='INFO')
        
        # History
        if len(props.edit_history) > 0:
            layout.separator()
            row = layout.row()
            row.prop(props, "show_history", 
                    text=f"History ({len(props.edit_history)} edits)" if not props.show_history else "Hide History",
                    toggle=True, icon='TIME')
            
            if props.show_history:
                box = layout.box()
                for i, item in enumerate(reversed(props.edit_history)):
                    actual_index = len(props.edit_history) - 1 - i
                    
                    row = box.row(align=True)
                    row.scale_y = 0.8
                    
                    # Timestamp and prompt preview
                    col = row.column()
                    col.label(text=f"#{len(props.edit_history) - i} • {item.timestamp}")
                    prompt_prev = item.prompt[:40] + "..." if len(item.prompt) > 40 else item.prompt
                    col.label(text=prompt_prev, icon='TEXT')
                    
                    # Load button
                    load_btn = row.operator("nano_banana.load_history_edit", text="", icon='LOOP_BACK')
                    load_btn.history_index = actual_index
                    
                    if i < len(props.edit_history) - 1:
                        box.separator()




class NANO_BANANA_OT_apply_edit(Operator):
    """Apply AI edit to the current image"""
    bl_idname = "nano_banana.apply_edit"
    bl_label = "Apply AI Edit"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        sima = context.space_data
        image = sima.image
        
        if not image:
            self.report({'ERROR'}, "No image in editor")
            return {'CANCELLED'}
        
        # Validate prompt
        if not props.edit_prompt.strip() and not props.use_reference_image:
            self.report({'ERROR'}, "Enter edit instructions or select reference image")
            return {'CANCELLED'}
        
        # Validate beta token
        prefs = context.preferences.addons.get("nano_banana_render")
        has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
        if not has_token:
            self.report({'ERROR'}, "Beta token not set. Enter it in addon preferences.")
            return {'CANCELLED'}
        
        # Start edit in background thread
        props.is_editing = True
        props.status_text = "Starting AI edit..."
        
        try:
            from . import image_edit_thread
            
            # Save current image to temp file
            import tempfile
            import os
            
            temp_dir = tempfile.mkdtemp(prefix="nano_banana_edit_")
            image_path = os.path.join(temp_dir, "original.png")
            
            # ─── CRITICAL: Export image with correct sRGB color ───
            # Blender stores pixel data internally as SCENE-LINEAR floats.
            # image.save() writes them with the image's colorspace inverse transform,
            # but this can fail or produce incorrect results for packed/AI-generated images.
            # save_render() applies the View Transform (Filmic/AgX) which destroys colors.
            #
            # SOLUTION: Read raw linear pixel data → apply sRGB gamma manually → save via PIL.
            # This produces a perfectly correct sRGB PNG every time, regardless of
            # Blender's color management settings or the image's internal state.
            print(f"[NANO BANANA] Exporting image via PIL (sRGB-safe, no view transform)...")
            print(f"[NANO BANANA] Image colorspace: {image.colorspace_settings.name}")
            print(f"[NANO BANANA] Image size: {image.size[0]}x{image.size[1]}")
            
            try:
                from PIL import Image as PILImage
                import numpy as np
                
                w, h = image.size
                
                # Read raw pixel data from Blender (always linear floats, RGBA)
                pixels = np.array(image.pixels[:]).reshape((h, w, image.channels))
                
                # Flip vertically (Blender stores bottom-up, PIL expects top-down)
                pixels = np.flip(pixels, axis=0)
                
                # Determine if this image is stored as linear or sRGB internally
                cs_name = image.colorspace_settings.name.lower()
                is_linear = ('linear' in cs_name or 'scene' in cs_name or 'raw' in cs_name)
                
                if is_linear:
                    # Image IS linear → apply sRGB gamma curve for PNG output
                    print(f"[NANO BANANA] Image is linear, applying sRGB gamma...")
                    rgb = pixels[:, :, :3]
                    # sRGB gamma: linear → sRGB
                    rgb = np.clip(rgb, 0.0, 1.0)
                    srgb = np.where(rgb <= 0.0031308,
                                    rgb * 12.92,
                                    1.055 * np.power(rgb, 1.0 / 2.4) - 0.055)
                    pixels[:, :, :3] = srgb
                else:
                    # Image is already sRGB-tagged → pixels are already in sRGB space
                    # Just clamp to valid output range
                    print(f"[NANO BANANA] Image is sRGB, direct export...")
                    pixels = np.clip(pixels, 0.0, 1.0)
                
                # Convert float [0,1] → uint8 [0,255]
                pixels_u8 = (pixels * 255.0 + 0.5).astype(np.uint8)
                
                # Create PIL image
                if image.channels == 4:
                    pil_img = PILImage.fromarray(pixels_u8, 'RGBA')
                else:
                    pil_img = PILImage.fromarray(pixels_u8[:, :, :3], 'RGB')
                
                pil_img.save(image_path, 'PNG')
                print(f"[NANO BANANA] PIL export successful: {image_path}")
                
            except ImportError:
                # PIL not available — fallback to Blender's save()
                print(f"[NANO BANANA] PIL not available, falling back to image.save()...")
                original_filepath = image.filepath_raw
                original_file_format = image.file_format
                try:
                    image.filepath_raw = image_path
                    image.file_format = 'PNG'
                    image.save()
                finally:
                    image.filepath_raw = original_filepath
                    image.file_format = original_file_format
            except Exception as e:
                print(f"[NANO BANANA] PIL export failed: {e}, falling back to image.save()...")
                original_filepath = image.filepath_raw
                original_file_format = image.file_format
                try:
                    image.filepath_raw = image_path
                    image.file_format = 'PNG'
                    image.save()
                finally:
                    image.filepath_raw = original_filepath
                    image.file_format = original_file_format
            
            # Get reference image path if provided
            reference_path = None
            if props.use_reference_image and props.reference_image:
                reference_path = os.path.join(temp_dir, "reference.png")
                
                # Save reference using PIL (same sRGB-safe method as main image)
                ref_image = props.reference_image
                
                try:
                    from PIL import Image as PILImage
                    import numpy as np
                    
                    rw, rh = ref_image.size
                    ref_pixels = np.array(ref_image.pixels[:]).reshape((rh, rw, ref_image.channels))
                    ref_pixels = np.flip(ref_pixels, axis=0)
                    
                    cs_name = ref_image.colorspace_settings.name.lower()
                    is_linear = ('linear' in cs_name or 'scene' in cs_name or 'raw' in cs_name)
                    
                    if is_linear:
                        rgb = ref_pixels[:, :, :3]
                        rgb = np.clip(rgb, 0.0, 1.0)
                        srgb = np.where(rgb <= 0.0031308,
                                        rgb * 12.92,
                                        1.055 * np.power(rgb, 1.0 / 2.4) - 0.055)
                        ref_pixels[:, :, :3] = srgb
                    else:
                        ref_pixels = np.clip(ref_pixels, 0.0, 1.0)
                    
                    ref_u8 = (ref_pixels * 255.0 + 0.5).astype(np.uint8)
                    if ref_image.channels == 4:
                        pil_ref = PILImage.fromarray(ref_u8, 'RGBA')
                    else:
                        pil_ref = PILImage.fromarray(ref_u8[:, :, :3], 'RGB')
                    pil_ref.save(reference_path, 'PNG')
                    print(f"[NANO BANANA] Reference exported via PIL: {reference_path}")
                    
                except Exception:
                    # Fallback to Blender save()
                    ref_original_filepath = ref_image.filepath_raw
                    ref_original_format = ref_image.file_format
                    try:
                        ref_image.filepath_raw = reference_path
                        ref_image.file_format = 'PNG'
                        ref_image.save()
                    finally:
                        ref_image.filepath_raw = ref_original_filepath
                        ref_image.file_format = ref_original_format
            
            # Get inpainting guide if enabled
            inpaint_guide_path = None
            if props.use_inpainting:
                # Extract user's drawing as guide for AI
                inpaint_guide_path = self._extract_inpaint_guide(image, temp_dir)
                if not inpaint_guide_path:
                    props.is_editing = False
                    self.report({'WARNING'}, "No drawing found. Click Draw and paint something!")
                    return {'CANCELLED'}
                print(f"[NANO BANANA] Extracted inpaint guide: {inpaint_guide_path}")
            
            # Map model enum to API model name
            MODEL_MAP = {
                'NANO_BANANA_2': 'gemini-3.1-flash-image-preview',
                'NANO_BANANA_PRO': 'gemini-3-pro-image-preview',
                'NANO_BANANA': 'gemini-2.5-flash-image',
            }
            model_name = MODEL_MAP.get(props.ai_model, 'gemini-3.1-flash-image-preview')
            
            # Get auth token (Google API key or beta token)
            token = prefs.preferences.beta_token.strip() if prefs else ""

            # Start background thread
            thread = image_edit_thread.ImageEditThread(
                image_path=image_path,
                edit_prompt=props.edit_prompt,
                mask_path=inpaint_guide_path,
                reference_path=reference_path,
                api_key=token,
                context=context,
                original_image_name=image.name,
                temp_dir=temp_dir,
                resolution=props.resolution,
                original_size=(image.size[0], image.size[1]),
                model_name=model_name,
            )
            
            thread.start()
            print(f"[NANO BANANA] Edit thread started with model: {model_name}")
            
            self.report({'INFO'}, "AI edit started in background...")
            
        except Exception as e:
            props.is_editing = False
            props.status_text = f"Error: {str(e)}"
            self.report({'ERROR'}, f"Failed to start edit: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def _extract_inpaint_guide(self, image: bpy.types.Image, temp_dir: str) -> Optional[str]:
        """Extract user's drawing (inpainting guide) for AI to understand what to create"""
        try:
            print(f"[NANO BANANA] Extracting inpaint guide from: {image.name}")
            
            width, height = image.size
            
            # Force update pixels
            image.update()
            
            # Try PIL method first (better)
            try:
                from PIL import Image as PILImage
                import numpy as np
                
                print("[NANO BANANA] Using PIL for inpaint extraction")
                
                pixels = list(image.pixels[:])
                
                if image.channels >= 3:
                    pixel_array = np.array(pixels).reshape((height, width, image.channels))
                    rgb = pixel_array[:, :, :3]
                    
                    # Detect painted areas (any non-black color)
                    has_paint = np.any(rgb > 0.05, axis=2)
                    painted_pixels = int(np.sum(has_paint))
                    
                    print(f"[NANO BANANA] Painted pixels: {painted_pixels}")
                    
                    if painted_pixels < 50:
                        print("[NANO BANANA] Not enough drawing - draw more!")
                        return None
                    
                    # Save colored guide
                    guide_path = os.path.join(temp_dir, "inpaint_guide.png")
                    rgb_uint8 = (rgb * 255).astype(np.uint8)
                    rgb_uint8 = np.flipud(rgb_uint8)
                    
                    pil_guide = PILImage.fromarray(rgb_uint8, mode='RGB')
                    pil_guide.save(guide_path)
                    
                    print(f"[NANO BANANA] Inpaint guide saved: {guide_path}")
                    return guide_path
                else:
                    print(f"[NANO BANANA] Image needs RGB channels")
                    return None
                    
            except ImportError as e:
                print(f"[NANO BANANA] PIL not available: {e}")
                print("[NANO BANANA] Using Blender native save method...")
                
                # Fallback: use Blender's native save
                guide_path = os.path.join(temp_dir, "inpaint_guide.png")
                
                # Save image directly using Blender
                original_path = image.filepath_raw
                original_format = image.file_format
                
                try:
                    image.filepath_raw = guide_path
                    image.file_format = 'PNG'
                    image.save()
                    
                    print(f"[NANO BANANA] Inpaint guide saved (Blender method): {guide_path}")
                    
                    # Check if file exists
                    if os.path.exists(guide_path):
                        file_size = os.path.getsize(guide_path)
                        print(f"[NANO BANANA] File saved successfully: {file_size} bytes")
                        return guide_path
                    else:
                        print(f"[NANO BANANA] File not created!")
                        return None
                        
                finally:
                    # Restore original settings
                    image.filepath_raw = original_path
                    image.file_format = original_format
                
        except Exception as e:
            print(f"[NANO BANANA] Error: {e}")
            import traceback
            traceback.print_exc()
            return None


class NANO_BANANA_OT_finalize_composite(Operator):
    """Finalize composite - unify colors, contrast, lighting across entire image"""
    bl_idname = "nano_banana.finalize_composite"
    bl_label = "Finalize Composite"
    bl_description = "Unify colors, contrast, and lighting to create seamless photorealistic result"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        wm = context.window_manager
        props = wm.nano_banana_editor
        
        if not context.space_data or context.space_data.type != 'IMAGE_EDITOR':
            self.report({'ERROR'}, "Must be in Image Editor")
            return {'CANCELLED'}
        
        current_image = context.space_data.image
        if not current_image:
            self.report({'ERROR'}, "No image to finalize")
            return {'CANCELLED'}
        
        # Set special finalization prompt
        props.edit_prompt = "[FINALIZE_COMPOSITE]"
        
        # Call apply edit with special mode
        bpy.ops.nano_banana.apply_edit()
        
        self.report({'INFO'}, "Finalizing composite - unifying colors, contrast, lighting...")
        return {'FINISHED'}


class NANO_BANANA_OT_rerender_image(Operator):
    """Re-render the image with the same settings (variation)"""
    bl_idname = "nano_banana.rerender_image"
    bl_label = "Re-render Image"
    bl_description = "Generate a new variation with the same prompt and settings"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        sima = context.space_data
        image = sima.image
        
        if not image:
            self.report({'ERROR'}, "No image in editor")
            return {'CANCELLED'}
        
        # Check if we have history to pull from
        if len(props.edit_history) == 0:
            self.report({'INFO'}, "No edit history - use 'Apply AI Edit' first")
            return {'CANCELLED'}
        
        # Get last edit from history
        last_edit = props.edit_history[-1]
        
        # Reload prompt from last edit
        props.edit_prompt = last_edit.prompt
        
        # Trigger edit operator
        bpy.ops.nano_banana.apply_edit()
        
        self.report({'INFO'}, "Re-rendering with previous settings...")
        return {'FINISHED'}


class NANO_BANANA_OT_save_version(Operator):
    """Save current image as a new version"""
    bl_idname = "nano_banana.save_version"
    bl_label = "Save Version"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        sima = context.space_data
        image = sima.image
        
        if not image:
            self.report({'ERROR'}, "No image in editor")
            return {'CANCELLED'}
        
        try:
            # Create a copy of the image
            new_image = image.copy()
            new_image.name = f"{image.name}_v{len(context.window_manager.nano_banana_editor.edit_history) + 1}"
            
            self.report({'INFO'}, f"Saved as {new_image.name}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save version: {str(e)}")
            return {'CANCELLED'}


class NANO_BANANA_OT_load_history_edit(Operator):
    """Load edit from history"""
    bl_idname = "nano_banana.load_history_edit"
    bl_label = "Load History Edit"
    bl_options = {'REGISTER'}
    
    history_index: IntProperty()
    
    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        
        if self.history_index < 0 or self.history_index >= len(props.edit_history):
            self.report({'ERROR'}, "Invalid history index")
            return {'CANCELLED'}
        
        item = props.edit_history[self.history_index]
        
        # Load prompt
        props.edit_prompt = item.prompt
        
        # Load image if available
        if item.image_name in bpy.data.images:
            context.space_data.image = bpy.data.images[item.image_name]
            self.report({'INFO'}, f"Loaded edit from {item.timestamp}")
        else:
            self.report({'WARNING'}, f"Image {item.image_name} not found")
        
        return {'FINISHED'}


class NANO_BANANA_OT_convert_render_result(Operator):
    """Convert Render Result to editable image with correct colors"""
    bl_idname = "nano_banana.convert_render_result"
    bl_label = "Convert Render Result"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        sima = context.space_data
        if not sima or not sima.image:
            return {'CANCELLED'}
            
        image = sima.image
        if image.type != 'RENDER_RESULT':
            self.report({'INFO'}, "Image is already editable")
            return {'FINISHED'}
            
        try:
            # Create temp file
            import tempfile
            import os
            temp_path = os.path.join(tempfile.gettempdir(), f"render_convert_{int(time.time())}.png")
            
            # Save using current scene color management settings
            # This "bakes" the view transform into the pixels, which is what we see on screen
            # This is usually what users want when editing "what they see"
            scene = context.scene
            
            # Store current settings
            old_settings = scene.render.image_settings
            old_format = old_settings.file_format
            old_mode = old_settings.color_mode
            old_depth = old_settings.color_depth
            
            # Force standard PNG settings
            old_settings.file_format = 'PNG'
            old_settings.color_mode = 'RGBA'
            old_settings.color_depth = '8'
            
            try:
                image.save_render(temp_path, scene=scene)
            finally:
                # Restore settings
                old_settings.file_format = old_format
                old_settings.color_mode = old_mode
                old_settings.color_depth = old_depth
            
            # Create new image
            new_image_name = f"Editable_Render_{len(bpy.data.images)}"
            new_image = bpy.data.images.load(temp_path)
            new_image.name = new_image_name
            new_image.pack() # Pack into blend file
            
            # Clean up temp ONLY if packing was successful
            if new_image.packed_file:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            else:
                print(f"[NANO BANANA] Warning: Image not packed, keeping temp file: {temp_path}")
            
            # Switch editor to new image
            sima.image = new_image
            
            self.report({'INFO'}, f"Converted to {new_image.name}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Conversion failed: {str(e)}")
            return {'CANCELLED'}


class NANO_BANANA_OT_switch_to_paint(Operator):
    """Switch Image Editor to Paint mode"""
    bl_idname = "nano_banana.switch_to_paint"
    bl_label = "Start Paint"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        sima = context.space_data
        
        if not sima or not sima.image:
            self.report({'ERROR'}, "No image in editor")
            return {'CANCELLED'}
        
        image = sima.image
        
        # Check if image is Render Result - cannot paint on it directly
        if image.type == 'RENDER_RESULT':
            self.report({'INFO'}, "Converting Render Result to editable image...")
            # Call our robust conversion operator
            bpy.ops.nano_banana.convert_render_result()
            # Update reference to new image
            if sima.image != image:
                image = sima.image
            else:
                # Conversion failed or cancelled
                return {'CANCELLED'}
        
        try:
            # Switch to Paint mode
            sima.mode = 'PAINT'
            
            # Setup brush
            ts = context.tool_settings
            paint = ts.image_paint
            
            if paint:
                # Blender 5.0: unified_paint_settings is on Paint struct
                # Blender 4.x: unified_paint_settings is on tool_settings
                ups = getattr(paint, 'unified_paint_settings', None)
                if ups is None:
                    ups = getattr(ts, 'unified_paint_settings', None)
                
                if ups:
                    try:
                        ups.use_unified_size = False
                        ups.use_unified_color = False
                    except Exception:
                        pass
                
                # Try to ensure we have a brush
                if not paint.brush:
                    # Blender 5.0: paint.brush is readonly, use asset_activate
                    try:
                        bpy.ops.brush.asset_activate(
                            asset_library_type='ESSENTIALS',
                            relative_asset_identifier="brushes\\essentials_brushes-texture_paint.blend\\Brush\\Draw"
                        )
                        print("[NANO BANANA] Activated Draw brush via asset_activate")
                    except Exception as e1:
                        print(f"[NANO BANANA] asset_activate failed: {e1}")
                        # Blender 4.x fallback: direct assignment
                        try:
                            if 'Draw' in bpy.data.brushes:
                                paint.brush = bpy.data.brushes['Draw']
                                print("[NANO BANANA] Set Draw brush via direct assignment")
                        except Exception as e2:
                            print(f"[NANO BANANA] Direct brush assignment also failed: {e2}")
                
                brush = paint.brush
                if brush:
                    try:
                        brush.size = props.brush_size
                        brush.color = (props.brush_color[0], props.brush_color[1], props.brush_color[2])
                        brush.strength = 1.0
                        print(f"[NANO BANANA] Brush configured: size={brush.size}, color={brush.color[:]}")
                    except Exception as e:
                        print(f"[NANO BANANA] Could not set brush properties: {e}")
                else:
                    print("[NANO BANANA] Warning: No brush available after setup")
            
            self.report({'INFO'}, "Draw mode")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed: {str(e)}")
            return {'CANCELLED'}


class NANO_BANANA_OT_apply_inpaint(Operator):
    """Apply inpainting - save drawing as new image"""
    bl_idname = "nano_banana.apply_inpaint"
    bl_label = "Apply Drawing"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        sima = context.space_data
        
        if not sima or not sima.image:
            return {'CANCELLED'}
        
        try:
            current_image = sima.image
            props = context.window_manager.nano_banana_editor
            
            # Update pixels to ensure latest changes
            current_image.update()
            
            # Save current image to history BEFORE creating copy
            from datetime import datetime
            
            # Create a backup copy for history
            history_image = current_image.copy()
            history_image.name = f"{current_image.name}_history_{len(props.edit_history)}"
            
            # If the image is already packed, we don't need to pack it again, 
            # but copy() might lose the packed data reference if not careful.
            # However, for a fresh copy, we should try to pack it to ensure it stays.
            try:
                if not history_image.packed_file:
                     history_image.pack() 
            except Exception as e:
                print(f"[NANO BANANA] Warning: Could not pack history image: {e}")
                # If packing fails (e.g. file missing), we might still be okay if data is in memory
                pass
            
            history_item = props.edit_history.add()
            history_item.prompt = "[Inpaint sketch applied]"
            history_item.image_name = history_image.name # Point to the BACKUP copy
            history_item.timestamp = datetime.now().strftime("%H:%M:%S")
            history_item.has_mask = True
            
            print(f"[NANO BANANA] Saved history backup: {history_image.name}")
            
            # Create duplicate with drawing
            new_image = current_image.copy()
            new_image.name = f"{current_image.name}_inpaint"
            
            # Copy pixel data
            new_image.pixels = list(current_image.pixels[:])
            new_image.update()
            
            # Try to pack (skip if fails - not critical)
            try:
                new_image.pack()
                print(f"[NANO BANANA] Packed into blend file")
            except Exception as pack_error:
                print(f"[NANO BANANA] Pack failed (not critical): {pack_error}")
            
            # Switch to duplicate
            sima.image = new_image
            
            # Switch to view mode
            sima.mode = 'VIEW'
            
            print(f"[NANO BANANA] Created inpaint copy: {new_image.name}")
            self.report({'INFO'}, f"Original saved to history! Drawing saved as {new_image.name}")
            
            return {'FINISHED'}
            
        except Exception as e:
            import traceback
            print(f"[NANO BANANA] Error creating inpaint copy: {e}")
            traceback.print_exc()
            self.report({'ERROR'}, f"Failed: {str(e)}")
            return {'CANCELLED'}


def on_mask_toggle(self, context):
    """Handle mask toggle - switch to Paint mode automatically
    Compatible with Blender 4.x and 5.0+
    """
    try:
        # Find Image Editor area
        for area in context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                for space in area.spaces:
                    if space.type == 'IMAGE_EDITOR':
                        if not space.image:
                            return
                        
                        if self.use_mask:
                            # Switch to Paint mode
                            with context.temp_override(area=area, space_data=space):
                                space.mode = 'PAINT'
                                print("[NANO BANANA] Switched to Paint mode")
                                
                                # Setup brush in Tool Settings
                                try:
                                    ts = context.tool_settings
                                    paint = ts.image_paint
                                    
                                    if paint:
                                        # Disable unified paint settings
                                        # Blender 5.0: on Paint struct; 4.x: on tool_settings
                                        ups = getattr(paint, 'unified_paint_settings', None)
                                        if ups is None:
                                            ups = getattr(ts, 'unified_paint_settings', None)
                                        
                                        if ups:
                                            try:
                                                ups.use_unified_size = False
                                                ups.use_unified_color = False
                                            except Exception:
                                                pass
                                        
                                        brush = paint.brush
                                        if not brush:
                                            # Blender 5.0: use asset_activate
                                            try:
                                                bpy.ops.brush.asset_activate(
                                                    asset_library_type='ESSENTIALS',
                                                    relative_asset_identifier="brushes\\essentials_brushes-texture_paint.blend\\Brush\\Draw"
                                                )
                                                brush = paint.brush
                                                print("[NANO BANANA] Activated Draw brush via asset_activate")
                                            except Exception:
                                                # Blender 4.x fallback
                                                try:
                                                    if 'Draw' in bpy.data.brushes:
                                                        paint.brush = bpy.data.brushes['Draw']
                                                        brush = paint.brush
                                                except Exception:
                                                    print("[NANO BANANA] No default brush found")
                                        
                                        if brush:
                                            try:
                                                brush.size = self.brush_size
                                                brush.color = (self.brush_color[0], self.brush_color[1], self.brush_color[2])
                                                brush.strength = 1.0
                                                brush.blend = 'MIX'
                                                print(f"[NANO BANANA] Brush configured: size={brush.size}, color={brush.color[:]}")
                                            except Exception as e:
                                                print(f"[NANO BANANA] Could not set brush properties: {e}")
                                except Exception as e:
                                    import traceback
                                    print(f"[NANO BANANA] Brush setup error: {e}")
                                    traceback.print_exc()
                        else:
                            # Switch to View mode
                            with context.temp_override(area=area, space_data=space):
                                space.mode = 'VIEW'
                                print("[NANO BANANA] Switched to View mode")
                        
                        area.tag_redraw()
                        break
                        
    except Exception as e:
        import traceback
        print(f"[NANO BANANA] Mask toggle error: {e}")
        traceback.print_exc()


class NANO_BANANA_OT_load_reference_image(Operator):
    """Load reference image from file without switching Image Editor"""
    bl_idname = "nano_banana.load_reference_image"
    bl_label = "Load Reference Image"
    bl_options = {'REGISTER'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_image: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        try:
            props = context.window_manager.nano_banana_editor
            
            # Load image without switching Image Editor
            if self.filepath:
                # Check if already loaded
                image_name = os.path.basename(self.filepath)
                if image_name in bpy.data.images:
                    loaded_image = bpy.data.images[image_name]
                    print(f"[NANO BANANA] Using existing image: {image_name}")
                else:
                    # Load new image
                    loaded_image = bpy.data.images.load(self.filepath, check_existing=False)
                    print(f"[NANO BANANA] Loaded new reference: {loaded_image.name}")
                
                # Set as reference WITHOUT switching Image Editor
                props.reference_image = loaded_image
                
                self.report({'INFO'}, f"Loaded: {loaded_image.name}")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No file selected")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load: {str(e)}")
            print(f"[NANO BANANA] Error loading reference: {e}")
            return {'CANCELLED'}


class NANO_BANANA_OT_unlink_reference_image(Operator):
    """Remove reference image"""
    bl_idname = "nano_banana.unlink_reference_image"
    bl_label = "Remove Reference"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        props.reference_image = None
        self.report({'INFO'}, "Reference removed")
        return {'FINISHED'}


def update_brush_settings(self, context):
    """Update brush settings when UI changes - apply to Tool Settings
    Compatible with Blender 4.x and 5.0+
    """
    try:
        ts = context.tool_settings
        paint = getattr(ts, 'image_paint', None)
        
        if paint:
            # Blender 5.0: unified_paint_settings is on Paint struct (ts.image_paint)
            # Blender 4.x: unified_paint_settings is on tool_settings
            ups = getattr(paint, 'unified_paint_settings', None)
            if ups is None:
                ups = getattr(ts, 'unified_paint_settings', None)
            
            if ups:
                try:
                    ups.use_unified_size = False
                    ups.use_unified_color = False
                except Exception:
                    pass
            
            brush = paint.brush
            if brush:
                try:
                    brush.size = self.brush_size
                    brush.color = (self.brush_color[0], self.brush_color[1], self.brush_color[2])
                    print(f"[NANO BANANA] Brush updated: size={self.brush_size}, color=({self.brush_color[0]:.2f}, {self.brush_color[1]:.2f}, {self.brush_color[2]:.2f})")
                except Exception as e:
                    print(f"[NANO BANANA] Could not set brush properties: {e}")
        
        # Force UI redraw
        if hasattr(context, 'screen') and context.screen:
            for area in context.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    area.tag_redraw()
        
    except Exception as e:
        import traceback
        print(f"[NANO BANANA] Brush update error: {e}")
        traceback.print_exc()


# Registration classes
classes = (
    EditHistoryItem,
    ImageEditorProperties,
    BANANA_PT_image_editor_panel,
    NANO_BANANA_OT_apply_edit,
    NANO_BANANA_OT_finalize_composite,
    NANO_BANANA_OT_convert_render_result,
    NANO_BANANA_OT_switch_to_paint,
    NANO_BANANA_OT_apply_inpaint,
    NANO_BANANA_OT_load_reference_image,
    NANO_BANANA_OT_unlink_reference_image,
    NANO_BANANA_OT_rerender_image,
    NANO_BANANA_OT_save_version,
    NANO_BANANA_OT_load_history_edit,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to WindowManager (session persistence)
    bpy.types.WindowManager.nano_banana_editor = PointerProperty(type=ImageEditorProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    if hasattr(bpy.types.WindowManager, 'nano_banana_editor'):
        del bpy.types.WindowManager.nano_banana_editor

