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
    
    def __init__(self, image_path: str, user_prompt: str, api_prompt: str, 
                 api_key: str, context, original_image_name: str, temp_dir: str,
                 mask_path: Optional[str] = None, reference_path: Optional[str] = None,
                 smart_points_json: str = "",
                 size_params: tuple = ('AUTO', (1024, 1024)),
                 model_name: str = None,
                 is_smart_points: bool = False):
        super().__init__(daemon=True)
        
        self.image_path = image_path
        self.user_prompt = user_prompt
        self.api_prompt = api_prompt
        self.mask_path = mask_path
        self.reference_path = reference_path
        self.api_key = api_key
        self.context = context
        self.original_image_name = original_image_name
        self.temp_dir = temp_dir
        self.smart_points_json = smart_points_json
        self.resolution, self.original_size = size_params
        self.model_name = model_name
        self.is_smart_points = is_smart_points
        
        self.result_image_data = None
        self.error_message = None
        
    def run(self):
        """Execute edit in background"""
        try:
            print("[NANO BANANA] Edit thread starting...")
            
            # Update status
            self._update_status("Sending to AI...")
            
            # Use original_size passed from the operator (Blender image.size)
            # This is reliable — PIL may not work inside Blender's bundled Python
            orig_w, orig_h = self.original_size
            print(f"[NANO BANANA] Original image size from Blender: {orig_w}x{orig_h}")
            
            # Sanity check — fallback to PIL only if original_size was somehow (0,0)
            if orig_w <= 0 or orig_h <= 0:
                try:
                    from PIL import Image
                    with Image.open(self.image_path) as img:
                        orig_w, orig_h = img.size
                    print(f"[NANO BANANA] PIL fallback size: {orig_w}x{orig_h}")
                except Exception as e:
                    orig_w, orig_h = 1024, 1024
                    print(f"[NANO BANANA] Could not read image size, defaulting to 1024x1024: {e}")
                
            # Determine target dimensions based on requested resolution
            max_dim = 1024
            if self.resolution == '2048' or self.resolution == '2K':
                max_dim = 2048
            elif self.resolution == '4096' or self.resolution == '4K':
                max_dim = 4096
            elif self.resolution == '1024' or self.resolution == '1K':
                max_dim = 1024
            elif self.resolution == 'AUTO':
                # AUTO: use the original image size, but at least 1024
                max_dim = max(max(orig_w, orig_h), 1024)
                
            # Scale to target while preserving aspect ratio
            if max(orig_w, orig_h) > 0:
                scale = max_dim / max(orig_w, orig_h)
            else:
                scale = 1.0
            width = int(orig_w * scale)
            height = int(orig_h * scale)
            print(f"[NANO BANANA] Edit target resolution: {width}x{height} (Mode: {self.resolution}, max_dim: {max_dim})")

            if self.api_key.startswith("AIza"):
                # ─── Direct Google API Mode ───
                from .gemini_api import GeminiAPI
                print("[NANO BANANA] Calling Google API directly for EDIT...")
                gemini = GeminiAPI(api_key=self.api_key, model=self.model_name)
                image_data, _ = gemini.edit_image(
                    image_path=self.image_path,
                    edit_prompt=self.api_prompt,
                    mask_path=self.mask_path,
                    reference_image_path=self.reference_path,
                    width=width,
                    height=height,
                    is_smart_points=self.is_smart_points
                )
                generation_id = 0
                new_balance = -1
            else:
                # ─── Server Mode (Nanode API) ───
                from . import beta_api
                from .gemini_api import GeminiAPI
                
                if self.is_smart_points:
                    # Smart points prompt is already fully built — use as-is
                    full_prompt = self.api_prompt
                else:
                    # Build prompt client-side (same logic as direct mode)
                    prompt_builder = GeminiAPI.__new__(GeminiAPI)
                    full_prompt = prompt_builder._build_edit_prompt(
                        self.api_prompt,
                        has_mask=bool(self.mask_path),
                        has_reference=bool(self.reference_path)
                    )
                
                print("[NANO BANANA] Calling beta_api.generate for INPAINT...")
                print(f"  - Image: {self.image_path}")
                print(f"  - Prompt: {full_prompt[:200]}...")
                print(f"  - Mask: {self.mask_path}")
                print(f"  - Reference: {self.reference_path}")
                print(f"  - Smart Points: {self.is_smart_points}")
                
                image_data, generation_id, new_balance = beta_api.generate(
                    prompt=full_prompt,
                    model=self.model_name,
                    input_image_path=self.image_path,
                    reference_image_path=self.reference_path,
                    mask_image_path=self.mask_path,
                    gen_type="inpaint",
                    width=width,
                    height=height,
                    user_prompt=self.user_prompt,
                    is_smart_points=self.is_smart_points,
                )
            
            print(f"[NANO BANANA] Edit completed: {len(image_data)} bytes")
            
            # Post-process: Enforce correct dimensions WITHOUT stretching
            # Gemini may return a different aspect ratio (e.g. 16:9 when input was 16:10).
            # Instead of stretching (which distorts), we:
            #   1. Crop the AI result to match the original aspect ratio (center crop)
            #   2. Then resize to the exact target dimensions
            # This prevents compounding vertical/horizontal stretch across iterations.
            try:
                from PIL import Image
                import io
                
                with Image.open(io.BytesIO(image_data)) as result_img:
                    res_w, res_h = result_img.size
                    
                    if (res_w, res_h) != (width, height):
                        print(f"[NANO BANANA] AI returned {res_w}x{res_h}, target is {width}x{height}")
                        
                        resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                        
                        # Calculate target aspect ratio
                        target_ratio = width / height
                        result_ratio = res_w / res_h
                        
                        if abs(target_ratio - result_ratio) > 0.01:
                            # Aspect ratios differ — crop to match target ratio first
                            if result_ratio > target_ratio:
                                # Result is wider than target → crop sides
                                new_w = int(res_h * target_ratio)
                                left = (res_w - new_w) // 2
                                result_img = result_img.crop((left, 0, left + new_w, res_h))
                                print(f"[NANO BANANA] Cropped width: {res_w} → {new_w} (removed {res_w - new_w}px sides)")
                            else:
                                # Result is taller than target → crop top/bottom
                                new_h = int(res_w / target_ratio)
                                top = (res_h - new_h) // 2
                                result_img = result_img.crop((0, top, res_w, top + new_h))
                                print(f"[NANO BANANA] Cropped height: {res_h} → {new_h} (removed {res_h - new_h}px top/bottom)")
                        
                        # Now resize to exact target (same aspect ratio, no distortion)
                        result_img = result_img.resize((width, height), resample_filter)
                        print(f"[NANO BANANA] Resized to exact target: {width}x{height}")
                        
                        out_bytes = io.BytesIO()
                        if result_img.mode not in ('RGB', 'RGBA'):
                            result_img = result_img.convert('RGB')
                        result_img.save(out_bytes, format='PNG')
                        image_data = out_bytes.getvalue()
                    else:
                        print(f"[NANO BANANA] AI result matches target dimensions perfectly: {width}x{height}")
            except Exception as e:
                print(f"[NANO BANANA] Warning: Could not post-process result: {e}")
            
            self.result_image_data = image_data
            
            def update_scene_props():
                if hasattr(bpy.context.scene, 'gemini_render'):
                    props = bpy.context.scene.gemini_render
                    props.beta_balance = new_balance
                    props.last_generation_id = int(generation_id) if generation_id else 0
                    props.last_generation_rated = False
            self._execute_in_main_thread(update_scene_props)
            
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
                from .threading_utils import ensure_image_editor_visible
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
                    print("[NANO BANANA] Set colorspace to sRGB")
                
                new_image.pack()  # Pack into blend file
                
                print(f"[NANO BANANA] Loaded result as: {new_image_name}")
                
                # Switch to new image in ALL Image Editor windows
                if ensure_image_editor_visible(new_image):
                    print("[NANO BANANA] All Image Editors updated")
                else:
                    print("[NANO BANANA] Warning: No Image Editor found to display result")
                
                # Store for history
                self.result_path_for_history = result_path
                self.result_image_name_for_history = new_image_name
                
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
                history_item.prompt = self.user_prompt
                
                # Use the generated image for history (if available)
                if hasattr(self, 'result_image_name_for_history'):
                    history_item.image_name = self.result_image_name_for_history
                    history_item.filepath = getattr(self, 'result_path_for_history', "")
                else:
                    history_item.image_name = self.original_image_name
                    
                history_item.original_image_name = self.original_image_name
                    
                history_item.timestamp = datetime.now().strftime("%H:%M:%S")
                history_item.has_mask = bool(self.mask_path)
                
                # Store smart points JSON if present
                if hasattr(history_item, 'smart_points_json'):
                    history_item.smart_points_json = self.smart_points_json
                
                print(f"[NANO BANANA] Added edit to history: {self.user_prompt[:50]}")
                
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

