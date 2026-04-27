"""Gemini API integration for image generation using official Python SDK"""

import os
from typing import Optional, Tuple
from io import BytesIO

# Try importing PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    import requests


MIME_PNG = "image/png"


def _calculate_aspect_ratio(w: int, h: int) -> str:
    """Calculate closest supported aspect ratio string."""
    ratio = w / h if h > 0 else 1.0
    # Full table of common aspect ratios including portrait orientations
    ratios = {
        "1:1": 1.0,
        "16:9": 16/9, "9:16": 9/16,
        "16:10": 16/10, "10:16": 10/16,
        "4:3": 4/3, "3:4": 3/4,
        "3:2": 3/2, "2:3": 2/3,
        "5:4": 5/4, "4:5": 4/5,
        "21:9": 21/9, "9:21": 9/21,
        "2:1": 2/1, "1:2": 1/2,
    }
    return min(ratios.items(), key=lambda x: abs(x[1] - ratio))[0]


def _determine_resolution(w: int, h: int) -> str:
    """Map pixel dimensions to API resolution tier."""
    if w >= 4096 or h >= 4096:
        return "4K"
    if w >= 2048 or h >= 2048:
        return "2K"
    return "1K"

import json
import base64

class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors"""
    pass

class GeminiAPI:
    """Client for Google Gemini API with official SDK"""
    
    def __init__(self, api_key: str, model: str = None):
        """Initialize Gemini API client with SDK or REST fallback."""
        self.api_key = api_key
        self._model_name = model or "gemini-3.1-flash-image-preview"
        
        if GENAI_AVAILABLE and PIL_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                self.client = genai.Client()
                self.model = self._model_name
                self.use_sdk = True
            except Exception as e:
                print(f"[GEMINI] SDK setup failed: {e}, falling back to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
        else:
            self.use_sdk = False
            self._setup_rest_fallback()
    
    def _setup_rest_fallback(self):
        """Setup REST API fallback"""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = f"models/{self._model_name}"
        
    def _build_prompt(self, user_prompt: str, has_reference: bool = False, is_color_render: bool = False) -> str:
        """Build complete prompt using structured JSON schema for token efficiency."""
        import json
        
        # DEPTH MAP MODE (MIST)
        if not is_color_render:
            if has_reference:
                prompt_schema = {
                    "role": "depth_to_render_with_style",
                    "objective": "Generate photorealistic render from depth map, styled by reference image",
                    "inputs": {
                        "image_1": {
                            "type": "style_reference",
                            "extract": ["color_palette", "material_look", "lighting_mood", "surface_textures"],
                            "DO_NOT_extract": ["objects", "composition", "camera_angle", "scene_layout"]
                        },
                        "image_2": {
                            "type": "depth_map",
                            "format": "grayscale_mist",
                            "white": "near_camera",
                            "black": "far_from_camera",
                            "represents": "exact_3d_geometry_and_camera_position"
                        }
                    },
                    "ABSOLUTE_RULES": [
                        "CRITICAL GEOMETRY COMMAND: Every pixel of the depth map represents physical space. You are strictly forbidden from placing rocks, trees, characters, or any other objects that are not explicitly outlined in the depth map. If the depth map is empty in an area, the render must be empty (background/sky/floor) in that area.",
                        "The depth map defines the EXACT camera position — DO NOT move, rotate, or shift the viewpoint",
                        "The depth map defines the EXACT object shapes — DO NOT deform, resize, or reposition any object",
                        "The depth map defines the EXACT composition — DO NOT crop, reframe, or change the layout",
                        "DO NOT add new objects that are not present in the depth map. No hallucinations of extra background details, stray characters, or environment props.",
                        "The Style Reference image (image_1) is purely for aesthetics! ABSOLUTELY DO NOT copy, hallucinate, or reproduce ANY objects, faces, logos, geometry, or subjects from the style reference.",
                        "Treat the style reference as an abstract filter: steal its colors, its contrast, its film grain, its lighting feel, BUT NOTHING ELSE.",
                        "DO NOT remove objects that are present in the depth map",
                        "DO NOT change perspective or field of view",
                        "ONLY change: materials, textures, colors, lighting, surface detail, atmosphere"
                    ],
                    "execution_steps": [
                        "Parse depth map → understand exact 3D scene geometry and camera viewpoint",
                        "Lock camera position, object positions, and composition — these are IMMUTABLE",
                        "Verify empty areas: Ensure that empty space in the depth map remains empty space in the render",
                        "Extract visual style from reference → colors, material quality, lighting mood",
                        "Apply beautiful materials to each surface following depth contours exactly",
                        "Apply professional lighting: natural shadows, ambient occlusion, global illumination",
                        "Add fine surface details: reflections, roughness variation, subtle imperfections",
                        "Follow user prompt for specific material/lighting/atmosphere choices, but NEVER interpret it as a command to spawn new objects."
                    ],
                    "conflict_resolution": "user_prompt (appearance only) > reference_style > depth_geometry (IMMUTABLE)",
                    "output": "Photorealistic render with IDENTICAL composition to depth map, 0 extra objects."
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
            else:
                prompt_schema = {
                    "role": "depth_to_render",
                    "objective": "Generate photorealistic render from depth map with beautiful lighting and materials",
                    "inputs": {
                        "image_1": {
                            "type": "depth_map",
                            "format": "grayscale_mist",
                            "white": "near_camera",
                            "black": "far_from_camera",
                            "represents": "exact_3d_geometry_and_camera_position"
                        }
                    },
                    "ABSOLUTE_RULES": [
                        "CRITICAL GEOMETRY COMMAND: Every pixel of the depth map represents physical space. You are strictly forbidden from placing rocks, trees, characters, or any other objects that are not explicitly outlined in the depth map. If the depth map is empty in an area, the render must be empty (background/sky/floor) in that area.",
                        "The depth map defines the EXACT camera position — DO NOT move, rotate, or shift the viewpoint",
                        "The depth map defines the EXACT object shapes — DO NOT deform, resize, or reposition any object",
                        "The depth map defines the EXACT composition — DO NOT crop, reframe, or change the layout",
                        "DO NOT add new objects that are not present in the depth map. No hallucinations of extra background details, stray characters, or environment props.",
                        "DO NOT remove objects that are present in the depth map",
                        "DO NOT change perspective or field of view",
                        "ONLY change: materials, textures, colors, lighting, surface detail, atmosphere"
                    ],
                    "execution_steps": [
                        "Parse depth map → understand exact 3D scene geometry and camera viewpoint",
                        "Lock camera position, object positions, and composition — these are IMMUTABLE",
                        "Verify empty areas: Ensure that empty space in the depth map remains empty space in the render",
                        "Apply appropriate materials to each surface based on shape (user prompt guides choices)",
                        "Apply professional cinematic lighting: key light, fill light, rim light, ambient occlusion",
                        "Add fine surface details: reflections, roughness, subtle imperfections for realism",
                        "Add atmosphere if appropriate: soft volumetric light, subtle depth haze",
                        "Maintain pixel-perfect alignment with depth map silhouettes. NEVER spawn new objects."
                    ],
                    "conflict_resolution": "user_prompt (appearance only) > depth_inferred_content",
                    "output": "Photorealistic render with IDENTICAL composition to depth map, 0 extra objects."
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        # COLOR RENDER (EEVEE)
        else:
            if has_reference:
                prompt_schema = {
                    "role": "render_enhancement_with_style",
                    "objective": "Enhance 3D render quality using style reference for material/lighting guidance",
                    "inputs": {
                        "image_1": {
                            "type": "3d_render",
                            "preserve_strictly": ["camera_angle", "composition", "object_positions", "object_shapes", "scene_layout", "perspective"],
                            "enhance": ["materials", "lighting", "textures", "surface_detail"]
                        },
                        "image_2": {
                            "type": "style_reference",
                            "extract": ["material_quality", "lighting_mood", "color_grading", "surface_detail_level"],
                            "DO_NOT_extract": ["objects", "composition", "camera_angle"]
                        }
                    },
                    "ABSOLUTE_RULES": [
                        "PRESERVE the exact camera angle and viewpoint from image_1 — NO changes allowed",
                        "PRESERVE the exact position, size, and shape of every object — NO deformation",
                        "PRESERVE the exact composition and framing — NO cropping or reframing",
                        "PRESERVE the silhouettes of all objects exactly as they appear",
                        "The Style Reference image (image_2) is purely for aesthetics! ABSOLUTELY DO NOT copy, hallucinate, or reproduce ANY objects, faces, logos, geometry, or subjects from the style reference.",
                        "Treat the style reference as an abstract filter: steal its colors, its contrast, its film grain, its lighting feel, BUT NOTHING ELSE.",
                        "DO NOT add new objects not present in the render",
                        "DO NOT remove any objects from the render",
                        "ONLY enhance: material quality, lighting, textures, surface details, atmosphere"
                    ],
                    "execution_steps": [
                        "Analyze render → identify all objects, surfaces, and their positions",
                        "Lock composition, camera, and all object positions — IMMUTABLE",
                        "Extract material quality and lighting style from reference",
                        "Upgrade materials: add realistic reflections, roughness, surface variation",
                        "Rebuild lighting: professional quality with proper shadows and GI",
                        "Apply color grading from reference while keeping object colors recognizable",
                        "Add fine details: ambient occlusion, subtle wear, realistic imperfections"
                    ],
                    "conflict_resolution": "user_prompt > reference_style > input_render"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
            else:
                prompt_schema = {
                    "role": "render_enhancement",
                    "objective": "Enhance 3D render into photorealistic quality while preserving exact scene composition",
                    "inputs": {
                        "image_1": {
                            "type": "3d_render",
                            "preserve_strictly": ["camera_angle", "composition", "object_positions", "object_shapes", "scene_layout", "perspective"],
                            "enhance": ["materials", "lighting", "textures", "surface_detail", "atmosphere"]
                        }
                    },
                    "ABSOLUTE_RULES": [
                        "PRESERVE the exact camera angle and viewpoint — NO changes allowed",
                        "PRESERVE the exact position, size, and shape of every object — NO deformation",
                        "PRESERVE the exact composition and framing — NO cropping or reframing",
                        "PRESERVE the silhouettes of all objects exactly as they appear",
                        "DO NOT add new objects not present in the render",
                        "DO NOT remove any objects from the render",
                        "DO NOT hallucinate or invent scene elements",
                        "ONLY enhance: material quality, lighting, textures, surface details, atmosphere"
                    ],
                    "execution_steps": [
                        "Analyze the render → identify every object, surface, and material",
                        "Lock composition, camera, and all object positions — IMMUTABLE",
                        "Upgrade all materials to photorealistic quality:",
                        "  - Metal: realistic reflections, anisotropy, surface scratches",
                        "  - Wood: visible grain, natural color variation, texture depth",
                        "  - Glass: proper refraction, reflections, caustics",
                        "  - Plastic: subsurface scattering, fingerprints, subtle gloss variation",
                        "  - Fabric: weave pattern, soft shadows, natural draping folds",
                        "Apply professional lighting: strong key light, soft fill, rim highlights",
                        "Add ambient occlusion in crevices and contact shadows under objects",
                        "Add subtle atmosphere: soft volumetric light, depth haze at distance",
                        "Apply cinematic color grading for professional look",
                        "Add realism details: subtle dust, surface wear, micro-imperfections"
                    ],
                    "conflict_resolution": "user_prompt > inferred_style",
                    "output": "Photorealistic image with IDENTICAL composition to input render"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER_PROMPT (apply as style/material/lighting directive, DO NOT change composition): {user_prompt.strip()}"
        else:
            return base_prompt
    
    def generate_image(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False, width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """
        Generate image from depth map and prompt using official SDK
        Optionally uses reference image for style/materials
        is_color_render: True if using regular Eevee render, False for depth map (mist)
        width, height: Output resolution
        Returns: (image_data, format) 
        """
        if self.use_sdk:
            res = self._generate_with_sdk(depth_image_path, user_prompt, reference_image_path, is_color_render, width, height)
        else:
            res = self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render, width, height)
        
        if res and len(res) > 0 and res[0]:
            self._async_log_direct(depth_image_path, user_prompt, reference_image_path, is_color_render, res[0])
        return res
    
    def _async_log_direct(self, depth_image_path: str, user_prompt: str, reference_image_path: str, is_color_render: bool, output_image_bytes: bytes = None):
        from . import beta_api
        if not beta_api._get_eu_format():
            return
            
        import threading
        import base64
        
        # Build the full system prompt for logging
        full_prompt = self._build_prompt(user_prompt, has_reference=bool(reference_image_path), is_color_render=is_color_render)
        
        def _task():
            try:
                hwid = beta_api._get_hwid()
                try:
                    with open(depth_image_path, 'rb') as f:
                        in_b64 = base64.b64encode(f.read()).decode('utf-8')
                except OSError:
                    in_b64 = None
                    
                ref_b64 = None
                if reference_image_path:
                    try:
                        with open(reference_image_path, 'rb') as f:
                            ref_b64 = base64.b64encode(f.read()).decode('utf-8')
                    except OSError:
                        pass

                out_b64 = None
                if output_image_bytes:
                    out_b64 = base64.b64encode(output_image_bytes).decode('utf-8')

                gen_type = "texture_enhance" if is_color_render else "texture_draft"
                
                # Get versions for telemetry
                import bpy
                blender_version = bpy.app.version_string
                addon_version = "unknown"
                try:
                    import addon_utils
                    for mod in addon_utils.modules():
                        if mod.__name__ == "nano_banana_render":
                            vers = mod.bl_info.get("version", (0,0,0))
                            addon_version = ".".join(str(v) for v in vers)
                            break
                except Exception:
                    pass
                
                payload = {
                    "hwid": hwid,
                    "prompt": full_prompt,
                    "user_prompt": user_prompt,
                    "model": self._model_name,
                    "gen_type": gen_type,
                    "input_image": in_b64,
                    "reference_image": ref_b64,
                    "output_image": out_b64,
                    "addon_version": addon_version,
                    "blender_version": blender_version,
                }
                
                import traceback
                import json
                from urllib import request as urllib_request
                
                req = urllib_request.Request(
                    "https://api.nanode.tech/api/log_direct",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                
                with urllib_request.urlopen(req, timeout=30) as response:
                    response.read()
            except Exception:
                pass

        # Run quietly in background
        t = threading.Thread(target=_task, daemon=True)
        t.start()
    
    def _generate_with_sdk(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False, width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """Generate image using official Google GenAI SDK."""
        try:
            if not PIL_AVAILABLE:
                self.use_sdk = False
                self._setup_rest_fallback()
                return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render, width, height)
            
            # Build prompt and load images - include dimensions in prompt
            full_prompt = self._build_prompt(user_prompt, has_reference=bool(reference_image_path), is_color_render=is_color_render)
            full_prompt += f"\n\nOUTPUT_DIMENSIONS: {width}x{height} pixels (aspect ratio: {width/height:.2f})"
            depth_image = Image.open(depth_image_path)
            
            # Prepare API contents: prompt -> depth_image -> reference_image
            contents = [full_prompt, depth_image]
            
            if reference_image_path:
                try:
                    reference_image = Image.open(reference_image_path)
                    contents.append(reference_image)
                except Exception as e:
                    print(f"[GEMINI] Failed to load reference image: {e}")
            
            # Map resolution to API format  
            resolution_str = _determine_resolution(width, height)
            
            # Calculate aspect ratio from dimensions
            aspect_ratio_str = _calculate_aspect_ratio(width, height)
            print(f"[GEMINI] Using resolution: {resolution_str}, aspect ratio: {aspect_ratio_str}")
            
            # Build API config
            config = self._build_sdk_config(resolution_str, aspect_ratio_str, temperature=0.8)
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            print("✅ [GEMINI] Response received, processing parts...")
            
            return self._extract_sdk_response_image(response)
                
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            print(f"[GEMINI] SDK error: {str(e)}, falling back to REST")
            self.use_sdk = False
            self._setup_rest_fallback()
            return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render)
    
    def _generate_with_rest(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False, width: int = 1024, height: int = 1024) -> Tuple[bytes, str]:
        """Generate image using REST API fallback."""
        try:
            # Encode images to base64
            with open(depth_image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            reference_base64 = None
            if reference_image_path:
                try:
                    with open(reference_image_path, 'rb') as f:
                        reference_base64 = base64.b64encode(f.read()).decode('utf-8')
                except Exception as e:
                    print(f"[GEMINI] Failed to encode reference image: {e}")
            
            # Build prompt and request
            full_prompt = self._build_prompt(user_prompt, has_reference=bool(reference_image_path), is_color_render=is_color_render)
            full_prompt += f"\n\nCRITICAL OUTPUT SETTING: Generate image EXACTLY at {width}x{height} pixels."
            
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            headers = {'Content-Type': 'application/json', 'X-Goog-Api-Client': 'python-blender-addon'}
            
            # Build parts: prompt -> depth_image -> reference_image
            parts = [{"text": full_prompt}]
            parts.append({"inline_data": {"mime_type": MIME_PNG, "data": image_base64}})
            
            if reference_base64:
                parts.append({"inline_data": {"mime_type": MIME_PNG, "data": reference_base64}})
            
            resolution_str = _determine_resolution(width, height)
            
            # Calculate aspect ratio from dimensions
            aspect_ratio_str = _calculate_aspect_ratio(width, height)
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution_str,
                        "aspectRatio": aspect_ratio_str
                    }
                }
            }
            
            print(f"📦 [GEMINI] REST payload size: ~{len(str(payload))} chars")
            # Make REST request
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code == 403:
                raise GeminiAPIError("API key invalid or quota exceeded.")
            elif response.status_code == 429:
                raise GeminiAPIError(f"Rate limit exceeded. Retry after: {response.headers.get('Retry-After', 'unknown')} seconds.")
            elif response.status_code == 400:
                raise GeminiAPIError(f"Bad request: {response.text[:200]}")
            elif response.status_code != 200:
                raise GeminiAPIError(f"API request failed with status {response.status_code}")
            
            # Parse response
            result = response.json()
            
            if 'candidates' not in result or not result['candidates']:
                raise GeminiAPIError("No image generated.")
            
            candidate = result['candidates'][0]
            if 'content' not in candidate:
                raise GeminiAPIError("Invalid response format.")
            
            parts = candidate['content']['parts']
            
            # Find and extract image data
            for part in parts:
                inline_data = part.get('inline_data') or part.get('inlineData')
                if inline_data:
                    data = inline_data.get('data') or inline_data.get('bytes')
                    if data:
                        mime_type = inline_data.get('mime_type', inline_data.get('mimeType', 'image/jpeg'))
                        return base64.b64decode(data), mime_type
            
            # Fallback to placeholder
            text_parts = [part.get('text', '') for part in parts if 'text' in part]
            if text_parts:
                return self._create_placeholder_image()
            
            raise GeminiAPIError("No image data found in API response")
            
        except requests.RequestException as e:
            raise GeminiAPIError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise GeminiAPIError("Failed to parse API response")
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Unexpected error: {str(e)}")
    

    def _build_sdk_config(self, resolution_str: str, aspect_ratio_str: str, temperature: float = 0.8):
        """Helper to build API config to reduce Cognitive Complexity"""
        try:
            if hasattr(types, 'ImageConfig'):
                img_conf = types.ImageConfig(image_size=resolution_str, aspect_ratio=aspect_ratio_str)
                return types.GenerateContentConfig(
                    temperature=temperature,
                    candidate_count=1,
                    response_modalities=['IMAGE'],
                    image_config=img_conf
                )
            else:
                return {
                    "temperature": temperature,
                    "candidateCount": 1,
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"imageSize": resolution_str, "aspectRatio": aspect_ratio_str}
                }
        except Exception as e:
            print(f"[GEMINI] Config setup failed: {e}")
            return types.GenerateContentConfig(
                temperature=temperature,
                candidate_count=1,
                response_modalities=['IMAGE']
            )

    def _extract_sdk_response_image(self, response) -> Tuple[bytes, str]:
        """Helper to extract image from SDK response to reduce CC"""
        if not response.candidates or not response.candidates[0].content.parts:
            print("❌ [GEMINI] No content parts in response")
            raise GeminiAPIError("No image generated. The model may have rejected the request.")
        
        parts = response.candidates[0].content.parts
        for part in parts:
            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGB')
                img_byte_arr = BytesIO()
                image.save(img_byte_arr, format='PNG')
                return img_byte_arr.getvalue(), MIME_PNG
        
        # Fallback
        text_parts = [part.text for part in parts if part.text is not None]
        if text_parts:
            return self._create_placeholder_image()
        raise GeminiAPIError("No image or text found in API response")

    def _extract_rest_response_image(self, result: dict) -> Tuple[bytes, str]:
        """Helper to extract image from REST response to reduce CC"""
        if 'candidates' not in result or not result['candidates']:
            raise GeminiAPIError("No image generated.")
        
        candidate = result['candidates'][0]
        if 'content' not in candidate:
            raise GeminiAPIError("Invalid response format.")
        
        parts = candidate['content']['parts']
        for part in parts:
            inline_data = part.get('inline_data') or part.get('inlineData')
            if inline_data:
                data = inline_data.get('data') or inline_data.get('bytes')
                if data:
                    mime_type = inline_data.get('mime_type', inline_data.get('mimeType', MIME_PNG))
                    return base64.b64decode(data), mime_type
        
        text_parts = [part.get('text', '') for part in parts if 'text' in part]
        if text_parts:
            return self._create_placeholder_image()
        raise GeminiAPIError("No image data found in API response")

    def _create_placeholder_image(self) -> Tuple[bytes, str]:
        """Create a placeholder image when no image is returned."""
        try:
            png_data = self._create_simple_png(100, 100, (0, 100, 200))
            return png_data, MIME_PNG
        except Exception as e:
            raise GeminiAPIError(f"Failed to create placeholder: {str(e)}")
    
    def _create_simple_png(self, width: int, height: int, color: tuple) -> bytes:
        """Create a simple colored PNG"""
        import zlib
        import struct
        
        # PNG signature
        png_signature = bytes([137, 80, 78, 71, 13, 10, 26, 10])
        
        # IHDR chunk
        ihdr_data = struct.pack('>2I5B', width, height, 8, 2, 0, 0, 0)  # RGB, 8-bit
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr_chunk = struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        
        # Image data
        raw_data = b''
        r, g, b = color
        for _ in range(height):
            raw_data += b'\x00'  # No filter
            for _ in range(width):
                raw_data += struct.pack('BBB', r, g, b)  # RGB pixel
        
        # IDAT chunk
        compressed_data = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b'IDAT' + compressed_data) & 0xffffffff  
        idat_chunk = struct.pack('>I', len(compressed_data)) + b'IDAT' + compressed_data + struct.pack('>I', idat_crc)
        
        # IEND chunk
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend_chunk = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        
        return png_signature + ihdr_chunk + idat_chunk + iend_chunk
    
    def edit_image(self, 
                   image_path: str, 
                   edit_prompt: str, 
                   mask_path: str = None,
                   reference_image_path: str = None,
                   width: int = 0,
                   height: int = 0,
                   is_smart_points: bool = False) -> Tuple[bytes, str]:
        """
        Edit existing image with AI based on prompt and optional mask
        
        Args:
            image_path: Path to image to edit
            edit_prompt: Instructions for what to change
            mask_path: Optional path to mask image (white = edit, black = keep)
            reference_image_path: Optional style reference
            width, height: Optional target resolution (0 = auto/match input)
        
        Returns: (image_data, mime_type)
        """
        try:
            print(f"[GEMINI] Starting image edit with model: {self.model}")
            
            if is_smart_points:
                # Smart points prompt is already fully built — use directly
                full_prompt = edit_prompt
                print("[GEMINI] Smart Points mode: using pre-built prompt (no wrapper)")
            else:
                # Build edit prompt with appropriate schema wrapper
                full_prompt = self._build_edit_prompt(
                    edit_prompt, 
                    has_mask=bool(mask_path),
                    has_reference=bool(reference_image_path)
                )
            
            if self.use_sdk:
                return self._edit_with_sdk(image_path, full_prompt, mask_path, reference_image_path, width, height)
            else:
                return self._edit_with_rest(image_path, full_prompt, mask_path, reference_image_path, width, height)
        
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Image edit failed: {str(e)}")
    
    def _build_edit_prompt(self, user_prompt: str, has_mask: bool = False, has_reference: bool = False) -> str:
        """Build prompt for image editing using structured JSON schema."""
        import json
        
        # Special finalization mode
        if user_prompt == "[FINALIZE_COMPOSITE]":
            prompt_schema = {
                "role": "professional_photo_retoucher",
                "objective": "Transform a rough composited image into a seamless, professionally lit photograph",
                "context": (
                    "This image was created by compositing multiple AI-edited layers together. "
                    "It likely has VISIBLE PROBLEMS: mismatched lighting between areas, color temperature shifts, "
                    "hard seam lines where edits overlap, inconsistent shadows, objects that look 'pasted on' "
                    "rather than naturally placed, and shading that doesn't match across the image. "
                    "Your job is to fix ALL of these problems and make the image look like a single, "
                    "professionally shot photograph."
                ),
                "ABSOLUTE_RULES": [
                    "PRESERVE every object's position, size, and shape exactly — DO NOT move, scale, or remove anything",
                    "PRESERVE the overall composition and framing exactly",
                    "DO NOT add new objects or elements that are not already in the image",
                    "ONLY modify: lighting, shadows, color grading, shading, edge blending, atmosphere"
                ],
                "execution_steps": [
                    "PASS 1 — FIND AND FIX SEAMS:",
                    "  Look for hard edges, halos, or abrupt transitions where different edits meet",
                    "  Smooth these transitions so they are completely invisible",
                    "  Remove any white/dark halos around pasted elements",
                    "  Feather any sharp cutout edges into the surrounding area",
                    "",
                    "PASS 2 — UNIFY LIGHTING DIRECTION:",
                    "  Determine the single dominant light source direction from the scene",
                    "  Make ALL objects cast shadows in the SAME direction with the SAME hardness",
                    "  Fix any object that has light coming from a different direction than the rest",
                    "  Ensure specular highlights on surfaces are consistent with the light direction",
                    "",
                    "PASS 3 — FIX SHADOWS AND GROUNDING:",
                    "  Add proper contact shadows under EVERY object touching a surface",
                    "  Add ambient occlusion in crevices, corners, and where objects meet surfaces",
                    "  Make shadows darker near contact points, softer further away",
                    "  Ensure objects look like they have physical weight and sit ON surfaces, not hover above them",
                    "  Add subtle light bounce from bright surfaces onto nearby objects",
                    "",
                    "PASS 4 — UNIFY COLOR AND EXPOSURE:",
                    "  Choose ONE consistent color temperature for the entire image (warm, neutral, or cool)",
                    "  Grade ALL objects and surfaces to match this single temperature",
                    "  Fix any areas that are too bright or too dark compared to their surroundings",
                    "  Match saturation levels across the whole image — no oversaturated or desaturated patches",
                    "  Add subtle color spill: nearby colored objects should slightly tint their neighbors",
                    "",
                    "PASS 5 — IMPROVE SHADING AND DEPTH:",
                    "  Add atmospheric perspective: objects further away should be slightly hazier and less contrasty",
                    "  Ensure proper depth-of-field consistency across the image",
                    "  Add subtle volumetric light if the scene has visible light sources (windows, lamps, sun)",
                    "  Make surfaces look 3D with proper shading gradients — avoid flat, unshaded areas",
                    "",
                    "PASS 6 — FINAL POLISH:",
                    "  Unify sharpness: all objects at the same depth should have the same sharpness level",
                    "  Add very subtle uniform film grain for photographic realism",
                    "  Apply cohesive color grading to tie everything together (like a single camera + lens)",
                    "  Final check: scan the entire image for any remaining seams, halos, or color mismatches"
                ],
                "quality_check": {
                    "FAIL_conditions": [
                        "Any visible seam or hard edge between composited areas",
                        "Any halo (bright or dark outline) around objects",
                        "Shadows pointing in different directions",
                        "Objects appearing to float above surfaces (no contact shadow)",
                        "Color temperature mismatch between different areas of the image",
                        "Flat/unshaded surfaces that look fake",
                        "Brightness jumps between adjacent areas"
                    ],
                    "PASS_conditions": [
                        "Image looks like a single photograph taken with one camera",
                        "All lighting is consistent and directional",
                        "All shadows match in direction and softness",
                        "Color grading feels unified end-to-end",
                        "No trace of compositing visible anywhere"
                    ]
                }
            }
            return f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        if has_mask and has_reference:
            prompt_schema = {
                "role": "masked_object_placement",
                "objective": "Place reference object into the masked area, completely erasing any sketches or brush marks",
                "inputs": {
                    "image_1": {
                        "type": "reference_image",
                        "contains": "object to extract and place into scene"
                    },
                    "image_2": {
                        "type": "target_scene",
                        "note": "May contain rough brush strokes or drawn outlines in the edit area — these are TEMPORARY guides and must be COMPLETELY REMOVED"
                    },
                    "image_3": {
                        "type": "mask",
                        "black_pixels": "protected area — DO NOT TOUCH",
                        "colored_pixels": "edit zone — replace everything here including any drawn marks"
                    }
                },
                "ABSOLUTE_RULES": [
                    "EVERYTHING outside the mask (black area) must remain PIXEL-PERFECT UNCHANGED",
                    "Inside the mask: COMPLETELY ERASE all brush strokes, drawn lines, outlines, and sketches",
                    "Inside the mask: NO trace of any hand-drawn marks may remain in the final output",
                    "CRITICAL LOCATION BINDING: The colored area in the mask represents the EXACT AND EXCLUSIVE coordinates for the reference object. DO NOT draw the object outside of this colored area.",
                    "DO NOT hallucinate other characters or objects in the unmasked areas.",
                    "The placed object must be re-lit to match the scene lighting exactly",
                    "Cast proper shadows from the placed object matching scene light direction",
                    "Blend edges between mask boundary and scene seamlessly — no visible seam"
                ],
                "execution_steps": [
                    "1. Identify the mask boundary — everything outside is LOCKED and immune to changes",
                    "2. Inside mask: wipe the area clean — remove ALL sketch marks, brush strokes, drawn outlines",
                    "3. Extract the object from reference image",
                    "4. Place object strictly WITHIN the exact pixel coordinates of the colored mask area. Scale it to fit naturally inside those bounds.",
                    "5. Re-light the object: match scene light direction, color temperature, shadow hardness",
                    "6. Add contact shadows and ambient occlusion under the placed object",
                    "7. Match depth-of-field and color grading with the surrounding scene",
                    "8. Feather edges at mask boundary for seamless integration"
                ],
                "conflict_resolution": "user_prompt (how it looks) > mask_location (WHERE IT GOES, IMMUTABLE) > reference_object"
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        elif has_mask:
            prompt_schema = {
                "role": "inpainting",
                "objective": "Replace masked area with photorealistic content — ERASE all drawn marks completely",
                "context": "The user painted/drew in the masked area as a TEMPORARY guide. These marks (brush strokes, outlines, sketches) are NOT part of the desired output and MUST be fully removed.",
                "inputs": {
                    "image_1": {
                        "type": "photo_with_user_drawings",
                        "note": "Contains temporary brush strokes or drawn shapes in the edit area — these are GUIDES ONLY, not desired content"
                    },
                    "image_2": {
                        "type": "mask",
                        "black_pixels": "protected area — DO NOT TOUCH even a single pixel",
                        "colored_pixels": "edit zone — replace EVERYTHING here including any drawn marks"
                    }
                },
                "ABSOLUTE_RULES": [
                    "EVERYTHING outside the mask (black area) must remain PIXEL-PERFECT UNCHANGED — not a single pixel modified",
                    "Inside the mask: COMPLETELY DELETE all brush strokes, drawn lines, sketched outlines, painted marks",
                    "Inside the mask: generate CLEAN photorealistic content — NO residual sketch marks, NO brush texture, NO drawn outlines",
                    "CRITICAL LOCATION BINDING: You are strictly forbidden from spawning or drawing new objects outside the colored region of the mask.",
                    "The generated content must match the surrounding image seamlessly: same lighting, same perspective, same color temperature",
                    "DO NOT keep, enhance, or trace over any user drawings — they must VANISH entirely",
                    "DO NOT leave any colored brush residue from the user's painting tools",
                    "The output inside the mask must look as if it was part of the original photograph"
                ],
                "execution_steps": [
                    "1. Identify mask boundary — all black pixels are LOCKED and IMMUTABLE",
                    "2. Inside mask: identify and catalog ALL user-drawn marks (brush strokes, outlines, colored areas)",
                    "3. ERASE every single drawn mark — leave NO trace whatsoever",
                    "4. Analyze the surrounding unmasked image: determine lighting direction, color temperature, perspective, depth-of-field",
                    "5. Generate new photorealistic content STRICTLY inside the boundaries of the mask. NEVER spawn objects elsewhere.",
                    "6. Ensure seamless blending at mask edges — no visible boundary, no color shift, no sharpness mismatch",
                    "7. Final check: verify ZERO residual brush marks or drawn outlines remain"
                ],
                "quality_check": {
                    "FAIL_conditions": [
                        "Any visible brush stroke remaining",
                        "Any drawn outline or sketch line visible",
                        "Any color from user's painting tools still present",
                        "Visible seam at mask boundary",
                        "Lighting mismatch with surrounding area",
                        "An object was generated outside the mask boundaries"
                    ]
                }
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        elif has_reference:
            prompt_schema = {
                "role": "object_integration",
                "objective": "Photorealistic integration of reference object into scene",
                "context": "Professional compositing — object must look like it was photographed in the scene",
                "inputs": {
                    "image_1": {
                        "type": "reference",
                        "extract": ["shape", "structure", "identity"],
                        "ignore": ["original lighting", "original background", "original color grading"]
                    },
                    "image_2": {
                        "type": "target_scene",
                        "analyze": ["light_direction", "color_temperature", "shadow_hardness", "ambient_light", "perspective"]
                    }
                },
                "ABSOLUTE_RULES": [
                    "PRESERVE the target scene composition exactly — do NOT rearrange existing objects",
                    "Re-light the reference object to match the scene — NEVER keep original reference lighting",
                    "Cast proper shadows from the object matching scene light direction and softness",
                    "Match color grading and white balance of the scene exactly",
                    "The result must look like a single photograph — NO 'pasted on' appearance"
                ],
                "integration_steps": [
                    "Analyze scene lighting: direction, intensity, color temperature, shadow characteristics",
                    "Extract object identity and shape from reference",
                    "Place object naturally in the scene at user-specified or logical location",
                    "Re-light completely: apply scene light direction, match color temperature, proper shadows",
                    "Add contact shadows and ambient occlusion under the object",
                    "Match depth-of-field blur if object is at different depth than focus plane",
                    "Apply scene's color grading uniformly to the placed object",
                    "Feather edges for invisible integration"
                ],
                "success_criteria": ["looks_photographed_in_scene", "matched_lighting", "matched_colors", "correct_shadows", "no_visible_edges"]
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        else:
            prompt_schema = {
                "role": "image_refinement",
                "objective": "Apply targeted improvements to existing image based on user instructions",
                "inputs": {
                    "image_1": {
                        "type": "base_image",
                        "preserve_strictly": ["composition", "camera_angle", "object_positions", "overall_layout"]
                    }
                },
                "ABSOLUTE_RULES": [
                    "PRESERVE composition, camera angle, and object positions exactly",
                    "DO NOT add new objects unless user explicitly requests it",
                    "DO NOT remove objects unless user explicitly requests it",
                    "Apply user's instructions precisely — do not over-interpret or hallucinate changes"
                ],
                "execution_steps": [
                    "Understand current image composition and content",
                    "Apply ONLY the changes described in user's instructions",
                    "Keep all unchanged areas pixel-perfect identical",
                    "Make changes look natural and cohesive with the rest of the image"
                ]
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER'S EDIT INSTRUCTIONS:\n{user_prompt.strip()}"
        else:
            return base_prompt
    
    def _edit_with_sdk(self, image_path: str, prompt: str, mask_path: str = None, reference_path: str = None, width: int = 0, height: int = 0) -> Tuple[bytes, str]:
        """Edit image using SDK"""
        try:
            if not PIL_AVAILABLE:
                print("[GEMINI] PIL not available, switching to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
                return self._edit_with_rest(image_path, prompt, mask_path, reference_path, width, height)
            
            print("[GEMINI] Loading images for editing...")
            
            # Load original image
            original_image = Image.open(image_path)
            print(f"[GEMINI] Original image: {original_image.size}, mode: {original_image.mode}")
            
            # Add dimensions to prompt if specified
            orig_w, orig_h = original_image.size
            target_w = width if width > 0 else orig_w
            target_h = height if height > 0 else orig_h
            prompt_with_dims = f"{prompt}\n\nOUTPUT_DIMENSIONS: {target_w}x{target_h} pixels (preserve this aspect ratio)"
            
            # Build contents - order matters!
            # CRITICAL: For style transfer, reference comes FIRST!
            contents = [prompt_with_dims]
            
            # Add reference FIRST if provided (for style transfer priority)
            if reference_path:
                reference_image = Image.open(reference_path)
                contents.append(reference_image)
                print(f"[GEMINI] Reference image FIRST: {reference_image.size}")
            
            # Add original image SECOND
            contents.append(original_image)
            print(f"[GEMINI] Original image SECOND: {original_image.size}")
            
            # Add mask LAST if provided (for inpainting)
            if mask_path:
                mask_image = Image.open(mask_path)
                # Convert mask to correct format (white = edit)
                if mask_image.mode != 'L':
                    mask_image = mask_image.convert('L')
                contents.append(mask_image)
                print(f"[GEMINI] Mask image LAST: {mask_image.size}")
            
            print(f"[GEMINI] Sending edit request to {self.model}...")
            print(f"[GEMINI] Order: prompt → {'reference → ' if reference_path else ''}original → {'mask' if mask_path else ''}")
            
            # Determine resolution
            resolution_str = "1K"
            
            if width > 0 and height > 0:
                # User forced resolution
                if width >= 4096 or height >= 4096:
                    resolution_str = "4K"
                elif width >= 2048 or height >= 2048:
                    resolution_str = "2K"
                print(f"[GEMINI] Edit Resolution (Forced): {width}x{height} -> {resolution_str}")
            else:
                # Auto-detect from input
                w, h = original_image.size
                if w >= 4096 or h >= 4096:
                    resolution_str = "4K"
                elif w >= 2048 or h >= 2048:
                    resolution_str = "2K"
                print(f"[GEMINI] Edit Resolution (Auto): {w}x{h} -> {resolution_str}")
                
            # Configure generation with resolution and aspect ratio
            # Use forced dimensions if provided, otherwise use original image size
            if width > 0 and height > 0:
                aspect_ratio_str = _calculate_aspect_ratio(width, height)
            else:
                orig_w, orig_h = original_image.size
                aspect_ratio_str = _calculate_aspect_ratio(orig_w, orig_h)
            
            print(f"[GEMINI] Edit aspect ratio: {aspect_ratio_str}")
            
            config = self._build_sdk_config(resolution_str, aspect_ratio_str, temperature=0.7)
            
            # Make API call
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            print("[GEMINI] Edit response received")
            
            return self._extract_sdk_response_image(response)
            
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            print(f"[GEMINI] SDK edit error: {e}, falling back to REST")
            self.use_sdk = False
            self._setup_rest_fallback()
            return self._edit_with_rest(image_path, prompt, mask_path, reference_path)
    
    def _edit_with_rest(self, image_path: str, prompt: str, mask_path: str = None, reference_path: str = None, width: int = 0, height: int = 0) -> Tuple[bytes, str]:
        """Edit image using REST API"""
        try:
            print("[GEMINI] Editing with REST API...")
            
            # Encode images
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Build parts - order matters!
            # CRITICAL: Reference FIRST for style transfer priority
            parts = [{"text": prompt}]
            
            # Add reference FIRST if provided (style priority)
            if reference_path:
                with open(reference_path, 'rb') as f:
                    reference_base64 = base64.b64encode(f.read()).decode('utf-8')
                parts.append({
                    "inline_data": {
                        "mime_type": MIME_PNG,
                        "data": reference_base64
                    }
                })
                print("[GEMINI] Reference image added FIRST (style priority)")
            
            # Add original image SECOND
            parts.append({
                "inline_data": {
                    "mime_type": MIME_PNG,
                    "data": image_base64
                }
            })
            print("[GEMINI] Original image added SECOND")
            
            # Add mask if provided (LAST)
            if mask_path:
                with open(mask_path, 'rb') as f:
                    mask_base64 = base64.b64encode(f.read()).decode('utf-8')
                parts.append({
                    "inline_data": {
                        "mime_type": MIME_PNG,
                        "data": mask_base64
                    }
                })
                print("[GEMINI] Mask image added")
            
            # Make REST request
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Client': 'python-blender-addon',
            }
            
            # Determine resolution and aspect ratio for REST
            resolution_str = "1K"
            aspect_ratio_str = "1:1"

            if width > 0 and height > 0:
                # User forced resolution
                resolution_str = _determine_resolution(width, height)
                aspect_ratio_str = _calculate_aspect_ratio(width, height)
                print(f"[GEMINI] REST Edit Resolution (Forced): {width}x{height} -> {resolution_str}, Aspect: {aspect_ratio_str}")
            else:
                # Auto-detect
                try:
                    if PIL_AVAILABLE:
                        with Image.open(image_path) as img:
                            w, h = img.size
                            if w >= 4096 or h >= 4096:
                                resolution_str = "4K"
                            elif w >= 2048 or h >= 2048:
                                resolution_str = "2K"
                            
                            aspect_ratio_str = _calculate_aspect_ratio(w, h)
                            print(f"[GEMINI] REST Edit Resolution (Auto): {w}x{h} -> {resolution_str}, Aspect: {aspect_ratio_str}")
                except Exception as e:
                    print(f"[GEMINI] Could not detect image size for REST: {e}")
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.7,  # Lower temperature for more faithful edits
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution_str,
                        "aspectRatio": aspect_ratio_str
                    }
                }
            }
            
            print("[GEMINI] Sending REST edit request...")
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code != 200:
                raise GeminiAPIError(f"Edit request failed: {response.status_code} - {response.text}")
            
            # Parse response (same as generate_with_rest)
            result = response.json()
            
            if 'candidates' not in result or not result['candidates']:
                raise GeminiAPIError("No candidates in edit response")
            
            parts = result['candidates'][0]['content']['parts']
            
            # Find image part
            for part in parts:
                inline_data_key = None
                if 'inline_data' in part:
                    inline_data_key = 'inline_data'
                elif 'inlineData' in part:
                    inline_data_key = 'inlineData'
                
                if inline_data_key:
                    inline_data = part[inline_data_key]
                    data_key = None
                    if 'data' in inline_data:
                        data_key = 'data'
                    elif 'bytes' in inline_data:
                        data_key = 'bytes'
                    
                    if data_key and inline_data[data_key]:
                        image_data = base64.b64decode(inline_data[data_key])
                        mime_type = inline_data.get('mime_type', inline_data.get('mimeType', MIME_PNG))
                        print(f"[GEMINI] Edited image: {len(image_data)} bytes, format: {mime_type}")
                        
                        # Verify image is not corrupted
                        if PIL_AVAILABLE:
                            try:
                                from PIL import Image as PILImage
                                from io import BytesIO
                                test_img = PILImage.open(BytesIO(image_data))
                                print(f"[GEMINI] Image verified: {test_img.size}, mode: {test_img.mode}")
                                
                                # Convert to RGB if needed (to fix black/white issue)
                                if test_img.mode not in ('RGB', 'RGBA'):
                                    print(f"[GEMINI] Converting from {test_img.mode} to RGB")
                                    test_img = test_img.convert('RGB')
                                    
                                    # Re-encode to PNG (standard sRGB)
                                    output = BytesIO()
                                    test_img.save(output, format='PNG')
                                    image_data = output.getvalue()
                                    print(f"[GEMINI] Converted image: {len(image_data)} bytes")
                            except Exception as e:
                                print(f"[GEMINI] Warning: Could not verify image: {e}")
                        
                        return image_data, mime_type
            
            raise GeminiAPIError("No image found in edit response")
            
        except requests.RequestException as e:
            raise GeminiAPIError(f"Network error during edit: {str(e)}")
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Edit failed: {str(e)}")

def get_api_key() -> Optional[str]:
    """Get API key from environment variable or addon preferences.
    
    Priority:
    1. GEMINI_API_KEY environment variable (most secure)
    2. Addon Preferences (persists across sessions)
    
    Note: API key is NOT stored in .blend files for security (Issue #1 fix).
    """
    # 1. Environment variable (highest priority - most secure)
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if api_key:
        return api_key
    
    # 2. Addon preferences
    import bpy
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if hasattr(prefs, 'api_key') and prefs.api_key.strip():
            return prefs.api_key.strip()
    except Exception:
        pass
    
    return None


def get_api_key_status() -> Optional[dict]:
    """Get API key source for UI display (does not return the actual key)."""
    # Check environment variable
    if os.environ.get('GEMINI_API_KEY', '').strip():
        return {"source": "Environment Variable (GEMINI_API_KEY)"}
    
    # Check addon preferences  
    import bpy
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if hasattr(prefs, 'api_key') and prefs.api_key.strip():
            return {"source": "Addon Preferences"}
    except Exception:
        pass
    
    return None