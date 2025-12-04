import bpy
from bpy.types import PropertyGroup, Panel
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    CollectionProperty,
    PointerProperty,
)

# Module-level init flag to avoid writing to ID data during draw
_provider_init_done = False


def get_preset_items(self, context):
    """Dynamically get preset items from preset manager"""
    try:
        from . import prompt_presets

        manager = prompt_presets.get_preset_manager()
        items = manager.get_preset_items_for_enum()
        return items
    except Exception as e:
        print(f"[UI] Error getting preset items: {e}")
        return [("NONE", "No Presets", "No presets available")]


def on_preset_change(self, context):
    """Load preset prompt when preset selection changes"""
    try:
        from . import prompt_presets

        # Skip if NONE selected
        if self.prompt_preset == "NONE":
            return

        # Load preset
        manager = prompt_presets.get_preset_manager()
        preset = manager.get_preset_by_name(self.prompt_preset)

        if preset:
            # Override prompt with preset content
            self.prompt = preset.get("prompt", "")
            print(f"[UI] Loaded preset: {self.prompt_preset}")
        else:
            print(f"[UI] Preset not found: {self.prompt_preset}")
    except Exception as e:
        print(f"[UI] Error loading preset: {e}")


class GeminiRenderHistoryItem(PropertyGroup):
    """Single render history entry with visual preview"""

    prompt: StringProperty(
        name="Prompt", description="Prompt used for this render", default=""
    )

    timestamp: StringProperty(
        name="Timestamp", description="When this render was created", default=""
    )

    image_name: StringProperty(
        name="Image Name",
        description="Name of the generated image in Blender",
        default="",
    )

    # Visual preview data
    thumbnail_name: StringProperty(
        name="Thumbnail Name",
        description="Name of thumbnail image in bpy.data.images",
        default="",
    )

    # Style reference data
    style_reference_used: BoolProperty(
        name="Style Reference Used",
        description="Whether style reference was used for this render",
        default=False,
    )

    style_reference_name: StringProperty(
        name="Style Reference Name",
        description="Name of style reference image used",
        default="",
    )

    style_reference_thumbnail: StringProperty(
        name="Style Reference Thumbnail",
        description="Name of style reference thumbnail in bpy.data.images",
        default="",
    )


def on_provider_change(self, context):
    """Auto-fill provider settings when provider is changed - from JSON config"""
    try:
        import bpy
        from . import providers

        # Set loading flag to prevent save during load
        self._loading_provider_config = True

        print(
            f"\n[UI] ========== Provider Changed to: {self.provider_type} ==========="
        )

        # Define default presets for each provider
        default_presets = {
            "google": {
                "base_url": "https://generativelanguage.googleapis.com",
                "model_id": "gemini-3-pro-image-preview",
            },
            "yunwu": {
                "base_url": "https://yunwu.zeabur.app",
                "model_id": "gemini-3-pro-image-preview",
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1/chat/completions",
                "model_id": "google/gemini-3-pro-image-preview",
            },
            "gptgod": {
                "base_url": "https://api.gptgod.online/v1/chat/completions",
                "model_id": "gemini-3-pro-image-preview",
            },
        }

        # Get provider manager
        manager = providers.get_provider_manager()

        # Get saved config for this provider type
        saved_config = manager.get_provider_by_type(self.provider_type)
        default_preset = default_presets.get(self.provider_type, {})

        print(f"[UI] Default preset for {self.provider_type}:")
        print(f"     URL: {default_preset.get('base_url', 'N/A')}")
        print(f"     Model: {default_preset.get('model_id', 'N/A')}")

        if saved_config:
            print(f"[UI] Found saved config in JSON:")
            print(f"     API Key: {'***' if saved_config.get('apiKey') else '(empty)'}")
            print(f"     Base URL: {saved_config.get('baseUrl', '(empty)')}")
            print(f"     Model: {saved_config.get('model', '(empty)')}")

            # Load from JSON, but use default if JSON value is empty
            self.api_key = saved_config.get("apiKey", "")

            # Use saved base_url if not empty, otherwise use default preset
            saved_url = saved_config.get("baseUrl", "")
            self.provider_base_url = (
                saved_url if saved_url else default_preset.get("base_url", "")
            )

            # Use saved model if not empty, otherwise use default preset
            saved_model = saved_config.get("model", "")
            self.provider_model_id = (
                saved_model if saved_model else default_preset.get("model_id", "")
            )

            print(f"[UI] Final values set:")
            print(f"     Base URL: {self.provider_base_url}")
            print(f"     Model ID: {self.provider_model_id}")
        else:
            print(f"[UI] No saved config found, using default preset")
            # Fallback to hardcoded presets if not in JSON
            self.api_key = ""
            self.provider_base_url = default_preset.get("base_url", "")
            self.provider_model_id = default_preset.get("model_id", "")
            print(f"[UI] Final values set:")
            print(f"     Base URL: {self.provider_base_url}")
            print(f"     Model ID: {self.provider_model_id}")

        # Persist selected provider
        try:
            manager.save_selected_provider(self.provider_type)
        except Exception as e:
            print(f"[UI] Failed to save selected provider: {e}")
        print(f"[UI] ========== End Provider Change ==========\n")

    except Exception as e:
        print(f"[GEMINI] Error in provider change: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Clear loading flag
        self._loading_provider_config = False


class GeminiRenderProperties(PropertyGroup):
    """Properties for Gemini Render addon stored in scene"""

    # Provider selection
    provider_type: EnumProperty(
        name="Provider",
        description="Select AI image generation provider",
        items=[
            ("google", "Google Gemini (Official)", "Official Google Gemini API"),
            ("yunwu", "Yunwu.ai", "Yunwu.ai Gemini proxy"),
            ("openrouter", "OpenRouter", "OpenRouter API"),
            ("gptgod", "GPTGod", "GPTGod API"),
        ],
        default="google",
        update=lambda self, context: on_provider_change(self, context),
    )

    # Main properties
    api_key: StringProperty(
        name="API Key",
        description="API Key for selected provider",
        default="",
        subtype="PASSWORD",
        update=lambda self, context: sync_api_key(self, context),
    )

    # Provider-specific settings
    provider_base_url: StringProperty(
        name="Base URL",
        description="Custom base URL for API provider (leave empty for default)",
        default="",
        update=lambda self, context: sync_provider_base_url(self, context),
    )

    provider_model_id: StringProperty(
        name="Model ID",
        description="Model ID for the provider (leave empty for default)",
        default="",
        update=lambda self, context: sync_provider_model_id(self, context),
    )

    prompt: StringProperty(
        name="Prompt",
        description="Describe how you want the depth map to be transformed",
        default="Make this photorealistic with detailed materials and proper lighting",
        maxlen=1000,
    )

    # Prompt presets
    prompt_preset: EnumProperty(
        name="Preset",
        description="Select a prompt preset",
        items=get_preset_items,
        update=on_preset_change,
    )

    # Render History (saved in blend file only)
    render_history: CollectionProperty(
        type=GeminiRenderHistoryItem, name="Render History"
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
            (
                "DEPTH",
                "Depth Map (Mist)",
                "Use mist pass for pure depth information - no textures/lighting needed",
            ),
            (
                "EEVEE",
                "Regular Render",
                "Use standard Eevee render - preserves colors, textures, and lighting",
            ),
        ],
        default="DEPTH",
        update=lambda self, context: on_render_mode_change(self, context),
    )

    # Resolution selection (API resolution tier)
    resolution: EnumProperty(
        name="Resolution",
        description="Choose AI generation resolution tier",
        items=[
            ("1K", "1K", "Standard resolution (~1024px)"),
            ("2K", "2K", "High resolution (~2048px)"),
            ("4K", "4K", "Ultra high resolution (~4096px)"),
        ],
        default="1K",
    )

    # Mist Pass settings for depth rendering
    mist_start: FloatProperty(
        name="Mist Start",
        description="Start distance for mist pass (in meters)",
        default=5.0,  # 5m
        min=0.01,
        max=1000.0,
        unit="LENGTH",
        update=lambda self, context: update_mist_settings(self, context),
    )

    mist_depth: FloatProperty(
        name="Mist Depth",
        description="Depth distance for mist pass (in meters)",
        default=25.0,  # 25m
        min=0.1,
        max=1000.0,
        unit="LENGTH",
        update=lambda self, context: update_mist_settings(self, context),
    )

    mist_falloff: EnumProperty(
        name="Mist Falloff",
        description="Mist falloff type - controls how depth gradient transitions",
        items=[
            ("LINEAR", "Linear", "Linear depth gradient - smooth and even transition"),
            (
                "QUADRATIC",
                "Quadratic",
                "Quadratic depth gradient - more contrast in middle range",
            ),
            (
                "INVERSE_QUADRATIC",
                "Inverse Quadratic",
                "Inverse quadratic - stronger contrast at distance",
            ),
        ],
        default="LINEAR",
        update=lambda self, context: update_mist_settings(self, context),
    )

    # Preview mist in viewport
    mist_preview: BoolProperty(
        name="Preview Mist",
        description="Show mist effect in 3D viewport for easy depth adjustment",
        default=False,
        update=lambda self, context: toggle_mist_preview(self, context),
    )

    # Style Reference Image (optional)
    use_style_reference: BoolProperty(
        name="Use Style Reference",
        description="Use a reference image to maintain style/materials",
        default=False,
    )

    style_reference_image: PointerProperty(
        type=bpy.types.Image,
        name="Style Reference",
        description="Reference image to maintain similar style/materials/lighting",
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
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nano Banana Pro"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render

        # Auto-sync API key from preferences if scene key is empty
        if not props.api_key:
            try:
                # Use __package__ to get the correct addon name
                package_name = __package__ if __package__ else "nano_banana_render"
                addon_prefs = context.preferences.addons.get(package_name)
                if (
                    addon_prefs
                    and hasattr(addon_prefs.preferences, "api_key")
                    and addon_prefs.preferences.api_key
                ):
                    props.api_key = addon_prefs.preferences.api_key
            except:
                pass

        # Authentication (collapsible)
        box = layout.box()
        row = box.row(align=True)
        row.prop(
            props,
            "show_auth",
            text=(
                "🔑 Authentication" if not props.show_auth else "🔑 Hide Authentication"
            ),
            toggle=True,
            icon="TRIA_DOWN" if props.show_auth else "TRIA_RIGHT",
        )

        if props.show_auth:
            # Provider selection dropdown
            box.prop(props, "provider_type", text="")

            # API Key input with label
            label_row = box.row()
            label_row.scale_y = 0.7
            label_row.label(text="API Key", icon="KEY_HLT")
            box.prop(props, "api_key", text="")

            if not props.api_key.strip():
                warn_row = box.row()
                warn_row.scale_y = 0.6
                warn_row.label(text="⚠ Enter API key", icon="ERROR")

            # Base URL with label
            label_row = box.row()
            label_row.scale_y = 0.7
            label_row.label(text="Base URL", icon="URL")
            box.prop(props, "provider_base_url", text="")

            # Model ID with label
            label_row = box.row()
            label_row.scale_y = 0.7
            label_row.label(text="Model ID", icon="PLUGIN")
            box.prop(props, "provider_model_id", text="")

            # Provider management buttons
            btn_row = box.row(align=True)
            btn_row.scale_y = 1.2
            btn_row.operator(
                "gemini.test_provider_connection", text="Test Connection", icon="PLUGIN"
            )

        # Prompt with Presets
        box = layout.box()

        # Preset dropdown and management buttons
        preset_row = box.row()
        preset_row.label(text="Prompt Presets", icon="TEXT")

        # Dropdown row
        dropdown_row = box.row()
        dropdown_row.prop(props, "prompt_preset", text="")

        # Management buttons row
        btn_row = box.row(align=True)
        btn_row.scale_y = 1.0

        # Check if preset is selected
        preset_selected = props.prompt_preset and props.prompt_preset != "NONE"

        # Add button (always enabled)
        btn_row.operator("gemini.add_prompt_preset", text="Add", icon="ADD")

        # Save, Rename, Delete buttons (disabled when no preset selected)
        save_col = btn_row.column()
        save_col.enabled = preset_selected
        save_col.operator("gemini.save_prompt_preset", text="Save", icon="FILE_TICK")

        rename_col = btn_row.column()
        rename_col.enabled = preset_selected
        rename_col.operator(
            "gemini.rename_prompt_preset", text="Rename", icon="SORTALPHA"
        )

        del_col = btn_row.column()
        del_col.enabled = preset_selected
        del_col.operator("gemini.delete_prompt_preset", text="Del", icon="TRASH")

        # Prompt text area
        # box.label(text="Prompt", icon='PROP_ON')
        col = box.column(align=True)
        col.prop(props, "prompt", text="")

        # Style Reference (always visible - main feature!)
        box = layout.box()
        row = box.row(align=True)
        row.scale_y = 1.5  # Make the main Style Reference toggle BIGGER!
        row.prop(props, "use_style_reference", text="🎨 Style Reference", toggle=True)

        if props.use_style_reference:
            col = box.column()
            col.prop(props, "style_reference_image", text="Reference Image")

            # Big intuitive buttons
            col.separator()

            # Load from file button
            load_row = col.row()
            load_row.scale_y = 1.5  # Normal size
            load_row.operator(
                "gemini.load_image_as_reference",
                text="Load Photo from Computer",
                icon="FILEBROWSER",
            )

            if props.style_reference_image:
                info_box = box.box()
                info_box.scale_y = 0.6
                info_box.label(
                    text="AI will copy: materials, colors, lighting, textures"
                )
                info_box.label(
                    text="AI will keep: depth map geometry (shapes & layout)"
                )
                info_box.label(
                    text="Note: Material base colors are preserved from scene",
                    icon="INFO",
                )

                # Show image info
                img_info = info_box.row(align=True)
                img_info.label(
                    text=f"📏 {props.style_reference_image.size[0]}x{props.style_reference_image.size[1]}"
                )
                img_info.label(text=f"🎨 {props.style_reference_image.name}")
            else:
                help_box = box.box()
                help_box.scale_y = 0.7
                help_box.label(text="📸 No reference image selected", icon="INFO")
                help_box.label(text="Load external photos to copy their STYLE:")
                help_box.label(text="✓ Colors, materials, lighting, textures")
                help_box.label(text="✓ Depth map provides shapes & composition")
                help_box.label(text="Examples: architectural photos, paintings, nature")
        else:
            help_box = box.box()
            help_box.scale_y = 0.7
            help_box.label(
                text="Enable to copy style from reference photos", icon="INFO"
            )
            help_box.label(
                text="AI will use only depth map + prompt without style reference"
            )

        # Settings toggle
        row = layout.row()
        row.prop(
            props,
            "show_settings",
            text="Settings" if not props.show_settings else "Hide Settings",
            toggle=True,
            icon="PREFERENCES",
        )

        if props.show_settings:
            box = layout.box()

            # Render Mode selection
            box.label(text="Render Mode:", icon="RENDERLAYERS")
            box.prop(props, "render_mode", text="")

            # Resolution & Smart Render Ratio moved above the Generate AI Render button
            # ... existing code ...

            # Show mist settings only if depth mode is selected
            if props.render_mode == "DEPTH":
                box.separator()
                box.label(text="Mist Pass Settings:", icon="WORLD")
                box.prop(props, "mist_start")
                box.prop(props, "mist_depth")
                box.prop(props, "mist_falloff")

                # Preview mist button
                row = box.row()
                if props.mist_preview:
                    row.prop(
                        props,
                        "mist_preview",
                        text="Hide Mist Preview",
                        toggle=True,
                        icon="HIDE_OFF",
                    )
                else:
                    row.prop(
                        props,
                        "mist_preview",
                        text="Show Mist Preview",
                        toggle=True,
                        icon="HIDE_ON",
                    )
            else:
                # Show info for regular render mode
                info_box = box.box()
                info_box.scale_y = 0.7
                info_box.label(text="Regular Render will use:", icon="INFO")
                info_box.label(text="  • Current scene textures")
                info_box.label(text="  • Current lighting setup")
                info_box.label(text="  • Scene colors")
                info_box.label(text="Great for preserving existing look!")

        # Style Reference moved to settings

        # Main render button
        layout.separator()
        # Resolution and Smart Ratio side-by-side above the render button
        top_row = layout.row(align=True)
        top_row.prop(props, "resolution", text="")
        top_row.operator("gemini.smart_render_ratio", text="Smart Render Ratio", icon="OUTPUT")

        col = layout.column(align=True)
        col.scale_y = 2.0  # Make it even bigger!

        if props.is_rendering:
            col.enabled = False
            col.operator(
                "gemini.ai_render",
                text="🔄 Rendering in Progress...",
                icon="RENDER_ANIMATION",
            )
        else:
            render_text = "Generate AI Render"
            if props.use_style_reference and props.style_reference_image:
                render_text = "Generate AI Render with Style"
            col.operator("gemini.ai_render", text=render_text, icon="RENDER_STILL")

        # Status and utilities
        layout.separator()

        # Status
        box = layout.box()
        status_icon = "INFO" if not props.is_rendering else "TIME"
        box.label(text=props.status_text, icon=status_icon)

        # Stop button if rendering
        if props.is_rendering:
            row = layout.row()
            row.scale_y = 1.2
            row.operator("gemini.stop_render", text="Stop Render", icon="CANCEL")

        # Quick help
        if not props.api_key.strip():
            box = layout.box()
            box.label(text="Quick Start:", icon="HELP")
            col = box.column(align=True)
            col.label(text="1. Get API key from Google AI Studio")
            col.label(text="2. Enter it above")
            col.label(text="3. Add objects and camera")
            col.label(text="4. Click AI Render!")


class BANANA_PT_history_panel(Panel):
    """Visual gallery render history panel"""

    bl_label = "Render Gallery"
    bl_idname = "BANANA_PT_history_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nano Banana Pro"
    bl_parent_id = "BANANA_PT_render_panel"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.gemini_render

        if len(props.render_history) == 0:
            box = layout.box()
            box.label(text="🔍 No renders yet", icon="INFO")
            box.label(text="Generate AI renders to see gallery")
            return

        # Gallery header
        header_row = layout.row(align=True)
        header_row.label(
            text=f"Gallery ({len(props.render_history)} renders)", icon="IMAGE_DATA"
        )

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
            date_row.label(text=f"#{render_number} • {item.timestamp}", icon="TIME")

            # Row 2: Buttons - View button (big) + Gear button (small, right)
            btn_row = card.row(align=True)
            btn_row.scale_y = 1.2

            # View photo button (takes most space)
            view_btn = btn_row.operator(
                "gemini.open_history_image", text="👁️ View Photo", icon="ZOOM_IN"
            )
            view_btn.history_index = actual_index

            # Gear button (small, just icon, right side)
            gear_btn = btn_row.operator(
                "gemini.history_context_menu", text="", icon="PREFERENCES", emboss=False
            )
            gear_btn.history_index = actual_index

            # Row 3: Prompt (styled exactly like style reference help text)
            prompt_preview = (
                item.prompt[:70] + "..." if len(item.prompt) > 70 else item.prompt
            )
            help_box = card.box()
            help_box.scale_y = 0.7
            help_box.label(text=prompt_preview, icon="TEXT")

            # Minimal separator between items
            if i < len(props.render_history) - 1:
                layout.separator()


# Update functions
def update_mist_settings(self, context):
    """Update world mist settings when UI values change"""
    try:
        import bpy

        if not context.scene.world:
            print("⚠️ [GEMINI] No world in scene for mist settings")
            return

        world = context.scene.world

        # Values are already in meters
        mist_start_m = self.mist_start
        mist_depth_m = self.mist_depth
        mist_falloff = self.mist_falloff if hasattr(self, "mist_falloff") else "LINEAR"

        # Use Blender 4.5+ API if available
        if hasattr(world, "mist_settings"):
            world.mist_settings.use_mist = True
            world.mist_settings.start = mist_start_m
            world.mist_settings.depth = mist_depth_m
            world.mist_settings.falloff = mist_falloff  # Use selected falloff
            print(
                f"✅ [GEMINI] Mist settings updated: start={mist_start_m}m, depth={mist_depth_m}m, falloff={mist_falloff}"
            )
        else:
            # Fallback for older Blender versions
            if hasattr(world, "use_mist"):
                world.use_mist = True
                world.mist_start = mist_start_m
                world.mist_depth = mist_depth_m
                world.mist_falloff = mist_falloff  # Use selected falloff
                print(
                    f"✅ [GEMINI] Legacy mist settings updated: start={mist_start_m}m, depth={mist_depth_m}m, falloff={mist_falloff}"
                )

    except Exception as e:
        print(f"⚠️ [GEMINI] Failed to update mist settings: {e}")


def toggle_mist_preview(self, context):
    """Toggle mist preview in 3D viewport"""
    try:
        import bpy

        print(f"🌫️ [GEMINI] Toggling mist preview: {self.mist_preview}")

        # Update world mist settings first
        update_mist_settings(self, context)

        # Find 3D viewport and set shading
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        if self.mist_preview:
                            # Enable mist preview
                            space.shading.type = "MATERIAL"
                            if hasattr(space.shading, "render_pass"):
                                space.shading.render_pass = "MIST"
                            print("✅ [GEMINI] Mist preview enabled in viewport")
                        else:
                            # Disable mist preview - return to normal shading
                            if hasattr(space.shading, "render_pass"):
                                space.shading.render_pass = "COMBINED"
                            space.shading.type = "MATERIAL"  # Keep material preview
                            print("✅ [GEMINI] Mist preview disabled in viewport")

                        # Force redraw
                        area.tag_redraw()
                        return

        print("⚠️ [GEMINI] No 3D viewport found for mist preview")

    except Exception as e:
        print(f"⚠️ [GEMINI] Failed to toggle mist preview: {e}")


def on_render_mode_change(self, context):
    """Handle render mode change - disable mist preview for Regular Render"""
    try:
        import bpy

        # If switching to Regular Render and mist preview is enabled, disable it
        if self.render_mode == "EEVEE" and self.mist_preview:
            print("[GEMINI] Switching to Regular Render - disabling mist preview")
            self.mist_preview = False  # This will trigger toggle_mist_preview

    except Exception as e:
        print(f"[GEMINI] Error in render mode change: {e}")


def sync_api_key(self, context):
    """Sync API key to JSON config file (user-only edit)"""
    try:
        import bpy
        from . import providers

        # Skip during provider preset loading to avoid accidental saves
        if hasattr(self, "_loading_provider_config") and self._loading_provider_config:
            return

        print(f"[UI] Syncing API key for {self.provider_type}...")

        # Save only API key; do not modify URL/Model here
        manager = providers.get_provider_manager()
        manager.update_provider(
            provider_type=self.provider_type,
            api_key=self.api_key,
            base_url=None,
            model=None,
        )
        print(f"[UI] Saved API key for {self.provider_type} to JSON")

        # Also sync to addon preferences (legacy support)
        package_name = __package__ if __package__ else "nano_banana_render"
        addon_prefs = context.preferences.addons.get(package_name)

        if addon_prefs and hasattr(addon_prefs.preferences, "api_key"):
            # Sync scene -> preferences
            if self.api_key and self.api_key != addon_prefs.preferences.api_key:
                addon_prefs.preferences.api_key = self.api_key

    except Exception as e:
        print(f"[UI] Failed to sync config: {e}")


def sync_provider_base_url(self, context):
    """Sync provider Base URL to JSON - called when Base URL is manually changed"""
    try:
        from . import providers

        # Skip if we're in the middle of loading (to avoid saving wrong values during provider switch)
        if hasattr(self, "_loading_provider_config") and self._loading_provider_config:
            return

        print(f"[UI] User edited Base URL for {self.provider_type}...")
        print(f"     Base URL: {self.provider_base_url}")

        # Save only Base URL
        manager = providers.get_provider_manager()
        manager.update_provider(
            provider_type=self.provider_type,
            api_key=self.api_key,
            base_url=self.provider_base_url,
            model=None,
        )
        print(f"[UI] Base URL saved to JSON")

    except Exception as e:
        print(f"[UI] Failed to sync Base URL: {e}")


def sync_provider_model_id(self, context):
    """Sync provider Model ID to JSON - called when Model ID is manually changed"""
    try:
        from . import providers

        # Skip if we're in the middle of loading (to avoid saving wrong values during provider switch)
        if hasattr(self, "_loading_provider_config") and self._loading_provider_config:
            return

        print(f"[UI] User edited Model ID for {self.provider_type}...")
        print(f"     Model ID: {self.provider_model_id}")

        # Save only Model ID
        manager = providers.get_provider_manager()
        manager.update_provider(
            provider_type=self.provider_type,
            api_key=self.api_key,
            base_url=None,
            model=self.provider_model_id,
        )
        print(f"[UI] Model ID saved to JSON")

    except Exception as e:
        print(f"[UI] Failed to sync Model ID: {e}")
