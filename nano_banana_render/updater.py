import bpy
import threading
import urllib.request
import json
import os
import tempfile
import ssl
import shutil

# Bypass SSL verify issues on some OS for basic update checks
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

class NANODE_OT_install_update(bpy.types.Operator):
    bl_idname = "nanode.install_update"
    bl_label = "Installing Update..."

    def execute(self, context):
        zip_path = os.path.join(tempfile.gettempdir(), "nanode_addon_update.zip")
        try:
            # Download file
            url = "https://api.nanode.tech/api/addon_download"
            
            # Using urllib with custom SSL context to avoid certificate problems
            with urllib.request.urlopen(url, context=_ssl_ctx, timeout=30) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
                
            # Safely extract files without using addon_install to avoid Blender crashing 
            # (addon_install unregisters the currently running operator, causing segfaults).
            import zipfile
            addon_dir = os.path.dirname(os.path.realpath(__file__))
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Analyze zip structure
                paths = [m.filename.replace('\\', '/') for m in zip_ref.infolist()]
                root_folders = set(p.split('/')[0] for p in paths if p)
                strip_root = len(root_folders) == 1
                
                for member in zip_ref.infolist():
                    member_path = member.filename.replace('\\', '/')
                    if strip_root:
                        parts = member_path.split('/')
                        if len(parts) <= 1 or not parts[1]:
                            continue
                        rel_path = '/'.join(parts[1:])
                    else:
                        rel_path = member_path
                        
                    if not rel_path or member_path.endswith('/'):
                        continue
                        
                    target_path = os.path.join(addon_dir, rel_path)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    
                    with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
            
            # Prevent showing the dialog again
            context.window_manager.nanode_update_version = "IGNORED" 
            
            self.report({'INFO'}, "Nanode Addon Updated! Reloading scripts...")
            
            def reload_scripts():
                import bpy
                bpy.ops.script.reload()
                return None
            
            bpy.app.timers.register(reload_scripts, first_interval=0.5)
            
            # Delete temp zip after install
            try:
                os.remove(zip_path)
            except OSError:
                pass
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to update Nanode: {e}")
            
        return {'FINISHED'}


class NANODE_OT_update_dialog(bpy.types.Operator):
    bl_idname = "nanode.update_dialog"
    bl_label = "Update Nanode add-on"
    
    action: bpy.props.EnumProperty(
        items=[
            ('UPDATE', "Update Now", ""),
            ('IGNORE', "Ignore", ""),
            ('DEFER', "Defer", "")
        ],
        name="Action",
        default='UPDATE'
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        version = context.window_manager.nanode_update_version
        
        layout.label(text=f"Update {version} ready!", icon='FILE_REFRESH')
        layout.label(text="Choose 'Update Now' & press OK to install,")
        layout.label(text="or click outside window to defer")
        layout.separator()
        
        row = layout.row()
        row.prop(self, "action", expand=True)

    def execute(self, context):
        if self.action == 'UPDATE':
            bpy.ops.nanode.install_update()
        elif self.action == 'IGNORE':
            context.window_manager.nanode_update_version = "IGNORED" 
            
        return {'FINISHED'}


def check_updates_in_background(local_version_tuple, local_build_number=0):
    """Network request to check version silently"""
    try:
        req = urllib.request.Request("https://api.nanode.tech/api/addon_version")
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            server_version = data.get("version")
            server_build = data.get("build_number", 0)
            
            if server_version:
                # Convert e.g. "(1, 0, 1)" or "1.0.1" to tuple
                clean_str = server_version.replace('(', '').replace(')', '').replace(',', '.')
                parts = clean_str.split('.')
                srv_tuple = tuple(int(p.strip()) for p in parts if p.strip().isdigit())
                
                # Check if server version is newer OR same version with higher build number
                needs_update = False
                if srv_tuple > local_version_tuple:
                    needs_update = True
                elif srv_tuple == local_version_tuple and int(server_build) > int(local_build_number):
                    needs_update = True
                
                if needs_update:
                    # Include build info in version string for display
                    display = server_version
                    if int(server_build) > 0:
                        display = f"{server_version} (build {server_build})"
                    import bpy
                    bpy.context.window_manager.nanode_update_version = display
    except Exception as e:
        # Silently fail update checks
        pass


def update_poll_timer():
    """Polled periodically by Blender to show the UI dialog safely in the main thread."""
    import bpy
    wm = bpy.context.window_manager
    version_str = getattr(wm, "nanode_update_version", "")
    
    # Wait until an update is found, but avoid showing if IGNORED
    if version_str and version_str != "IGNORED":
        # Find exactly where the user is looking
        for window in wm.windows:
            screen = window.screen
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            # Trigger dialog in 3D viewport context
                            with bpy.context.temp_override(window=window, area=area, region=region):
                                try:
                                    bpy.ops.nanode.update_dialog('INVOKE_DEFAULT')
                                    # Disarm timer returning None
                                    return None
                                except RuntimeError:
                                    pass
        # If no active 3D view yet, poll again
        return 2.0
    
    # Keeping polling. Disarm after trying too many times?
    # We will poll every 5 seconds until it updates.
    return 5.0

classes = (
    NANODE_OT_install_update,
    NANODE_OT_update_dialog,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
