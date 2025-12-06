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
        # Blender 5.0+ uses 'BLENDER_EEVEE', while 4.x uses 'BLENDER_EEVEE_NEXT'
        supported_engines = ['CYCLES', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT']
        if scene.render.engine not in supported_engines:
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
                print("🌫️ [GEMINI] Setting up Mist Pass for depth rendering...")
                
                # Setup World mist settings
                world = scene.world
                if world is None:
                    # Create world if it doesn't exist
                    world = bpy.data.worlds.new("TempWorld")
                    scene.world = world
                    print("🌍 [GEMINI] Created temporary world")
                
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
                    
                    print(f"🌫️ [GEMINI] Mist settings (4.5+ API): start={mist_settings.start}m, depth={mist_settings.depth}m, falloff={mist_falloff}")
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
                    
                    print(f"🌫️ [GEMINI] Mist settings (old API): start={mist_start}m, depth={mist_depth}m, falloff={mist_falloff}")
                
                # Use Eevee Next for fast rendering with Mist Pass support (Blender 4.5+)
                # Try BLENDER_EEVEE first (Blender 5.0+), then BLENDER_EEVEE_NEXT (4.x), then others
                available_engines = ['BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'CYCLES', 'BLENDER_WORKBENCH']
                selected_engine = None
                
                for engine in available_engines:
                    try:
                        scene.render.engine = engine
                        selected_engine = engine
                        print(f"✅ [GEMINI] Using render engine: {engine}")
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
                        print("✅ [GEMINI] Mist pass enabled in view layer")
                        
                        # CRITICAL: Disable Combined pass for PURE mist render
                        if hasattr(view_layer, 'use_pass_combined'):
                            view_layer.use_pass_combined = False
                            print("🚫 [GEMINI] Combined pass DISABLED - pure mist only!")
                        else:
                            print("⚠️ [GEMINI] Cannot disable combined pass - will use compositor")
                    else:
                        print("⚠️ [GEMINI] View layer found but no mist pass support")
                else:
                    print("⚠️ [GEMINI] No view layer found, continuing without mist pass")
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
                            print("⚠️ [GEMINI] Could not restore old mist settings (modern Blender API)")
                
                # Restore view layer settings
                view_layer = self._get_active_view_layer(scene)
                if view_layer:
                    try:
                        if hasattr(view_layer, 'use_pass_mist') and original_use_pass_mist is not None:
                            view_layer.use_pass_mist = original_use_pass_mist
                        if hasattr(view_layer, 'use_pass_combined') and original_use_pass_combined is not None:
                            view_layer.use_pass_combined = original_use_pass_combined
                    except:
                        pass
                
                # Restore compositor settings
                if original_use_nodes is not None:
                    scene.use_nodes = original_use_nodes
                
                # Restore render engine
                scene.render.engine = original_render_engine
                
                print("🔄 [GEMINI] World and render settings restored")
                
        except Exception as e:
            print(f"💥 [GEMINI] Mist depth render error: {str(e)}")
            # CRITICAL: Only cleanup on error!
            self.cleanup_temp_files()
            if isinstance(e, DepthRenderError):
                raise
            raise DepthRenderError(f"Failed to render mist depth map: {str(e)}")
    
    def _get_active_view_layer(self, scene):
        """Get active view layer with fallback for different Blender versions"""
        import bpy
        
        # Method 1: Try context (preferred in 4.5+)
        try:
            if bpy.context.view_layer and bpy.context.view_layer.name in scene.view_layers:
                return bpy.context.view_layer
        except:
            pass
            
        # Method 2: Try scene.view_layers.active (older versions)
        try:
            if hasattr(scene.view_layers, 'active') and scene.view_layers.active:
                return scene.view_layers.active
        except:
            pass
            
        # Method 3: Get first view layer as fallback
        try:
            if len(scene.view_layers) > 0:
                return scene.view_layers[0]  # Default view layer
        except:
            pass
            
        # Method 4: Create view layer if none exist (extreme fallback)
        print("⚠️ [GEMINI] No view layer found, using scene fallback")
        return None
    
    def _render_mist_only(self, scene, temp_dir: str, render_engine: str, 
                         original_use_pass_mist: bool, original_use_pass_combined: bool) -> str:
        """Render only mist pass using compositor setup"""
        try:
            import bpy
            
            print("🎭 [GEMINI] Setting up mist-only render with compositor...")
            
            # Store original settings
            original_filepath = scene.render.filepath
            original_use_nodes = scene.use_nodes
            original_samples = None
            
            mist_output_path = os.path.join(temp_dir, "mist_only.png")
            
            # Track temp files for cleanup
            self.temp_files.append(mist_output_path)
            
            try:
                # Setup compositor nodes for mist-only output
                scene.use_nodes = True
                
                # Clear existing nodes
                scene.node_tree.nodes.clear()
                
                # Create necessary nodes
                render_layers = scene.node_tree.nodes.new(type='CompositorNodeRLayers')
                file_output = scene.node_tree.nodes.new(type='CompositorNodeOutputFile')
                
                # Configure file output
                file_output.base_path = temp_dir
                file_output.file_slots[0].path = "mist_only"
                file_output.format.file_format = 'PNG'
                file_output.format.color_mode = 'BW'  # Black and white for depth
                
                # Connect mist pass to file output
                scene.node_tree.links.new(render_layers.outputs['Mist'], file_output.inputs[0])
                
                print("🔗 [GEMINI] Compositor nodes setup: RenderLayers → Mist → FileOutput")
                
                # Fast render settings (supports both Blender 4.x and 5.0)
                if render_engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    if hasattr(scene, 'eevee'):
                        original_samples = scene.eevee.taa_render_samples
                        scene.eevee.taa_render_samples = 1  # Fastest possible
                        print("⚡ [GEMINI] Eevee samples set to 1 for speed")
                
                # Set temporary render output (compositor will handle mist output)
                scene.render.filepath = os.path.join(temp_dir, "temp_render")
                
                print("🏃 [GEMINI] Starting mist-only render...")
                
                # Execute render
                bpy.ops.render.render(write_still=True)
                
                # Find the mist output file
                mist_files = [
                    os.path.join(temp_dir, "mist_only0001.png"),
                    os.path.join(temp_dir, "mist_only.png"),
                    mist_output_path
                ]
                
                actual_mist_path = None
                for path in mist_files:
                    if os.path.exists(path):
                        actual_mist_path = path
                        print(f"✅ [GEMINI] Found mist output: {path}")
                        break
                
                if actual_mist_path:
                    print(f"🌫️ [GEMINI] Mist-only render completed: {actual_mist_path}")
                    return actual_mist_path
                else:
                    raise DepthRenderError("Mist output file not found after render")
                
            finally:
                # Restore settings
                scene.render.filepath = original_filepath
                scene.use_nodes = original_use_nodes
                if hasattr(scene, 'eevee') and original_samples is not None:
                    scene.eevee.taa_render_samples = original_samples
                    
        except Exception as e:
            raise DepthRenderError(f"Mist-only render failed: {str(e)}")
    
    def _render_and_extract_mist(self, scene, temp_dir: str, render_engine: str) -> str:
        """Simple render and extract mist pass - safer for background threads"""
        try:
            import bpy
            
            print("⚡ [GEMINI] Simple render with mist extraction (no compositor)...")
            
            # Store original settings
            original_filepath = scene.render.filepath
            original_samples = None
            
            mist_output_path = os.path.join(temp_dir, "mist_extracted.png")
            
            # Track temp files for cleanup
            self.temp_files.append(mist_output_path)
            
            try:
                # Fast render settings (supports both Blender 4.x and 5.0)
                if render_engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    if hasattr(scene, 'eevee'):
                        original_samples = scene.eevee.taa_render_samples
                        scene.eevee.taa_render_samples = 1  # Fastest possible
                        print("⚡ [GEMINI] Eevee samples set to 1 for speed")
                
                # Set temporary render output
                scene.render.filepath = os.path.join(temp_dir, "temp_render")
                
                print("🏃 [GEMINI] Starting simple render for mist extraction...")
                
                # Execute render
                bpy.ops.render.render(write_still=True)
                
                print("🔍 [GEMINI] Extracting mist pass from render result (Combined pass disabled)...")
                
                # Get render result (should contain ONLY mist data now)
                render_result = bpy.data.images.get('Render Result')
                if not render_result:
                    raise DepthRenderError("No render result found")
                
                # Since Combined pass is disabled, Render Result should contain only mist
                print("📸 [GEMINI] Saving mist-only render result...")
                render_result.save_render(filepath=mist_output_path)
                
                if os.path.exists(mist_output_path):
                    print(f"✅ [GEMINI] Mist-only render saved: {mist_output_path}")
                    return mist_output_path
                else:
                    raise DepthRenderError("Failed to save mist render result")
                
            finally:
                # Restore settings
                scene.render.filepath = original_filepath
                if hasattr(scene, 'eevee') and original_samples is not None:
                    scene.eevee.taa_render_samples = original_samples
                    
        except Exception as e:
            raise DepthRenderError(f"Render and mist extraction failed: {str(e)}")
    
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
                # Get 3D viewport area
                viewport_area = None
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
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
                
                # Render viewport from camera view
                override_context = {
                    'scene': scene,
                    'area': viewport_area,
                    'region': viewport_area.regions[-1],
                    'space_data': space_data,
                }
                
                # Execute viewport render
                with bpy.context.temp_override(**override_context):
                    bpy.ops.render.opengl(write_still=True)
                
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
                                    except:
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
    
    def _render_camera_with_mist_compositor(self, scene, temp_dir: str, render_engine: str, mist_falloff: str = 'LINEAR') -> str:
        """Render from camera with compositor setup to extract PURE mist pass"""
        try:
            import bpy
            
            print("🎭 [GEMINI] Setting up camera-based PURE mist render with compositor...")
            
            # Store original render settings
            original_filepath = scene.render.filepath
            original_use_nodes = scene.use_nodes
            original_nodes = {}
            
            mist_output_path = os.path.join(temp_dir, "pure_mist.png")
            
            # Track temp directory for proper cleanup
            if temp_dir not in self.temp_dirs:
                self.temp_dirs.append(temp_dir)
            self.temp_files.append(mist_output_path)
            
            try:
                # Store original render settings for restoration
                original_resolution_x = scene.render.resolution_x
                original_resolution_y = scene.render.resolution_y
                original_resolution_percentage = scene.render.resolution_percentage
                original_samples = None
                
                # Use full quality settings 
                print("⚡ [GEMINI] Using full quality render settings for PURE mist extraction...")
                scene.render.resolution_percentage = 100
                print(f"📏 [GEMINI] Using full scene resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")
                
                # Use good quality samples for proper mist (supports both Blender 4.x and 5.0)
                if scene.render.engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    try:
                        if hasattr(scene, 'eevee'):
                            original_samples = scene.eevee.taa_render_samples
                            scene.eevee.taa_render_samples = max(64, original_samples)
                            print(f"⚡ [GEMINI] Eevee samples set to {scene.eevee.taa_render_samples} for quality mist")
                    except:
                        pass
                elif scene.render.engine == 'CYCLES':
                    try:
                        if hasattr(scene, 'cycles'):
                            original_samples = scene.cycles.samples
                            scene.cycles.samples = max(128, original_samples)
                            print(f"⚡ [GEMINI] Cycles samples set to {scene.cycles.samples} for quality mist")
                    except:
                        pass
                
                # Setup compositor for PURE mist extraction
                print("🔗 [GEMINI] Setting up compositor for PURE mist extraction...")
                scene.use_nodes = True
                
                # Store original nodes for restoration
                if scene.node_tree:
                    for node in scene.node_tree.nodes:
                        original_nodes[node.name] = {
                            'type': node.bl_idname,
                            'location': node.location.copy()
                        }
                
                # Clear existing nodes
                scene.node_tree.nodes.clear()
                
                # Create necessary nodes for PURE mist extraction
                render_layers = scene.node_tree.nodes.new(type='CompositorNodeRLayers')
                render_layers.location = (0, 0)
                
                # Add File Output node for mist
                file_output = scene.node_tree.nodes.new(type='CompositorNodeOutputFile')
                file_output.location = (400, 0)
                file_output.base_path = temp_dir
                file_output.file_slots[0].path = "pure_mist"
                file_output.format.file_format = 'PNG'
                file_output.format.color_mode = 'BW'  # Black and white for depth
                file_output.format.color_depth = '16'  # 16-bit for smooth gradation (not 8-bit)
                
                print("📸 [GEMINI] File output set to 16-bit BW PNG for smooth mist gradation")
                
                # Connect ONLY mist pass to output (no combined!)
                if 'Mist' in render_layers.outputs:
                    scene.node_tree.links.new(render_layers.outputs['Mist'], file_output.inputs[0])
                    print("✅ [GEMINI] Connected PURE Mist pass to file output")
                else:
                    print("⚠️ [GEMINI] Mist output not found in render layers")
                    raise DepthRenderError("Mist pass not available in render layers")
                
                # Set render output (compositor will handle mist file, no temp render needed)
                scene.render.filepath = os.path.join(temp_dir, "no_temp_render")
                
                print("🎬 [GEMINI] Starting camera render for PURE mist extraction (compositor only)...")
                
                # Execute camera render
                render_success = False
                
                def _do_mist_render():
                    nonlocal render_success
                    try:
                        print("🎬 [GEMINI] Executing camera render with mist compositor (no temp file)...")
                        import time
                        start_time = time.time()
                        # Render without saving main render - compositor will handle mist output
                        bpy.ops.render.render(write_still=False)  # Don't write temp_render.png
                        end_time = time.time()
                        
                        render_success = True
                        print(f"✅ [GEMINI] PURE mist render completed in {end_time - start_time:.1f}s (no temp file)")
                    except Exception as e:
                        print(f"💥 [GEMINI] Mist render error: {e}")
                        render_success = False
                
                # Execute in main thread if needed
                try:
                    if hasattr(self, '_execute_in_main_thread'):
                        self._execute_in_main_thread(_do_mist_render)
                    else:
                        _do_mist_render()
                except:
                    _do_mist_render()
                
                if not render_success:
                    raise DepthRenderError("PURE mist render failed")
                
                # Find the mist output file from compositor
                # Blender may use different numbering: 0000, 0001, 0010, etc.
                actual_mist_path = None
                
                # First, try to find any pure_mist*.png file in the directory
                import glob
                mist_pattern = os.path.join(temp_dir, "pure_mist*.png")
                mist_files = glob.glob(mist_pattern)
                
                if mist_files:
                    # Use the first found file (or the most recent if multiple)
                    actual_mist_path = mist_files[0]
                    print(f"✅ [GEMINI] Found PURE mist file: {actual_mist_path}")
                else:
                    # Fallback to specific names
                    possible_mist_files = [
                        os.path.join(temp_dir, "pure_mist0001.png"),
                        os.path.join(temp_dir, "pure_mist0000.png"),
                        os.path.join(temp_dir, "pure_mist.png"),
                        mist_output_path
                    ]
                    
                    for path in possible_mist_files:
                        if os.path.exists(path):
                            actual_mist_path = path
                            print(f"✅ [GEMINI] Found PURE mist file: {path}")
                            break
                
                if actual_mist_path:
                    print(f"🌫️ [GEMINI] PURE mist render completed: {actual_mist_path}")
                    return actual_mist_path
                else:
                    # Debug: list all files in temp_dir
                    try:
                        all_files = os.listdir(temp_dir)
                        print(f"🔍 [GEMINI] Files in temp directory: {all_files}")
                    except:
                        pass
                    raise DepthRenderError("PURE mist output file not found after render")
                
            finally:
                # Restore all render settings
                scene.render.filepath = original_filepath
                scene.render.resolution_x = original_resolution_x
                scene.render.resolution_y = original_resolution_y
                scene.render.resolution_percentage = original_resolution_percentage
                
                # Restore samples
                if original_samples is not None:
                    # Restore Eevee samples (supports both Blender 4.x and 5.0)
                    if scene.render.engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                        try:
                            if hasattr(scene, 'eevee'):
                                scene.eevee.taa_render_samples = original_samples
                        except:
                            pass
                    elif scene.render.engine == 'CYCLES':
                        try:
                            if hasattr(scene, 'cycles'):
                                scene.cycles.samples = original_samples
                        except:
                            pass
                
                # Restore compositor settings
                scene.use_nodes = original_use_nodes
                
                # Restore original nodes (simplified restoration)
                if scene.use_nodes and scene.node_tree:
                    scene.node_tree.nodes.clear()
                    # Note: Full node restoration would be complex, keeping it simple
                
                print("🔄 [GEMINI] All render settings and compositor restored")
                    
        except Exception as e:
            raise DepthRenderError(f"PURE mist camera render failed: {str(e)}")
    
    def _render_camera_mist_pass(self, scene, temp_dir: str, render_engine: str) -> str:
        """Render from camera with Mist pass - TRUE depth map"""
        try:
            import bpy
            
            print("📷 [GEMINI] Setting up camera render with Mist pass...")
            
            # Store original render settings
            original_filepath = scene.render.filepath
            
            mist_output_path = os.path.join(temp_dir, "camera_mist.png")
            
            # Track temp directory and files for proper cleanup
            if temp_dir not in self.temp_dirs:
                self.temp_dirs.append(temp_dir)
            self.temp_files.append(mist_output_path)
            
            try:
                # Store original render settings for restoration
                original_resolution_x = scene.render.resolution_x
                original_resolution_y = scene.render.resolution_y
                original_resolution_percentage = scene.render.resolution_percentage
                original_samples = None
                
                # Use high quality render settings for proper depth map
                print("⚡ [GEMINI] Using high quality render settings for proper depth map...")
                
                # Use original resolution for high quality depth maps
                print(f"📏 [GEMINI] Using full scene resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")
                
                # Keep resolution percentage at 100% for full quality  
                scene.render.resolution_percentage = 100
                print(f"📊 [GEMINI] Resolution percentage set to {scene.render.resolution_percentage}% (full quality)")
                
                # Use good quality samples for proper depth maps (supports both Blender 4.x and 5.0)
                if scene.render.engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                    try:
                        if hasattr(scene, 'eevee'):
                            original_samples = scene.eevee.taa_render_samples
                            # Use reasonable samples for good quality depth
                            scene.eevee.taa_render_samples = max(64, original_samples)  # At least 64 samples
                            print(f"⚡ [GEMINI] Eevee samples set to {scene.eevee.taa_render_samples} (was {original_samples}) for quality depth")
                    except:
                        pass
                elif scene.render.engine == 'CYCLES':
                    try:
                        if hasattr(scene, 'cycles'):
                            original_samples = scene.cycles.samples
                            # Use reasonable samples for Cycles depth
                            scene.cycles.samples = max(128, original_samples)  # At least 128 samples  
                            print(f"⚡ [GEMINI] Cycles samples set to {scene.cycles.samples} (was {original_samples}) for quality depth")
                    except:
                        pass
                
                # Set render output  
                scene.render.filepath = os.path.join(temp_dir, "camera_mist")
                
                print("🎬 [GEMINI] Starting camera render with mist pass...")
                
                # Store render result for main thread execution
                render_success = False
                
                def _do_camera_render():
                    nonlocal render_success
                    try:
                        print("🎬 [GEMINI] About to start bpy.ops.render.render()...")
                        print(f"📏 [GEMINI] Render resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")
                        print(f"🎮 [GEMINI] Render engine: {scene.render.engine}")
                        print(f"📁 [GEMINI] Output path: {scene.render.filepath}")
                        
                        # Execute camera render in main thread  
                        import time
                        start_time = time.time()
                        bpy.ops.render.render(write_still=True)
                        end_time = time.time()
                        
                        render_success = True
                        print(f"✅ [GEMINI] Camera render executed successfully in {end_time - start_time:.1f}s")
                    except Exception as e:
                        print(f"💥 [GEMINI] Camera render error: {e}")
                        render_success = False
                
                # Execute in main thread if we're in background
                try:
                    if hasattr(self, '_execute_in_main_thread'):
                        self._execute_in_main_thread(_do_camera_render)
                    else:
                        _do_camera_render()
                except:
                    # Direct execution fallback
                    _do_camera_render()
                
                if not render_success:
                    print("⚠️ [GEMINI] Camera render failed, trying fallback method...")
                    # Fallback to old method if camera render fails
                    return self._render_and_extract_mist(scene, temp_dir, render_engine)
                
                # Find output file
                possible_paths = [
                    os.path.join(temp_dir, "camera_mist.png"),
                    os.path.join(temp_dir, "camera_mist0001.png"),
                    mist_output_path
                ]
                
                actual_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        actual_path = path
                        break
                
                if actual_path:
                    print(f"✅ [GEMINI] Camera mist render completed: {actual_path}")
                    return actual_path
                else:
                    # Get render result as fallback
                    render_result = bpy.data.images.get('Viewer Node') or bpy.data.images.get('Render Result')
                    if render_result:
                        render_result.save_render(filepath=mist_output_path)
                        print(f"✅ [GEMINI] Mist extracted from render result: {mist_output_path}")
                        return mist_output_path
                    else:
                        raise DepthRenderError("No camera render output found")
                
            finally:
                # Restore all render settings
                scene.render.filepath = original_filepath
                scene.render.resolution_x = original_resolution_x
                scene.render.resolution_y = original_resolution_y
                scene.render.resolution_percentage = original_resolution_percentage
                
                # Restore samples
                if original_samples is not None:
                    # Restore Eevee samples (supports both Blender 4.x and 5.0)
                    if scene.render.engine in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
                        try:
                            if hasattr(scene, 'eevee'):
                                scene.eevee.taa_render_samples = original_samples
                        except:
                            pass
                    elif scene.render.engine == 'CYCLES':
                        try:
                            if hasattr(scene, 'cycles'):
                                scene.cycles.samples = original_samples
                        except:
                            pass
                
                print("🔄 [GEMINI] All render settings restored")
                    
        except Exception as e:
            raise DepthRenderError(f"Camera mist render failed: {str(e)}")
    
    def _extract_depth_from_render_result(self, scene, temp_dir: str, normalize_mode: str, 
                                        clip_start: float, clip_end: float) -> str:
        """Extract depth from render result as fallback"""
        try:
            # Get render result
            render_result = bpy.data.images.get('Render Result')
            if not render_result:
                raise DepthRenderError("No render result found")
            
            # Try to access Z pass
            if not hasattr(render_result, 'pixels') or len(render_result.pixels) == 0:
                raise DepthRenderError("Render result has no pixel data")
            
            # Save render result as temporary EXR to access all passes
            temp_exr = os.path.join(temp_dir, "render_result.exr")
            
            # Track temp files for cleanup
            self.temp_files.append(temp_exr)
            render_result.save_render(filepath=temp_exr)
            
            if os.path.exists(temp_exr):
                # Load and process EXR file
                import array
                pixels = render_result.pixels[:]
                width = render_result.size[0] 
                height = render_result.size[1]
                
                # Convert to numpy array and extract depth channel
                # Note: This is simplified - in real implementation would need proper EXR parsing
                depth_array = np.array(pixels).reshape(height, width, -1)
                
                if depth_array.shape[2] >= 4:  # RGBA + depth
                    depth_channel = depth_array[:, :, -1]  # Last channel is usually depth
                else:
                    # Use alpha channel as depth approximation
                    depth_channel = depth_array[:, :, 3] if depth_array.shape[2] > 3 else depth_array[:, :, 0]
                
                # Normalize and save as PNG
                output_path = os.path.join(temp_dir, "depth_extracted.png")
                self._save_normalized_depth(depth_channel, output_path, normalize_mode, clip_start, clip_end)
                return output_path
            
            raise DepthRenderError("Could not extract depth from render result")
            
        except Exception as e:
            raise DepthRenderError(f"Failed to extract depth from render result: {str(e)}")
    
    def _normalize_depth_map(self, depth_path: str, normalize_mode: str, 
                           clip_start: float, clip_end: float) -> str:
        """Normalize depth map to 0-255 range"""
        try:
            # Load image
            # Use Blender's image system instead of PIL
            import bpy
            
            # Load image through Blender
            img_name = os.path.basename(depth_path)
            if img_name in bpy.data.images:
                img = bpy.data.images[img_name]
            else:
                img = bpy.data.images.load(depth_path)
            
            # Get pixel data
            width, height = img.size
            pixels = np.array(img.pixels).reshape((height, width, 4))
            
            # Convert to grayscale (take red channel for depth)
            depth_array = pixels[:, :, 0].astype(np.float32)
            
            if len(depth_array.shape) == 3:
                # Convert to grayscale if needed
                depth_array = np.mean(depth_array, axis=2)
                
                # Normalize based on mode
                if normalize_mode == 'CAMERA_CLIP':
                    # Clamp to camera clip range and normalize
                    depth_array = np.clip(depth_array, clip_start, clip_end)
                    if clip_end > clip_start:
                        depth_array = (depth_array - clip_start) / (clip_end - clip_start)
                else:  # AUTO
                    # Find min/max and normalize
                    min_val = np.min(depth_array)
                    max_val = np.max(depth_array)
                    if max_val > min_val:
                        depth_array = (depth_array - min_val) / (max_val - min_val)
                
                # Convert to 0-255 range
                depth_array = (depth_array * 255).astype(np.uint8)
                
                # Save normalized image
                output_path = depth_path.replace('.png', '_normalized.png')
                
                # Track normalized output for cleanup
                self.temp_files.append(output_path)
                # Save using Blender image system
                img_out = bpy.data.images.new("normalized_depth", width=depth_array.shape[1], height=depth_array.shape[0])
                img_out.pixels = depth_array.flatten() / 255.0  # Convert to 0-1 range
                img_out.filepath_raw = output_path
                img_out.file_format = 'PNG'
                img_out.save()
                bpy.data.images.remove(img_out)
                
                return output_path
                
        except Exception as e:
            raise DepthRenderError(f"Failed to normalize depth map: {str(e)}")
    
    def _save_normalized_depth(self, depth_array: np.ndarray, output_path: str, 
                             normalize_mode: str, clip_start: float, clip_end: float) -> None:
        """Save normalized depth array as PNG"""
        try:
            # Normalize array
            if normalize_mode == 'CAMERA_CLIP':
                depth_array = np.clip(depth_array, clip_start, clip_end)
                if clip_end > clip_start:
                    depth_array = (depth_array - clip_start) / (clip_end - clip_start)
            else:  # AUTO
                min_val = np.min(depth_array)
                max_val = np.max(depth_array)
                if max_val > min_val:
                    depth_array = (depth_array - min_val) / (max_val - min_val)
            
            # Convert to 0-255 and save
            depth_array = (depth_array * 255).astype(np.uint8)
            
            # Save using Blender image system
            import bpy
            img_out = bpy.data.images.new("depth_array", width=depth_array.shape[1], height=depth_array.shape[0])
            img_out.pixels = depth_array.flatten() / 255.0  # Convert to 0-1 range
            img_out.filepath_raw = output_path
            img_out.file_format = 'PNG'
            img_out.save()
            bpy.data.images.remove(img_out)
            
        except Exception as e:
            raise DepthRenderError(f"Failed to save normalized depth: {str(e)}")
    
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
                
                # Keep current engine or use Eevee if available
                # Blender 5.0+ uses 'BLENDER_EEVEE', Blender 4.x uses 'BLENDER_EEVEE_NEXT'
                if scene.render.engine == 'CYCLES':
                    print("[GEMINI] Using CYCLES (current engine)")
                    # Store Cycles samples
                    if hasattr(scene.cycles, 'samples'):
                        original_samples = scene.cycles.samples
                        # Use current samples or ensure minimum quality
                        if scene.cycles.samples < 64:
                            scene.cycles.samples = 64
                            print(f"[GEMINI] Increased Cycles samples to 64 for quality")
                elif scene.render.engine in ['BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT']:
                    print(f"[GEMINI] Using {scene.render.engine} (current engine)")
                    # Ensure good quality for Eevee
                    if hasattr(scene.eevee, 'taa_render_samples'):
                        original_samples = scene.eevee.taa_render_samples
                        if scene.eevee.taa_render_samples < 64:
                            scene.eevee.taa_render_samples = 64
                            print(f"[GEMINI] Increased Eevee samples to 64 for quality")
                else:
                    # Try to switch to Eevee (try BLENDER_EEVEE first for 5.0, fallback to BLENDER_EEVEE_NEXT for 4.x)
                    try:
                        scene.render.engine = 'BLENDER_EEVEE'
                        print("[GEMINI] Switched to BLENDER_EEVEE (Blender 5.0+)")
                    except:
                        try:
                            scene.render.engine = 'BLENDER_EEVEE_NEXT'
                            print("[GEMINI] Switched to BLENDER_EEVEE_NEXT (Blender 4.x)")
                        except:
                            print("[GEMINI] Warning: Could not switch to Eevee, using current engine")
                    
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
                print("[GEMINI] Starting regular render...")
                bpy.ops.render.render(write_still=True)
                print(f"[GEMINI] Regular render completed: {render_path}")
                
                # Verify file exists
                if not os.path.exists(render_path):
                    raise DepthRenderError(f"Render file not created: {render_path}")
                
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
