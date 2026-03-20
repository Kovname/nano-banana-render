bl_info = {
    "name": "Nanode AI Render Engine",
    "blender": (4, 5, 0),  # Minimum version, supports up to 5.0+
    "category": "Render", 
    "version": (2, 5, 0),
    "author": "Kovname",
    "description": "Professional AI rendering and editing suite for Blender — v2.5.0",
    "location": "Render Properties (select 'Nano Banana' engine), Image Editor > N Panel > Nano Banana Pro Edit",
    "doc_url": "https://nanode.tech/",
    "tracker_url": "https://nanode.tech/",
}

# Blender version compatibility helpers
def get_blender_version():
    """Get Blender version as tuple (major, minor, patch)"""
    import bpy
    return bpy.app.version

def is_blender_5():
    """Check if running on Blender 5.0+"""
    import bpy
    return bpy.app.version >= (5, 0, 0)

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty

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
    if "threading_utils" in locals():
        importlib.reload(threading_utils)
    if "image_editor" in locals():
        importlib.reload(image_editor)
    if "image_edit_thread" in locals():
        importlib.reload(image_edit_thread)
    if "render_engine" in locals():
        importlib.reload(render_engine)
    if "beta_api" in locals():
        importlib.reload(beta_api)

# Import our modules
from . import ui_panel
from . import operators
from . import depth_utils
from . import gemini_api
from . import threading_utils
from . import image_editor
from . import image_edit_thread
from . import render_engine
from . import beta_api

class NanoBananaPreferences(AddonPreferences):
    bl_idname = __name__

    beta_token: StringProperty(
        name="API Key",
        description="Your API key (from Google login) or beta access token",
        default="",
        subtype='PASSWORD',
    )

    # Account info display — show email on logged-in state
    def draw(self, context):
        layout = self.layout
        from . import operators as ops
        
        # Main access section
        box = layout.box()
        box.label(text="Account:", icon='USER')
        
        if self.beta_token.strip():
            email = ops._get_user_email()
            name = ops._get_user_name()
            
            if email:
                # Show logged-in state with email (no checkmarks)
                box.label(text=email, icon='LINKED')
                if name:
                    row = box.row()
                    row.scale_y = 0.7
                    row.label(text=f"     {name}")
            else:
                # Token is set but no email (beta user or manual key)
                if self.beta_token.strip().startswith("nk_"):
                    box.label(text="Nanode Account", icon='LINKED')
                elif self.beta_token.strip().startswith("AIza"):
                    box.label(text="API", icon='LINKED')
                else:
                    box.label(text="Beta Tester", icon='LINKED')
            
            # Refresh + logout
            row = box.row(align=True)
            if not self.beta_token.strip().startswith("AIza"):
                row.operator("banana.refresh_balance", text="Refresh Balance", icon='FILE_REFRESH')
            row.operator("banana.logout", text="Log Out", icon='PANEL_CLOSE')
            
            # Buy Credits for credit users
            if self.beta_token.strip().startswith("nk_"):
                row = box.row()
                row.scale_y = 1.2
                row.operator("banana.open_store", text="Buy More Credits", icon='PLUS')
            
            # Advanced: show API key field
            col = box.column()
            col.scale_y = 0.8
            col.prop(self, "beta_token")
        else:
            # No key — show login button prominently
            col = box.column(align=True)
            col.scale_y = 1.5
            col.operator("banana.google_login", text="Login with Google", icon='URL')
            
            box.separator()
            box.label(text="Or paste API key manually:", icon='INFO')
            box.prop(self, "beta_token")
        
        # Debug section
        box = layout.box()
        box.label(text="Debug Tools:", icon='TOOL_SETTINGS')
        
        row = box.row(align=True)
        try:
            if hasattr(bpy.types, 'GEMINI_OT_reset_state'):
                row.operator("gemini.reset_state", text="Reset UI State", icon='FILE_REFRESH')
            if hasattr(bpy.types, 'GEMINI_OT_open_console'):  
                row.operator("gemini.open_console", text="Open Console", icon='CONSOLE')
        except:
            row.label(text="Debug operators not available", icon='INFO')

# Registration - Core classes first
core_classes = (
    NanoBananaPreferences,
    ui_panel.GeminiRenderHistoryItem,
    ui_panel.GeminiRenderProperties,
    ui_panel.BANANA_PT_render_panel,
    ui_panel.BANANA_PT_prompt,
    ui_panel.BANANA_PT_render_mode,
    ui_panel.BANANA_PT_mist,
    ui_panel.BANANA_PT_style_reference,
    ui_panel.BANANA_PT_history_panel,
    ui_panel.BANANA_PT_beta_npanel,
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
    operators.GEMINI_OT_open_preferences,
    operators.BANANA_OT_send_feedback,
    operators.BANANA_OT_rate_generation,
    operators.BANANA_OT_refresh_balance,
    operators.BANANA_OT_toggle_feedback,
    operators.BANANA_OT_google_login,
    operators.BANANA_OT_logout,
    operators.BANANA_OT_open_store,
    operators.BANANA_OT_show_no_credits_popup,
)

# Optional debug classes (register separately to avoid conflicts)
debug_classes = (
    operators.GEMINI_OT_reset_state,
    operators.GEMINI_OT_open_console,
)

# All classes combined
classes = core_classes + debug_classes

def register():
    # Register render engine first
    try:
        render_engine.register()
        print("[NANO BANANA] Render engine registered")
    except Exception as e:
        print(f"Error registering render engine: {e}")
    
    # Register core classes
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
        print("[NANO BANANA] Image Editor panel registered")
    except Exception as e:
        print(f"Warning: Could not register Image Editor: {e}")
    
    # Add properties to scene
    bpy.types.Scene.gemini_render = bpy.props.PointerProperty(type=ui_panel.GeminiRenderProperties)
    
    # Add properties to window manager for context menus
    bpy.types.WindowManager.history_menu_index = bpy.props.IntProperty(
        name="History Menu Index",
        description="Index for history context menu",
        default=0
    )
    
    # Restore saved credentials on startup
    try:
        operators.restore_credentials_on_startup()
    except Exception as e:
        print(f"[NANO BANANA] Could not restore credentials: {e}")

def unregister():
    # Unregister render engine
    try:
        render_engine.unregister()
    except:
        pass
    
    # Stop any background threads
    try:
        threading_utils.stop_thread_manager()
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
    if hasattr(bpy.types.Scene, 'gemini_render'):
        del bpy.types.Scene.gemini_render
    
    # Remove properties from window manager
    if hasattr(bpy.types.WindowManager, 'history_menu_index'):
        del bpy.types.WindowManager.history_menu_index

if __name__ == "__main__":
    register()
