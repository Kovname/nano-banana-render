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
    import json
    import base64

class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors"""
    pass

class GeminiAPI:
    """Client for Google Gemini API with official SDK"""
    
    def __init__(self, api_key: str):
        """Initialize Gemini API client with SDK or REST fallback."""
        self.api_key = api_key
        
        if GENAI_AVAILABLE and PIL_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                self.client = genai.Client()
                self.model = "gemini-3-pro-image-preview"
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
        self.model = "models/gemini-3-pro-image-preview"
        
    def _build_prompt(self, user_prompt: str, has_reference: bool = False, is_color_render: bool = False) -> str:
        """Build complete prompt using structured JSON schema for token efficiency."""
        import json
        
        # DEPTH MAP MODE (MIST)
        if not is_color_render:
            if has_reference:
                prompt_schema = {
                    "role": "depth_to_render_with_style",
                    "objective": "Generate photorealistic render from depth map + style reference",
                    "inputs": {
                        "image_1": {"type": "style_reference", "use_for": ["colors", "materials", "lighting", "textures"], "ignore": ["composition", "objects"]},
                        "image_2": {"type": "depth_map", "format": "grayscale", "white": "near", "black": "far", "use_for": ["geometry", "layout", "3d_structure"]}
                    },
                    "execution_steps": [
                        "Parse depth map -> understand 3D scene structure",
                        "Extract style from reference -> colors, materials, lighting mood",
                        "Combine: reference_style + depth_geometry -> photorealistic render",
                        "Match reference aspect ratio"
                    ],
                    "priority_rules": {"strict_mode": True},
                    "conflict_resolution": "user_prompt > reference_style > depth_map",
                    "user_prompt_role": "SUPREME_COMMAND for content decisions"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
            else:
                prompt_schema = {
                    "role": "depth_to_render",
                    "objective": "Generate photorealistic render from depth map only",
                    "inputs": {
                        "image_1": {"type": "depth_map", "format": "grayscale", "white": "near", "black": "far"}
                    },
                    "execution_steps": [
                        "Interpret depth map -> scene geometry",
                        "Generate appropriate materials, colors, lighting",
                        "Create photorealistic 3D render"
                    ],
                    "priority_rules": {"strict_mode": True},
                    "conflict_resolution": "user_prompt > depth_inferred_content",
                    "user_prompt_role": "PRIMARY_INSTRUCTION for materials, colors, lighting"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        # COLOR RENDER (EEVEE)
        else:
            if has_reference:
                prompt_schema = {
                    "role": "render_transformation_with_style",
                    "objective": "Aggressively transform low-quality render using style reference",
                    "inputs": {
                        "image_1": {"type": "3d_render", "use_for": ["geometry", "layout", "composition"], "ignore": ["materials", "lighting", "colors"]},
                        "image_2": {"type": "style_reference", "use_for": ["materials", "lighting", "colors", "mood", "atmosphere"]}
                    },
                    "execution_steps": [
                        "Preserve ONLY composition/layout from image_1",
                        "REPLACE all materials with image_2 style",
                        "REPLACE lighting: direction, intensity, color_temperature",
                        "REPLACE colors with image_2 palette",
                        "REPLICATE atmosphere, depth, mood from image_2"
                    ],
                    "constraints": {
                        "transformation_mode": "aggressive",
                        "preserve_geometry": True,
                        "copy_objects_from_style": False
                    },
                    "priority_rules": {"strict_mode": True},
                    "conflict_resolution": "user_prompt > reference_style > input_render"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
            else:
                prompt_schema = {
                    "role": "render_enhancement",
                    "objective": "Complete visual overhaul of low-quality 3D render",
                    "inputs": {
                        "image_1": {"type": "rough_3d_render", "use_for": ["composition", "layout"], "quality": "placeholder"}
                    },
                    "material_upgrades": {
                        "metal": "realistic_reflections + anisotropy + scratches",
                        "plastic": "varied_finish + color_variation + wear",
                        "wood": "visible_grain + natural_color + texture_depth",
                        "glass": "refraction + reflections + imperfections",
                        "fabric": "weave_patterns + soft_shadows + natural_draping"
                    },
                    "lighting_rebuild": ["3-point_or_natural", "strong_shadows", "bounce_light", "ambient_occlusion", "color_temperature_variation"],
                    "color_grading": ["professional", "harmonious_palette", "natural_surface_variation"],
                    "atmosphere": ["volumetric_lighting", "atmospheric_perspective", "particles_if_appropriate"],
                    "imperfections": ["scratches", "dents", "wear", "dust", "fingerprints"],
                    "constraints": {
                        "transformation_mode": "total",
                        "target_quality": "movie_vfx | high_end_product_photography"
                    },
                    "priority_rules": {"strict_mode": True},
                    "conflict_resolution": "user_prompt > inferred_style"
                }
                base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER_PROMPT (EXECUTE THIS): {user_prompt.strip()}"
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
            return self._generate_with_sdk(depth_image_path, user_prompt, reference_image_path, is_color_render, width, height)
        else:
            return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render, width, height)
    
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
            resolution_str = "4K" if width >= 4096 or height >= 4096 else "2K" if width >= 2048 or height >= 2048 else "1K"
            
            # Calculate aspect ratio from dimensions
            def calculate_aspect_ratio(w, h):
                """Calculate closest supported aspect ratio."""
                ratio = w / h
                # Supported ratios: 1:1, 16:9, 9:16, 4:3, 3:2
                ratios = {
                    "1:1": 1.0,
                    "16:9": 16/9,
                    "9:16": 9/16,
                    "4:3": 4/3,
                    "3:2": 3/2
                }
                closest = min(ratios.items(), key=lambda x: abs(x[1] - ratio))
                return closest[0]
            
            aspect_ratio_str = calculate_aspect_ratio(width, height)
            print(f"[GEMINI] Using resolution: {resolution_str}, aspect ratio: {aspect_ratio_str}")
            
            # Build API config
            try:
                config = types.GenerateContentConfig(
                    temperature=0.8,
                    candidate_count=1,
                    response_modalities=['IMAGE'],
                )
                
                # Try using ImageConfig if available
                if hasattr(types, 'ImageConfig'):
                    img_conf = types.ImageConfig(image_size=resolution_str, aspect_ratio=aspect_ratio_str)
                    config = types.GenerateContentConfig(
                        temperature=0.8,
                        candidate_count=1,
                        response_modalities=['IMAGE'],
                        image_config=img_conf
                    )
                else:
                    # Fallback to dictionary config
                    config = {
                        "temperature": 0.8,
                        "candidateCount": 1,
                        "responseModalities": ["IMAGE"],
                        "imageConfig": {"imageSize": resolution_str, "aspectRatio": aspect_ratio_str}
                    }
            except Exception as e:
                print(f"[GEMINI] Config setup failed: {e}")
                config = types.GenerateContentConfig(
                    temperature=0.8,
                    candidate_count=1,
                    response_modalities=['IMAGE']
                )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            print("✅ [GEMINI] Response received, processing parts...")
            
            # Process response parts
            if not response.candidates or not response.candidates[0].content.parts:
                print("❌ [GEMINI] No content parts in response")
                raise GeminiAPIError("No image generated. The model may have rejected the request.")
            
            parts = response.candidates[0].content.parts
            print(f"🧩 [GEMINI] Found {len(parts)} parts in response")
            
            # Find image part
            for i, part in enumerate(parts):
                print(f"🔍 [GEMINI] Part {i}: text={part.text is not None}, inline_data={part.inline_data is not None}")
                
                if part.text is not None:
                    print(f"📝 [GEMINI] Text part: {part.text[:100]}...")
                
                if part.inline_data is not None:
                    print("🖼️ [GEMINI] Found inline_data - extracting image...")
                    
                    # Convert to PIL Image and then to bytes
                    image = Image.open(BytesIO(part.inline_data.data))
                    
                    if image.mode not in ('RGB', 'RGBA'):
                        image = image.convert('RGB')
                    
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    return img_byte_arr.getvalue(), "image/png"
            
            # Fallback to placeholder if no image found
            text_parts = [part.text for part in parts if part.text is not None]
            if text_parts:
                return self._create_placeholder_image(f"Model response: {' '.join(text_parts)}")
            else:
                raise GeminiAPIError("No image or text found in API response")
                
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
            parts.append({"inline_data": {"mime_type": "image/png", "data": image_base64}})
            
            if reference_base64:
                parts.append({"inline_data": {"mime_type": "image/png", "data": reference_base64}})
            
            resolution_str = "4K" if width >= 4096 or height >= 4096 else "2K" if width >= 2048 or height >= 2048 else "1K"
            
            # Calculate aspect ratio from dimensions
            def calculate_aspect_ratio(w, h):
                ratio = w / h
                ratios = {"1:1": 1.0, "16:9": 16/9, "9:16": 9/16, "4:3": 4/3, "3:2": 3/2}
                return min(ratios.items(), key=lambda x: abs(x[1] - ratio))[0]
            
            aspect_ratio_str = calculate_aspect_ratio(width, height)
            
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
                inline_data_key = 'inline_data' if 'inline_data' in part else 'inlineData' if 'inlineData' in part else None
                
                if inline_data_key:
                    inline_data = part[inline_data_key]
                    data_key = 'data' if 'data' in inline_data else 'bytes' if 'bytes' in inline_data else None
                    
                    if data_key and inline_data[data_key]:
                        mime_type = inline_data.get('mime_type', inline_data.get('mimeType', 'image/jpeg'))
                        return base64.b64decode(inline_data[data_key]), mime_type
            
            # Fallback to placeholder
            text_parts = [part.get('text', '') for part in parts if 'text' in part]
            if text_parts:
                return self._create_placeholder_image(f"Model response: {' '.join(text_parts)}")
            
            raise GeminiAPIError("No image data found in API response")
            
        except requests.RequestException as e:
            raise GeminiAPIError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise GeminiAPIError("Failed to parse API response")
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Unexpected error: {str(e)}")
    
    def _create_placeholder_image(self, text_response: str) -> Tuple[bytes, str]:
        """Create a placeholder image when no image is returned."""
        try:
            png_data = self._create_simple_png(100, 100, (0, 100, 200))
            return png_data, "image/png"
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
        for y in range(height):
            raw_data += b'\x00'  # No filter
            for x in range(width):
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
                   height: int = 0) -> Tuple[bytes, str]:
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
            
            # Build edit prompt
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
                "role": "composite_finalization",
                "objective": "Unify composited image into seamless photorealistic photograph",
                "context": "Image created through multiple compositing steps - needs unification",
                "problems_to_fix": [
                    "color_temperature_conflicts",
                    "brightness_mismatches",
                    "contrast_differences",
                    "shadow_inconsistencies",
                    "visible_compositing_edges",
                    "ungrounded_objects"
                ],
                "execution_steps": {
                    "analyze": ["find_disconnected_areas", "detect_color_conflicts", "find_unnatural_edges"],
                    "unify_lighting": ["establish_dominant_light_direction", "match_shadow_hardness", "add_ambient_occlusion", "strengthen_contact_shadows"],
                    "color_harmony": ["choose_single_color_temperature", "grade_all_objects", "add_color_spill", "match_saturation"],
                    "exposure": ["unify_brightness", "match_contrast_levels", "balance_highlights_shadows"],
                    "integration": ["blend_compositing_edges", "remove_halos", "add_atmospheric_perspective", "unify_sharpness", "add_uniform_film_grain"],
                    "grounding": ["cast_appropriate_shadows", "add_reflections", "create_light_bounce", "add_depth_cues"]
                },
                "success_criteria": {
                    "required": ["unified_photograph", "consistent_lighting", "consistent_color_temperature", "no_visible_seams", "consistent_shadows", "grounded_objects", "color_harmony"]
                },
                "constraints": {
                    "strict_mode": True,
                    "never_allow": ["color_conflicts", "exposure_mismatches", "visible_edges", "pasted_on_look", "lighting_conflicts"]
                }
            }
            return f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        
        if has_mask and has_reference:
            prompt_schema = {
                "role": "object_placement_with_mask",
                "objective": "Place object from reference into masked area of scene",
                "inputs": {
                    "image_1": {"type": "reference", "contains": "object_to_add"},
                    "image_2": {"type": "scene", "contains": "target_location + sketch_to_erase"},
                    "image_3": {"type": "mask", "colored_area": "placement_location"}
                },
                "execution_steps": [
                    "Parse user_prompt for: what_object, where_to_place, how_to_place",
                    "Extract object from image_1",
                    "Find colored area in image_3 = exact placement spot",
                    "ERASE sketch from image_2",
                    "Place object at masked location",
                    "Relight object to match image_2 lighting",
                    "Cast shadows matching scene",
                    "Blend edges seamlessly"
                ],
                "constraints": {
                    "strict_mode": True,
                    "erase_sketch": True,
                    "match_scene_lighting": True
                },
                "priority_rules": {"user_prompt_is_law": True},
                "conflict_resolution": "user_prompt > mask_location > reference_object",
                "user_prompt": f"{user_prompt}"
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        elif has_mask:
            prompt_schema = {
                "role": "inpainting",
                "objective": "Replace sketch with photorealistic content",
                "context": "User drew rough sketch as temporary guide - must DELETE and replace",
                "inputs": {
                    "image_1": {"type": "photo_with_sketch", "sketch_is": "temporary_guide_to_delete"},
                    "image_2": {"type": "mask", "black": "dont_touch", "colored": "sketch_location_to_replace"}
                },
                "execution_steps": [
                    "Identify sketch areas from mask",
                    "COMPLETELY ERASE sketch (100%)",
                    "CREATE photorealistic content per user_prompt",
                    "Match original image lighting, shadows, perspective",
                    "Blend edges seamlessly"
                ],
                "constraints": {
                    "strict_mode": True,
                    "never_keep_sketch_visible": True,
                    "never_improve_sketch": True,
                    "always_delete_completely": True
                },
                "output_requirement": "photorealistic with NO sketch traces"
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        elif has_reference:
            prompt_schema = {
                "role": "object_integration",
                "objective": "Photorealistic integration of reference object into scene",
                "context": "NOT copy-paste - requires professional compositing with relighting",
                "inputs": {
                    "image_1": {"type": "reference", "extract": ["shape", "structure"], "ignore": ["lighting", "colors", "background"]},
                    "image_2": {"type": "target_scene", "analyze": ["light_direction", "color_temperature", "shadow_hardness", "ambient_light"]}
                },
                "integration_steps": {
                    "relighting": ["apply_scene_light_direction", "match_color_temperature", "create_matching_shadows", "add_ambient_occlusion"],
                    "color_grading": ["match_scene_palette", "match_saturation", "match_exposure"],
                    "shadows": ["cast_onto_surfaces", "match_direction", "match_softness", "add_contact_shadows"],
                    "perspective": ["match_camera_angle", "scale_appropriately", "align_ground_plane"],
                    "final_blend": ["match_sharpness", "match_depth_of_field", "match_film_grain"]
                },
                "success_criteria": {
                    "required": ["looks_photographed_in_scene", "matched_lighting", "matched_colors", "correct_shadows", "no_visible_edges"]
                },
                "constraints": {
                    "strict_mode": True,
                    "never_allow": ["original_lighting", "original_colors", "missing_shadows", "pasted_on_look"]
                }
            }
            base_prompt = f"PROMPT_SCHEMA:\n{json.dumps(prompt_schema, ensure_ascii=False, indent=2)}"
        else:
            prompt_schema = {
                "role": "image_refinement",
                "objective": "Refine and improve existing image",
                "inputs": {
                    "image_1": {"type": "base_image", "preserve": ["composition", "subjects", "layout"]}
                },
                "execution_steps": [
                    "Understand current image",
                    "Apply user's improvement instructions",
                    "Keep composition intact",
                    "Make changes natural and cohesive",
                    "Enhance quality while preserving intent"
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
            # Calculate aspect ratio from dimensions
            def calculate_aspect_ratio_edit(w, h):
                ratio = w / h if h > 0 else 1.0
                ratios = {"1:1": 1.0, "16:9": 16/9, "9:16": 9/16, "4:3": 4/3, "3:2": 3/2}
                return min(ratios.items(), key=lambda x: abs(x[1] - ratio))[0]
            
            # Use forced dimensions if provided, otherwise use original image size
            if width > 0 and height > 0:
                aspect_ratio_str = calculate_aspect_ratio_edit(width, height)
            else:
                orig_w, orig_h = original_image.size
                aspect_ratio_str = calculate_aspect_ratio_edit(orig_w, orig_h)
            
            print(f"[GEMINI] Edit aspect ratio: {aspect_ratio_str}")
            
            try:
                # Try to use the structure that worked for generation
                if hasattr(types, 'ImageConfig'):
                    img_conf = types.ImageConfig(
                        image_size=resolution_str,
                        aspect_ratio=aspect_ratio_str
                    )
                    config = types.GenerateContentConfig(
                        temperature=0.7,
                        candidate_count=1,
                        response_modalities=['IMAGE'],
                        image_config=img_conf
                    )
                else:
                    # Dictionary fallback
                    config = {
                        "temperature": 0.7,
                        "candidateCount": 1,
                        "responseModalities": ["IMAGE"],
                        "imageConfig": {
                            "imageSize": resolution_str,
                            "aspectRatio": aspect_ratio_str
                        }
                    }
                    print("[GEMINI] Using dictionary config for edit")
            except Exception as e:
                print(f"[GEMINI] Edit config setup failed: {e}")
                config = types.GenerateContentConfig(
                    temperature=0.7,
                    candidate_count=1,
                    response_modalities=['IMAGE']
                )
            
            # Make API call
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            print("[GEMINI] Edit response received")
            
            # Process response
            if not response.candidates or not response.candidates[0].content.parts:
                raise GeminiAPIError("No content in edit response")
            
            parts = response.candidates[0].content.parts
            
            # Find image part
            for part in parts:
                if part.inline_data is not None:
                    image = Image.open(BytesIO(part.inline_data.data))
                    
                    # Ensure RGB
                    if image.mode not in ('RGB', 'RGBA'):
                        print(f"[GEMINI] Converting {image.mode} to RGB")
                        image = image.convert('RGB')
                    
                    # Convert to PNG (standard sRGB)
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    image_data = img_byte_arr.getvalue()
                    
                    print(f"[GEMINI] Edited image: {len(image_data)} bytes")
                    return image_data, "image/png"
            
            raise GeminiAPIError("No image found in edit response")
            
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
                        "mime_type": "image/png",
                        "data": reference_base64
                    }
                })
                print("[GEMINI] Reference image added FIRST (style priority)")
            
            # Add original image SECOND
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
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
                        "mime_type": "image/png",
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
            
            # Determine resolution
            # Determine resolution and aspect ratio for REST
            resolution_str = "1K"
            aspect_ratio_str = "1:1"
            
            # Helper to calculate aspect ratio
            def calculate_aspect_ratio_rest(w, h):
                ratio = w / h if h > 0 else 1.0
                ratios = {"1:1": 1.0, "16:9": 16/9, "9:16": 9/16, "4:3": 4/3, "3:2": 3/2}
                return min(ratios.items(), key=lambda x: abs(x[1] - ratio))[0]

            if width > 0 and height > 0:
                # User forced resolution
                if width >= 4096 or height >= 4096:
                    resolution_str = "4K"
                elif width >= 2048 or height >= 2048:
                    resolution_str = "2K"
                
                aspect_ratio_str = calculate_aspect_ratio_rest(width, height)
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
                            
                            aspect_ratio_str = calculate_aspect_ratio_rest(w, h)
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
                inline_data_key = 'inline_data' if 'inline_data' in part else 'inlineData' if 'inlineData' in part else None
                
                if inline_data_key:
                    inline_data = part[inline_data_key]
                    data_key = 'data' if 'data' in inline_data else 'bytes' if 'bytes' in inline_data else None
                    
                    if data_key and inline_data[data_key]:
                        image_data = base64.b64decode(inline_data[data_key])
                        mime_type = inline_data.get('mime_type', inline_data.get('mimeType', 'image/png'))
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
    except:
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
    except:
        pass
    
    return None