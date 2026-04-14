import bpy
import numpy as np
import os
import tempfile
from typing import Optional, Tuple

class DepthRenderError(Exception):
    """Custom exception for depth rendering errors"""
    pass

class DepthRenderer:
    """Handles depth map rendering and normalization"""
    
    def __init__(self):
        self.temp_files = []
        self.temp_dirs = []  # Track temporary directories too
    
    def cleanup_temp_files(self):
        """Clean up temporary files AND directories completely"""
        print("[GEMINI] Starting cleanup of temporary files and directories...")
        
        # Clean up individual files
        files_cleaned = 0
        for filepath in self.temp_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    files_cleaned += 1
                    print(f"[GEMINI] Removed temp file: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"[GEMINI] Could not remove temp file {filepath}: {e}")
        
        # Clean up temporary directories (with all contents)
        dirs_cleaned = 0
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
                    dirs_cleaned += 1
                    print(f"[GEMINI] Removed temp directory: {os.path.basename(temp_dir)}")
            except Exception as e:
                print(f"[GEMINI] Could not remove temp directory {temp_dir}: {e}")
        
        # Clear tracking lists
        self.temp_files.clear()
        self.temp_dirs.clear()
        
        print(f"[GEMINI] Cleanup completed: {files_cleaned} files, {dirs_cleaned} directories removed")
    
    
    def validate_scene(self, scene) -> None:
        """Validate scene is ready for rendering"""
        # Check camera
        if not scene.camera:
            raise DepthRenderError("No active camera found. Please add a camera to the scene.")
        
        # Check objects
        visible_objects = [obj for obj in scene.objects if obj.visible_get()]
        if len(visible_objects) == 0:
            raise DepthRenderError("No visible objects found. Please add some objects to the scene.")
        
        # Check render engine supports Z pass
        if scene.render.engine not in ['CYCLES', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT']:
            print(f"Warning: Render engine {scene.render.engine} may not support depth pass properly")
    
    def render_depth_map_mist(self, scene, mist_start: float = 5.0, mist_depth: float = 25.0, mist_falloff: str = 'LINEAR') -> str:
        """
        Fast depth map generation using viewport render with Mist Pass - REAL depth info!
        """
        try:
            # Validate scene
            self.validate_scene(scene)
            print("[GEMINI] Scene validation passed")
            
            # Create temporary directory for output
            temp_dir = tempfile.mkdtemp(prefix="gemini_depth_mist_")
            depth_path = os.path.join(temp_dir, "mist_depth.png")
            self.temp_files.append(depth_path)
            self.temp_dirs.append(temp_dir)  # Track directory for cleanup
            print(f"[GEMINI] Created temp directory: {temp_dir}")
            
            import bpy
            
            # Store original settings to restore later
            original_use_mist = None
            original_mist_start = None
            original_mist_depth = None
            original_mist_falloff = None
            original_render_engine = scene.render.engine
            original_use_pass_mist = None
            original_use_pass_combined = None
            original_use_nodes = scene.use_nodes
            
            try:
                print("[GEMINI] Setting up Mist Pass for depth rendering...")
                
                # Setup World mist settings
                world = scene.world
                if world is None:
                    # Create world if it doesn't exist
                    world = bpy.data.worlds.new("TempWorld")
                    scene.world = world
                    print("[GEMINI] Created temporary world")
                
                # Store original world settings (Blender 4.5+ uses mist_settings)
                if hasattr(world, 'mist_settings') and world.mist_settings:
                    mist_settings = world.mist_settings
                    original_use_mist = mist_settings.use_mist if hasattr(mist_settings, 'use_mist') else False
                    original_mist_start = mist_settings.start if hasattr(mist_settings, 'start') else 5.0
                    original_mist_depth = mist_settings.depth if hasattr(mist_settings, 'depth') else 25.0
                    original_mist_falloff = mist_settings.falloff if hasattr(mist_settings, 'falloff') else 'QUADRATIC'
                    
                    # Configure mist settings (Blender 4.5+ API)
                    mist_settings.use_mist = True
                    mist_settings.start = mist_start  # Already in meters
                    mist_settings.depth = mist_depth  # Already in meters 
                    mist_settings.falloff = mist_falloff  # Use user-selected falloff
                    
                    print(f"[GEMINI] Mist settings (4.5+ API): start={mist_settings.start}m, depth={mist_settings.depth}m, falloff={mist_falloff}")
                else:
                    # Fallback for older Blender versions
                    original_use_mist = getattr(world, 'use_mist', False)
                    original_mist_start = getattr(world, 'mist_start', 5.0)
                    original_mist_depth = getattr(world, 'mist_depth', 25.0)
                    original_mist_falloff = getattr(world, 'mist_falloff', 'QUADRATIC')
                    
                    # Try old API (might not exist in 4.5+)
                    setattr(world, 'use_mist', True)
                    setattr(world, 'mist_start', mist_start)  # Already in meters
                    setattr(world, 'mist_depth', mist_depth)  # Already in meters
                    setattr(world, 'mist_falloff', mist_falloff)  # Use user-selected falloff
                    
                    print(f"[GEMINI] Mist settings (legacy API): start={mist_start}m, depth={mist_depth}m, falloff={mist_falloff}")
                
                # Use Eevee Next for fast rendering with Mist Pass support (Blender 4.5+)
                available_engines = ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES', 'BLENDER_WORKBENCH']
                selected_engine = None
                
                for engine in available_engines:
                    try:
                        scene.render.engine = engine
                        selected_engine = engine
                        print(f"[GEMINI] Using render engine: {engine}")
                        break
                    except TypeError:
                        continue
                
                if not selected_engine:
                    raise DepthRenderError("No compatible render engine found")
                
                # Enable ONLY Mist Pass, disable Combined pass for pure depth
                view_layer = self._get_active_view_layer(scene)
                if view_layer:
                    original_use_pass_mist = getattr(view_layer, 'use_pass_mist', False)
                    original_use_pass_combined = getattr(view_layer, 'use_pass_combined', True)
                    
                    if hasattr(view_layer, 'use_pass_mist'):
                        view_layer.use_pass_mist = True
                        print("[GEMINI] Mist pass enabled in view layer")
                        
                        # Disable Combined pass for pure mist render
                        if hasattr(view_layer, 'use_pass_combined'):
                            view_layer.use_pass_combined = False
                            print("[GEMINI] Combined pass disabled - pure mist only")
                    else:
                        print("[GEMINI] Warning: View layer found but no mist pass support")
                else:
                    print("[GEMINI] Warning: No view layer found, continuing without mist pass")
                    original_use_pass_mist = False
                    original_use_pass_combined = True
                
                # Use VIEWPORT render with mist shading for accurate depth
                return self._render_viewport_mist(scene, temp_dir, selected_engine, mist_falloff)
                
            finally:
                # Restore original world settings (Blender 4.5+ compatible)
                if scene.world:
                    if hasattr(scene.world, 'mist_settings') and scene.world.mist_settings:
                        # Blender 4.5+ API
                        mist_settings = scene.world.mist_settings
                        if original_use_mist is not None:
                            mist_settings.use_mist = original_use_mist
                        if original_mist_start is not None:
                            mist_settings.start = original_mist_start
                        if original_mist_depth is not None:
                            mist_settings.depth = original_mist_depth
                        if original_mist_falloff is not None:
                            mist_settings.falloff = original_mist_falloff
                    else:
                        # Fallback for older versions (might not work in 4.5+)
                        try:
                            if original_use_mist is not None:
                                setattr(scene.world, 'use_mist', original_use_mist)
                            if original_mist_start is not None:
                                setattr(scene.world, 'mist_start', original_mist_start)
                            if original_mist_depth is not None:
                                setattr(scene.world, 'mist_depth', original_mist_depth)
                            if original_mist_falloff is not None:
                                setattr(scene.world, 'mist_falloff', original_mist_falloff)
                        except AttributeError:
                            pass  # Legacy API not available in modern Blender
                
                # Restore view layer settings
                view_layer = self._get_active_view_layer(scene)
                if view_layer:
                    try:
                        if hasattr(view_layer, 'use_pass_mist') and original_use_pass_mist is not None:
                            view_layer.use_pass_mist = original_use_pass_mist
                        if hasattr(view_layer, 'use_pass_combined') and original_use_pass_combined is not None:
                            view_layer.use_pass_combined = original_use_pass_combined
                    except Exception:
                        pass
                
                # Restore compositor settings
                if original_use_nodes is not None:
                    scene.use_nodes = original_use_nodes
                
                # Restore render engine
                scene.render.engine = original_render_engine
                
                print("[GEMINI] World and render settings restored")
                
        except Exception as e:
            print(f"[GEMINI] Mist depth render error: {str(e)}")
            # CRITICAL: Only cleanup on error!
            self.cleanup_temp_files()
            if isinstance(e, DepthRenderError):
                raise
            raise DepthRenderError(f"Failed to render mist depth map: {str(e)}")
    
    def _get_active_view_layer(self, scene):
        """Get active view layer with fallback for different Blender versions."""
        
        # Method 1: Try context (preferred in 4.5+)
        try:
            if bpy.context.view_layer and bpy.context.view_layer.name in scene.view_layers:
                return bpy.context.view_layer
        except Exception:
            pass
            
        # Method 2: Try scene.view_layers.active (older versions)
        try:
            if hasattr(scene.view_layers, 'active') and scene.view_layers.active:
                return scene.view_layers.active
        except Exception:
            pass
            
        # Method 3: Get first view layer as fallback
        try:
            if len(scene.view_layers) > 0:
                return scene.view_layers[0]  # Default view layer
        except Exception:
            pass
            
        # Method 4: Create view layer if none exist (extreme fallback)
        print("[GEMINI] Warning: No view layer found, using scene fallback")
        return None
    

    def _render_viewport_mist(self, scene, temp_dir: str, render_engine: str, mist_falloff: str = 'LINEAR') -> str:
        """Render VIEWPORT with mist shading from camera - accurate depth like in viewport"""
        try:
            import bpy
            
            print("[GEMINI] Setting up VIEWPORT mist render from camera...")
            
            # Store original settings
            original_filepath = scene.render.filepath
            original_shading_type = None
            original_render_pass = None
            original_use_scene_world = None
            original_overlays = {}
            original_show_gizmo = None
            original_show_gizmo_navigate = None
            original_region_3d = None
            space_data = None
            overlay = None
            
            mist_output_path = os.path.join(temp_dir, "viewport_mist.png")
            
            # Track temp directory and files
            if temp_dir not in self.temp_dirs:
                self.temp_dirs.append(temp_dir)
            self.temp_files.append(mist_output_path)
            
            try:
                # Get 3D viewport area, window, and screen
                viewport_window = None
                viewport_screen = None
                viewport_area = None
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            viewport_window = window
                            viewport_screen = window.screen
                            viewport_area = area
                            break
                    if viewport_area:
                        break
                
                if not viewport_area:
                    print("[GEMINI] No 3D viewport found, creating temporary context")
                    # Fallback if no viewport found
                    raise DepthRenderError("No 3D viewport available for mist render")
                
                # Get space_data (viewport settings)
                space_data = None
                for space in viewport_area.spaces:
                    if space.type == 'VIEW_3D':
                        space_data = space
                        break
                
                if not space_data:
                    raise DepthRenderError("Cannot access viewport settings")
                
                # Store original viewport settings
                original_shading_type = space_data.shading.type
                original_render_pass = space_data.shading.render_pass if hasattr(space_data.shading, 'render_pass') else None
                original_use_scene_world = space_data.shading.use_scene_world if hasattr(space_data.shading, 'use_scene_world') else None
                
                # Store ALL overlay settings to disable them
                overlay = space_data.overlay
                original_overlays = {
                    'show_overlays': overlay.show_overlays if hasattr(overlay, 'show_overlays') else None,
                    'show_floor': overlay.show_floor if hasattr(overlay, 'show_floor') else None,
                    'show_axis_x': overlay.show_axis_x if hasattr(overlay, 'show_axis_x') else None,
                    'show_axis_y': overlay.show_axis_y if hasattr(overlay, 'show_axis_y') else None,
                    'show_axis_z': overlay.show_axis_z if hasattr(overlay, 'show_axis_z') else None,
                    'show_text': overlay.show_text if hasattr(overlay, 'show_text') else None,
                    'show_stats': overlay.show_stats if hasattr(overlay, 'show_stats') else None,
                    'show_cursor': overlay.show_cursor if hasattr(overlay, 'show_cursor') else None,
                    'show_object_origins': overlay.show_object_origins if hasattr(overlay, 'show_object_origins') else None,
                    'show_relationship_lines': overlay.show_relationship_lines if hasattr(overlay, 'show_relationship_lines') else None,
                }
                
                # Store gizmo settings
                original_show_gizmo = space_data.show_gizmo if hasattr(space_data, 'show_gizmo') else None
                original_show_gizmo_navigate = space_data.show_gizmo_navigate if hasattr(space_data, 'show_gizmo_navigate') else None
                
                # Store camera view state
                original_region_3d = None
                for region in viewport_area.regions:
                    if region.type == 'WINDOW':
                        region_3d = space_data.region_3d
                        if region_3d:
                            original_region_3d = {
                                'view_perspective': region_3d.view_perspective,
                            }
                        break
                
                print(f"[GEMINI] Original viewport shading: {original_shading_type}")
                
                # CRITICAL: Switch viewport to CAMERA VIEW
                if space_data.region_3d:
                    space_data.region_3d.view_perspective = 'CAMERA'
                    print("[GEMINI] Switched viewport to CAMERA VIEW")
                
                # CRITICAL: Set viewport to MATERIAL shading with MIST pass!
                space_data.shading.type = 'MATERIAL'
                
                # CRITICAL: Set render pass to MIST (this is what shows mist!)
                if hasattr(space_data.shading, 'render_pass'):
                    space_data.shading.render_pass = 'MIST'
                    print("[GEMINI] Set viewport render_pass to MIST!")
                else:
                    print("[GEMINI] WARNING: render_pass not available in shading")
                
                # Enable scene world (for mist to work)
                if hasattr(space_data.shading, 'use_scene_world'):
                    space_data.shading.use_scene_world = True
                    print("[GEMINI] Enabled use_scene_world for mist")
                
                # CRITICAL: DISABLE ALL OVERLAYS (grid, axes, text, gizmos, etc.)
                if hasattr(overlay, 'show_overlays'):
                    overlay.show_overlays = False
                    print("[GEMINI] DISABLED all overlays")
                
                # Disable gizmos
                if hasattr(space_data, 'show_gizmo'):
                    space_data.show_gizmo = False
                    print("[GEMINI] DISABLED gizmos")
                if hasattr(space_data, 'show_gizmo_navigate'):
                    space_data.show_gizmo_navigate = False
                    print("[GEMINI] DISABLED gizmo navigate")
                
                print("[GEMINI] Viewport configured for clean camera mist rendering (no overlays)")
                
                # Set render output
                scene.render.filepath = mist_output_path
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_mode = 'BW'
                scene.render.image_settings.color_depth = '16'
                
                print("[GEMINI] Starting viewport render with mist from camera...")
                
                # Execute viewport render
                override_context = {
                    'window': viewport_window,
                    'screen': viewport_screen,
                    'scene': scene,
                    'area': viewport_area,
                    'region': viewport_area.regions[-1],
                    'space_data': space_data,
                }
                
                with bpy.context.temp_override(**override_context):
                    result = bpy.ops.render.opengl(write_still=True)
                    print(f"[GEMINI] OpenGL mist render result: {result}")
                
                print(f"[GEMINI] Viewport mist render completed")
                
                # Find output file
                if os.path.exists(mist_output_path):
                    print(f"[GEMINI] Viewport mist saved: {mist_output_path}")
                    return mist_output_path
                else:
                    # Try with numbering
                    import glob
                    viewport_pattern = os.path.join(temp_dir, "viewport_mist*.png")
                    viewport_files = glob.glob(viewport_pattern)
                    
                    if viewport_files:
                        actual_path = viewport_files[0]
                        print(f"[GEMINI] Found viewport mist: {actual_path}")
                        return actual_path
                    else:
                        raise DepthRenderError("Viewport mist output not found after render")
            
            finally:
                # Restore viewport settings
                if space_data:
                    try:
                        # Restore render pass FIRST (before changing shading type)
                        if original_render_pass is not None and hasattr(space_data.shading, 'render_pass'):
                            space_data.shading.render_pass = original_render_pass
                        
                        # Restore shading type
                        if original_shading_type:
                            space_data.shading.type = original_shading_type
                        
                        # Restore scene world setting
                        if original_use_scene_world is not None and hasattr(space_data.shading, 'use_scene_world'):
                            space_data.shading.use_scene_world = original_use_scene_world
                        
                        # Restore ALL overlay settings
                        if overlay and original_overlays:
                            for key, value in original_overlays.items():
                                if value is not None and hasattr(overlay, key):
                                    try:
                                        setattr(overlay, key, value)
                                    except Exception:
                                        pass
                        
                        # Restore gizmo settings
                        if original_show_gizmo is not None and hasattr(space_data, 'show_gizmo'):
                            space_data.show_gizmo = original_show_gizmo
                        if original_show_gizmo_navigate is not None and hasattr(space_data, 'show_gizmo_navigate'):
                            space_data.show_gizmo_navigate = original_show_gizmo_navigate
                        
                        # Restore camera view
                        if original_region_3d and space_data.region_3d:
                            space_data.region_3d.view_perspective = original_region_3d['view_perspective']
                        
                        print("[GEMINI] Viewport settings restored (overlays, gizmos, camera view)")
                    except Exception as e:
                        print(f"[GEMINI] Error restoring viewport: {e}")
                
                # Restore render filepath
                scene.render.filepath = original_filepath
                
        except Exception as e:
            raise DepthRenderError(f"Viewport mist render failed: {str(e)}")
    

    def render_regular_eevee(self, scene) -> str:
        """
        Render using regular Eevee/Cycles - preserves colors, textures, lighting.
        Returns path to rendered image.
        """
        try:
            # Validate scene
            self.validate_scene(scene)
            print("[GEMINI] Scene validation passed for regular render")
            
            # Create temporary directory for output
            temp_dir = tempfile.mkdtemp(prefix="gemini_regular_render_")
            render_path = os.path.join(temp_dir, "regular_render.png")
            self.temp_files.append(render_path)
            self.temp_dirs.append(temp_dir)
            print(f"[GEMINI] Created temp directory: {temp_dir}")
            
            import bpy
            
            # Store original settings
            original_filepath = scene.render.filepath
            original_file_format = scene.render.image_settings.file_format
            original_color_mode = scene.render.image_settings.color_mode
            original_color_depth = scene.render.image_settings.color_depth
            original_engine = scene.render.engine
            original_samples = None
            
            # Store color management settings for viewport-like render
            original_view_transform = scene.view_settings.view_transform
            original_look = scene.view_settings.look
            original_exposure = scene.view_settings.exposure
            original_gamma = scene.view_settings.gamma
            
            try:
                print("[GEMINI] Setting up regular render...")
                
                # Detect available Eevee engine (Blender 5.0 uses BLENDER_EEVEE_NEXT, 4.5 uses BLENDER_EEVEE)
                import bpy
                available_eevee = None
                for engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    try:
                        # Test if engine exists by checking enum items
                        if engine in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]:
                            available_eevee = engine
                            break
                    except Exception:
                        continue
                
                if not available_eevee:
                    available_eevee = 'BLENDER_EEVEE'  # Fallback
                
                # Keep current engine or use available Eevee
                if scene.render.engine == 'CYCLES':
                    print("[GEMINI] Using CYCLES (current engine)")
                    # Store Cycles samples
                    if hasattr(scene.cycles, 'samples'):
                        original_samples = scene.cycles.samples
                        # Use current samples or ensure minimum quality
                        if scene.cycles.samples < 64:
                            scene.cycles.samples = 64
                            print(f"[GEMINI] Increased Cycles samples to 64 for quality")
                elif scene.render.engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    print(f"[GEMINI] Using {scene.render.engine} (current engine)")
                    # Ensure good quality for Eevee
                    if hasattr(scene.eevee, 'taa_render_samples'):
                        original_samples = scene.eevee.taa_render_samples
                        if scene.eevee.taa_render_samples < 64:
                            scene.eevee.taa_render_samples = 64
                            print(f"[GEMINI] Increased Eevee samples to 64 for quality")
                else:
                    # Switch to available Eevee engine
                    scene.render.engine = available_eevee
                    print(f"[GEMINI] Switched to {available_eevee}")
                    
                    # Ensure good quality
                    if hasattr(scene.eevee, 'taa_render_samples'):
                        original_samples = scene.eevee.taa_render_samples
                        if scene.eevee.taa_render_samples < 64:
                            scene.eevee.taa_render_samples = 64
                            print(f"[GEMINI] Set Eevee samples to 64 for quality")
                
                # Configure render output for viewport-like rendering (RGB, no alpha)
                scene.render.filepath = render_path
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_mode = 'RGB'  # RGB without alpha - like viewport
                scene.render.image_settings.color_depth = '8'  # Standard 8-bit color
                scene.render.image_settings.compression = 15  # PNG compression
                
                # Use Standard view transform for viewport-like colors (not Filmic which adds contrast)
                scene.view_settings.view_transform = 'Standard'
                scene.view_settings.look = 'None'
                # Keep current exposure and gamma (or reset to defaults)
                # scene.view_settings.exposure = 0.0
                # scene.view_settings.gamma = 1.0
                
                print(f"[GEMINI] Render settings: {scene.render.engine}, color_mode=RGB, view_transform=Standard, resolution={scene.render.resolution_x}x{scene.render.resolution_y}")
                
                # Ensure render resolution is good
                print(f"[GEMINI] Resolution: {scene.render.resolution_x}x{scene.render.resolution_y} @ {scene.render.resolution_percentage}%")
                
                # Execute render
                # Execute viewport/OpenGL render instead of regular render to avoid infinite engine loop
                print("[GEMINI] Starting regular Eevee viewport render...")
                
                # Find viewport area, window, screen to render from
                viewport_window = None
                viewport_screen = None
                viewport_area = None
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            viewport_window = window
                            viewport_screen = window.screen
                            viewport_area = area
                            break
                    if viewport_area:
                        break
                
                if not viewport_area:
                    raise DepthRenderError("No 3D viewport found for Eevee rendering")
                    
                space_data = None
                for space in viewport_area.spaces:
                    if space.type == 'VIEW_3D':
                        space_data = space
                        break
                        
                # Store viewport original settings
                original_shading_type = space_data.shading.type
                original_use_scene_lights = getattr(space_data.shading, 'use_scene_lights', None)
                original_use_scene_world = getattr(space_data.shading, 'use_scene_world', None)
                original_render_pass = getattr(space_data.shading, 'render_pass', None)
                overlay = space_data.overlay
                original_show_overlays = getattr(overlay, 'show_overlays', None)
                original_show_gizmo = getattr(space_data, 'show_gizmo', None)
                
                original_region_3d = None
                for region in viewport_area.regions:
                    if region.type == 'WINDOW':
                        original_region_3d = {'view_perspective': space_data.region_3d.view_perspective}
                        break
                
                try:
                    # Switch to Camera View
                    if space_data.region_3d:
                        space_data.region_3d.view_perspective = 'CAMERA'
                        
                    # Set up Eevee shading
                    space_data.shading.type = 'MATERIAL' # Material Preview/Rendered
                    if hasattr(space_data.shading, 'use_scene_lights'):
                        space_data.shading.use_scene_lights = True
                    if hasattr(space_data.shading, 'use_scene_world'):
                        space_data.shading.use_scene_world = True
                    if hasattr(space_data.shading, 'render_pass'):
                        space_data.shading.render_pass = 'COMBINED'
                        
                    # Disable overlays
                    if hasattr(overlay, 'show_overlays'):
                        overlay.show_overlays = False
                    if hasattr(space_data, 'show_gizmo'):
                        space_data.show_gizmo = False
                        
                    # Execute render
                    override_context = {
                        'window': viewport_window,
                        'screen': viewport_screen,
                        'scene': scene,
                        'area': viewport_area,
                        'region': viewport_area.regions[-1],
                        'space_data': space_data,
                    }
                    
                    with bpy.context.temp_override(**override_context):
                        result = bpy.ops.render.opengl(write_still=True)
                        print(f"[GEMINI] OpenGL EEVEE render result: {result}")
                        
                finally:
                    # Restore viewport settings
                    if original_shading_type:
                        space_data.shading.type = original_shading_type
                    if original_use_scene_lights is not None and hasattr(space_data.shading, 'use_scene_lights'):
                        space_data.shading.use_scene_lights = original_use_scene_lights
                    if original_use_scene_world is not None and hasattr(space_data.shading, 'use_scene_world'):
                        space_data.shading.use_scene_world = original_use_scene_world
                    if original_render_pass is not None and hasattr(space_data.shading, 'render_pass'):
                        space_data.shading.render_pass = original_render_pass
                    if original_show_overlays is not None and hasattr(overlay, 'show_overlays'):
                        overlay.show_overlays = original_show_overlays
                    if original_show_gizmo is not None and hasattr(space_data, 'show_gizmo'):
                        space_data.show_gizmo = original_show_gizmo
                    if original_region_3d and space_data.region_3d:
                        space_data.region_3d.view_perspective = original_region_3d['view_perspective']
                
                print(f"[GEMINI] Regular viewport render completed: {render_path}")
                
                # Check for image
                if not os.path.exists(render_path):
                    # Check for numbered versions
                    import glob
                    pattern = render_path.replace('.png', '*.png')
                    matches = glob.glob(pattern)
                    if matches:
                        render_path = matches[0]
                    else:
                        raise DepthRenderError("Render file not created.")
                
                print(f"[GEMINI] Render file size: {os.path.getsize(render_path)} bytes")
                
                return render_path
                
            finally:
                # Restore original settings
                scene.render.filepath = original_filepath
                scene.render.image_settings.file_format = original_file_format
                scene.render.image_settings.color_mode = original_color_mode
                scene.render.image_settings.color_depth = original_color_depth
                scene.render.engine = original_engine
                
                # Restore color management settings
                scene.view_settings.view_transform = original_view_transform
                scene.view_settings.look = original_look
                scene.view_settings.exposure = original_exposure
                scene.view_settings.gamma = original_gamma
                
                # Restore samples
                if original_samples is not None:
                    if scene.render.engine == 'CYCLES' and hasattr(scene.cycles, 'samples'):
                        scene.cycles.samples = original_samples
                    elif hasattr(scene.eevee, 'taa_render_samples'):
                        scene.eevee.taa_render_samples = original_samples
                
                print("[GEMINI] Restored original render settings and color management")
                
        except Exception as e:
            raise DepthRenderError(f"Regular render failed: {str(e)}")
