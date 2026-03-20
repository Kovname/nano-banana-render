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
    
    # AI Model selection (shown like Device selector in Cycles)
    ai_model: EnumProperty(
        name="Model",
        description="Select which AI model to use for rendering",
        items=[
            ('NANO_BANANA_2', "Nano Banana 2", "gemini-3.1-flash-image-preview — Fast, balanced quality"),
            ('NANO_BANANA_PRO', "Nano Banana Pro", "gemini-3-pro-image-preview — Highest quality, slower"),
            ('NANO_BANANA', "Nano Banana", "gemini-2.5-flash-image — Basic, fastest"),
        ],
        default='NANO_BANANA_PRO',
    )
    
    prompt: StringProperty(
        name="Prompt", 
        description="Describe how you want the depth map to be transformed into a photorealistic render",
        default="Make this photorealistic with detailed materials and proper lighting",
        maxlen=1000,
    )
    
    # Render History
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
            ('DEPTH', "Depth Map (Mist)", "Use mist pass for pure depth information — no textures/lighting needed"),
            ('EEVEE', "Regular Render", "Use standard Eevee render — preserves colors, textures, and lighting"),
        ],
        default='DEPTH',
        update=lambda self, context: on_render_mode_change(self, context)
    )
    
    # Resolution selection
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
        name="Start",
        description="Start distance for mist pass (objects closer than this are fully white)",
        default=5.0,
        min=0.01,
        max=1000.0,
        unit='LENGTH',
        update=lambda self, context: update_mist_settings(self, context)
    )
    
    mist_depth: FloatProperty(
        name="Depth", 
        description="Depth distance for mist pass (range over which mist fades from white to black)",
        default=25.0,
        min=0.1,
        max=1000.0,
        unit='LENGTH',
        update=lambda self, context: update_mist_settings(self, context)
    )
    
    mist_falloff: EnumProperty(
        name="Falloff",
        description="Mist falloff type — controls how depth gradient transitions",
        items=[
            ('LINEAR', "Linear", "Linear depth gradient — smooth and even transition"),
            ('QUADRATIC', "Quadratic", "Quadratic depth gradient — more contrast in middle range"),
            ('INVERSE_QUADRATIC', "Inverse Quadratic", "Inverse quadratic — stronger contrast at distance"),
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
    
    # Style Reference Image
    use_style_reference: BoolProperty(
        name="Style Reference",
        description="Use a reference image to copy its style, materials, colors, and lighting to the render",
        default=False
    )
    
    style_reference_image: PointerProperty(
        type=bpy.types.Image,
        name="Reference",
        description="Reference image — AI will copy materials, colors, lighting, textures from this image while using depth map geometry"
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
        default=True,
    )
    
    # Status
    status_text: StringProperty(
        name="Status",
        description="Current operation status",
        default="Ready",
    )
    
    is_rendering: BoolProperty(
        name="Is Rendering",
        description="Whether AI render is in progress",
        default=False,
    )

    # ─── Beta Properties ──────────────────────────────────────
    beta_balance: IntProperty(
        name="Balance",
        description="Remaining AI generations",
        default=-1,
    )
    
    feedback_text: StringProperty(
        name="Feedback",
        description="Your feedback about the addon",
        default="",
        maxlen=500,
    )
    
    show_feedback: BoolProperty(
        name="Show Feedback",
        description="Toggle feedback input",
        default=False,
    )
    
    has_submitted_feedback: BoolProperty(
        name="Feedback Submitted",
        default=False,
    )
    
    last_generation_id: IntProperty(
        name="Last Generation ID",
        description="ID of the last generation for rating",
        default=0,
    )
    
    last_generation_rated: BoolProperty(
        name="Rated",
        description="Whether the last generation has been rated",
        default=True,
    )


# ─── Main Panel (like Render settings header in Cycles) ───

class BANANA_PT_render_panel(Panel):
    """Nano Banana main settings — appears under Render Properties when engine is selected"""
    bl_label = "Nano Banana"
    bl_idname = "BANANA_PT_render_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        scene = context.scene
        props = scene.gemini_render
        
        # Model selector (like Device: CPU/GPU in Cycles)
        layout.prop(props, "ai_model")
        
        # Credit cost hint for current model
        prefs = context.preferences.addons.get("nano_banana_render")
        has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
        is_credit_user = has_token and prefs.preferences.beta_token.strip().startswith("nk_")
        is_api_user = has_token and prefs.preferences.beta_token.strip().startswith("AIza")
        
        if is_credit_user:
            # Cost per model+resolution
            model_tier = 'pro' if props.ai_model == 'NANO_BANANA_PRO' else 'flash'
            cost_grid = {
                'flash': {'1024': 10, '2048': 15, '4096': 60},
                'pro':   {'1024': 30, '2048': 45, '4096': 60},
            }
            res = getattr(props, 'resolution', '1024')
            cost = cost_grid.get(model_tier, cost_grid['pro']).get(res, 30)
            row = layout.row()
            row.scale_y = 0.7
            row.label(text=f"Cost: {cost} credits per render")
        
        if not has_token:
            row = layout.row()
            row.alert = True
            row.operator("banana.google_login", text="Login with Google", icon='URL')
        else:
            if not is_api_user:
                # Balance display
                row = layout.row()
                if props.beta_balance >= 0:
                    if is_credit_user:
                        row.label(text=f"Credits: {props.beta_balance}")
                    else:
                        row.label(text=f"Generations left: {props.beta_balance}")
                else:
                    if is_credit_user:
                        row.label(text="Account Active", icon='LINKED')
                    else:
                        row.label(text="Beta Active", icon='LINKED')
                row.operator("banana.refresh_balance", text="", icon='FILE_REFRESH')
                
                # Buy Credits button for credit users (on the same row)
                if is_credit_user:
                    if props.beta_balance >= 0 and props.beta_balance < 30:
                        row.alert = True
                    row.operator("banana.open_store", text="Buy Credits", icon='PLUS')
                
                # ─── Rating buttons (after render) ────────────────
                if props.last_generation_id > 0 and not props.last_generation_rated:
                    box = layout.box()
                    box.label(text="Rate this result:", icon='QUESTION')
                    row = box.row(align=True)
                    op_like = row.operator("banana.rate_generation", text="👍 Good")
                    op_like.rating = "like"
                    op_dislike = row.operator("banana.rate_generation", text="👎 Bad")
                    op_dislike.rating = "dislike"
            
            # ─── Feedback section ─────────────────────────────
            bonus_label = "" if is_api_user else ("+50 Credits" if is_credit_user else "+50 Gens")
            
            if props.show_feedback:
                box = layout.box()
                if props.has_submitted_feedback:
                    box.label(text="Leave additional feedback:", icon='INFO')
                else:
                    if bonus_label:
                        box.label(text=f"Leave feedback (min. 50 chars) for {bonus_label}!", icon='INFO')
                    else:
                        box.label(text="Leave feedback (min. 50 chars):", icon='INFO')
                box.prop(props, "feedback_text", text="")
                row = box.row()
                row.enabled = len(props.feedback_text.strip()) >= 50
                row.operator("banana.send_feedback", text="Submit Feedback", icon='CHECKMARK')
            else:
                row = layout.row()
                if props.has_submitted_feedback:
                    row.operator("banana.toggle_feedback", text="Thanks for your Feedback!", icon='HEART')
                else:
                    text = f"Leave Feedback ({bonus_label})" if bonus_label else "Leave Feedback"
                    row.operator("banana.toggle_feedback", text=text, icon='GREASEPENCIL')
        
        # Status (only show during/after render)
        if props.status_text and props.status_text != "Ready":
            layout.separator()
            box = layout.box()
            status_icon = 'TIME' if props.is_rendering else 'INFO'
            box.label(text=props.status_text, icon=status_icon)


# ─── Prompt Sub-panel ───

class BANANA_PT_prompt(Panel):
    """Prompt configuration"""
    bl_label = "Prompt"
    bl_idname = "BANANA_PT_prompt"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "BANANA_PT_render_panel"
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.gemini_render
        
        layout.prop(props, "prompt", text="")


# ─── Render Mode Sub-panel (like Sampling in Cycles) ───

class BANANA_PT_render_mode(Panel):
    """Render mode and resolution settings"""
    bl_label = "Render Mode"
    bl_idname = "BANANA_PT_render_mode"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "BANANA_PT_render_panel"
    bl_options = {'DEFAULT_CLOSED'}
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        props = context.scene.gemini_render
        
        layout.prop(props, "render_mode", text="Mode")
        layout.prop(props, "resolution")
        
        # Warn if 2K/4K selected with Nano Banana (gemini-2.5-flash only supports 1K)
        if props.ai_model == 'NANO_BANANA' and props.resolution != '1024':
            row = layout.row()
            row.alert = True
            row.label(text="Nano Banana supports 1K only", icon='ERROR')
        
        # Show auto-detected dimensions
        width, height = get_render_dimensions_from_scene(context)
        


# ─── Mist Settings Sub-panel ───

class BANANA_PT_mist(Panel):
    """Mist pass settings for depth rendering"""
    bl_label = "Mist Pass"
    bl_idname = "BANANA_PT_mist"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "BANANA_PT_render_panel"
    bl_options = {'DEFAULT_CLOSED'}
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return (context.engine in cls.COMPAT_ENGINES and 
                hasattr(context.scene, 'gemini_render') and 
                context.scene.gemini_render.render_mode == 'DEPTH')
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        props = context.scene.gemini_render
        
        layout.prop(props, "mist_start")
        layout.prop(props, "mist_depth")
        layout.prop(props, "mist_falloff")
        
        layout.separator()
        layout.prop(props, "mist_preview", toggle=True)


# ─── Style Reference Sub-panel ───

class BANANA_PT_style_reference(Panel):
    """Style reference for AI rendering"""
    bl_label = "Style Reference"
    bl_idname = "BANANA_PT_style_reference"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "BANANA_PT_render_panel"
    bl_options = {'DEFAULT_CLOSED'}
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES
    
    def draw_header(self, context):
        props = context.scene.gemini_render
        self.layout.prop(props, "use_style_reference", text="")
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        props = context.scene.gemini_render
        layout.active = props.use_style_reference
        
        layout.prop(props, "style_reference_image", text="Image")
        
        # Load from file
        row = layout.row()
        row.operator("gemini.load_image_as_reference", text="Load from File", icon='FILEBROWSER')
        
        if props.style_reference_image:
            col = layout.column(align=True)
            col.scale_y = 0.8
            col.label(text=f"{props.style_reference_image.size[0]}×{props.style_reference_image.size[1]}", icon='IMAGE_DATA')


# ─── Render Gallery Sub-panel ───

class BANANA_PT_history_panel(Panel):
    """Visual gallery render history panel"""
    bl_label = "Render Gallery" 
    bl_idname = "BANANA_PT_history_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "BANANA_PT_render_panel"
    bl_options = {'DEFAULT_CLOSED'}
    COMPAT_ENGINES = {'NANO_BANANA'}
    
    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render
        
        if len(props.render_history) == 0:
            layout.label(text="No renders yet", icon='INFO')
            return
        
        layout.label(text=f"{len(props.render_history)} renders", icon='IMAGE_DATA')
        
        # Gallery — newest first
        for i, item in enumerate(reversed(props.render_history)):
            actual_index = len(props.render_history) - 1 - i
            render_number = len(props.render_history) - i
            
            box = layout.box()
            
            # Header row: number + timestamp
            row = box.row()
            row.scale_y = 0.8
            row.label(text=f"#{render_number} • {item.timestamp}", icon='TIME')
            
            # Buttons row
            btn_row = box.row(align=True)
            view_btn = btn_row.operator("gemini.load_history", text="View", icon='ZOOM_IN')
            view_btn.history_index = actual_index
            
            gear_btn = btn_row.operator("gemini.history_context_menu", text="", icon='DOWNARROW_HLT')
            gear_btn.history_index = actual_index
            
            # Prompt preview
            prompt_preview = item.prompt[:60] + "..." if len(item.prompt) > 60 else item.prompt
            row = box.row()
            row.scale_y = 0.7
            row.label(text=prompt_preview, icon='TEXT')


# ─── 3D Viewport N-Panel (Beta) ───

class BANANA_PT_beta_npanel(Panel):
    """Beta info panel in the 3D viewport sidebar (N-key)"""
    bl_label = "Nano Banana Beta"
    bl_idname = "BANANA_PT_beta_npanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Banana"
    
    @classmethod
    def poll(cls, context):
        return context.engine == 'NANO_BANANA'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render
        
        prefs = context.preferences.addons.get("nano_banana_render")
        has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
        is_credit_user = has_token and prefs.preferences.beta_token.strip().startswith("nk_")
        is_api_user = has_token and prefs.preferences.beta_token.strip().startswith("AIza")
        
        if not has_token:
            box = layout.box()
            box.alert = True
            box.label(text="No API key!", icon='ERROR')
            box.operator("banana.google_login", text="Login with Google", icon='URL')
            box.operator("gemini.open_preferences", text="Set Key Manually", icon='PREFERENCES')
            return
        
        # Balance (hide for API users)
        if not is_api_user:
            row = layout.row()
            if props.beta_balance >= 0:
                if is_credit_user:
                    row.label(text=f"Credits: {props.beta_balance}")
                else:
                    row.label(text=f"Generations left: {props.beta_balance}")
            else:
                if is_credit_user:
                    row.label(text="Account Active", icon='LINKED')
                else:
                    row.label(text="Beta Active", icon='LINKED')
            row.operator("banana.refresh_balance", text="", icon='FILE_REFRESH')
            
            # Buy Credits (credit users — on the same row)
            if is_credit_user:
                if props.beta_balance >= 0 and props.beta_balance < 30:
                    row.alert = True
                row.operator("banana.open_store", text="Buy Credits", icon='PLUS')
        
        # Cost info for credit users
        if is_credit_user:
            model_tier = 'pro' if props.ai_model == 'NANO_BANANA_PRO' else 'flash'
            cost_grid = {
                'flash': {'1024': 10, '2048': 15, '4096': 60},
                'pro':   {'1024': 30, '2048': 45, '4096': 60},
            }
            res = getattr(props, 'resolution', '1024')
            cost = cost_grid.get(model_tier, cost_grid['pro']).get(res, 30)
            row = layout.row()
            row.scale_y = 0.7
            row.label(text=f"Cost: {cost} credits")
        
        # Render button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.enabled = not props.is_rendering and (props.beta_balance > 0 or props.beta_balance < 0)
        row.operator("banana.ai_render", text="AI Render", icon='RENDER_STILL')
        
        # Status
        if props.status_text and props.status_text != "Ready":
            box = layout.box()
            status_icon = 'TIME' if props.is_rendering else 'INFO'
            box.label(text=props.status_text, icon=status_icon)
        
        # Rating buttons (after render)
        if props.last_generation_id > 0 and not props.last_generation_rated:
            layout.separator()
            box = layout.box()
            box.label(text="Rate this result:", icon='QUESTION')
            row = box.row(align=True)
            op_like = row.operator("banana.rate_generation", text="👍 Good")
            op_like.rating = "like"
            op_dislike = row.operator("banana.rate_generation", text="👎 Bad")
            op_dislike.rating = "dislike"
        
        # Feedback (same system as Render Properties panel)
        bonus_label = "" if is_api_user else ("+50 Credits" if is_credit_user else "+50 Gens")
        layout.separator()
        if props.show_feedback:
            box = layout.box()
            if props.has_submitted_feedback:
                box.label(text="Leave additional feedback:", icon='INFO')
            else:
                if bonus_label:
                    box.label(text=f"Leave feedback (min. 50 chars) for {bonus_label}!", icon='INFO')
                else:
                    box.label(text="Leave feedback (min. 50 chars):", icon='INFO')
            box.prop(props, "feedback_text", text="")
            row = box.row()
            row.enabled = len(props.feedback_text.strip()) >= 50
            row.operator("banana.send_feedback", text="Submit Feedback", icon='CHECKMARK')
        else:
            if props.has_submitted_feedback:
                layout.operator("banana.toggle_feedback", text="Thanks for your Feedback!", icon='HEART')
            else:
                text = f"Leave Feedback ({bonus_label})" if bonus_label else "Leave Feedback"
                layout.operator("banana.toggle_feedback", text=text, icon='GREASEPENCIL')


# ─── Helper functions ───

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
    """Handle render mode change — switch viewport to match mode."""
    try:
        # Disable mist preview if switching to EEVEE
        if self.render_mode == 'EEVEE' and self.mist_preview:
            self.mist_preview = False
        
        # Auto-switch viewport shading to match render mode
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        if self.render_mode == 'DEPTH':
                            # Switch to Material mode with Mist pass
                            space.shading.type = 'MATERIAL'
                            if hasattr(space.shading, 'render_pass'):
                                space.shading.render_pass = 'MIST'
                            if hasattr(space.shading, 'use_scene_world'):
                                space.shading.use_scene_world = True
                            # Update mist settings so the preview is accurate
                            update_mist_settings(self, context)
                        else:
                            # Switch to Material Preview (EEVEE-like)
                            space.shading.type = 'MATERIAL'
                            if hasattr(space.shading, 'render_pass'):
                                space.shading.render_pass = 'COMBINED'
                            if hasattr(space.shading, 'use_scene_lights'):
                                space.shading.use_scene_lights = True
                        area.tag_redraw()
                        return
    except Exception as e:
        print(f"[NANO BANANA] Render mode change error: {e}")


def get_render_dimensions_from_scene(context) -> tuple:
    """Get render dimensions from scene settings with base resolution scaling."""
    try:
        scene = context.scene
        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None
        base = int(props.resolution) if props else 1024
        
        render = scene.render
        scene_width = render.resolution_x
        scene_height = render.resolution_y
        
        aspect = scene_width / scene_height
        
        if aspect >= 1.0:
            width = base
            height = int(base / aspect)
        else:
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
