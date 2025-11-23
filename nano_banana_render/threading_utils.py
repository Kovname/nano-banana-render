import bpy
import threading
from queue import Queue
from typing import Callable, Any
import time

class BlenderThreadManager:
    """Manager for thread-safe operations with Blender"""
    
    def __init__(self):
        self.command_queue = Queue()
        self.timer_registered = False
        
    def execute_in_main_thread(self, func: Callable, *args, **kwargs) -> None:
        """Execute function in main Blender thread via timer"""
        self.command_queue.put((func, args, kwargs))
        
        # Register timer if not already registered
        if not self.timer_registered:
            bpy.app.timers.register(self._process_queue, first_interval=0.01)
            self.timer_registered = True
    
    def _process_queue(self) -> float:
        """Process queued commands in main thread"""
        try:
            while not self.command_queue.empty():
                func, args, kwargs = self.command_queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print(f"Error executing queued command: {e}")
                    # Continue processing other commands
                    
            # Return interval for next check
            return 0.1
            
        except Exception as e:
            print(f"Error in queue processor: {e}")
            return 0.1
    
    def stop_timer(self) -> None:
        """Stop the timer (call when addon is unregistered)"""
        if self.timer_registered:
            try:
                bpy.app.timers.unregister(self._process_queue)
            except:
                pass
            self.timer_registered = False

# Global thread manager instance
_thread_manager = BlenderThreadManager()

def execute_in_main_thread(func: Callable, *args, **kwargs) -> None:
    """Convenience function to execute in main thread"""
    _thread_manager.execute_in_main_thread(func, *args, **kwargs)

def update_render_status(scene, status_text: str, is_rendering: bool = None) -> None:
    """Update render status in UI (thread-safe)"""
    def _update():
        try:
            print(f"[GEMINI] Updating status: {status_text}")
            if hasattr(scene, 'gemini_render'):
                props = scene.gemini_render
                props.status_text = status_text
                if is_rendering is not None:
                    props.is_rendering = is_rendering
                    print(f"[GEMINI] Set is_rendering = {is_rendering}")
                
                # Force redraw all areas
                try:
                    import bpy
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.type == 'VIEW_3D':
                                area.tag_redraw()
                except Exception as redraw_error:
                    print(f"[GEMINI] Redraw warning: {redraw_error}")
                    
                print("[GEMINI] Status updated successfully")
            else:
                print("[GEMINI] Scene has no gemini_render property")
        except Exception as e:
            print(f"[GEMINI] Error updating status: {e}")
            import traceback
            print(f"[GEMINI] Status update traceback:\n{traceback.format_exc()}")
    
    execute_in_main_thread(_update)

def save_reference_image_temp(scene) -> str:
    """Save reference image from scene properties to temporary file"""
    try:
        import bpy
        import tempfile
        import os
        
        # Get scene properties
        props = scene.gemini_render if hasattr(scene, 'gemini_render') else None
        if not props or not props.use_style_reference or not props.style_reference_image:
            return None
            
        reference_image = props.style_reference_image
        print(f"🎨 [GEMINI] Saving reference image: {reference_image.name}")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Save image using different methods based on image type
        saved_successfully = False
        
        # Method 1: For images without filepath (generated images) - use pixel data
        if not reference_image.filepath:
            print("[GEMINI] Saving generated image via pixel data...")
            try:
                # Get pixel data directly
                pixels = list(reference_image.pixels)
                width, height = reference_image.size
                
                # Convert to PIL Image and save
                try:
                    # Try to use PIL if available
                    from PIL import Image
                    try:
                        import numpy as np
                    except ImportError:
                        raise ImportError("NumPy required for PIL image processing")
                    
                    # Convert pixels to numpy array and reshape
                    pixel_array = np.array(pixels).reshape((height, width, reference_image.channels))
                    
                    # Convert to 0-255 range and uint8
                    if pixel_array.max() <= 1.0:
                        pixel_array = (pixel_array * 255).astype(np.uint8)
                    
                    # Handle different channel counts
                    if reference_image.channels == 4:  # RGBA
                        img = Image.fromarray(pixel_array, 'RGBA')
                    elif reference_image.channels == 3:  # RGB
                        img = Image.fromarray(pixel_array, 'RGB')
                    else:  # Grayscale
                        img = Image.fromarray(pixel_array[:,:,0], 'L')
                    
                    img.save(temp_path, 'PNG')
                    saved_successfully = True
                    print("[GEMINI] Saved via PIL")
                    
                except ImportError:
                    print("[GEMINI] PIL not available, trying Blender save_render...")
                    # Fallback to Blender's save_render
                    original_settings = {
                        'filepath': reference_image.filepath,
                        'file_format': reference_image.file_format
                    }
                    
                    reference_image.filepath_raw = temp_path
                    reference_image.file_format = 'PNG'
                    reference_image.save_render(temp_path)
                    
                    # Restore original settings
                    reference_image.filepath = original_settings['filepath']
                    reference_image.file_format = original_settings['file_format']
                    saved_successfully = True
                    print("[GEMINI] Saved via Blender save_render")
                    
            except Exception as e:
                print(f"[GEMINI] Pixel data method failed: {e}")
        
        # Method 2: For packed images
        elif reference_image.packed_file:
            print("📦 [GEMINI] Reference image is packed, extracting...")
            try:
                with open(temp_path, 'wb') as f:
                    f.write(reference_image.packed_file.data)
                saved_successfully = True
                print("[GEMINI] Saved from packed data")
            except Exception as e:
                print(f"[GEMINI] Packed file method failed: {e}")
        
        # Method 3: For images with filepath
        elif reference_image.filepath:
            print(f"📁 [GEMINI] Copying reference from filepath...")
            try:
                import shutil
                abs_path = bpy.path.abspath(reference_image.filepath)
                if os.path.exists(abs_path):
                    shutil.copy2(abs_path, temp_path)
                    saved_successfully = True
                    print(f"[GEMINI] Copied from: {abs_path}")
                else:
                    print(f"[GEMINI] Reference file not found: {abs_path}")
            except Exception as e:
                print(f"[GEMINI] Filepath method failed: {e}")
        
        # Check if saving was successful
        if saved_successfully and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            print(f"[GEMINI] Reference image saved to: {temp_path}")
            return temp_path
        else:
            print("[GEMINI] Failed to save reference image")
            # Clean up failed temp file
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            return None
            
    except Exception as e:
        print(f"[GEMINI] Error saving reference image: {e}")
        return None

def load_result_image(image_data: bytes, image_name: str = "AI_Result", user_prompt: str = "") -> None:
    """Load result image into Blender and save to history (thread-safe)"""
    print(f"🚀 [GEMINI] load_result_image called with user_prompt: '{user_prompt}', image_name: '{image_name}'")
    def _load_image():
        print("[GEMINI] Starting _load_image function...")
        try:
            import tempfile
            import os
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                f.write(image_data)
                temp_path = f.name
            
            try:
                # Load image into Blender
                if image_name in bpy.data.images:
                    bpy.data.images.remove(bpy.data.images[image_name])
                
                img = bpy.data.images.load(temp_path)
                img.name = image_name
                
                # Keep original image for history (don't make copies that lose data)
                permanent_image_for_history = None
                if user_prompt:  # Only if we need to save to history
                    import datetime
                    permanent_name = f"AI_Result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Rename the original loaded image to be our permanent image  
                    img.name = permanent_name
                    img.pack()  # Pack to save with .blend file
                    permanent_image_for_history = img
                    print(f"[GEMINI] ORIGINAL image kept for history: {permanent_name}")
                    print(f"[GEMINI] Original image has_data: {permanent_image_for_history.has_data}, size: {permanent_image_for_history.size}")
                
                # Method 1: Try to replace existing Render Result completely
                print(f"[GEMINI] Loaded image: {img.name}, size: {img.size}, channels: {img.channels}")
                
                # Remove existing Render Result if it exists
                render_result = bpy.data.images.get('Render Result')
                if render_result:
                    print("[GEMINI] Removing existing Render Result")
                    bpy.data.images.remove(render_result)
                
                # Create a copy for Render Result display (keep original for history)
                render_result = img.copy()
                render_result.name = 'Render Result'
                print(f"[GEMINI] Created Render Result copy: {render_result.size}")
                print(f"[GEMINI] Render Result has_data: {render_result.has_data}")
                
                # Note: render_result.type is read-only, so we can't set it directly
                print("📋 [GEMINI] Render Result copy is ready for display")
                
                # Force update all Image Editors to show the new Render Result
                updated_editors = 0
                for area in bpy.context.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        for space in area.spaces:
                            if space.type == 'IMAGE_EDITOR':
                                # Force set the image to our new render result
                                space.image = render_result
                                updated_editors += 1
                                print(f"[GEMINI] Updated Image Editor {updated_editors}")
                        # Force refresh the area
                        area.tag_redraw()
                
                print(f"[GEMINI] Updated {updated_editors} Image Editors")
                
                # Also try to update the render view if it exists
                for area in bpy.context.screen.areas:
                    area.tag_redraw()
                
                print(f"[GEMINI] AI result loaded successfully as Render Result")
                
                # Show the render result like F12 does - open/switch to render view
                print("[GEMINI] Opening Render Result view...")
                
                # Try different methods to show the result (but ALWAYS continue to history afterward)
                try:
                    # Method 1: Try to create a completely new Blender window
                    try:
                        print("🪟 [GEMINI] Creating new Blender window...")
                        bpy.ops.wm.window_new()
                        
                        # Set the new window to Image Editor
                        new_window = bpy.context.window_manager.windows[-1]  # Last created window
                        for area in new_window.screen.areas:
                            if area.type != 'IMAGE_EDITOR':
                                area.type = 'IMAGE_EDITOR'
                                for space in area.spaces:
                                    if space.type == 'IMAGE_EDITOR':
                                        space.image = render_result
                                        area.tag_redraw()
                                        print("[GEMINI] New window created with render result!")
                                        break  # Exit spaces loop only
                                break  # Exit areas loop only
                                        
                    except Exception as e1:
                        print(f"[GEMINI] Could not create new window: {e1}")
                        
                        # Method 2: Try to duplicate current area to new window
                        try:
                            print("📱 [GEMINI] Trying area duplication...")
                            bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
                            
                            # Find the duplicated area and set it to Image Editor
                            for area in bpy.context.screen.areas:
                                if area.type == 'EMPTY':
                                    area.type = 'IMAGE_EDITOR'
                                    for space in area.spaces:
                                        if space.type == 'IMAGE_EDITOR':
                                            space.image = render_result
                                            area.tag_redraw()
                                            print("[GEMINI] Duplicated area set to show render result")
                                            break  # Exit spaces loop only
                                    break  # Exit areas loop only
                            
                        except Exception as e2:
                            print(f"[GEMINI] Could not duplicate area: {e2}")
                            
                            # Method 3: SAFE area conversion
                            try:
                                print("[GEMINI] Trying to switch SAFE existing area...")
                                
                                # SAFE areas to convert (don't touch animation!)
                                SAFE_AREAS_TO_CONVERT = [
                                    'TEXT_EDITOR', 'CONSOLE', 'INFO', 'FILE_BROWSER',
                                ]
                                
                                area_converted = False
                                for area in bpy.context.screen.areas:
                                    if area.type in SAFE_AREAS_TO_CONVERT:
                                        old_type = area.type
                                        area.type = 'IMAGE_EDITOR'
                                        for space in area.spaces:
                                            if space.type == 'IMAGE_EDITOR':
                                                space.image = render_result
                                                area.tag_redraw()
                                                print(f"[GEMINI] Safely converted {old_type} to Image Editor")
                                                area_converted = True
                                                break  # Exit spaces loop only
                                        break  # Exit areas loop only
                                
                                if not area_converted:
                                    print("[GEMINI] No SAFE areas found, trying existing Image Editor...")
                                    
                                    # Method 4: Use existing Image Editor
                                    for area in bpy.context.screen.areas:
                                        if area.type == 'IMAGE_EDITOR':
                                            for space in area.spaces:
                                                if space.type == 'IMAGE_EDITOR':
                                                    space.image = render_result
                                                    area.tag_redraw()
                                                    print("[GEMINI] Using existing Image Editor for render result")
                                                    break  # Exit spaces loop only
                                            break  # Exit areas loop only
                                    
                                    print("💡 [GEMINI] Render result is available as 'Render Result' image in Blender")
                                    
                            except Exception as e3:
                                print(f"[GEMINI] Safe area conversion failed: {e3}")
                                print("[GEMINI] Render result loaded - access manually via Image Editor")
                
                except Exception as e:
                    print(f"[GEMINI] All window methods failed: {e}")
                    print("[GEMINI] Render result loaded - access manually via Image Editor")
                
                print("[GEMINI] Finished window/editor setup, now starting history save...")
                
                # Add to render history
                print(f"[GEMINI] Attempting to save to history, user_prompt: '{user_prompt}'")
                if user_prompt:
                    print("[GEMINI] User prompt found, proceeding with history save...")
                else:
                    print("[GEMINI] User prompt is empty, skipping history save")
                
                if user_prompt:
                    try:
                        scene = bpy.context.scene
                        print(f"[GEMINI] Scene: {scene.name if scene else 'None'}")
                        print(f"[GEMINI] Scene has gemini_render: {hasattr(scene, 'gemini_render')}")
                        
                        if hasattr(scene, 'gemini_render'):
                            props = scene.gemini_render
                            print(f"[GEMINI] Current history length: {len(props.render_history)}")
                            
                            # Create history entry
                            history_item = props.render_history.add()
                            history_item.prompt = user_prompt
                            
                            # Use the PERMANENT image created at the beginning of _load_image
                            if permanent_image_for_history:
                                history_item.image_name = permanent_image_for_history.name
                                print(f"[GEMINI] Using pre-created permanent image for history: {permanent_image_for_history.name}")
                                print(f"[GEMINI] Pre-created image has_data: {permanent_image_for_history.has_data}, size: {permanent_image_for_history.size}")
                            else:
                                # Fallback - create now (shouldn't happen if user_prompt exists)
                                import datetime
                                permanent_name = f"AI_Result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                                try:
                                    permanent_image = render_result.copy()
                                    permanent_image.name = permanent_name
                                    permanent_image.pack()
                                    history_item.image_name = permanent_name
                                    print(f"[GEMINI] Created fallback permanent image: {permanent_name}")
                                except Exception as e:
                                    print(f"[GEMINI] Failed to create fallback permanent copy: {e}")
                                    history_item.image_name = render_result.name
                                    print(f"[GEMINI] Using render result directly as last resort: {render_result.name}")
                                    
                            print(f"[GEMINI] History item created: {history_item.prompt[:30]}...")
                            
                            # Save style reference info if used
                            if props.use_style_reference and props.style_reference_image:
                                history_item.style_reference_used = True
                                history_item.style_reference_name = props.style_reference_image.name
                                print(f"[GEMINI] Style reference saved: {props.style_reference_image.name}")
                                
                                # NO THUMBNAIL CREATION - style thumbnails removed
                                history_item.style_reference_thumbnail = ""
                                print(f"[GEMINI] Style reference linked (no thumbnail created)")
                            else:
                                history_item.style_reference_used = False
                                print("[GEMINI] No style reference used for this render")
                            
                            # Add timestamp
                            import datetime
                            history_item.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            # NO THUMBNAIL CREATION - use the main AI_Result image directly  
                            history_item.thumbnail_name = ""  # No thumbnail needed
                            print(f"[GEMINI] No thumbnail created - using main AI_Result image directly")
                            
                            # Keep only last 10 renders to avoid bloating blend file
                            while len(props.render_history) > 10:
                                # Remove oldest entry and its images
                                oldest = props.render_history[0]
                                
                                # Remove main AI_Result image
                                if oldest.image_name in bpy.data.images:
                                    old_image = bpy.data.images[oldest.image_name]
                                    print(f"[GEMINI] Removing old AI_Result image: {oldest.image_name}")
                                    bpy.data.images.remove(old_image)
                                
                                # NO STYLE THUMBNAIL REMOVAL - they don't exist anymore
                                
                                props.render_history.remove(0)
                            
                            print(f"[GEMINI] Added to history: {user_prompt[:50]}... (Total: {len(props.render_history)})")
                            print(f"[GEMINI] History successfully saved!")
                        else:
                            print("[GEMINI] Scene does not have gemini_render property")
                        
                    except Exception as e:
                        print(f"[GEMINI] Failed to save to history: {e}")
                        import traceback
                        print(f"[GEMINI] History error traceback: {traceback.format_exc()}")
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"Error loading result image: {e}")
    
    execute_in_main_thread(_load_image)

class RenderThread(threading.Thread):
    """Background thread for AI rendering operations (DEPRECATED - use APIThread)"""
    
    def __init__(self, scene, depth_renderer, api_client, user_prompt: str):
        super().__init__(daemon=True)
        self.scene = scene
        self.depth_renderer = depth_renderer
        self.api_client = api_client
        self.user_prompt = user_prompt
        self._stop_event = threading.Event()
        print("[GEMINI] RenderThread initialized (DEPRECATED)")
    
    def stop(self):
        """Request thread to stop"""
        print("[GEMINI] Stop requested for RenderThread")
        self._stop_event.set()
    
    def run(self):
        """Main thread execution"""
        # This is deprecated - should not be used
        print("[GEMINI] RenderThread is deprecated, use APIThread instead")
        update_render_status(self.scene, "Deprecated render method used", False)

class APIThread(threading.Thread):
    """Background thread for API calls only (render happens in main thread)"""
    
    def __init__(self, scene, api_client, user_prompt: str, depth_path: str):
        super().__init__(daemon=True)
        self.scene = scene
        self.api_client = api_client
        self.user_prompt = user_prompt
        self.depth_path = depth_path
        self._stop_event = threading.Event()
        print("[GEMINI] APIThread initialized")
    
    def stop(self):
        """Request thread to stop"""
        print("[GEMINI] Stop requested for APIThread")
        self._stop_event.set()
    
    def run(self):
        """Main thread execution - API calls only"""
        print("🚀 [GEMINI] APIThread starting execution...")
        
        try:
            if self._stop_event.is_set():
                print("[GEMINI] Stopped before API call")
                return
            
            # Send to AI
            print("[GEMINI] Step 1: Sending to Gemini AI...")
            update_render_status(self.scene, "Sending to AI...", True)
            
            # Check for reference image
            reference_path = save_reference_image_temp(self.scene)
            
            # Get resolution
            props = self.scene.gemini_render if hasattr(self.scene, 'gemini_render') else None
            resolution = int(props.resolution) if props and hasattr(props, 'resolution') else 1024
            
            try:
                image_data, mime_type = self.api_client.generate_image(self.depth_path, self.user_prompt, reference_path, width=resolution, height=resolution)
                print(f"[GEMINI] AI response received, image size: {len(image_data)} bytes")
            finally:
                # Clean up reference temp file
                if reference_path:
                    try:
                        import os
                        os.unlink(reference_path)
                        print(f"[GEMINI] Reference temp file cleaned up")
                    except:
                        pass
            
            if self._stop_event.is_set():
                print("[GEMINI] Stopped after AI response")
                return
            
            # Load result
            print("[GEMINI] Step 2: Loading result into Blender...")
            update_render_status(self.scene, "📥 Loading result...", True)
            print(f"[GEMINI] About to call load_result_image with user_prompt: '{self.user_prompt}' (length: {len(self.user_prompt) if self.user_prompt else 0})")
            load_result_image(image_data, "Gemini_AI_Result", self.user_prompt)
            
            # Success
            print("🎉 [GEMINI] AI render completed successfully!")
            update_render_status(self.scene, "AI render completed successfully!", False)
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"[GEMINI] API thread error: {error_msg}")
            print(f"[GEMINI] Exception type: {type(e).__name__}")
            import traceback
            print(f"[GEMINI] Full traceback:\n{traceback.format_exc()}")
            
            update_render_status(self.scene, error_msg, False)
            
        finally:
            print("[GEMINI] API thread cleanup starting...")
            # Cleanup depth file if needed
            try:
                import os
                if os.path.exists(self.depth_path):
                    os.remove(self.depth_path)
                    print(f"[GEMINI] Cleaned up depth file: {self.depth_path}")
            except Exception as cleanup_error:
                print(f"[GEMINI] Cleanup warning: {cleanup_error}")
            print("[GEMINI] APIThread finished")

class FullRenderThread(threading.Thread):
    """Background thread for full render pipeline with proper context handling"""
    
    def __init__(self, context, depth_renderer, api_client, user_prompt: str):
        super().__init__(daemon=True)
        # Store only what we need from context
        self.scene = context.scene
        self.view_layer = context.view_layer
        # Store window manager for render operations
        import bpy
        self.window_manager = bpy.context.window_manager
        
        self.depth_renderer = depth_renderer
        self.api_client = api_client
        self.user_prompt = user_prompt
        self._stop_event = threading.Event()
        print("[GEMINI] FullRenderThread initialized")
    
    def stop(self):
        """Request thread to stop"""
        print("[GEMINI] Stop requested for FullRenderThread")
        self._stop_event.set()
    
    def run(self):
        """Main thread execution with proper context override"""
        print("[GEMINI] FullRenderThread starting execution...")
        
        try:
            # Update status
            print("[GEMINI] Step 1: Updating status to 'rendering depth'")
            update_render_status(self.scene, "Rendering depth map...", True)
            
            if self._stop_event.is_set():
                print("[GEMINI] Stopped before depth render")
                return
            
            # Get render mode from scene properties
            props = self.scene.gemini_render if hasattr(self.scene, 'gemini_render') else None
            render_mode = props.render_mode if props and hasattr(props, 'render_mode') else 'DEPTH'
            
            # Execute render based on mode
            render_result = None
            depth_path = None
            
            if render_mode == 'DEPTH':
                # Depth Map (Mist) Mode
                print("[GEMINI] Using DEPTH MAP (Mist) mode...")
                
                mist_start = props.mist_start if props else 5.0
                mist_depth = props.mist_depth if props else 25.0
                mist_falloff = props.mist_falloff if props and hasattr(props, 'mist_falloff') else 'LINEAR'
                
                def _do_safe_mist_render():
                    nonlocal render_result, depth_path
                    try:
                        depth_path = self.depth_renderer.render_depth_map_mist(
                            self.scene, mist_start, mist_depth, mist_falloff
                        )
                        render_result = "success"
                        print(f"[GEMINI] Mist depth render completed: {depth_path}")
                        
                    except Exception as e:
                        render_result = f"error: {str(e)}"
                        print(f"[GEMINI] Mist render error in main thread: {str(e)}")
                
                # Execute mist render in main thread
                print("[GEMINI] Executing mist render in main thread for safety...")
                execute_in_main_thread(_do_safe_mist_render)
                
            else:
                # Regular Eevee Render Mode
                print("[GEMINI] Using REGULAR RENDER (Eevee) mode...")
                
                def _do_safe_eevee_render():
                    nonlocal render_result, depth_path
                    try:
                        # Use regular render method
                        depth_path = self.depth_renderer.render_regular_eevee(self.scene)
                        render_result = "success"
                        print(f"[GEMINI] Regular Eevee render completed: {depth_path}")
                        
                    except Exception as e:
                        render_result = f"error: {str(e)}"
                        print(f"[GEMINI] Eevee render error in main thread: {str(e)}")
                
                # Execute eevee render in main thread
                print("[GEMINI] Executing regular Eevee render in main thread...")
                execute_in_main_thread(_do_safe_eevee_render)
            
            # Wait for render completion
            import time
            timeout = 180  # 3 minutes timeout for mist render
            elapsed = 0
            while render_result is None and elapsed < timeout and not self._stop_event.is_set():
                time.sleep(0.1)
                elapsed += 0.1
            
            if self._stop_event.is_set():
                print("[GEMINI] Stopped during mist render")
                return
            
            if render_result is None:
                raise Exception("Mist render timeout - took longer than 3 minutes")
            elif render_result.startswith("error:"):
                raise Exception(f"Mist render failed: {render_result[7:]}")
            
            if not depth_path:
                raise Exception("No depth path returned from mist render")
            
            # Continue with AI processing
            print("[GEMINI] Step 2: Sending to Gemini AI...")
            update_render_status(self.scene, "Sending to AI...", True)
            
            # Check for reference image
            reference_path = save_reference_image_temp(self.scene)
            
            # Determine if using color render mode
            is_color_render = (render_mode == 'EEVEE')
            
            # Get resolution
            resolution = int(props.resolution) if props and hasattr(props, 'resolution') else 1024
            print(f"[GEMINI] Using resolution: {resolution}x{resolution}")
            
            try:
                image_data, mime_type = self.api_client.generate_image(depth_path, self.user_prompt, reference_path, is_color_render, width=resolution, height=resolution)
                print(f"[GEMINI] AI response received, image size: {len(image_data)} bytes")
            finally:
                # Clean up reference temp file
                if reference_path:
                    try:
                        import os
                        os.unlink(reference_path)
                        print(f"[GEMINI] Reference temp file cleaned up")
                    except:
                        pass
                        
                # CRITICAL: Clean up depth temp files after API usage
                try:
                    self.depth_renderer.cleanup_temp_files()
                    print("[GEMINI] Depth temp files cleaned up after API usage")
                except Exception as cleanup_error:
                    print(f"[GEMINI] Depth cleanup warning: {cleanup_error}")
            
            if self._stop_event.is_set():
                print("[GEMINI] Stopped after AI response")
                return
            
            # Load result
            print("[GEMINI] Step 3: Loading result into Blender...")
            update_render_status(self.scene, "📥 Loading result...", True)
            print(f"[GEMINI] About to call load_result_image with user_prompt: '{self.user_prompt}' (length: {len(self.user_prompt) if self.user_prompt else 0})")
            load_result_image(image_data, "Gemini_AI_Result", self.user_prompt)
            
            # Success
            print("🎉 [GEMINI] AI render completed successfully!")
            update_render_status(self.scene, "AI render completed successfully!", False)
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"[GEMINI] Full render thread error: {error_msg}")
            print(f"[GEMINI] Exception type: {type(e).__name__}")
            import traceback
            print(f"[GEMINI] Full traceback:\n{traceback.format_exc()}")
            
            update_render_status(self.scene, error_msg, False)
            
        finally:
            print("[GEMINI] Full render thread cleanup starting...")
            # Note: Depth temp files are now cleaned up after API usage, not here
            print("[GEMINI] FullRenderThread finished")
    
    def _render_depth_with_override(self, override_context):
        """Render depth with context override"""
        import bpy
        
        scene = override_context['scene']
        view_layer = override_context['view_layer']
        
        # Setup scene
        print("[GEMINI] Setting up depth render...")
        
        # Store original settings
        original_filepath = scene.render.filepath
        original_use_nodes = scene.use_nodes
        original_file_format = scene.render.image_settings.file_format
        original_color_mode = scene.render.image_settings.color_mode
        
        # Create temp directory
        import tempfile, os
        temp_dir = tempfile.mkdtemp(prefix="gemini_depth_")
        depth_file_path = os.path.join(temp_dir, "depth")
        
        try:
            # Configure render settings
            scene.render.filepath = depth_file_path
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'BW'
            
            # Setup compositor
            scene.use_nodes = True
            tree = scene.node_tree
            tree.nodes.clear()
            
            # Create nodes
            render_layers = tree.nodes.new(type='CompositorNodeRLayers')
            render_layers.location = (0, 0)
            
            output_node = tree.nodes.new(type='CompositorNodeOutputFile')
            output_node.location = (300, 0)
            output_node.base_path = temp_dir
            output_node.file_slots[0].path = "depth"
            output_node.format.file_format = 'PNG'
            output_node.format.color_mode = 'BW'
            
            # Enable depth pass
            view_layer.use_pass_z = True
            
            # Connect depth output
            if 'Depth' in render_layers.outputs:
                tree.links.new(render_layers.outputs['Depth'], output_node.inputs[0])
            elif 'Z' in render_layers.outputs:
                tree.links.new(render_layers.outputs['Z'], output_node.inputs[0])
            else:
                print("[GEMINI] No depth pass found, using Image")
                tree.links.new(render_layers.outputs['Image'], output_node.inputs[0])
            
            print("[GEMINI] Starting render operation...")
            
            # Use render operator with override
            with bpy.context.temp_override(**override_context):
                bpy.ops.render.render(write_still=True)
            
            print("[GEMINI] Render operation completed")
            
            # Find output file
            possible_paths = [
                os.path.join(temp_dir, "depth0001.png"),
                os.path.join(temp_dir, "depth.png"),
                depth_file_path + ".png"
            ]
            
            actual_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    actual_path = path
                    break
            
            if not actual_path:
                raise Exception("Depth render file not found")
            
            # Normalize depth map
            normalized_path = self.depth_renderer._normalize_depth_map(
                actual_path, self.normalize_mode, self.clip_start, self.clip_end
            )
            
            return normalized_path
            
        finally:
            # Restore settings
            scene.render.filepath = original_filepath
            scene.use_nodes = original_use_nodes
            scene.render.image_settings.file_format = original_file_format
            scene.render.image_settings.color_mode = original_color_mode

def stop_thread_manager():
    """Stop the thread manager (call on addon unregister)"""
    _thread_manager.stop_timer()
