"""
API Provider abstraction layer for multiple image generation services
Supports: Google Gemini, Yunwu.ai, OpenRouter, GPTGod
"""

import os
import json
import base64
from typing import Optional, Tuple, Dict, Any
from io import BytesIO

# Try importing PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import requests for REST APIs
import requests


class ProviderConfig:
    """Configuration for an API provider"""
    def __init__(self, provider_type: str, api_key: str, base_url: str = "", model_id: str = ""):
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.model_id = model_id


class BaseProvider:
    """Base class for all providers"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
    
    def generate_image(self, depth_image_path: str, user_prompt: str, 
                      reference_image_path: str = None, is_color_render: bool = False,
                      width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """Generate image from depth map/render"""
        raise NotImplementedError("Subclasses must implement generate_image")
    
    def edit_image(self, image_path: str, edit_prompt: str, 
                  mask_path: str = None, reference_image_path: str = None,
                  width: int = 0, height: int = 0) -> Tuple[bytes, str]:
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
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _determine_resolution(self, width: int, height: int) -> str:
        """Map resolution to API format"""
        if width >= 4096 or height >= 4096:
            return "4K"
        elif width >= 2048 or height >= 2048:
            return "2K"
        return "1K"
    
    def _determine_aspect_ratio(self, width: int, height: int) -> str:
        """Calculate aspect ratio"""
        from math import gcd
        divisor = gcd(width, height)
        w_ratio = width // divisor
        h_ratio = height // divisor
        return f"{w_ratio}:{h_ratio}"
    
    def generate_image(self, depth_image_path: str, user_prompt: str,
                      reference_image_path: str = None, is_color_render: bool = False,
                      width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """Generate image using Yunwu.ai native Gemini API"""
        try:
            print(f"[YUNWU] Generating image with model: {self.model_id}")
            
            # Encode images
            depth_base64 = self._encode_image(depth_image_path)
            
            # Build parts array
            parts = [{"text": user_prompt}]
            
            # Add depth/render image
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": depth_base64
                }
            })
            
            # Add reference if provided
            if reference_image_path:
                ref_base64 = self._encode_image(reference_image_path)
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": ref_base64
                    }
                })
                print("[YUNWU] Reference image added")
            
            # Build request payload (Gemini native format)
            resolution = self._determine_resolution(width, height)
            aspect_ratio = self._determine_aspect_ratio(width, height)
            
            url = f"{self.base_url}/v1beta/models/{self.model_id}:generateContent"
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "aspectRatio": aspect_ratio,
                        "imageSize": resolution
                    }
                }
            }
            
            # Add API key to URL query parameter
            url = f"{url}?key={self.config.api_key}"
            
            print(f"[YUNWU] Requesting {resolution} resolution, aspect ratio {aspect_ratio}")
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code != 200:
                raise Exception(f"Yunwu API error {response.status_code}: {response.text}")
            
            # Parse response
            result = response.json()
            
            # Extract image from response
            if 'candidates' in result and result['candidates']:
                parts = result['candidates'][0].get('content', {}).get('parts', [])
                
                for part in parts:
                    if 'inlineData' in part or 'inline_data' in part:
                        inline_key = 'inlineData' if 'inlineData' in part else 'inline_data'
                        inline_data = part[inline_key]
                        data_key = 'data' if 'data' in inline_data else 'bytes'
                        
                        if data_key in inline_data:
                            image_data = base64.b64decode(inline_data[data_key])
                            print(f"[YUNWU] Image received: {len(image_data)} bytes")
                            return image_data, "image/png"
            
            raise Exception("No image found in Yunwu response")
            
        except Exception as e:
            raise Exception(f"Yunwu generation failed: {str(e)}")


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider (OpenAI-compatible API)""" 
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://openrouter.ai/api/v1"
        self.model_id = config.model_id or "google/gemini-3-pro-image-preview"
    
    def _encode_image_to_data_url(self, image_path: str) -> str:
        """Encode image to data URL"""
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{image_data}"
    
    def generate_image(self, depth_image_path: str, user_prompt: str,
                      reference_image_path: str = None, is_color_render: bool = False,
                      width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """Generate image using OpenRouter API"""
        try:
            print(f"[OPENROUTER] Generating with model: {self.model_id}")
            
            # Build messages array (OpenAI format with images)
            content_parts = [{"type": "text", "text": user_prompt}]
            
            # Add depth/render image
            depth_url = self._encode_image_to_data_url(depth_image_path)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": depth_url}
            })
            
            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": ref_url}
                })
                print("[OPENROUTER] Reference image added")
            
            # Determine resolution and aspect ratio
            resolution = "1K"
            if width >= 4096 or height >= 4096:
                resolution = "4K"
            elif width >= 2048 or height >= 2048:
                resolution = "2K"
            
            from math import gcd
            divisor = gcd(width, height)
            aspect_ratio = f"{width // divisor}:{height // divisor}"
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": content_parts
                    }
                ],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": aspect_ratio,
                    "image_size": resolution
                }
            }
            
            print(f"[OPENROUTER] Requesting {resolution}, aspect {aspect_ratio}")
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter API error {response.status_code}: {response.text}")
            
            result = response.json()
            
            # Extract image from response (OpenAI format)
            if 'choices' in result and result['choices']:
                message = result['choices'][0].get('message', {})
                
                # Check for images array
                if 'images' in message:
                    for img in message['images']:
                        image_url = img.get('image_url', {}).get('url', '')
                        if image_url.startswith('data:image'):
                            # Extract base64 data
                            base64_data = image_url.split(',')[1]
                            image_data = base64.b64decode(base64_data)
                            print(f"[OPENROUTER] Image received: {len(image_data)} bytes")
                            return image_data, "image/png"
            
            raise Exception("No image found in OpenRouter response")
            
        except Exception as e:
            raise Exception(f"OpenRouter generation failed: {str(e)}")


class GPTGodProvider(BaseProvider):
    """GPTGod provider (OpenAI-compatible)"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.gptgod.online/v1"
        
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
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{image_data}"
    
    def generate_image(self, depth_image_path: str, user_prompt: str,
                      reference_image_path: str = None, is_color_render: bool = False,
                      width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
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
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": depth_url}
            })
            
            # Add reference if provided
            if reference_image_path:
                ref_url = self._encode_image_to_data_url(reference_image_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": ref_url}
                })
                print("[GPTGOD] Reference image added")
            
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model_id,
                "stream": False,
                "n": 1,
                "messages": [
                    {
                        "role": "user",
                        "content": content_parts
                    }
                ]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code != 200:
                raise Exception(f"GPTGod API error {response.status_code}: {response.text}")
            
            result = response.json()
            
            # Parse GPTGod response (multiple formats supported)
            # Try direct images array
            if 'images' in result:
                for img_url in result['images']:
                    if img_url.startswith('data:image'):
                        base64_data = img_url.split(',')[1]
                        image_data = base64.b64decode(base64_data)
                        print(f"[GPTGOD] Image from images array: {len(image_data)} bytes")
                        return image_data, "image/png"
            
            # Try choices format
            if 'choices' in result and result['choices']:
                message_content = result['choices'][0].get('message', {}).get('content', '')
                
                # Check if content is array
                if isinstance(message_content, list):
                    for part in message_content:
                        if part.get('type') == 'image_url':
                            img_url = part.get('image_url', {}).get('url', '')
                            if img_url.startswith('data:image'):
                                base64_data = img_url.split(',')[1]
                                image_data = base64.b64decode(base64_data)
                                print(f"[GPTGOD] Image from content array: {len(image_data)} bytes")
                                return image_data, "image/png"
                
                # Check if content is string with URL
                if isinstance(message_content, str):
                    if message_content.startswith('data:image'):
                        base64_data = message_content.split(',')[1]
                        image_data = base64.b64decode(base64_data)
                        print(f"[GPTGOD] Image from content string: {len(image_data)} bytes")
                        return image_data, "image/png"
            
            raise Exception("No image found in GPTGod response")
            
        except Exception as e:
            raise Exception(f"GPTGod generation failed: {str(e)}")


class ProviderFactory:
    """Factory for creating provider instances"""
    
    PROVIDER_TYPES = {
        'google': 'Google Gemini (Official)',
        'yunwu': 'Yunwu.ai',
        'openrouter': 'OpenRouter',
        'gptgod': 'GPTGod'
    }
    
    @staticmethod
    def create_provider(config: ProviderConfig) -> BaseProvider:
        """Create provider instance based on config"""
        provider_type = config.provider_type.lower()
        
        if provider_type == 'yunwu':
            return YunwuProvider(config)
        elif provider_type == 'openrouter':
            return OpenRouterProvider(config)
        elif provider_type == 'gptgod':
            return GPTGodProvider(config)
        elif provider_type == 'google':
            # Return original Gemini API (will be handled separately)
            raise Exception("Google provider handled by gemini_api.py")
        else:
            raise Exception(f"Unknown provider type: {config.provider_type}")
    
    @staticmethod
    def get_provider_list():
        """Get list of available providers"""
        return [(key, value, "") for key, value in ProviderFactory.PROVIDER_TYPES.items()]
