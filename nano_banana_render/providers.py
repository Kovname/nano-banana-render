"""
API Provider abstraction layer for multiple image generation services
Supports: Google Gemini, Yunwu.ai, OpenRouter, GPTGod
"""

import os
import json
import base64
from typing import Optional, Tuple, Dict, Any, List
from io import BytesIO

# Try importing PIL
try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import requests for REST APIs
import requests

# --- Unified image handling helpers ---
from typing import Tuple


def _detect_mime_from_url(url: str) -> str:
    """Best-effort MIME detection from URL extension"""
    lower = url.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _download_image(url: str) -> Tuple[bytes, str]:
    """Download image bytes and return (content, mime_type)"""
    resp = requests.get(url, timeout=300)
    if resp.status_code != 200:
        raise Exception(f"Image download failed {resp.status_code}: {resp.text[:120]}")
    mime = resp.headers.get("Content-Type", "")
    if not mime:
        mime = _detect_mime_from_url(url)
    # Strip any parameters (e.g., charset)
    mime = mime.split(";")[0].strip() if mime else "application/octet-stream"
    return resp.content, mime


def _ensure_png(image_bytes: bytes, mime_type: str) -> Tuple[bytes, str]:
    """Convert arbitrary image bytes (jpeg/webp/png) to PNG bytes if PIL is available.
    Returns (png_bytes, 'image/png'). If PIL is unavailable and input is already PNG, returns as-is.
    """
    try:
        if PIL_AVAILABLE:
            bio = BytesIO(image_bytes)
            img = Image.open(bio)
            # Prefer RGBA to preserve alpha if present
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            out = BytesIO()
            img.save(out, format="PNG")
            return out.getvalue(), "image/png"
        else:
            # If no PIL, but bytes already are a PNG, keep them
            png_sig = b"\x89PNG\r\n\x1a\n"
            if image_bytes.startswith(png_sig):
                return image_bytes, "image/png"
            # Fallback: return original bytes; downstream uses PNG filename but most loaders use magic signatures
            return image_bytes, mime_type or "application/octet-stream"
    except Exception:
        # On any conversion error, return original bytes
        return image_bytes, mime_type or "application/octet-stream"


class ProviderManager:
    """Manage multiple provider configurations with JSON persistence"""

    def __init__(self):
        self.config_file = self._get_config_path()
        self.settings_file = self._get_settings_path()
        self.providers = []
        self.load()

    def _get_config_path(self) -> str:
        """Get configuration file path in user config directory"""
        try:
            import bpy

            # Try Blender 4.5+ extension path
            try:
                config_dir = bpy.utils.extension_path_user(
                    __package__.split(".")[0], create=True
                )
            except:
                # Fallback: use addon directory
                import addon_utils

                for mod in addon_utils.modules():
                    if mod.__name__ == __package__.split(".")[0]:
                        config_dir = os.path.dirname(mod.__file__)
                        break
                else:
                    # Last resort: current file directory
                    config_dir = os.path.dirname(os.path.realpath(__file__))

            config_file = os.path.join(config_dir, "providers.json")
            print(f"[PROVIDER_MANAGER] Config file: {config_file}")
            return config_file
        except Exception as e:
            print(f"[PROVIDER_MANAGER] Error getting config path: {e}")
            # Fallback to current directory
            return os.path.join(os.path.dirname(__file__), "providers.json")

    def _get_settings_path(self) -> str:
        """Get settings.json path to persist selected provider"""
        try:
            import bpy

            try:
                config_dir = bpy.utils.extension_path_user(
                    __package__.split(".")[0], create=True
                )
            except:
                import addon_utils

                for mod in addon_utils.modules():
                    if mod.__name__ == __package__.split(".")[0]:
                        config_dir = os.path.dirname(mod.__file__)
                        break
                else:
                    config_dir = os.path.dirname(os.path.realpath(__file__))
            settings_file = os.path.join(config_dir, "settings.json")
            print(f"[PROVIDER_MANAGER] Settings file: {settings_file}")
            return settings_file
        except Exception as e:
            print(f"[PROVIDER_MANAGER] Error getting settings path: {e}")
            return os.path.join(os.path.dirname(__file__), "settings.json")

    def load(self):
        """Load providers from JSON file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.providers = json.load(f)
                print(
                    f"[PROVIDER_MANAGER] Loaded {len(self.providers)} providers from JSON"
                )
            except Exception as e:
                print(f"[PROVIDER_MANAGER] Error loading providers: {e}")
                self.providers = []
        else:
            print("[PROVIDER_MANAGER] No config file found - will use default presets")
            # Don't create JSON yet - wait for user to save something
            self.providers = []

    def save(self):
        """Save providers to JSON file"""
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.providers, f, indent=4, ensure_ascii=False)
            print(
                f"[PROVIDER_MANAGER] Saved {len(self.providers)} providers to {self.config_file}"
            )
        except Exception as e:
            print(f"[PROVIDER_MANAGER] Error saving providers: {e}")

    def load_selected_provider(self) -> Optional[str]:
        """Load last selected provider type from settings.json"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sel = data.get("selected_provider", "")
                    return sel if isinstance(sel, str) else None
        except Exception as e:
            print(f"[PROVIDER_MANAGER] Error loading selected provider: {e}")
        return None

    def save_selected_provider(self, provider_type: str) -> None:
        """Persist last selected provider type to settings.json"""
        try:
            # Ensure directory exists
            settings_dir = os.path.dirname(self.settings_file)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"selected_provider": provider_type},
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
            print(f"[PROVIDER_MANAGER] Saved selected provider: {provider_type}")
        except Exception as e:
            print(f"[PROVIDER_MANAGER] Error saving selected provider: {e}")

    def get_provider_by_type(self, provider_type: str) -> Optional[Dict]:
        """Get provider config by type (google/yunwu/gptgod/openrouter)"""
        for p in self.providers:
            if p.get("type") == provider_type:
                return p
        # Return None if not found - UI will use default preset
        return None

    def get_provider_by_name(self, name: str) -> Optional[Dict]:
        """Get provider config by name"""
        for p in self.providers:
            if p.get("name") == name:
                return p
        return None

    def update_provider(
        self, provider_type: str, api_key: str, base_url: str = None, model: str = None
    ):
        """Update provider configuration - creates entry if not exists"""
        # Find existing provider
        for p in self.providers:
            if p.get("type") == provider_type:
                # Update existing
                p["apiKey"] = api_key
                if base_url is not None:
                    p["baseUrl"] = base_url
                if model is not None:
                    p["model"] = model
                self.save()
                print(f"[PROVIDER_MANAGER] Updated {provider_type} provider")
                return True

        # Create new entry
        new_provider = {
            "name": self._get_provider_name(provider_type),
            "type": provider_type,
            "apiKey": api_key,
            "baseUrl": base_url if base_url is not None else "",
            "model": model if model is not None else "",
        }
        self.providers.append(new_provider)
        self.save()
        print(f"[PROVIDER_MANAGER] Created new {provider_type} provider entry")
        return True

    def _get_provider_name(self, provider_type: str) -> str:
        """Get display name for provider type"""
        names = {
            "google": "Google Gemini",
            "yunwu": "Yunwu Gemini",
            "gptgod": "GPTGod",
            "openrouter": "OpenRouter",
        }
        return names.get(provider_type, provider_type)

    def get_all_provider_types(self) -> List[str]:
        """Get list of all provider types"""
        return [p.get("type") for p in self.providers if "type" in p]


# Global provider manager instance
_provider_manager = None


def get_provider_manager() -> ProviderManager:
    """Get global provider manager instance"""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager


class ProviderConfig:
    """Configuration for an API provider"""

    def __init__(
        self, provider_type: str, api_key: str, base_url: str = "", model_id: str = ""
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.model_id = model_id


class BaseProvider:
    """Base class for all providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """Generate image from depth map/render"""
        raise NotImplementedError("Subclasses must implement generate_image")

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit existing image"""
        raise NotImplementedError("Subclasses must implement edit_image")


class YunwuProvider(BaseProvider):
    """Yunwu.ai provider (native Gemini API format)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://yunwu.zeabur.app"
        self.model_id = config.model_id or "gemini-3-pro-image-preview"

    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _determine_resolution(self, width: int, height: int) -> str:
        """Map resolution to API format"""
        if width >= 4096 or height >= 4096:
            return "4K"
        elif width >= 2048 or height >= 2048:
            return "2K"
        return "1K"

    def _determine_aspect_ratio(self, width: int, height: int) -> str:
        """Calculate closest supported aspect ratio"""
        from . import aspect_ratio_utils

        return aspect_ratio_utils.find_closest_ratio(width, height)

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """Generate image using Yunwu.ai native Gemini API"""
        try:
            print(f"[YUNWU] Generating image with model: {self.model_id}")

            # Encode images
            depth_base64 = self._encode_image(depth_image_path)

            # Build parts array
            parts = [{"text": user_prompt}]

            # Add depth/render image
            parts.append(
                {"inline_data": {"mime_type": "image/png", "data": depth_base64}}
            )

            # Add reference if provided
            if reference_image_path:
                ref_base64 = self._encode_image(reference_image_path)
                parts.append(
                    {"inline_data": {"mime_type": "image/png", "data": ref_base64}}
                )
                print("[YUNWU] Reference image added")

            # Build request payload (Gemini native format)
            resolution = self._determine_resolution(width, height)
            aspect_ratio = self._determine_aspect_ratio(width, height)

            url = f"{self.base_url}/v1beta/models/{self.model_id}:generateContent"
            headers = {"Content-Type": "application/json"}

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "aspectRatio": aspect_ratio,
                        "imageSize": resolution,
                    },
                },
            }

            # Add API key to URL query parameter
            url = f"{url}?key={self.config.api_key}"

            print(
                f"[YUNWU] Requesting {resolution} resolution, aspect ratio {aspect_ratio}"
            )
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"Yunwu API error {response.status_code}: {response.text}"
                )

            # Parse response
            result = response.json()

            # Extract image from response
            if "candidates" in result and result["candidates"]:
                parts = result["candidates"][0].get("content", {}).get("parts", [])

                for part in parts:
                    if "inlineData" in part or "inline_data" in part:
                        inline_key = (
                            "inlineData" if "inlineData" in part else "inline_data"
                        )
                        inline_data = part[inline_key]
                        data_key = "data" if "data" in inline_data else "bytes"

                        if data_key in inline_data:
                            image_data = base64.b64decode(inline_data[data_key])
                            print(f"[YUNWU] Image received: {len(image_data)} bytes")
                            return image_data, "image/png"

            raise Exception("No image found in Yunwu response")

        except Exception as e:
            raise Exception(f"Yunwu generation failed: {str(e)}")

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit existing image using Yunwu.ai native Gemini API"""
        try:
            print(f"[YUNWU] Editing image with model: {self.model_id}")

            # Encode source image
            source_base64 = self._encode_image(image_path)

            # Build parts array with edit prompt
            parts = [{"text": edit_prompt}]

            # Add source image first
            parts.append(
                {"inline_data": {"mime_type": "image/png", "data": source_base64}}
            )

            # Add reference if provided
            if reference_image_path:
                ref_base64 = self._encode_image(reference_image_path)
                parts.append(
                    {"inline_data": {"mime_type": "image/png", "data": ref_base64}}
                )
                print("[YUNWU] Reference image added for edit")

            # Add mask if provided
            if mask_path:
                mask_base64 = self._encode_image(mask_path)
                parts.append(
                    {"inline_data": {"mime_type": "image/png", "data": mask_base64}}
                )
                print("[YUNWU] Mask image added for edit")

            # Build request payload
            resolution = self._determine_resolution(width, height)
            aspect_ratio = self._determine_aspect_ratio(width, height)

            url = f"{self.base_url}/v1beta/models/{self.model_id}:generateContent"
            headers = {"Content-Type": "application/json"}

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "aspectRatio": aspect_ratio,
                        "imageSize": resolution,
                    },
                },
            }

            # Add API key to URL query parameter
            url = f"{url}?key={self.config.api_key}"

            print(
                f"[YUNWU] Edit requesting {resolution} resolution, aspect {aspect_ratio}"
            )
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"Yunwu API error {response.status_code}: {response.text}"
                )

            # Parse response
            result = response.json()

            # Extract image from response
            if "candidates" in result and result["candidates"]:
                parts = result["candidates"][0].get("content", {}).get("parts", [])

                for part in parts:
                    if "inlineData" in part or "inline_data" in part:
                        inline_key = (
                            "inlineData" if "inlineData" in part else "inline_data"
                        )
                        inline_data = part[inline_key]
                        data_key = "data" if "data" in inline_data else "bytes"

                        if data_key in inline_data:
                            image_data = base64.b64decode(inline_data[data_key])
                            print(
                                f"[YUNWU] Edit result received: {len(image_data)} bytes"
                            )
                            return image_data, "image/png"

            raise Exception("No image found in Yunwu edit response")

        except Exception as e:
            raise Exception(f"Yunwu edit failed: {str(e)}")


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider (OpenAI-compatible API)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (
            config.base_url or "https://openrouter.ai/api/v1/chat/completions"
        )
        self.model_id = config.model_id or "google/gemini-3-pro-image-preview"

    def _encode_image_to_data_url(self, image_path: str) -> str:
        """Encode image to data URL"""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{image_data}"

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """Generate image using OpenRouter API"""
        try:
            print(f"[OPENROUTER] Generating with model: {self.model_id}")

            # Build messages array (OpenAI format with images)
            content_parts = [{"type": "text", "text": user_prompt}]

            # Add depth/render image
            depth_url = self._encode_image_to_data_url(depth_image_path)
            content_parts.append({"type": "image_url", "image_url": {"url": depth_url}})

            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": ref_url}}
                )
                print("[OPENROUTER] Reference image added")

            # Determine resolution and aspect ratio
            resolution = "1K"
            if width >= 4096 or height >= 4096:
                resolution = "4K"
            elif width >= 2048 or height >= 2048:
                resolution = "2K"

            from . import aspect_ratio_utils

            aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)

            # Use base_url directly - it should already include /chat/completions
            url = self.base_url
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model_id,
                "messages": [{"role": "user", "content": content_parts}],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": aspect_ratio,
                    "image_size": resolution,
                },
            }

            print(f"[OPENROUTER] Requesting {resolution}, aspect {aspect_ratio}")
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"OpenRouter API error {response.status_code}: {response.text}"
                )

            result = response.json()

            # Extract image from response (OpenAI format)
            if "choices" in result and result["choices"]:
                message = result["choices"][0].get("message", {})

                # Check for images array
                if "images" in message:
                    for img in message["images"]:
                        image_url = img.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image"):
                            # Parse MIME and base64 data
                            header, base64_data = image_url.split(",", 1)
                            # header example: data:image/webp;base64
                            mime_type = "image/png"
                            try:
                                mime_type = header.split(";")[0].split(":", 1)[1]
                            except Exception:
                                pass
                            raw_bytes = base64.b64decode(base64_data)
                            png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                            print(
                                f"[OPENROUTER] Image received (data URL): {len(png_bytes)} bytes"
                            )
                            return png_bytes, "image/png"
                        elif image_url.startswith("http://") or image_url.startswith(
                            "https://"
                        ):
                            raw_bytes, mime_type = _download_image(image_url)
                            png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                            print(
                                f"[OPENROUTER] Image downloaded: {len(png_bytes)} bytes (source {mime_type})"
                            )
                            return png_bytes, "image/png"

            raise Exception("No image found in OpenRouter response")

        except Exception as e:
            raise Exception(f"OpenRouter generation failed: {str(e)}")

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit existing image using OpenRouter API"""
        try:
            print(f"[OPENROUTER] Editing with model: {self.model_id}")

            # Build content parts for edit
            content_parts = [{"type": "text", "text": edit_prompt}]

            # Add source image
            source_url = self._encode_image_to_data_url(image_path)
            content_parts.append(
                {"type": "image_url", "image_url": {"url": source_url}}
            )

            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": ref_url}}
                )
                print("[OPENROUTER] Reference image added for edit")

            # Add mask if provided
            if mask_path:
                mask_url = self._encode_image_to_data_url(mask_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": mask_url}}
                )
                print("[OPENROUTER] Mask image added for edit")

            # Determine resolution and aspect ratio
            resolution = "1K"
            if width >= 4096 or height >= 4096:
                resolution = "4K"
            elif width >= 2048 or height >= 2048:
                resolution = "2K"

            from . import aspect_ratio_utils

            aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)

            url = self.base_url
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model_id,
                "messages": [{"role": "user", "content": content_parts}],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": aspect_ratio,
                    "image_size": resolution,
                },
            }

            print(f"[OPENROUTER] Edit requesting {resolution}, aspect {aspect_ratio}")
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"OpenRouter API error {response.status_code}: {response.text}"
                )

            result = response.json()

            # Extract image from response (OpenAI format)
            if "choices" in result and result["choices"]:
                message = result["choices"][0].get("message", {})

                if "images" in message:
                    for img in message["images"]:
                        image_url = img.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image"):
                            header, base64_data = image_url.split(",", 1)
                            mime_type = "image/png"
                            try:
                                mime_type = header.split(";")[0].split(":", 1)[1]
                            except Exception:
                                pass
                            raw_bytes = base64.b64decode(base64_data)
                            png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                            print(
                                f"[OPENROUTER] Edit result (data URL): {len(png_bytes)} bytes"
                            )
                            return png_bytes, "image/png"
                        elif image_url.startswith("http://") or image_url.startswith(
                            "https://"
                        ):
                            raw_bytes, mime_type = _download_image(image_url)
                            png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                            print(
                                f"[OPENROUTER] Edit result downloaded: {len(png_bytes)} bytes"
                            )
                            return png_bytes, "image/png"

            raise Exception("No image found in OpenRouter edit response")

        except Exception as e:
            raise Exception(f"OpenRouter edit failed: {str(e)}")


class GPTGodProvider(BaseProvider):
    """GPTGod provider (OpenAI-compatible)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (
            config.base_url or "https://api.gptgod.online/v1/chat/completions"
        )

        # Model ID can include resolution suffix (-2k, -4k)
        base_model = config.model_id or "gemini-3-pro-image-preview"
        self.base_model_id = base_model.replace("-2k", "").replace("-4k", "")

    def _get_model_for_resolution(self, width: int, height: int) -> str:
        """Get model ID with resolution suffix"""
        if width >= 4096 or height >= 4096:
            return f"{self.base_model_id}-4k"
        elif width >= 2048 or height >= 2048:
            return f"{self.base_model_id}-2k"
        return self.base_model_id

    def _encode_image_to_data_url(self, image_path: str) -> str:
        """Encode image to data URL"""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{image_data}"

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """Generate image using GPTGod API"""
        try:
            # Determine model with resolution
            model_id = self._get_model_for_resolution(width, height)
            print(f"[GPTGOD] Generating with model: {model_id}")

            # Build prompt with image count request
            full_prompt = f"{user_prompt}\n请生成 1 张图片。"

            # Build content parts
            content_parts = [{"type": "text", "text": full_prompt}]

            # Add depth/render image
            depth_url = self._encode_image_to_data_url(depth_image_path)
            content_parts.append({"type": "image_url", "image_url": {"url": depth_url}})

            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": ref_url}}
                )
                print("[GPTGOD] Reference image added")

            # Use base_url directly - it should already include /chat/completions
            url = self.base_url
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": model_id,
                "stream": False,
                "n": 1,
                "messages": [{"role": "user", "content": content_parts}],
            }

            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"GPTGod API error {response.status_code}: {response.text}"
                )

            result = response.json()

            # Parse GPTGod response (multiple formats supported)
            # Format 1: direct 'image' field (single URL)
            if "image" in result:
                img_url = result["image"]
                if img_url.startswith("http://") or img_url.startswith("https://"):
                    raw_bytes, mime_type = _download_image(img_url)
                    png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                    print(f"[GPTGOD] Image from 'image' field: {len(png_bytes)} bytes")
                    return png_bytes, "image/png"

            # Format 2: 'images' array
            if "images" in result and result["images"]:
                img_url = result["images"][0]
                if isinstance(img_url, str):
                    if img_url.startswith("data:image"):
                        header, base64_data = img_url.split(",", 1)
                        mime_type = "image/png"
                        try:
                            mime_type = header.split(";")[0].split(":", 1)[1]
                        except Exception:
                            pass
                        raw_bytes = base64.b64decode(base64_data)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Image from images array (data URL): {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"
                    elif img_url.startswith("http://") or img_url.startswith(
                        "https://"
                    ):
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Image from images array (URL): {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"

            # Format 3: 'data' array with 'url'
            if "data" in result and result["data"] and isinstance(result["data"], list):
                if "url" in result["data"][0]:
                    img_url = result["data"][0]["url"]
                    if img_url.startswith("http://") or img_url.startswith("https://"):
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(f"[GPTGOD] Image from data array: {len(png_bytes)} bytes")
                        return png_bytes, "image/png"

            # Format 4: choices format with markdown or URL in content
            if "choices" in result and result["choices"]:
                message_content = (
                    result["choices"][0].get("message", {}).get("content", "")
                )

                if isinstance(message_content, str):
                    # Try to extract URL from markdown: ![](url)
                    import re

                    match = re.search(r"!\[.*?\]\((https?://[^)]+)\)", message_content)
                    if match:
                        img_url = match.group(1)
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(f"[GPTGOD] Image from markdown: {len(png_bytes)} bytes")
                        return png_bytes, "image/png"

                    # Try to find direct image URL
                    match = re.search(
                        r"(https?://[^\s]+\.(png|jpg|jpeg|webp|gif))",
                        message_content,
                        re.IGNORECASE,
                    )
                    if match:
                        img_url = match.group(1)
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Image from URL in content: {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"

            raise Exception("No image found in GPTGod response")

        except Exception as e:
            raise Exception(f"GPTGod generation failed: {str(e)}")

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit existing image using GPTGod API"""
        try:
            # Determine model with resolution
            model_id = self._get_model_for_resolution(width, height)
            print(f"[GPTGOD] Editing with model: {model_id}")

            # Build prompt for edit
            full_prompt = f"{edit_prompt}\n请生成 1 张图片。"

            # Build content parts
            content_parts = [{"type": "text", "text": full_prompt}]

            # Add source image
            source_url = self._encode_image_to_data_url(image_path)
            content_parts.append(
                {"type": "image_url", "image_url": {"url": source_url}}
            )

            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": ref_url}}
                )
                print("[GPTGOD] Reference image added for edit")

            # Add mask if provided
            if mask_path:
                mask_url = self._encode_image_to_data_url(mask_path)
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": mask_url}}
                )
                print("[GPTGOD] Mask image added for edit")

            url = self.base_url
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": model_id,
                "stream": False,
                "n": 1,
                "messages": [{"role": "user", "content": content_parts}],
            }

            print(f"[GPTGOD] Edit requesting with model: {model_id}")
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise Exception(
                    f"GPTGod API error {response.status_code}: {response.text}"
                )

            result = response.json()

            # Parse GPTGod response (multiple formats supported)
            # Format 1: direct 'image' field
            if "image" in result:
                img_url = result["image"]
                if img_url.startswith("http://") or img_url.startswith("https://"):
                    raw_bytes, mime_type = _download_image(img_url)
                    png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                    print(f"[GPTGOD] Edit from 'image' field: {len(png_bytes)} bytes")
                    return png_bytes, "image/png"

            # Format 2: 'images' array
            if "images" in result and result["images"]:
                img_url = result["images"][0]
                if isinstance(img_url, str):
                    if img_url.startswith("data:image"):
                        header, base64_data = img_url.split(",", 1)
                        mime_type = "image/png"
                        try:
                            mime_type = header.split(";")[0].split(":", 1)[1]
                        except Exception:
                            pass
                        raw_bytes = base64.b64decode(base64_data)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Edit from images array (data URL): {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"
                    elif img_url.startswith("http://") or img_url.startswith(
                        "https://"
                    ):
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Edit from images array (URL): {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"

            # Format 3: 'data' array with 'url'
            if "data" in result and result["data"] and isinstance(result["data"], list):
                if "url" in result["data"][0]:
                    img_url = result["data"][0]["url"]
                    if img_url.startswith("http://") or img_url.startswith("https://"):
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(f"[GPTGOD] Edit from data array: {len(png_bytes)} bytes")
                        return png_bytes, "image/png"

            # Format 4: choices format with markdown or URL in content
            if "choices" in result and result["choices"]:
                message_content = (
                    result["choices"][0].get("message", {}).get("content", "")
                )

                if isinstance(message_content, str):
                    import re

                    # Try markdown image
                    match = re.search(r"!\[.*?\]\((https?://[^)]+)\)", message_content)
                    if match:
                        img_url = match.group(1)
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(f"[GPTGOD] Edit from markdown: {len(png_bytes)} bytes")
                        return png_bytes, "image/png"

                    # Try direct image URL
                    match = re.search(
                        r"(https?://[^\s]+\.(png|jpg|jpeg|webp|gif))",
                        message_content,
                        re.IGNORECASE,
                    )
                    if match:
                        img_url = match.group(1)
                        raw_bytes, mime_type = _download_image(img_url)
                        png_bytes, _ = _ensure_png(raw_bytes, mime_type)
                        print(
                            f"[GPTGOD] Edit from URL in content: {len(png_bytes)} bytes"
                        )
                        return png_bytes, "image/png"

            raise Exception("No image found in GPTGod edit response")

        except Exception as e:
            raise Exception(f"GPTGod edit failed: {str(e)}")


class ProviderFactory:
    """Factory for creating provider instances"""

    PROVIDER_TYPES = {
        "google": "Google Gemini (Official)",
        "yunwu": "Yunwu.ai",
        "openrouter": "OpenRouter",
        "gptgod": "GPTGod",
    }

    @staticmethod
    def create_provider(config: ProviderConfig) -> BaseProvider:
        """Create provider instance based on config"""
        provider_type = config.provider_type.lower()

        if provider_type == "yunwu":
            return YunwuProvider(config)
        elif provider_type == "openrouter":
            return OpenRouterProvider(config)
        elif provider_type == "gptgod":
            return GPTGodProvider(config)
        elif provider_type == "google":
            # Return original Gemini API (will be handled separately)
            raise Exception("Google provider handled by gemini_api.py")
        else:
            raise Exception(f"Unknown provider type: {config.provider_type}")

    @staticmethod
    def get_provider_list():
        """Get list of available providers"""
        return [
            (key, value, "") for key, value in ProviderFactory.PROVIDER_TYPES.items()
        ]
