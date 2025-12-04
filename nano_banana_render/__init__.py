bl_info = {
    "name": "Nano Banana Pro Render Fork",
    "blender": (4, 5, 0),
    "category": "Render",
    "version": (2, 1, 10),
    "author": "Kovname",
    "LiuYang"
    "description": "Professional AI rendering and editing suite for Blender. Transform depth maps and edit renders with AI. Supports mask-based editing, style transfer, and iterative refinement.",
    "location": "3D Viewport > N Panel > Nano Banana Pro, Image Editor > N Panel > Nano Banana Pro Edit",
    "doc_url": "https://github.com/kovname/nano-banana-render",
    "tracker_url": "https://github.com/kovname/nano-banana-render/issues",
}

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty
from bpy.app.handlers import persistent

# Flag to track if provider has been initialized for current session
_provider_initialized = False

# Reload modules for development
if "bpy" in locals():
    import importlib

    if "ui_panel" in locals():
        importlib.reload(ui_panel)
    if "operators" in locals():
        importlib.reload(operators)
    if "depth_utils" in locals():
        importlib.reload(depth_utils)
    if "gemini_api" in locals():
        importlib.reload(gemini_api)
    if "providers" in locals():
        importlib.reload(providers)
    if "threading_utils" in locals():
        importlib.reload(threading_utils)
    if "image_editor" in locals():
        importlib.reload(image_editor)
    if "image_edit_thread" in locals():
        importlib.reload(image_edit_thread)
    if "prompt_presets" in locals():
        importlib.reload(prompt_presets)

# Import our modules
from . import ui_panel
from . import operators
from . import depth_utils
from . import gemini_api
from . import providers
from . import threading_utils
from . import image_editor
from . import image_edit_thread
from . import prompt_presets


def init_provider_from_settings():
    """Initialize provider from saved settings.json"""
    global _provider_initialized

    if _provider_initialized:
        return True

    try:
        scene = bpy.context.scene
        if not scene or not hasattr(scene, "gemini_render"):
            return False

        props = scene.gemini_render
        manager = providers.get_provider_manager()
        selected = manager.load_selected_provider()

        print(f"[INIT] Loaded selected provider from settings: {selected}")

        valid = selected in ("google", "yunwu", "openrouter", "gptgod")
        if valid and props.provider_type != selected:
            # Set provider_type which will trigger on_provider_change callback
            props.provider_type = selected
            print(f"[INIT] Provider set to: {selected}")
        elif valid:
            # Provider already matches, just load config
            ui_panel.on_provider_change(props, bpy.context)
            print(f"[INIT] Provider config loaded for: {selected}")
        else:
            # No valid saved selection, ensure defaults for current provider
            ui_panel.on_provider_change(props, bpy.context)
            print(f"[INIT] Using default provider: {props.provider_type}")

        _provider_initialized = True
        return True

    except Exception as e:
        print(f"[INIT] Provider init failed: {e}")
        import traceback

        traceback.print_exc()
        return False


@persistent
def load_post_handler(dummy):
    """Handler called after a .blend file is loaded or on Blender startup."""
    global _provider_initialized
    _provider_initialized = False  # Reset flag for new file

    # Delay initialization slightly to ensure scene is fully ready
    bpy.app.timers.register(init_provider_from_settings, first_interval=0.1)


@persistent
def depsgraph_update_handler(scene, depsgraph):
    """Fallback handler to initialize provider if load_post didn't work."""
    global _provider_initialized

    if not _provider_initialized:
        init_provider_from_settings()


class NanoBananaPreferences(AddonPreferences):
    bl_idname = __name__

    api_key: StringProperty(
        name="API Key",
        description="AI API Key for generating stunning renders",
        default="",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout

        # API Key section
        box = layout.box()
        box.label(text="API Configuration:", icon="KEYFRAME_HLT")
        box.prop(self, "api_key")

        # Debug section
        box = layout.box()
        box.label(text="Debug Tools:", icon="TOOL_SETTINGS")

        row = box.row(align=True)
        # Check if debug operators are available
        try:
            if hasattr(bpy.types, "GEMINI_OT_reset_state"):
                row.operator(
                    "gemini.reset_state", text="Reset UI State", icon="FILE_REFRESH"
                )
            if hasattr(bpy.types, "GEMINI_OT_open_console"):
                row.operator("gemini.open_console", text="Open Console", icon="CONSOLE")
        except:
            row.label(text="Debug operators not available", icon="INFO")

        box.label(
            text="Note: Debug tools are also available in Blender's Console",
            icon="INFO",
        )


# Registration - Core classes first
core_classes = (
    NanoBananaPreferences,
    ui_panel.GeminiRenderHistoryItem,
    ui_panel.GeminiRenderProperties,
    ui_panel.BANANA_PT_render_panel,
    ui_panel.BANANA_PT_history_panel,
    operators.GEMINI_OT_ai_render,
    operators.GEMINI_OT_stop_render,
    operators.GEMINI_OT_load_history,
    operators.GEMINI_OT_delete_history,
    operators.GEMINI_OT_use_history_prompt,
    operators.GEMINI_OT_use_history_style,
    operators.GEMINI_OT_use_history_both,
    operators.GEMINI_OT_history_context_menu,
    operators.GEMINI_OT_open_history_image,
    operators.GEMINI_OT_load_image_as_reference,
    operators.GEMINI_OT_open_api_key_url,
    operators.GEMINI_OT_validate_api_key,
    operators.GEMINI_OT_test_provider_connection,
    # Prompt preset operators
    operators.GEMINI_OT_add_prompt_preset,
    operators.GEMINI_OT_save_prompt_preset,
    operators.GEMINI_OT_rename_prompt_preset,
    operators.GEMINI_OT_delete_prompt_preset,
)

# Optional debug classes (register separately to avoid conflicts)
debug_classes = (
    operators.GEMINI_OT_reset_state,
    operators.GEMINI_OT_open_console,
)

# All classes combined
classes = core_classes + debug_classes


def register():
    # Register core classes first
    for cls in core_classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Error registering core class {cls}: {e}")

    # Try to register debug classes (optional)
    for cls in debug_classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Warning: Could not register debug class {cls}: {e}")
            # Continue without debug classes if they fail

    # Register Image Editor module
    try:
        image_editor.register()
        print("✅ [NANO BANANA] Image Editor panel registered")
    except Exception as e:
        print(f"Warning: Could not register Image Editor: {e}")

    # Add properties to scene
    bpy.types.Scene.gemini_render = bpy.props.PointerProperty(
        type=ui_panel.GeminiRenderProperties
    )

    # Register app handlers for provider initialization
    # load_post: Called after a .blend file is loaded
    if load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_post_handler)

    # depsgraph_update_pre: Fallback to catch first scene update
    if depsgraph_update_handler not in bpy.app.handlers.depsgraph_update_pre:
        bpy.app.handlers.depsgraph_update_pre.append(depsgraph_update_handler)

    # Try immediate initialization (works when re-enabling addon in same session)
    global _provider_initialized
    _provider_initialized = False
    bpy.app.timers.register(init_provider_from_settings, first_interval=0.2)

    print("✅ [NANO BANANA] Provider initialization handlers registered")

    # Add properties to window manager for context menus
    bpy.types.WindowManager.history_menu_index = bpy.props.IntProperty(
        name="History Menu Index",
        description="Index for history context menu",
        default=0,
    )


def unregister():
    # Stop any background threads
    try:
        threading_utils.stop_thread_manager()
    except:
        pass

    # Remove app handlers
    try:
        if load_post_handler in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(load_post_handler)
        if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_pre:
            bpy.app.handlers.depsgraph_update_pre.remove(depsgraph_update_handler)
    except:
        pass

    # Unregister Image Editor module
    try:
        image_editor.unregister()
    except:
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Remove properties from scene
    if hasattr(bpy.types.Scene, "gemini_render"):
        del bpy.types.Scene.gemini_render

    # Remove properties from window manager
    if hasattr(bpy.types.WindowManager, "history_menu_index"):
        del bpy.types.WindowManager.history_menu_index


if __name__ == "__main__":
    register()
