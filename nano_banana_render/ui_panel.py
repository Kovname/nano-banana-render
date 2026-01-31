import bpy
from bpy.types import PropertyGroup, Panel
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty, CollectionProperty, PointerProperty

class GeminiRenderHistoryItem(PropertyGroup):
    """Single render history entry with visual preview"""
    
    prompt: StringProperty(
        name="Prompt",
        description="Prompt used for this render",
        default=""
    )
    
    timestamp: StringProperty(
        name="Timestamp", 
        description="When this render was created",
        default=""
    )
    
    image_name: StringProperty(
        name="Image Name",
        description="Name of the generated image in Blender",
        default=""
    )
    
    # Visual preview data
    thumbnail_name: StringProperty(
        name="Thumbnail Name",
        description="Name of thumbnail image in bpy.data.images",
        default=""
    )
    
    # Style reference data
    style_reference_used: BoolProperty(
        name="Style Reference Used",
        description="Whether style reference was used for this render",
        default=False
    )
    
    style_reference_name: StringProperty(
        name="Style Reference Name",
        description="Name of style reference image used",
        default=""
    )
    
    style_reference_thumbnail: StringProperty(
        name="Style Reference Thumbnail",
        description="Name of style reference thumbnail in bpy.data.images",
        default=""
    )

class GeminiRenderProperties(PropertyGroup):
    """Properties for Gemini Render addon stored in scene"""
    
    # Note: API key is NOT stored here for security - use environment variable or addon preferences
    
    prompt: StringProperty(
        name="Prompt", 
        description="Describe how you want the depth map to be transformed",
        default="Make this photorealistic with detailed materials and proper lighting",
        maxlen=1000,
    )
    
    # Render History (saved in blend file only)
    render_history: CollectionProperty(
        type=GeminiRenderHistoryItem,
        name="Render History"
    )
    
    history_index: IntProperty(
        name="History Index",
        default=-1,
    )
    
    # Render mode selection
    render_mode: EnumProperty(
        name="Render Mode",
        description="Choose between depth map (mist) or regular Eevee render",
        items=[
            ('DEPTH', "Depth Map (Mist)", "Use mist pass for pure depth information - no textures/lighting needed"),
            ('EEVEE', "Regular Render", "Use standard Eevee render - preserves colors, textures, and lighting"),
        ],
        default='DEPTH',
        update=lambda self, context: on_render_mode_change(self, context)
    )
    
    # Resolution selection (base size - aspect ratio auto-detected from scene)
    resolution: EnumProperty(
        name="Resolution",
        description="AI output resolution (aspect ratio auto-detected from scene/camera)",
        items=[
            ('1024', "1K", "Base 1024px (auto aspect ratio)"),
            ('2048', "2K", "High resolution 2048px"),
            ('4096', "4K", "Ultra high resolution 4096px"),
        ],
        default='1024',
    )
    
    # Mist Pass settings for depth rendering
    mist_start: FloatProperty(
        name="Mist Start",
        description="Start distance for mist pass (in meters)",
        default=5.0,  # 5m
        min=0.01,
        max=1000.0,
        unit='LENGTH',
        update=lambda self, context: update_mist_settings(self, context)
    )
    
    mist_depth: FloatProperty(
        name="Mist Depth", 
        description="Depth distance for mist pass (in meters)",
        default=25.0,  # 25m
        min=0.1,
        max=1000.0,
        unit='LENGTH',
        update=lambda self, context: update_mist_settings(self, context)
    )
    
    mist_falloff: EnumProperty(
        name="Mist Falloff",
        description="Mist falloff type - controls how depth gradient transitions",
        items=[
            ('LINEAR', "Linear", "Linear depth gradient - smooth and even transition"),
            ('QUADRATIC', "Quadratic", "Quadratic depth gradient - more contrast in middle range"),
            ('INVERSE_QUADRATIC', "Inverse Quadratic", "Inverse quadratic - stronger contrast at distance"),
        ],
        default='LINEAR',
        update=lambda self, context: update_mist_settings(self, context)
    )
    
    # Preview mist in viewport
    mist_preview: BoolProperty(
        name="Preview Mist",
        description="Show mist effect in 3D viewport for easy depth adjustment",
        default=False,
        update=lambda self, context: toggle_mist_preview(self, context)
    )
    
    # Style Reference Image (optional)
    use_style_reference: BoolProperty(
        name="Use Style Reference",
        description="Use a reference image to maintain style/materials",
        default=False
    )
    
    style_reference_image: PointerProperty(
        type=bpy.types.Image,
        name="Style Reference",
        description="Reference image to maintain similar style/materials/lighting"
    )
    
    # UI state
    show_settings: BoolProperty(
        name="Show Settings",
        description="Show advanced settings",
        default=False,
    )
    
    show_auth: BoolProperty(
        name="Show Authentication",
        description="Show authentication panel",
        default=True,  # Show by default first time
    )
    
    # Status
    status_text: StringProperty(
        name="Status",
        description="Current operation status",
        default="Ready to render",
    )
    
    is_rendering: BoolProperty(
        name="Is Rendering",
        description="Whether AI render is in progress",
        default=False,
    )

class BANANA_PT_render_panel(Panel):
    """Main Nano Banana Render Panel"""
    bl_label = "Nano Banana Pro"
    bl_idname = "BANANA_PT_render_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Banana Pro"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render
        
        # Import API key functions
        from . import gemini_api
        api_key = gemini_api.get_api_key()
        api_key_status = gemini_api.get_api_key_status()
        
        # Authentication (collapsible)
        box = layout.box()
        row = box.row(align=True)
        row.prop(props, "show_auth", 
                text="🔑 Authentication" if not props.show_auth else "🔑 Hide Authentication",
                toggle=True, icon='TRIA_DOWN' if props.show_auth else 'TRIA_RIGHT')
        
        if props.show_auth:
            if api_key_status:
                box.label(text="API Key configured", icon='CHECKMARK')
                box.label(text=f"Source: {api_key_status['source']}", icon='INFO')
            else:
                box.label(text="No API key found", icon='ERROR')
                col = box.column(align=True)
                col.scale_y = 0.8
                col.label(text="Set GEMINI_API_KEY environment variable, or")
                col.label(text="enter key in Addon Preferences")
                box.operator("gemini.open_preferences", text="Open Addon Preferences", icon='PREFERENCES')
        
        # Prompt
        box = layout.box()
        box.label(text="Prompt", icon='TEXT')
        box.prop(props, "prompt", text="")
        
        # Style Reference (always visible - main feature!)
        box = layout.box()
        row = box.row(align=True)
        row.scale_y = 2.0  # Make the main Style Reference toggle BIGGER!
        row.prop(props, "use_style_reference", text="🎨 Style Reference", toggle=True)
        
        if props.use_style_reference:
            col = box.column()
            col.prop(props, "style_reference_image", text="Reference Image")
            
            # Big intuitive buttons
            col.separator()
            
            # Load from file button
            load_row = col.row()
            load_row.scale_y = 1.5  # Normal size
            load_row.operator("gemini.load_image_as_reference", text="Load Photo from Computer", icon='FILEBROWSER')
            
            if props.style_reference_image:
                info_box = box.box()
                info_box.scale_y = 0.6
                info_box.label(text="AI will copy: materials, colors, lighting, textures")
                info_box.label(text="AI will keep: depth map geometry (shapes & layout)")
                info_box.label(text="Note: Material base colors are preserved from scene", icon='INFO')
                
                # Show image info
                img_info = info_box.row(align=True)
                img_info.label(text=f"📏 {props.style_reference_image.size[0]}x{props.style_reference_image.size[1]}")
                img_info.label(text=f"🎨 {props.style_reference_image.name}")
            else:
                help_box = box.box() 
                help_box.scale_y = 0.7
                help_box.label(text="📸 No reference image selected", icon='INFO')
                help_box.label(text="Load external photos to copy their STYLE:")
                help_box.label(text="✓ Colors, materials, lighting, textures")
                help_box.label(text="✓ Depth map provides shapes & composition")
                help_box.label(text="Examples: architectural photos, paintings, nature")
        else:
            help_box = box.box()
            help_box.scale_y = 0.7
            help_box.label(text="Enable to copy style from reference photos", icon='INFO')
            help_box.label(text="AI will use only depth map + prompt without style reference")
        
        
        # Settings toggle
        row = layout.row()
        row.prop(props, "show_settings", 
                text="Settings" if not props.show_settings else "Hide Settings",
                toggle=True, icon='PREFERENCES')
        
        if props.show_settings:
            box = layout.box()
            
            # Render Mode selection
            box.label(text="Render Mode:", icon='RENDERLAYERS')
            box.prop(props, "render_mode", text="")
            
            # Resolution selection (aspect ratio auto-detected)
            box.label(text="Resolution:", icon='FULLSCREEN_ENTER')
            box.prop(props, "resolution", text="")
            
            # Show auto-detected dimensions from scene
            width, height = get_render_dimensions_from_scene(context)
            box.label(text=f"Output: {width}x{height} (auto from scene)", icon='INFO')
            
            # Show mist settings only if depth mode is selected
            if props.render_mode == 'DEPTH':
                box.separator()
                box.label(text="Mist Pass Settings:", icon='WORLD')
                box.prop(props, "mist_start")
                box.prop(props, "mist_depth")
                box.prop(props, "mist_falloff")
                
                # Preview mist button
                row = box.row()
                if props.mist_preview:
                    row.prop(props, "mist_preview", text="Hide Mist Preview", toggle=True, icon='HIDE_OFF')
                else:
                    row.prop(props, "mist_preview", text="Show Mist Preview", toggle=True, icon='HIDE_ON')
            else:
                # Show info for regular render mode
                info_box = box.box()
                info_box.scale_y = 0.7
                info_box.label(text="Regular Render will use:", icon='INFO')
                info_box.label(text="  • Current scene textures")
                info_box.label(text="  • Current lighting setup")
                info_box.label(text="  • Scene colors")
                info_box.label(text="Great for preserving existing look!")
            
        
        # Style Reference moved to settings
        
        # Main render button
        layout.separator()
        col = layout.column(align=True)
        col.scale_y = 2.0  # Make it even bigger!
        
        if props.is_rendering:
            col.enabled = False
            col.operator("gemini.ai_render", text="🔄 Rendering in Progress...", icon='RENDER_ANIMATION')
        else:
            render_text = "Generate AI Render"
            if props.use_style_reference and props.style_reference_image:
                render_text = "Generate AI Render with Style"
            col.operator("gemini.ai_render", text=render_text, icon='RENDER_STILL')
        
        # Status and utilities
        layout.separator()
        
        # Status
        box = layout.box()
        status_icon = 'INFO' if not props.is_rendering else 'TIME'
        box.label(text=props.status_text, icon=status_icon)
        
        # Stop button if rendering
        if props.is_rendering:
            row = layout.row()
            row.scale_y = 1.2
            row.operator("gemini.stop_render", text="Stop Render", icon='CANCEL')
            
        
        # Quick help (only show if no API key)
        if not api_key:
            box = layout.box()
            box.label(text="Quick Start:", icon='HELP')
            col = box.column(align=True)
            col.label(text="1. Get API key from Google AI Studio")
            col.label(text="2. Set GEMINI_API_KEY env var or use Preferences")  
            col.label(text="3. Add objects and camera")
            col.label(text="4. Click AI Render!")


class BANANA_PT_history_panel(Panel):
    """Visual gallery render history panel"""
    bl_label = "Render Gallery" 
    bl_idname = "BANANA_PT_history_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Banana Pro"
    bl_parent_id = "BANANA_PT_render_panel"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render
        
        if len(props.render_history) == 0:
            box = layout.box()
            box.label(text="🔍 No renders yet", icon='INFO')
            box.label(text="Generate AI renders to see gallery")
            return
        
        # Gallery header
        header_row = layout.row(align=True)
        header_row.label(text=f"Gallery ({len(props.render_history)} renders)", icon='IMAGE_DATA')
        
        layout.separator()
        
        # Gallery grid - newest first
        for i, item in enumerate(reversed(props.render_history)):
            actual_index = len(props.render_history) - 1 - i
            render_number = len(props.render_history) - i  # Numbered from newest
            
            # Compact render card with proper structure
            card = layout.box()
            card.scale_y = 0.9
            
            # Row 1: Date and render number (compact)
            date_row = card.row()
            date_row.scale_y = 0.6
            date_row.label(text=f"#{render_number} • {item.timestamp}", icon='TIME')
            
            # Row 2: Buttons - View button (big) + Gear button (small, right)
            btn_row = card.row(align=True)
            btn_row.scale_y = 1.2
            
            # View photo button (takes most space)
            # Use the correct operator name from operators.py
            view_btn = btn_row.operator("gemini.load_history", text="👁️ View Photo", icon='ZOOM_IN')
            view_btn.history_index = actual_index
            
            # Gear button (small, just icon, right side)
            gear_btn = btn_row.operator("gemini.history_context_menu", text="", icon='PREFERENCES', emboss=False)
            gear_btn.history_index = actual_index
            
            # Row 3: Prompt (styled exactly like style reference help text)
            prompt_preview = item.prompt[:70] + "..." if len(item.prompt) > 70 else item.prompt
            help_box = card.box() 
            help_box.scale_y = 0.7
            help_box.label(text=prompt_preview, icon='TEXT')
            
            # Minimal separator between items
            if i < len(props.render_history) - 1:
                layout.separator()


def update_mist_settings(self, context):
    """Update world mist settings when UI values change."""
    try:
        if not context.scene.world:
            return
        
        world = context.scene.world
        mist_start_m = self.mist_start
        mist_depth_m = self.mist_depth
        mist_falloff = self.mist_falloff if hasattr(self, 'mist_falloff') else 'LINEAR'
        
        if hasattr(world, 'mist_settings'):
            world.mist_settings.use_mist = True
            world.mist_settings.start = mist_start_m
            world.mist_settings.depth = mist_depth_m
            world.mist_settings.falloff = mist_falloff
        elif hasattr(world, 'use_mist'):
            world.use_mist = True
            world.mist_start = mist_start_m
            world.mist_depth = mist_depth_m
            world.mist_falloff = mist_falloff
        
    except Exception as e:
        print(f"[GEMINI] Failed to update mist settings: {e}")

def toggle_mist_preview(self, context):
    """Toggle mist preview in 3D viewport."""
    try:
        update_mist_settings(self, context)
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        if self.mist_preview:
                            space.shading.type = 'MATERIAL'
                            if hasattr(space.shading, 'render_pass'):
                                space.shading.render_pass = 'MIST'
                        else:
                            if hasattr(space.shading, 'render_pass'):
                                space.shading.render_pass = 'COMBINED'
                            space.shading.type = 'MATERIAL'
                        area.tag_redraw()
                        return
        
    except Exception as e:
        print(f"[GEMINI] Failed to toggle mist preview: {e}")

def on_render_mode_change(self, context):
    """Handle render mode change - disable mist preview for Regular Render."""
    try:
        if self.render_mode == 'EEVEE' and self.mist_preview:
            self.mist_preview = False
    except Exception:
        pass


def get_render_dimensions_from_scene(context) -> tuple:
    """Get render dimensions from scene settings with base resolution scaling.
    
    Auto-detects aspect ratio from Blender's render settings.
    Scales to match the addon's resolution setting while preserving aspect ratio.
    """
    try:
        scene = context.scene
        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None
        base = int(props.resolution) if props else 1024
        
        # Get scene render resolution
        render = scene.render
        scene_width = render.resolution_x
        scene_height = render.resolution_y
        
        # Calculate aspect ratio from scene
        aspect = scene_width / scene_height
        
        # Scale to base resolution while preserving aspect ratio
        if aspect >= 1.0:
            # Landscape or square
            width = base
            height = int(base / aspect)
        else:
            # Portrait
            height = base
            width = int(base * aspect)
        
        return (width, height)
    except:
        return (1024, 1024)


def get_scene_aspect_ratio_string(context) -> str:
    """Get the closest supported aspect ratio string for Gemini API."""
    try:
        scene = context.scene
        render = scene.render
        aspect = render.resolution_x / render.resolution_y
        
        # Map to closest supported Gemini aspect ratio
        ratios = {
            "1:1": 1.0,
            "16:9": 16/9,
            "9:16": 9/16,
            "4:3": 4/3,
            "3:2": 3/2
        }
        closest = min(ratios.items(), key=lambda x: abs(x[1] - aspect))
        return closest[0]
    except:
        return "1:1"
