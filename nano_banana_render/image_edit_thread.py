"""
Background thread for AI image editing
Handles async editing without blocking UI
"""

import threading
import bpy
import os
import shutil
from datetime import datetime
from typing import Optional

class ImageEditThread(threading.Thread):
    """Background thread for AI image editing"""
    
    def __init__(self, image_path: str, edit_prompt: str, 
                 mask_path: Optional[str], reference_path: Optional[str],
                 api_key: str, context, original_image_name: str, temp_dir: str,
                 resolution: str = 'AUTO', original_size: tuple = (1024, 1024)):
        super().__init__(daemon=True)
        
        self.image_path = image_path
        self.edit_prompt = edit_prompt
        self.mask_path = mask_path
        self.reference_path = reference_path
        self.api_key = api_key
        self.context = context
        self.original_image_name = original_image_name
        self.temp_dir = temp_dir
        self.resolution = resolution
        self.original_size = original_size
        
        self.result_image_data = None
        self.error_message = None
        
    def run(self):
        """Execute edit in background"""
        try:
            print("[NANO BANANA] Edit thread starting...")
            
            # Update status
            self._update_status("Sending to AI...")
            
            # Call Gemini API
            from . import gemini_api
            
            api_client = gemini_api.GeminiAPI(self.api_key)
            
            print(f"[NANO BANANA] Calling edit_image API...")
            print(f"  - Image: {self.image_path}")
            print(f"  - Prompt: {self.edit_prompt[:100]}...")
            print(f"  - Mask: {self.mask_path}")
            print(f"  - Reference: {self.reference_path}")
            print(f"  - Resolution Mode: {self.resolution}")
            print(f"  - Original Size: {self.original_size}")
            
            # Resolve resolution
            width = 1024
            height = 1024
            
            if self.resolution == '4096':
                width = 4096
                height = 4096
            elif self.resolution == '2048':
                width = 2048
                height = 2048
            elif self.resolution == '1024':
                width = 1024
                height = 1024
            else: # AUTO
                # Robust auto-detection based on original size
                orig_w, orig_h = self.original_size
                max_dim = max(orig_w, orig_h)
                
                if max_dim > 2048:
                    width = 4096
                    height = 4096
                    print(f"[NANO BANANA] Auto-resolution: Detected large image ({max_dim}px) -> Setting 4K")
                elif max_dim > 1024:
                    width = 2048
                    height = 2048
                    print(f"[NANO BANANA] Auto-resolution: Detected medium image ({max_dim}px) -> Setting 2K")
                else:
                    width = 1024
                    height = 1024
                    print(f"[NANO BANANA] Auto-resolution: Detected standard image ({max_dim}px) -> Setting 1K")
            
            image_data, mime_type = api_client.edit_image(
                image_path=self.image_path,
                edit_prompt=self.edit_prompt,
                mask_path=self.mask_path,
                reference_image_path=self.reference_path,
                width=width,
                height=height
            )
            
            print(f"[NANO BANANA] Edit completed: {len(image_data)} bytes, {mime_type}")
            
            self.result_image_data = image_data
            
            # Load result into Blender (must be done in main thread)
            self._update_status("Loading result...")
            self._load_result_in_main_thread()
            
            # Add to history
            self._add_to_history()
            
            self._update_status("Edit complete!")
            print("[NANO BANANA] Edit thread finished successfully")
            
        except Exception as e:
            error_msg = str(e)
            print(f"[NANO BANANA] Edit thread error: {error_msg}")
            import traceback
            traceback.print_exc()
            self.error_message = error_msg
            self._update_status(f"Error: {error_msg[:50]}")
        
        finally:
            # Reset editing flag
            def reset_flag():
                props = bpy.context.window_manager.nano_banana_editor
                props.is_editing = False
            
            self._execute_in_main_thread(reset_flag)
    
    def _update_status(self, message: str):
        """Update status in UI (main thread)"""
        def update():
            props = bpy.context.window_manager.nano_banana_editor
            props.status_text = message
        
        self._execute_in_main_thread(update)
    
    def _load_result_in_main_thread(self):
        """Load edited image into Blender (main thread)"""
        if not self.result_image_data:
            return
        
        def load_image():
            try:
                # Create new temp directory for result (since old one might be cleaned up)
                import tempfile
                result_temp_dir = tempfile.mkdtemp(prefix="nano_banana_result_")
                result_path = os.path.join(result_temp_dir, "edited_result.png")
                
                with open(result_path, 'wb') as f:
                    f.write(self.result_image_data)
                
                print(f"[NANO BANANA] Saved result to: {result_path}")
                
                # Create new image name
                timestamp = datetime.now().strftime("%H%M%S")
                new_image_name = f"{self.original_image_name}_edit_{timestamp}"
                
                # Load image into Blender
                if result_path in bpy.data.images:
                    bpy.data.images.remove(bpy.data.images[result_path])
                
                new_image = bpy.data.images.load(result_path, check_existing=False)
                new_image.name = new_image_name
                
                # CRITICAL: Set colorspace to sRGB (prevent color shifting)
                if hasattr(new_image, 'colorspace_settings'):
                    new_image.colorspace_settings.name = 'sRGB'
                    print(f"[NANO BANANA] Set colorspace to sRGB")
                
                new_image.pack()  # Pack into blend file
                
                print(f"[NANO BANANA] Loaded result as: {new_image_name}")
                
                # Switch to new image in ALL Image Editor windows
                switched = False
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'IMAGE_EDITOR':
                            for space in area.spaces:
                                if space.type == 'IMAGE_EDITOR':
                                    space.image = new_image
                                    # Force switch to View mode to see result
                                    space.mode = 'VIEW'
                                    area.tag_redraw()
                                    switched = True
                                    print(f"[NANO BANANA] Switched window {window.as_pointer()} to edited image")
                
                if switched:
                    print(f"[NANO BANANA] All Image Editors updated")
                else:
                    print(f"[NANO BANANA] Warning: No Image Editor found to display result")
                
                # Clean up result temp directory after a delay
                import shutil
                try:
                    shutil.rmtree(result_temp_dir)
                    print(f"[NANO BANANA] Cleaned up result temp dir")
                except:
                    pass
                
            except Exception as e:
                print(f"[NANO BANANA] Error loading result: {e}")
                import traceback
                traceback.print_exc()
        
        self._execute_in_main_thread(load_image)
    
    def _add_to_history(self):
        """Add edit to history (main thread)"""
        def add_history():
            try:
                props = bpy.context.window_manager.nano_banana_editor
                
                history_item = props.edit_history.add()
                history_item.prompt = self.edit_prompt
                history_item.image_name = self.original_image_name
                history_item.timestamp = datetime.now().strftime("%H:%M:%S")
                history_item.has_mask = bool(self.mask_path)
                
                print(f"[NANO BANANA] Added edit to history: {self.edit_prompt[:50]}")
                
            except Exception as e:
                print(f"[NANO BANANA] Error adding to history: {e}")
        
        self._execute_in_main_thread(add_history)
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                print(f"[NANO BANANA] Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            print(f"[NANO BANANA] Warning: Could not cleanup temp files: {e}")
    
    def _execute_in_main_thread(self, func):
        """Execute function in Blender's main thread"""
        try:
            # Use Blender's app.timers to execute in main thread
            bpy.app.timers.register(lambda: (func(), None)[1], first_interval=0.01)
        except Exception as e:
            print(f"[NANO BANANA] Error executing in main thread: {e}")

