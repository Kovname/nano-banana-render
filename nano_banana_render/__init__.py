bl_info = {
    "name": "Nanode AI Render Engine",
    "blender": (4, 5, 0),  # Minimum version, supports up to 5.0+
    "category": "Render", 
    "version": (2, 7, 0),
    "author": "Kovname",
    "description": "Generative Pipeline for Blender",
    "location": "Render Properties (select 'Nano Banana' engine), Image Editor > N Panel > Nanode AI Editor",
    "doc_url": "https://nanode.tech/",
    "tracker_url": "https://github.com/Kovname/nano-banana-render/issues",
}

# Build number — increment this for hotfix releases without changing bl_info["version"].
# The updater checks both version AND build number, so users get prompted even for same-version fixes.
BUILD_NUMBER = 1
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
from bpy.props import StringProperty, BoolProperty

# Reload modules for development
if "bpy" in locals():
    import importlib
    if "log" in locals():
        importlib.reload(log)
    if "credentials" in locals():
        importlib.reload(credentials)
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
    if "smart_points" in locals():
        importlib.reload(smart_points)
    if "image_edit_thread" in locals():
        importlib.reload(image_edit_thread)
    if "render_engine" in locals():
        importlib.reload(render_engine)
    if "beta_api" in locals():
        importlib.reload(beta_api)
    if "texture_pipeline" in locals():
        importlib.reload(texture_pipeline)
    if "texture_operators" in locals():
        importlib.reload(texture_operators)
    if "updater" in locals():
        importlib.reload(updater)
    if "history_previews" in locals():
        importlib.reload(history_previews)

# Import our modules
from . import log
from . import credentials
from . import ui_panel
from . import operators
from . import depth_utils
from . import gemini_api
from . import threading_utils
from . import image_editor
from . import smart_points
from . import image_edit_thread
from . import render_engine
from . import beta_api
from . import texture_pipeline
from . import texture_operators
from . import updater
from . import history_previews

def get_hwid_stable() -> str:
    """Generate a stable 16-char Hardware ID hash based on MAC address."""
    import uuid
    import hashlib
    mac = str(uuid.getnode()).encode('utf-8')
    return hashlib.sha256(mac).hexdigest()[:16]

class NanoBananaPreferences(AddonPreferences):
    bl_idname = __name__

    beta_token: StringProperty(
        name="API Key",
        description="Your API key (from Google login) or beta access token",
        default="",
        subtype='PASSWORD',
    )
    
    eu_format: BoolProperty(
        name="Allow sending generation data to improve Nanode",
        description="When enabled, your generation parameters are sent to our server for additional processing. Your personal API keys remain only on your device and are never transmitted.",
        default=True,
    )

    hwid: StringProperty(
        name="Hardware ID",
        default="",
        options={'HIDDEN'},
    )

    # Account info display — show email on logged-in state
    def draw(self, context):
        layout = self.layout
        from . import operators as ops
        
        # Main access section
        box = layout.box()
        box.label(text="Account:", icon='USER')
        
        if self.beta_token.strip():
            email = credentials.get_user_email()
            name = credentials.get_user_name()
            
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
        
        # Privacy / Data Collection
        box = layout.box()
        box.label(text="Privacy & Data Collection:", icon='LOCKED')
        box.prop(self, "eu_format")


# Registration - Core classes first
core_classes = (
    NanoBananaPreferences,
    ui_panel.GeminiRenderHistoryItem,
    ui_panel.GeminiRenderProperties,
    ui_panel.BananaPTRenderPanel,
    ui_panel.BananaPTPrompt,
    ui_panel.BananaPTRenderMode,
    ui_panel.BananaPTMist,
    ui_panel.BananaPTStyleReference,
    ui_panel.BananaPTHistoryPanel,
    operators.GeminiOTAIRender,
    operators.GeminiOTStopRender,
    operators.GeminiOTLoadHistory,
    operators.GeminiOTDeleteHistory,
    operators.GeminiOTUseHistoryPrompt,
    operators.GeminiOTUseHistoryStyle,
    operators.GeminiOTUseHistoryBoth,
    operators.GeminiOTHistoryContextMenu,
    operators.GeminiOTOpenHistoryImage,
    operators.GeminiOTLoadImageAsReference,
    operators.GeminiOTOpenApiKeyUrl,
    operators.GeminiOTValidateApiKey,
    operators.GeminiOTOpenPreferences,
    operators.BananaOTSendFeedback,
    operators.BananaOTRateGeneration,
    operators.BananaOTRefreshBalance,
    operators.BananaOTToggleFeedback,
    operators.BananaOTGoogleLogin,
    operators.BananaOTLogout,
    operators.BananaOTOpenStore,
    operators.BananaOTShowNoCreditsPopup,
    ui_panel.BananaPTTexturingNpanel,
    texture_operators.BananaOTInitTexCameras,
    texture_operators.BananaOTUpdateTexCameras,
    texture_operators.BananaOTPreviewTexCamera,
    texture_operators.BananaOTTextureDraft,
    texture_operators.BananaOTTextureEnhance,
    texture_operators.BananaOTCleanupTex,
    texture_operators.BananaOTClearTexReference,
    texture_operators.BananaOTLoadTexReference,
    updater.NanodeOTInstallUpdate,
    updater.NanodeOTUpdateDialog,
)

# All core classes combined
classes = core_classes

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
    
    # Init history previews gallery
    history_previews.init_previews()
    
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
        credentials.restore_credentials_on_startup()
    except Exception as e:
        print(f"[NANO BANANA] Could not restore credentials: {e}")

    # Auto-Updater
    bpy.types.WindowManager.nanode_update_version = StringProperty(default="")
    import threading
    t = threading.Thread(target=updater.check_updates_in_background, args=(bl_info["version"], BUILD_NUMBER), daemon=True)
    t.start()
    if not bpy.app.timers.is_registered(updater.update_poll_timer):
        bpy.app.timers.register(updater.update_poll_timer, first_interval=3.0)

def unregister():
    # Clear history previews gallery
    history_previews.clear_previews()

    # Unregister render engine
    try:
        render_engine.unregister()
    except Exception:
        pass
    
    # Stop any background threads
    try:
        threading_utils.stop_thread_manager()
    except Exception:
        pass
        
    if bpy.app.timers.is_registered(updater.update_poll_timer):
        bpy.app.timers.unregister(updater.update_poll_timer)
    
    # Unregister Image Editor module
    try:
        image_editor.unregister()
    except Exception:
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
