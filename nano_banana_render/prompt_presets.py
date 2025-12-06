"""
Prompt Presets Manager
Manages prompt presets with JSON persistence
"""

import os
import json
from typing import Optional, Dict, List, Tuple


class PromptPresetManager:
    """Manage prompt presets with JSON persistence"""
    
    def __init__(self):
        self.config_file = self._get_config_path()
        self.presets = []
        self.load()
    
    def _get_config_path(self) -> str:
        """Get configuration file path (same location as providers.json)"""
        try:
            import bpy
            # Try Blender 4.5+ extension path
            try:
                config_dir = bpy.utils.extension_path_user(__package__.split('.')[0], create=True)
            except:
                # Fallback: use addon directory
                import addon_utils
                for mod in addon_utils.modules():
                    if mod.__name__ == __package__.split('.')[0]:
                        config_dir = os.path.dirname(mod.__file__)
                        break
                else:
                    # Last resort: current file directory
                    config_dir = os.path.dirname(os.path.realpath(__file__))
            
            config_file = os.path.join(config_dir, "presets.json")
            print(f"[PRESET_MANAGER] Config file: {config_file}")
            return config_file
        except Exception as e:
            print(f"[PRESET_MANAGER] Error getting config path: {e}")
            # Fallback to current directory
            return os.path.join(os.path.dirname(__file__), "presets.json")
    
    def load(self):
        """Load presets from JSON file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.presets = json.load(f)
                print(f"[PRESET_MANAGER] Loaded {len(self.presets)} presets from JSON")
            except Exception as e:
                print(f"[PRESET_MANAGER] Error loading presets: {e}")
                self.presets = []
        else:
            print("[PRESET_MANAGER] No presets.json found - will create on first save")
            self.presets = []
    
    def save(self):
        """Save presets to JSON file"""
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=4, ensure_ascii=False)
            print(f"[PRESET_MANAGER] Saved {len(self.presets)} presets to {self.config_file}")
        except Exception as e:
            print(f"[PRESET_MANAGER] Error saving presets: {e}")
    
    def get_preset_by_name(self, name: str) -> Optional[Dict]:
        """Get preset by name"""
        for preset in self.presets:
            if preset.get("name") == name:
                return preset
        return None
    
    def get_all_presets(self) -> List[Dict]:
        """Get all presets"""
        return self.presets.copy()
    
    def get_preset_names(self) -> List[str]:
        """Get list of all preset names"""
        return [p.get("name", "") for p in self.presets if "name" in p]
    
    def add_preset(self, name: str, prompt: str) -> bool:
        """Add new preset"""
        # Check if name already exists
        if self.get_preset_by_name(name):
            print(f"[PRESET_MANAGER] Preset '{name}' already exists")
            return False
        
        new_preset = {
            "name": name,
            "prompt": prompt
        }
        self.presets.append(new_preset)
        self.save()
        print(f"[PRESET_MANAGER] Added preset '{name}'")
        return True
    
    def update_preset(self, old_name: str, new_name: str = None, new_prompt: str = None) -> bool:
        """Update existing preset (rename and/or change prompt)"""
        for preset in self.presets:
            if preset.get("name") == old_name:
                if new_name is not None and new_name != old_name:
                    # Check if new name conflicts
                    if self.get_preset_by_name(new_name):
                        print(f"[PRESET_MANAGER] Cannot rename: '{new_name}' already exists")
                        return False
                    preset["name"] = new_name
                    print(f"[PRESET_MANAGER] Renamed preset '{old_name}' -> '{new_name}'")
                
                if new_prompt is not None:
                    preset["prompt"] = new_prompt
                    print(f"[PRESET_MANAGER] Updated prompt for '{preset['name']}'")
                
                self.save()
                return True
        
        print(f"[PRESET_MANAGER] Preset '{old_name}' not found")
        return False
    
    def delete_preset(self, name: str) -> bool:
        """Delete preset by name"""
        for i, preset in enumerate(self.presets):
            if preset.get("name") == name:
                self.presets.pop(i)
                self.save()
                print(f"[PRESET_MANAGER] Deleted preset '{name}'")
                return True
        
        print(f"[PRESET_MANAGER] Preset '{name}' not found")
        return False
    
    def get_preset_items_for_enum(self) -> List[Tuple[str, str, str]]:
        """Get preset items formatted for Blender EnumProperty"""
        items = []
        for i, preset in enumerate(self.presets):
            name = preset.get("name", f"Preset {i+1}")
            # Use index as identifier for stability
            items.append((name, name, preset.get("prompt", "")[:100]))  # Truncate description
        
        # Add empty item if no presets
        if not items:
            items.append(("NONE", "No Presets", "No presets available"))
        
        return items


# Global preset manager instance
_preset_manager = None

def get_preset_manager() -> PromptPresetManager:
    """Get global preset manager instance"""
    global _preset_manager
    if _preset_manager is None:
        _preset_manager = PromptPresetManager()
    return _preset_manager


def reload_preset_manager():
    """Reload preset manager from disk (useful after external changes)"""
    global _preset_manager
    if _preset_manager is not None:
        _preset_manager.load()
    return _preset_manager
