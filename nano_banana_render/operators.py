import bpy
from bpy.types import Operator
from bpy.props import IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
import os
import tempfile
from . import gemini_api
from . import depth_utils
from . import threading_utils

class GEMINI_OT_ai_render(Operator):
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
            
            # Get API key (from environment variable or addon preferences only - not scene for security)
            api_key = gemini_api.get_api_key()
            if not api_key:
                error_msg = "No API key found. Set GEMINI_API_KEY environment variable or configure in Addon Preferences."
                self.report({'ERROR'}, error_msg)
                props.status_text = "No API key"
                return {'CANCELLED'}
            
            # Initialize components
            depth_renderer = depth_utils.DepthRenderer()
            api_client = gemini_api.GeminiAPI(api_key)
            
            # Update UI state and start thread
            props.is_rendering = True
            props.status_text = "Starting AI render..."
            
            self.current_thread = threading_utils.FullRenderThread(
                context=context,
                depth_renderer=depth_renderer,
                api_client=api_client,
                user_prompt=props.prompt
            )
            
            self.current_thread.start()
            self.report({'INFO'}, "AI render started in background")
            return {'FINISHED'}
            
        except Exception as e:
            error_msg = f"Failed to start AI render: {str(e)}"
            self.report({'ERROR'}, error_msg)
            props.is_rendering = False
            props.status_text = f"Error: {str(e)}"
            return {'CANCELLED'}
    
    def _validate_inputs(self, context, props) -> str:
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

class GEMINI_OT_stop_render(Operator):
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
            if hasattr(GEMINI_OT_ai_render, 'current_thread') and GEMINI_OT_ai_render.current_thread:
                if GEMINI_OT_ai_render.current_thread.is_alive():
                    GEMINI_OT_ai_render.current_thread.stop()
                    GEMINI_OT_ai_render.current_thread.join(timeout=3.0)
            
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
            except:
                pass
            self.report({'ERROR'}, f"Failed to stop render: {str(e)}")
            return {'CANCELLED'}

# Additional utility operators

class GEMINI_OT_open_api_key_url(Operator):
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

class GEMINI_OT_validate_api_key(Operator):
    """Validate API key"""
    bl_idname = "gemini.validate_api_key"
    bl_label = "Test API Key"
    bl_description = "Test if the API key is valid"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Validate API key"""
        try:
            api_key = gemini_api.get_api_key()
            
            if not api_key:
                self.report({'ERROR'}, "No API key configured. Set GEMINI_API_KEY or configure in Addon Preferences.")
                return {'CANCELLED'}
            
            # Check format
            if api_key.startswith('AIza') and len(api_key) > 35:
                self.report({'INFO'}, "API key format looks valid")
            else:
                self.report({'WARNING'}, "API key format seems invalid (should start with 'AIza')")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to validate API key: {str(e)}")
            return {'CANCELLED'}


class GEMINI_OT_open_preferences(Operator):
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

class GEMINI_OT_reset_state(Operator):
    """Reset UI state in case of stuck rendering"""
    bl_idname = "gemini.reset_state"
    bl_label = "Reset UI State"
    bl_description = "Force reset render state (use if UI is stuck)"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        """Reset UI state"""
        try:
            print("[GEMINI] Force resetting UI state...")
            props = context.scene.gemini_render
            
            # Force reset all state
            props.is_rendering = False
            props.status_text = "🔄 UI state reset"
            
            # Try to stop any running background threads
            if hasattr(GEMINI_OT_ai_render, 'current_thread') and GEMINI_OT_ai_render.current_thread:
                try:
                    GEMINI_OT_ai_render.current_thread.stop()
                    GEMINI_OT_ai_render.current_thread = None
                except:
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

class GEMINI_OT_open_console(Operator):
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


class GEMINI_OT_load_history(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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
                        print(f"[GEMINI] Image found but has no data: {history_item.image_name}")
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


class GEMINI_OT_delete_history(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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


class GEMINI_OT_use_history_prompt(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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


class GEMINI_OT_use_history_style(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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


class GEMINI_OT_history_context_menu(Operator):
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


class GEMINI_OT_use_history_both(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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
                    self.report({'WARNING'}, f"Style missing, copied prompt only")
            else:
                props.use_style_reference = False
                self.report({'INFO'}, f"Prompt copied (no style was used)")
            
            return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to use history: {str(e)}")
            return {'CANCELLED'}


class GEMINI_OT_open_history_image(Operator):
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
                self.report({'ERROR'}, "Invalid history index")
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


class GEMINI_OT_load_image_as_reference(Operator, ImportHelper):
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
        except:
            pass
            
        # Open the file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class GEMINI_OT_load_example_reference(Operator):
    """Load example reference image"""
    bl_idname = "gemini.load_example_reference"
    bl_label = "Load Example Reference"
    bl_description = "Load an example reference image to test style transfer"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            props = context.scene.gemini_render
            
            # Create a simple example image programmatically
            import bpy
            import bmesh
            from mathutils import Vector
            
            # Check if example image already exists
            example_name = "Gemini_Example_Reference"
            if example_name in bpy.data.images:
                existing_img = bpy.data.images[example_name]
                props.style_reference_image = existing_img
                if not props.use_style_reference:
                    props.use_style_reference = True
                self.report({'INFO'}, "Example reference reloaded")
                return {'FINISHED'}
            
            # Create a simple gradient example image
            width, height = 512, 512
            example_img = bpy.data.images.new(example_name, width, height)
            
            # Create a simple colorful pattern as example
            pixels = [0.0] * (width * height * 4)  # RGBA
            
            for y in range(height):
                for x in range(width):
                    index = (y * width + x) * 4
                    
                    # Create a nice gradient pattern
                    r = (x / width) * 0.8 + 0.2  # Red gradient
                    g = (y / height) * 0.6 + 0.3  # Green gradient  
                    b = ((x + y) / (width + height)) * 0.9 + 0.1  # Blue mix
                    a = 1.0
                    
                    # Add some noise for texture
                    import random
                    noise = random.random() * 0.1 - 0.05
                    r = max(0, min(1, r + noise))
                    g = max(0, min(1, g + noise))
                    b = max(0, min(1, b + noise))
                    
                    pixels[index] = r
                    pixels[index + 1] = g  
                    pixels[index + 2] = b
                    pixels[index + 3] = a
            
            # Update the image
            example_img.pixels = pixels
            
            # Set as reference
            props.style_reference_image = example_img
            
            # Enable style reference if not enabled
            if not props.use_style_reference:
                props.use_style_reference = True
            
            self.report({'INFO'}, "Example reference created and loaded")
            print("🎨 [GEMINI] Example reference image created")
            return {'FINISHED'}
            
        except Exception as e:
            # Fallback: Show helpful message
            message = (
                "Style reference ideas:\n" +
                "• Find architectural photos online\n" +
                "• Download artwork or paintings\n" +
                "• Use nature photography\n" +
                "• Load via 'Load Photo from Computer' button"
            )
            
            def draw_message(self, context):
                layout = self.layout
                for line in message.split('\n'):
                    layout.label(text=line)
            
            context.window_manager.popup_menu(draw_message, title="Style Reference Examples", icon='IMAGE_DATA')
            self.report({'INFO'}, "Check popup for reference image ideas")
            return {'FINISHED'}
