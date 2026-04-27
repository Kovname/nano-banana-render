import bpy
import bpy.utils.previews
import os

# Global dictionary for storing loaded thumbnails
custom_icons = None
_load_queue = set()
_timer_registered = False

def init_previews():
    global custom_icons
    custom_icons = bpy.utils.previews.new()

def clear_previews():
    global custom_icons
    if custom_icons:
        bpy.utils.previews.remove(custom_icons)
        custom_icons = None

def _redraw_all_areas():
    """Force redraw of all areas to update UI icons."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

def _process_queue():
    """Timer callback to load icons outside of draw()"""
    global _load_queue, _timer_registered, custom_icons
    
    if not custom_icons or not _load_queue:
        _timer_registered = False
        return None # Stop timer
        
    filepath = _load_queue.pop()
    if filepath not in custom_icons and os.path.exists(filepath):
        try:
            custom_icons.load(filepath, filepath, 'IMAGE')
            _redraw_all_areas()
        except Exception as e:
            print(f"[NANO BANANA] Failed to load preview icon: {e}")
            
    # Continue timer if queue not empty
    if _load_queue:
        return 0.1
    
    _timer_registered = False
    return None

def get_preview_icon_id_safe(filepath, fallback_image_name=""):
    """
    Returns the icon_id for the given filepath safely.
    If the image is loaded in memory, uses Blender's native preview_ensure().
    If filepath is empty, tries to find the file via bpy.data.images[fallback_image_name].
    If not loaded, queues it for background loading and returns 0.
    """
    global custom_icons, _load_queue, _timer_registered
    
    # 1. Native Blender Preview (Best and fastest method if image is in memory)
    if fallback_image_name and fallback_image_name in bpy.data.images:
        img = bpy.data.images[fallback_image_name]
        try:
            preview = img.preview_ensure()
            if preview:
                return preview.icon_id
        except Exception:
            pass
            
    if not custom_icons:
        return 0
        
    # 2. Fallback to Blender's internal image filepath if needed
    if not filepath and fallback_image_name and fallback_image_name in bpy.data.images:
        img = bpy.data.images[fallback_image_name]
        if img.filepath:
            filepath = bpy.path.abspath(img.filepath)
            
    if not filepath:
        return 0
        
    # 3. Use our custom external file loader queue
    if filepath in custom_icons:
        return custom_icons[filepath].icon_id
        
    if os.path.exists(filepath):
        _load_queue.add(filepath)
        if not _timer_registered:
            bpy.app.timers.register(_process_queue, first_interval=0.1)
            _timer_registered = True
            
    return 0
