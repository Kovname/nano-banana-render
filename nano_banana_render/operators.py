import bpy
from typing import Optional
from bpy.types import Operator
from bpy.props import IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
import os
import tempfile
import logging
from . import gemini_api
from . import depth_utils
from . import threading_utils
from .credentials import (
    save_credentials_file,
    load_credentials_file,
    delete_credentials_file,
    get_user_email,
    get_user_name,
    restore_credentials_on_startup,
)

logger = logging.getLogger("nano_banana")

MSG_INVALID_HISTORY = "Invalid history index"

class GeminiOTAIRender(Operator):
    """AI Render operator - main functionality"""
    bl_idname = "gemini.ai_render"
    bl_label = "AI Render"
    bl_description = "Render depth map and send to Gemini AI for photorealistic conversion"
    bl_options = {'REGISTER'}
    
    current_thread = None
    
    def execute(self, context):
        """Execute AI render operation."""
        scene = context.scene
        props = scene.gemini_render
        
        try:
            # Reset status if stuck
            if props.is_rendering:
                props.is_rendering = False
            
            # Validate inputs
            error = self._validate_inputs(context, props)
            if error:
                self.report({'ERROR'}, error)
                props.status_text = f"Error: {error}"
                return {'CANCELLED'}
            
            # Stop any existing background thread
            if self.current_thread and self.current_thread.is_alive():
                self.current_thread.stop()
                self.current_thread.join(timeout=2.0)
            
            # Validate beta token
            prefs = context.preferences.addons.get("nano_banana_render")
            has_token = prefs and hasattr(prefs.preferences, 'beta_token') and prefs.preferences.beta_token.strip()
            if not has_token:
                error_msg = "No beta token. Go to Edit → Preferences → Add-ons → Nano Banana"
                self.report({'ERROR'}, error_msg)
                props.status_text = "No beta token"
                return {'CANCELLED'}
            
            # Update UI state and trigger render via the render engine
            props.is_rendering = True
            props.status_text = "Starting AI render..."
            
            # The actual rendering happens in NanoBananaRenderEngine.render()
            # which uses beta_api to communicate with the server
            bpy.ops.render.render('INVOKE_DEFAULT')
            
            self.report({'INFO'}, "AI render started")
            return {'FINISHED'}
            
        except Exception as e:
            error_msg = f"Failed to start AI render: {str(e)}"
            self.report({'ERROR'}, error_msg)
            props.is_rendering = False
            props.status_text = f"Error: {str(e)}"
            return {'CANCELLED'}
    
    def _validate_inputs(self, context, props) -> Optional[str]:
        """Validate inputs and return error message if invalid"""
        # Check prompt
        if not props.prompt.strip():
            return "Prompt cannot be empty"
        
        if len(props.prompt.strip()) < 10:
            return "Prompt too short (minimum 10 characters)"
        
        # Check scene
        scene = context.scene
        if not scene.camera:
            return "No active camera found. Add a camera to the scene."
        
        # Check visible objects
        visible_objects = [obj for obj in scene.objects if obj.visible_get() and obj.type == 'MESH']
        if len(visible_objects) == 0:
            return "No visible mesh objects found. Add some objects to the scene."
        
        # Note: clip values validation removed since normalize_depth was removed
        
        return None  # No errors

class GeminiOTStopRender(Operator):
    """Stop current AI render operation"""
    bl_idname = "gemini.stop_render"
    bl_label = "Stop Render"
    bl_description = "Stop the current AI render operation"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Execute stop render operation."""
        try:
            props = context.scene.gemini_render
            
            # Stop background thread if running
            if hasattr(GeminiOTAIRender, 'current_thread') and GeminiOTAIRender.current_thread:
                if GeminiOTAIRender.current_thread.is_alive():
                    GeminiOTAIRender.current_thread.stop()
                    GeminiOTAIRender.current_thread.join(timeout=3.0)
            
            # Reset UI state
            props.is_rendering = False
            props.status_text = "Cancelled by user"
            
            self.report({'INFO'}, "AI render stopped")
            return {'FINISHED'}
            
        except Exception as e:
            try:
                props = context.scene.gemini_render
                props.is_rendering = False
                props.status_text = "Error stopping - reset manually"
            except Exception:
                pass
            self.report({'ERROR'}, f"Failed to stop render: {str(e)}")
            return {'CANCELLED'}

# Additional utility operators

class GeminiOTOpenApiKeyUrl(Operator):
    """Open Google AI Studio URL to get API key"""
    bl_idname = "gemini.open_api_key_url"
    bl_label = "Get API Key"
    bl_description = "Open Google AI Studio to get your Gemini API key"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Open API key URL"""
        import webbrowser
        webbrowser.open("https://aistudio.google.com/app/apikey")
        self.report({'INFO'}, "Opened Google AI Studio in browser")
        return {'FINISHED'}

class GeminiOTValidateApiKey(Operator):
    """Validate beta token"""
    bl_idname = "gemini.validate_api_key"
    bl_label = "Test Beta Token"
    bl_description = "Test if the beta token is configured"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Validate beta token"""
        try:
            prefs = context.preferences.addons.get("nano_banana_render")
            if not prefs or not hasattr(prefs.preferences, 'beta_token'):
                self.report({'ERROR'}, "Addon preferences not found")
                return {'CANCELLED'}
            
            token = prefs.preferences.beta_token.strip()
            if not token:
                self.report({'ERROR'}, "No beta token set. Enter it in addon preferences.")
                return {'CANCELLED'}
            
            # Try to get balance from server as a connectivity test
            from . import beta_api
            balance = beta_api.get_balance()
            if balance >= 0:
                self.report({'INFO'}, f"Token valid! Balance: {balance} generations")
            else:
                self.report({'WARNING'}, "Token set but server returned invalid response")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Connection error: {str(e)}")
            return {'CANCELLED'}


class GeminiOTOpenPreferences(Operator):
    """Open addon preferences to configure API key"""
    bl_idname = "gemini.open_preferences"
    bl_label = "Open Addon Preferences"
    bl_description = "Open addon preferences to configure API key"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        try:
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
            # Set the addon filter to show our addon
            context.preferences.active_section = 'ADDONS'
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open preferences: {str(e)}")
            return {'CANCELLED'}

class GeminiOTResetState(Operator):
    """Reset UI state in case of stuck rendering"""
    bl_idname = "gemini.reset_state"
    bl_label = "Reset UI State"
    bl_description = "Force reset render state (use if UI is stuck)"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Reset UI state"""
        try:
            logger.info("Force resetting UI state...")
            props = context.scene.gemini_render
            
            # Force reset all state
            props.is_rendering = False
            props.status_text = "🔄 UI state reset"
            
            # Try to stop any running background threads
            if hasattr(GeminiOTAIRender, 'current_thread') and GeminiOTAIRender.current_thread:
                try:
                    GeminiOTAIRender.current_thread.stop()
                    GeminiOTAIRender.current_thread = None
                except Exception:
                    pass
            
            # Redraw UI
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            self.report({'INFO'}, "UI state reset")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to reset state: {str(e)}")
            return {'CANCELLED'}

class GeminiOTOpenConsole(Operator):
    """Open Blender console to view logs"""
    bl_idname = "gemini.open_console"
    bl_label = "Open Console"
    bl_description = "Open Blender console to view detailed logs"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Open console."""
        try:
            bpy.ops.wm.console_toggle()
            self.report({'INFO'}, "Console toggled")
            return {'FINISHED'}
        except Exception:
            self.report({'WARNING'}, "Console toggle not available on this platform")
            return {'CANCELLED'}


class GeminiOTLoadHistory(Operator):
    """Load render result from history"""
    bl_idname = "gemini.load_history"
    bl_label = "Load History Render"
    bl_description = "Load this render result from history"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item to load",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            print(f"[GEMINI] Loading history item #{self.history_index}: {history_item.image_name}")
            
            # Try to find the AI_Result image
            image = None
            if history_item.image_name and history_item.image_name in bpy.data.images:
                try:
                    candidate = bpy.data.images[history_item.image_name]
                    if candidate.has_data:
                        image = candidate
                        print(f"[GEMINI] Found image: {image.name}")
                    else:
                        # Image exists but has no data — try to reload it
                        print(f"[GEMINI] Image has no data, attempting reload: {history_item.image_name}")
                        
                        # Method 1: If packed, unpack and repack to force data reload
                        if candidate.packed_file:
                            try:
                                import tempfile
                                import os
                                reload_dir = os.path.join(tempfile.gettempdir(), "nano_banana_reload")
                                os.makedirs(reload_dir, exist_ok=True)
                                reload_path = os.path.join(reload_dir, f"{history_item.image_name}.png")
                                candidate.unpack(method='WRITE_LOCAL')
                                candidate.filepath = reload_path
                                candidate.reload()
                                if candidate.has_data:
                                    candidate.pack()
                                    image = candidate
                                    print(f"[GEMINI] Reloaded from packed data: {image.name}")
                            except Exception as e:
                                print(f"[GEMINI] Packed reload failed: {e}")
                        
                        # Method 2: Try loading from permanent history folder
                        if not image:
                            import tempfile
                            import os
                            perm_path = os.path.join(tempfile.gettempdir(), "nano_banana_history", f"{history_item.image_name}.png")
                            if os.path.exists(perm_path):
                                try:
                                    bpy.data.images.remove(candidate)
                                    image = bpy.data.images.load(perm_path)
                                    image.name = history_item.image_name
                                    image.pack()
                                    image.use_fake_user = True
                                    print(f"[GEMINI] Reloaded from permanent file: {perm_path}")
                                except Exception as e:
                                    print(f"[GEMINI] Permanent file reload failed: {e}")
                            else:
                                print(f"[GEMINI] No permanent file at: {perm_path}")
                except Exception as e:
                    print(f"[GEMINI] Error accessing image: {e}")
            else:
                print(f"[GEMINI] Image not found in bpy.data.images: {history_item.image_name}")
            
            if image:
                from .threading_utils import execute_in_main_thread
                
                def _load_from_history():
                    try:
                        try:
                            bpy.ops.wm.window_new()
                            new_window = bpy.context.window_manager.windows[-1]
                            for area in new_window.screen.areas:
                                if area.type != 'IMAGE_EDITOR':
                                    area.type = 'IMAGE_EDITOR'
                                    for space in area.spaces:
                                        if space.type == 'IMAGE_EDITOR':
                                            space.image = image
                                            area.tag_redraw()
                                            return
                                    break
                        except Exception:
                            for area in context.screen.areas:
                                if area.type == 'IMAGE_EDITOR':
                                    for space in area.spaces:
                                        if space.type == 'IMAGE_EDITOR':
                                            space.image = image
                                            area.tag_redraw()
                                            return
                    except Exception:
                        pass
                
                execute_in_main_thread(_load_from_history)
                self.report({'INFO'}, f"Opened: {image.name}")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "History image not found")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load history: {str(e)}")
            return {'CANCELLED'}


class GeminiOTDeleteHistory(Operator):
    """Delete render from history"""
    bl_idname = "gemini.delete_history"
    bl_label = "Delete History Render"
    bl_description = "Delete this render from history"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item to delete",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            
            # Remove images from Blender
            if history_item.image_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[history_item.image_name])
            
            if history_item.style_reference_thumbnail and history_item.style_reference_thumbnail in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[history_item.style_reference_thumbnail])
            
            # Remove from history
            props.render_history.remove(self.history_index)
            
            self.report({'INFO'}, f"Deleted: {history_item.prompt[:30]}...")
            print(f"🗑️ [GEMINI] History item deleted: {history_item.prompt[:50]}...")
            return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to delete history: {str(e)}")
            return {'CANCELLED'}


class GeminiOTUseHistoryPrompt(Operator):
    """Use prompt from render history"""
    bl_idname = "gemini.use_history_prompt"
    bl_label = "Use History Prompt"
    bl_description = "Copy prompt from this history item to current prompt field"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item to use prompt from",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            
            # Copy prompt to current prompt field
            props.prompt = history_item.prompt
            
            self.report({'INFO'}, f"Prompt copied: {history_item.prompt[:50]}...")
            print(f"📝 [GEMINI] Prompt copied from history: {history_item.prompt[:50]}...")
            return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to use history prompt: {str(e)}")
            return {'CANCELLED'}


class GeminiOTUseHistoryStyle(Operator):
    """Use style reference from render history"""
    bl_idname = "gemini.use_history_style"
    bl_label = "Use History Style"
    bl_description = "Copy style reference from this history item to current style reference"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index", 
        description="Index of history item to use style from",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            
            if not history_item.style_reference_used:
                self.report({'WARNING'}, "This render didn't use a style reference")
                return {'CANCELLED'}
            
            # Find the original style reference image
            style_image = None
            if history_item.style_reference_name in bpy.data.images:
                style_image = bpy.data.images[history_item.style_reference_name]
            elif history_item.style_reference_thumbnail in bpy.data.images:
                # Fallback to thumbnail if original is missing
                style_image = bpy.data.images[history_item.style_reference_thumbnail]
            
            if not style_image:
                self.report({'ERROR'}, "Style reference image not found")
                return {'CANCELLED'}
            
            # Set as current style reference
            props.style_reference_image = style_image
            props.use_style_reference = True
            
            self.report({'INFO'}, f"Style reference set: {style_image.name}")
            return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to use history style: {str(e)}")
            return {'CANCELLED'}


class GeminiOTHistoryContextMenu(Operator):
    """Show context menu for render history item"""
    bl_idname = "gemini.history_context_menu"
    bl_label = "History Context Menu"
    bl_description = "Show options for this render history item"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item",
        default=0
    )

    def execute(self, context):
        # Show the compact context menu
        def draw_menu(menu_self, menu_context):
            layout = menu_self.layout
            props = menu_context.scene.gemini_render
            history_idx = menu_context.window_manager.history_menu_index
            
            if history_idx >= len(props.render_history):
                layout.label(text="Invalid history item")
                return
            
            item = props.render_history[history_idx]
            
            # Compact menu - just the essential actions
            
            # Copy settings
            prompt_op = layout.operator("gemini.use_history_prompt", text="Use Prompt", icon='TEXT')
            prompt_op.history_index = history_idx
            
            # Use style only (if available)
            if item.style_reference_used:
                style_op = layout.operator("gemini.use_history_style", text="Use Style", icon='IMAGE_DATA')  
                style_op.history_index = history_idx
                
                # Use both
                both_op = layout.operator("gemini.use_history_both", text="Use Both", icon='GHOST_ENABLED')
                both_op.history_index = history_idx
            else:
                layout.label(text="No style used", icon='INFO')
            
            # Delete action
            layout.separator()
            delete_op = layout.operator("gemini.delete_history", text="Delete", icon='X')
            delete_op.history_index = history_idx

        # Store history index in context for menu
        context.window_manager.history_menu_index = self.history_index
        context.window_manager.popup_menu(draw_menu, title="History Options", icon='RENDER_RESULT')
        
        return {'FINISHED'}


class GeminiOTUseHistoryBoth(Operator):
    """Use both prompt and style from render history"""
    bl_idname = "gemini.use_history_both"
    bl_label = "Use History Prompt + Style"
    bl_description = "Copy both prompt and style reference from this history item"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item to use",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            
            # Copy prompt
            props.prompt = history_item.prompt
            
            # Copy style reference if available
            if history_item.style_reference_used:
                style_image = None
                if history_item.style_reference_name in bpy.data.images:
                    style_image = bpy.data.images[history_item.style_reference_name]
                elif history_item.style_reference_thumbnail in bpy.data.images:
                    style_image = bpy.data.images[history_item.style_reference_thumbnail]
                
                if style_image:
                    props.style_reference_image = style_image
                    props.use_style_reference = True
                    self.report({'INFO'}, f"Both copied: prompt + style ({style_image.name})")
                else:
                    props.use_style_reference = False
                    self.report({'WARNING'}, "Style missing, copied prompt only")
            else:
                props.use_style_reference = False
                self.report({'INFO'}, "Prompt copied (no style was used)")
            
            return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to use history: {str(e)}")
            return {'CANCELLED'}


class GeminiOTOpenHistoryImage(Operator):
    """Open history image in full size"""
    bl_idname = "gemini.open_history_image"
    bl_label = "Open History Image"
    bl_description = "Open history image in full size view"
    bl_options = {'REGISTER'}

    history_index: IntProperty(
        name="History Index",
        description="Index of history item to open image from",
        default=0
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            if self.history_index < 0 or self.history_index >= len(props.render_history):
                self.report({'ERROR'}, MSG_INVALID_HISTORY)
                return {'CANCELLED'}
            
            history_item = props.render_history[self.history_index]
            
            # Get the main AI_Result image
            image_to_open = None
            if history_item.image_name and history_item.image_name in bpy.data.images:
                try:
                    candidate = bpy.data.images[history_item.image_name]
                    if candidate.has_data:
                        image_to_open = candidate
                except Exception:
                    pass
            
            if not image_to_open:
                self.report({'ERROR'}, "AI Result image not found")
                return {'CANCELLED'}
            print(f"🖼️ [GEMINI] Using original AI_Result image directly: {image_to_open.name}")
            duplicate_image = image_to_open
            
            # Try to open in new window or existing Image Editor
            try:
                bpy.ops.wm.window_new()
                new_window = bpy.context.window_manager.windows[-1]
                
                for area in new_window.screen.areas:
                    if area.type != 'IMAGE_EDITOR':
                        area.type = 'IMAGE_EDITOR'
                        for space in area.spaces:
                            if space.type == 'IMAGE_EDITOR':
                                space.image = duplicate_image
                                area.tag_redraw()
                                self.report({'INFO'}, f"Opened: {duplicate_image.name}")
                                return {'FINISHED'}
                        break
                
            except Exception:
                # Fallback: Find existing Image Editor
                for area in bpy.context.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        for space in area.spaces:
                            if space.type == 'IMAGE_EDITOR':
                                space.image = duplicate_image
                                area.tag_redraw()
                                self.report({'INFO'}, f"Opened: {duplicate_image.name}")
                                return {'FINISHED'}
                
                # Last resort: Convert safe area to Image Editor
                SAFE_AREAS = ['TEXT_EDITOR', 'CONSOLE', 'INFO', 'FILE_BROWSER']
                for area in bpy.context.screen.areas:
                    if area.type in SAFE_AREAS:
                        area.type = 'IMAGE_EDITOR'
                        for space in area.spaces:
                            if space.type == 'IMAGE_EDITOR':
                                space.image = duplicate_image
                                area.tag_redraw()
                                self.report({'INFO'}, f"Opened: {duplicate_image.name}")
                                return {'FINISHED'}
                
                self.report({'WARNING'}, "Could not find suitable area to display image")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open image: {str(e)}")
            return {'CANCELLED'}


class GeminiOTLoadImageAsReference(Operator, ImportHelper):
    """Load image file as style reference"""
    bl_idname = "gemini.load_image_as_reference"
    bl_label = "Load Image as Reference"
    bl_description = "Load an image file to use as style reference"
    bl_options = {'REGISTER'}

    # File browser properties
    filename_ext = ""
    filter_glob: StringProperty(
        default="*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.tga;*.exr;*.hdr",
        options={'HIDDEN'}
    )
    
    filepath: StringProperty(
        name="File Path",
        description="Filepath used for importing the image file",
        maxlen=1024,
        subtype='FILE_PATH'
    )

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            # Check if filepath was provided
            if not self.filepath:
                self.report({'WARNING'}, "No file selected")
                return {'CANCELLED'}
            
            # Load the image into Blender
            try:
                # Load the image
                image = bpy.data.images.load(self.filepath, check_existing=False)
                image_name = os.path.basename(self.filepath)
                
                # Set a nice name
                if image_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.tga', '.exr', '.hdr')):
                    base_name = os.path.splitext(image_name)[0]
                image.name = f"Reference_{base_name}"
                
            except Exception as e:
                self.report({'ERROR'}, f"Failed to load image: {str(e)}")
                return {'CANCELLED'}
            
            # Automatically set as reference
            props.style_reference_image = image
            
            if not props.use_style_reference:
                props.use_style_reference = True
                
            self.report({'INFO'}, f"Reference image loaded: {image.name}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load reference image: {str(e)}")
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        # Set default path to user's Pictures folder or Documents
        import os
        try:
            if os.name == 'nt':  # Windows
                pictures_folder = os.path.join(os.path.expanduser('~'), 'Pictures')
                if os.path.exists(pictures_folder):
                    self.filepath = pictures_folder
                else:
                    self.filepath = os.path.expanduser('~')
            else:  # Linux/Mac
                self.filepath = os.path.expanduser('~')
        except Exception:
            pass
            
        # Open the file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}





# ─── Beta Operators ───────────────────────────────────────────

class BananaOTSendFeedback(Operator):
    """Submit feedback and earn bonus generations"""
    bl_idname = "banana.send_feedback"
    bl_label = "Submit Feedback"
    bl_description = "Send your feedback to the developers and earn +50 bonus generations"

    def execute(self, context):
        from . import beta_api

        props = context.scene.gemini_render
        text = props.feedback_text.strip()

        if len(text) < 5:
            self.report({'WARNING'}, "Feedback too short (min 5 characters)")
            return {'CANCELLED'}

        try:
            new_balance = beta_api.send_feedback(text)
            props.beta_balance = new_balance
            props.feedback_text = ""
            props.show_feedback = False
            props.has_submitted_feedback = True
            self.report({'INFO'}, f"Thanks! +50 generations awarded. Balance: {new_balance}")
        except beta_api.BetaAPIError as e:
            self.report({'ERROR'}, f"Failed to submit feedback: {e.message}")
        except Exception as e:
            self.report({'ERROR'}, f"Network error: {str(e)}")

        return {'FINISHED'}


class BananaOTRateGeneration(Operator):
    """Rate the last AI generation"""
    bl_idname = "banana.rate_generation"
    bl_label = "Rate Generation"
    bl_description = "Rate this generation result"

    rating: StringProperty(
        name="Rating",
        default="like"
    )

    def execute(self, context):
        from . import beta_api

        props = context.scene.gemini_render
        gen_id = props.last_generation_id

        if gen_id <= 0:
            return {'CANCELLED'}

        # Send rating silently in background
        import threading

        def _rate():
            beta_api.send_rating(gen_id, self.rating)

        threading.Thread(target=_rate, daemon=True).start()

        # Update UI immediately
        props.last_generation_rated = True
        emoji = "👍" if self.rating == "like" else "👎"
        self.report({'INFO'}, f"{emoji} Thanks for the feedback!")

        return {'FINISHED'}


class BananaOTRefreshBalance(Operator):
    """Refresh generations balance from server"""
    bl_idname = "banana.refresh_balance"
    bl_label = "Refresh Balance"
    bl_description = "Check remaining generations from the server"

    def execute(self, context):
        from . import beta_api

        try:
            info = beta_api.get_balance_info()
            balance = info.get("balance", -1)
            if balance >= 0:
                props = context.scene.gemini_render
                props.beta_balance = balance
                # Sync feedback bonus status from server
                if info.get("feedback_given", False):
                    props.has_submitted_feedback = True
                self.report({'INFO'}, f"Balance: {balance} generations left")
            else:
                self.report({'WARNING'}, "Could not fetch balance — check your token")
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")

        return {'FINISHED'}


class BananaOTToggleFeedback(Operator):
    """Toggle the feedback input panel"""
    bl_idname = "banana.toggle_feedback"
    bl_label = "Toggle Feedback"
    bl_description = "Show or hide the feedback form"

    def execute(self, context):
        props = context.scene.gemini_render
        props.show_feedback = not props.show_feedback
        return {'FINISHED'}


class BananaOTGoogleLogin(Operator):
    """Login with Google — opens browser, receives API key automatically"""
    bl_idname = "banana.google_login"
    bl_label = "Login with Google"
    bl_description = "Log in with your Google account. API key is saved automatically — no copy-paste needed!"

    _server = None
    _thread = None

    def execute(self, context):
        import webbrowser
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs
        import socket
        from . import beta_api

        
        # ─── Find a free port ─────────────────────────────────
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', 0))
        port = sock.getsockname()[1]
        sock.close()

        # ─── Callback handler ─────────────────────────────────
        class CallbackHandler(BaseHTTPRequestHandler):
            received_data = {}

            def do_GET(self_handler):
                parsed = urlparse(self_handler.path)
                if parsed.path == "/nanode_auth_callback":
                    params = parse_qs(parsed.query)
                    api_key = params.get("api_key", [""])[0]
                    email = params.get("email", [""])[0]
                    name = params.get("name", [""])[0]
                    balance = params.get("balance", ["0"])[0]

                    CallbackHandler.received_data = {
                        "api_key": api_key,
                        "email": email,
                        "name": name,
                        "balance": int(balance) if balance.isdigit() else 0,
                    }

                    # Show success page in browser
                    html = _login_success_html(name, email, balance)
                    self_handler.send_response(200)
                    self_handler.send_header("Content-Type", "text/html; charset=utf-8")
                    self_handler.end_headers()
                    self_handler.wfile.write(html.encode("utf-8"))

                    # Schedule saving to Blender prefs from main thread
                    from .threading_utils import execute_in_main_thread

                    def _save_credentials():
                        try:
                            prefs = bpy.context.preferences.addons.get("nano_banana_render")
                            if prefs and hasattr(prefs.preferences, "beta_token"):
                                prefs.preferences.beta_token = api_key
                                logger.info("API key saved automatically for %s", email)

                            # Save to persistent file
                            save_credentials_file(api_key, email, name)

                            # Update balance in scene props
                            try:
                                for scene in bpy.data.scenes:
                                    if hasattr(scene, "gemini_render"):
                                        scene.gemini_render.beta_balance = int(balance) if balance.isdigit() else 0
                            except Exception:
                                pass

                            # Redraw all UI
                            for window in bpy.context.window_manager.windows:
                                for area in window.screen.areas:
                                    area.tag_redraw()

                        except Exception as ex:
                            logger.error("Error saving credentials: %s", ex)

                    execute_in_main_thread(_save_credentials)

                    # Shut down server after a short delay
                    import threading as _th
                    _th.Timer(1.0, self_handler.server.shutdown).start()

                else:
                    self_handler.send_response(404)
                    self_handler.end_headers()

            def log_message(self_handler, format, *args):
                pass  # Silence HTTP logs

        # ─── Start local server in background ────────────────
        server = HTTPServer(('localhost', port), CallbackHandler)
        BananaOTGoogleLogin._server = server

        def _run_server():
            try:
                server.handle_request()  # Handle single request then stop
            except Exception:
                pass

        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()
        BananaOTGoogleLogin._thread = thread

        # ─── Open browser via api.nanode.tech ──────────────────
        login_url = f"https://api.nanode.tech/auth/google/login?callback_port={port}"
        webbrowser.open(login_url)

        self.report({'INFO'}, "Browser opened — log in with Google and you'll be connected automatically!")
        return {'FINISHED'}


class BananaOTLogout(Operator):
    """Log out of Nanode account"""
    bl_idname = "banana.logout"
    bl_label = "Log Out"
    bl_description = "Clear saved credentials and log out"

    def execute(self, context):
        prefs = context.preferences.addons.get("nano_banana_render")
        if prefs and hasattr(prefs.preferences, "beta_token"):
            prefs.preferences.beta_token = ""

        # Clear persistent file
        delete_credentials_file()

        # Reset balance
        try:
            context.scene.gemini_render.beta_balance = -1
        except Exception:
            pass

        self.report({'INFO'}, "Logged out successfully")
        return {'FINISHED'}



# ─── Backward compatibility aliases ──────────────────────────
# These re-export the credential functions so existing internal
# references (e.g. __init__.py calling operators.restore_credentials_on_startup)
# continue to work without changes.
_get_user_email = get_user_email
_get_user_name = get_user_name


def _login_success_html(name: str, email: str, balance: str) -> str:
    """HTML page shown in browser after successful auto-login."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nanode — Connected!</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: #000;
            color: #e5e5e5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 24px;
            overflow: hidden;
        }}
        body::before {{
            content: '';
            position: fixed;
            top: 50%; left: 50%;
            width: 600px; height: 600px;
            transform: translate(-50%, -50%);
            background: radial-gradient(circle, rgba(255,200,50,0.06) 0%, transparent 70%);
            pointer-events: none;
        }}
        .logo {{
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 40px;
            animation: fadeDown 0.5s ease-out;
        }}
        .logo svg {{ width: 32px; height: 32px; }}
        .logo span {{
            font-size: 1.25rem;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.02em;
        }}
        @keyframes fadeDown {{
            from {{ opacity: 0; transform: translateY(-12px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        .card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 48px 40px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            backdrop-filter: blur(20px);
            animation: fadeUp 0.6s ease-out;
        }}
        @keyframes fadeUp {{
            from {{ opacity: 0; transform: translateY(16px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        .icon {{
            width: 56px; height: 56px;
            margin: 0 auto 20px;
            background: rgba(255,200,50,0.1);
            border: 1px solid rgba(255,200,50,0.25);
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            animation: pop 0.7s ease-out;
        }}
        .icon svg {{ width: 28px; height: 28px; }}
        @keyframes pop {{
            0%   {{ transform: scale(0); }}
            70%  {{ transform: scale(1.15); }}
            100% {{ transform: scale(1); }}
        }}
        h1 {{
            font-size: 1.35rem;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.02em;
            margin-bottom: 6px;
        }}
        .subtitle {{
            font-size: 0.9rem;
            color: #888;
            margin-bottom: 28px;
        }}
        .details {{
            display: flex;
            gap: 12px;
            margin-bottom: 28px;
        }}
        .detail {{
            flex: 1;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 14px 12px;
            text-align: center;
        }}
        .detail .label {{
            font-size: 0.7rem;
            font-weight: 500;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }}
        .detail .value {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #fff;
            word-break: break-all;
        }}
        .detail .value.gold {{ color: #FFC832; }}
        .hint {{
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 20px;
        }}
        .btn {{
            display: inline-block;
            background: #fff;
            color: #000;
            padding: 12px 28px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.95rem;
            border: none;
            cursor: pointer;
            transition: transform 0.2s, background 0.2s;
        }}
        .btn:hover {{
            background: #f0f0f0;
            transform: scale(1.02);
        }}
        .btn:active {{ transform: scale(0.98); }}
    </style>
</head>
<body>
    <div class="logo">
        <svg viewBox="0 0 1920 1920" fill="none" xmlns="http://www.w3.org/2000/svg">
            <g clip-path="url(#clip0_1_8)">
                <path d="M0.00708008 960H576.003V1919.99H297.605C133.246 1919.99 0.00708008 1786.75 0.00708008 1622.39V960Z" fill="#FFFFFF"></path>
                <rect x="0.000244141" y="383.997" width="543.054" height="2172.24" transform="rotate(-45 0.000244141 383.997)" fill="#FFC107"></rect>
                <path d="M1344 0.00732422H1622.39C1786.75 0.00732422 1919.99 133.246 1919.99 297.605V960H1344V0.00732422Z" fill="#FFFFFF"></path>
            </g>
            <defs>
                <clipPath id="clip0_1_8"><rect width="1920" height="1920" fill="white"></rect></clipPath>
            </defs>
        </svg>
        <span>Nanode</span>
    </div>
    <div class="card">
        <div class="icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="#FFC832" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
        </div>
        <h1>Connected to Blender</h1>
        <p class="subtitle">Welcome, {name}! Your account is linked.</p>
        <div class="details">
            <div class="detail">
                <div class="label">Account</div>
                <div class="value">{email}</div>
            </div>
            <div class="detail">
                <div class="label">Credits</div>
                <div class="value gold">{balance}</div>
            </div>
        </div>
        <p class="hint">You can safely close this tab and return to Blender 🍌</p>
        <button class="btn" onclick="window.close()">Close Tab</button>
    </div>
    <script>
        // Try to auto-close after a short delay (works in some browsers if opened via API)
        setTimeout(() => {{ window.close(); }}, 3000);
    </script>
</body>
</html>"""


class BananaOTOpenStore(Operator):
    """Open the credits store in browser"""
    bl_idname = "banana.open_store"
    bl_label = "Buy Credits"
    bl_description = "Open the credits store to purchase more AI generation credits"

    def execute(self, context):
        import webbrowser
        webbrowser.open("https://nanode.tech/pricing")
        self.report({'INFO'}, "Store opened in browser")
        return {'FINISHED'}


class BananaOTShowNoCreditsPopup(Operator):
    """Show popup when user doesn't have enough credits"""
    bl_idname = "banana.show_no_credits_popup"
    bl_label = "Not Enough Credits"
    bl_description = "Not enough credits for this generation"

    credits_needed: IntProperty(name="Credits Needed", default=0)
    credits_available: IntProperty(name="Credits Available", default=0)

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.label(text="⚠️ Not enough credits!", icon='ERROR')
        layout.separator()
        layout.label(text=f"This render needs {self.credits_needed} credits")
        layout.label(text=f"You have {self.credits_available} credits")
        layout.separator()
        layout.operator("banana.open_store", text="🛒 Buy Credits", icon='URL')

