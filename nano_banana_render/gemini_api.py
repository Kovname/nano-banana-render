"""
Gemini API integration for image generation using official Python SDK
"""

import os
from typing import Optional, Tuple
from io import BytesIO

# Try importing PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
    print("✅ [GEMINI] PIL (Pillow) available")
except ImportError:
    print("⚠️ [GEMINI] PIL not installed - some features will use fallback")
    PIL_AVAILABLE = False

# Try importing official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
    print("✅ [GEMINI] Official google-genai SDK available")
except ImportError:
    print("⚠️ [GEMINI] google-genai not installed, using fallback REST API")
    GENAI_AVAILABLE = False
    # Fallback to REST API
    import requests
    import json
    import base64

class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors"""
    pass

class GeminiAPI:
    """Client for Google Gemini API with official SDK"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
        if GENAI_AVAILABLE and PIL_AVAILABLE:
            print("🚀 [GEMINI] Using official Google GenAI SDK")
            try:
                # Configure the official client
                genai.configure(api_key=api_key)
                self.client = genai.Client()
                self.model = "gemini-2.5-flash-image-preview"
                self.use_sdk = True
            except Exception as e:
                print(f"⚠️ [GEMINI] SDK setup failed: {e}, falling back to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
        else:
            if not GENAI_AVAILABLE:
                print("🔄 [GEMINI] google-genai SDK not available, using REST API fallback")
            elif not PIL_AVAILABLE:
                print("🔄 [GEMINI] PIL not available, using REST API fallback (SDK requires PIL)")
            self.use_sdk = False
            self._setup_rest_fallback()
    
    def _setup_rest_fallback(self):
        """Setup REST API fallback"""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "models/gemini-2.5-flash-image-preview"
        
    def _build_prompt(self, user_prompt: str, has_reference: bool = False, is_color_render: bool = False) -> str:
        """Build complete prompt with correct image order and render mode"""
        
        # СТАРЫЙ ПРОМПТ ДЛЯ DEPTH MAP (MIST) - работал лучше!
        if not is_color_render:
            if has_reference:
                base_prompt = (
                    "You are receiving TWO images with different purposes:\n\n"
                    
                    "IMAGE 1 (Style Reference):\n"
                    "- Use ONLY for: color palette, material textures, lighting mood, surface details\n"
                    "- DO NOT copy: composition, object placement, camera angle\n"
                    "- Extract: visual aesthetics, aspect ratio\n\n"
                    
                    "IMAGE 2 (Depth Map):\n"
                    "- Black and white gradient representing depth\n"
                    "- White = closest objects, Black = farthest objects\n"
                    "- Use for: scene composition, object placement, 3D structure\n"
                    "- This depth map shows the spatial layout\n\n"
                    
                    "YOUR TASK:\n"
                    "1. Understand 3D scene structure from depth map (IMAGE 2)\n"
                    "2. Apply visual style from reference (IMAGE 1) to that structure\n"
                    "3. Create photorealistic render combining: reference style + depth map geometry\n"
                    "4. Match aspect ratio of reference image\n"
                )
            else:
                base_prompt = (
                    "You are receiving a DEPTH MAP image:\n\n"
                    
                    "DEPTH MAP:\n"
                    "- Black and white gradient representing depth\n"
                    "- White = closest objects, Black = farthest objects\n"
                    "- Shows spatial relationships and 3D structure\n\n"
                    
                    "YOUR TASK:\n"
                    "1. Interpret the depth map to understand scene geometry\n"
                    "2. Generate photorealistic 3D render based on this structure\n"
                    "3. Choose appropriate materials, colors, and lighting\n"
                )
        
        # ПРОМПТ ДЛЯ COLOR RENDER (EEVEE) - с трансформацией
        else:
            if has_reference:
                base_prompt = (
                    "You are receiving TWO images:\n\n"
                    
                    "IMAGE 1 (Style Reference - YOUR MAIN GUIDE):\n"
                    "- This is your PRIMARY reference for EVERYTHING visual\n"
                    "- COPY AGGRESSIVELY: lighting setup, material types, color palette, texture quality, mood, atmosphere\n"
                    "- Study this image's visual language and REPLICATE it\n"
                    "- Ignore the rough render quality of IMAGE 2 - focus on IMAGE 1's style\n\n"
                    
                    "IMAGE 2 (3D Render - ONLY for composition/layout):\n"
                    "- Use EXCLUSIVELY for object positions and scene layout\n"
                    "- IGNORE its colors, materials, lighting, and quality\n"
                    "- Treat this as a rough sketch, not the final look\n"
                    "- The render quality here is BAD - you must fix it\n\n"
                    
                    "YOUR TASK - AGGRESSIVE TRANSFORMATION:\n"
                    "1. Keep ONLY the composition/layout from IMAGE 2\n"
                    "2. COMPLETELY REPLACE materials, lighting, colors with IMAGE 1's style\n"
                    "3. Make materials look like IMAGE 1 (if metallic there → metallic here)\n"
                    "4. Match IMAGE 1's lighting direction, intensity, and color temperature\n"
                    "5. Use IMAGE 1's color palette - forget IMAGE 2's colors\n"
                    "6. Replicate IMAGE 1's atmosphere, depth, and mood\n"
                    "7. Think: 'IMAGE 2 is a placeholder, IMAGE 1 is the goal'\n\n"
                    
                    "CRITICAL - DON'T BE CONSERVATIVE:\n"
                    "- If IMAGE 2 is blue but IMAGE 1 is warm → make it WARM\n"
                    "- If IMAGE 2 is flat but IMAGE 1 has depth → add DEPTH\n"
                    "- If IMAGE 2 is simple but IMAGE 1 is detailed → add DETAILS\n"
                    "- TRANSFORM aggressively, don't just 'improve' IMAGE 2\n"
                )
            else:
                base_prompt = (
                    "You are receiving a LOW-QUALITY 3D RENDER that needs COMPLETE VISUAL OVERHAUL:\n\n"
                    
                    "INPUT IMAGE (ROUGH DRAFT ONLY):\n"
                    "- Amateur 3D render with placeholder materials and basic lighting\n"
                    "- Use ONLY for general composition and object positions\n"
                    "- Colors are WRONG, materials are FAKE, lighting is FLAT\n"
                    "- This is NOT the target quality - you must COMPLETELY rebuild it\n\n"
                    
                    "YOUR MISSION - TOTAL TRANSFORMATION:\n"
                    "1. REPLACE all materials with photorealistic equivalents:\n"
                    "   - Metal → realistic metal with proper reflections, anisotropy, scratches\n"
                    "   - Plastic → varied surface finish, subtle color variation, wear\n"
                    "   - Wood → visible grain, natural color variation, texture depth\n"
                    "   - Glass → proper refraction, reflections, subtle imperfections\n"
                    "   - Fabric → weave patterns, soft shadows, natural draping\n\n"
                    
                    "2. REBUILD lighting from scratch:\n"
                    "   - Add professional 3-point lighting or natural light sources\n"
                    "   - Strong shadows with soft edges\n"
                    "   - Realistic reflections and bounce light\n"
                    "   - Ambient occlusion in corners and crevices\n"
                    "   - Color temperature variation (warm/cool balance)\n\n"
                    
                    "3. REIMAGINE colors:\n"
                    "   - Input colors are just suggestions - make them BETTER\n"
                    "   - Add professional color grading\n"
                    "   - Harmonious palette with contrast\n"
                    "   - Natural color variation within surfaces\n\n"
                    
                    "4. ADD depth and atmosphere:\n"
                    "   - Volumetric lighting effects (god rays, haze)\n"
                    "   - Atmospheric perspective (depth fog)\n"
                    "   - Particle effects if appropriate (dust, moisture)\n"
                    "   - Background depth and detail\n\n"
                    
                    "5. ENHANCE with imperfections:\n"
                    "   - Surface scratches, dents, wear patterns\n"
                    "   - Fingerprints on smooth surfaces\n"
                    "   - Dust accumulation in corners\n"
                    "   - Natural aging and weathering\n\n"
                    
                    "CRITICAL MINDSET:\n"
                    "- Think: 'This is a SKETCH, not the final image'\n"
                    "- Your goal: 'Student work' → 'Professional portfolio piece'\n"
                    "- Be BOLD with changes - the input is intentionally low quality\n"
                    "- Don't preserve bad materials or flat lighting\n"
                    "- Make every surface, light, and color DRAMATICALLY better\n"
                    "- Aim for: movie VFX quality or high-end product photography\n"
                )
        
        if user_prompt.strip():
            return f"{base_prompt}\n\nUser instructions: {user_prompt.strip()}"
        else:
            return base_prompt
    
    def generate_image(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False) -> Tuple[bytes, str]:
        """
        Generate image from depth map and prompt using official SDK
        Optionally uses reference image for style/materials
        is_color_render: True if using regular Eevee render, False for depth map (mist)
        Returns: (image_data, format) 
        """
        if self.use_sdk:
            return self._generate_with_sdk(depth_image_path, user_prompt, reference_image_path, is_color_render)
        else:
            return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render)
    
    def _generate_with_sdk(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False) -> Tuple[bytes, str]:
        """Generate image using official Google GenAI SDK"""
        try:
            if reference_image_path:
                print("🎯 [GEMINI] Using official SDK with depth + style reference")
            else:
                print("🎯 [GEMINI] Using official SDK for image generation")
            
            if not PIL_AVAILABLE:
                print("❌ [GEMINI] PIL not available for SDK, switching to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
                return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render)
            
            # Build complete prompt
            full_prompt = self._build_prompt(user_prompt, has_reference=bool(reference_image_path), is_color_render=is_color_render)
            print(f"📝 [GEMINI] Prompt: {full_prompt[:100]}...")
            
            # Load depth image using PIL
            print(f"🖼️ [GEMINI] Loading depth image: {depth_image_path}")
            depth_image = Image.open(depth_image_path)
            print(f"📏 [GEMINI] Depth image size: {depth_image.size}, mode: {depth_image.mode}")
            
            # Prepare contents for the API call - REFERENCE IMAGE FIRST!
            contents = [full_prompt]
            
            # Add reference image FIRST if provided (for aspect ratio priority)
            if reference_image_path:
                print(f"🎨 [GEMINI] Loading reference image: {reference_image_path}")
                try:
                    reference_image = Image.open(reference_image_path)
                    contents.append(reference_image)
                    print(f"📏 [GEMINI] Reference image size: {reference_image.size}, mode: {reference_image.mode}")
                    print("🔄 [GEMINI] Reference image sent FIRST for aspect ratio priority!")
                except Exception as e:
                    print(f"⚠️ [GEMINI] Failed to load reference image, continuing without it: {e}")
            
            # Add depth image SECOND
            contents.append(depth_image)
            
            print("🚀 [GEMINI] Sending request to official API...")
            print(f"🎯 [GEMINI] Model: {self.model}")
            
            # Make the API call
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
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
                    print(f"✅ [GEMINI] Image extracted: {image.size}, mode: {image.mode}")
                    
                    # Convert to PNG bytes
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    image_data = img_byte_arr.getvalue()
                    
                    print(f"💾 [GEMINI] Image converted to PNG: {len(image_data)} bytes")
                    return image_data, "image/png"
            
            # If no image found, create placeholder
            print("🎨 [GEMINI] No image part found, creating placeholder...")
            text_parts = [part.text for part in parts if part.text is not None]
            if text_parts:
                return self._create_placeholder_image(f"Model response: {' '.join(text_parts)}")
            else:
                raise GeminiAPIError("No image or text found in API response")
                
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            print(f"💥 [GEMINI] SDK error: {str(e)}")
            print("🔄 [GEMINI] Falling back to REST API...")
            # Fallback to REST API with is_color_render
            self.use_sdk = False
            self._setup_rest_fallback()
            return self._generate_with_rest(depth_image_path, user_prompt, reference_image_path, is_color_render)
    
    def _generate_with_rest(self, depth_image_path: str, user_prompt: str, reference_image_path: str = None, is_color_render: bool = False) -> Tuple[bytes, str]:
        """Generate image using REST API fallback"""
        try:
            if reference_image_path:
                print("🔄 [GEMINI] Using REST API fallback with depth + style reference")
            else:
                print("🔄 [GEMINI] Using REST API fallback")
            
            # Encode depth image to base64
            with open(depth_image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Encode reference image if provided
            reference_base64 = None
            if reference_image_path:
                try:
                    with open(reference_image_path, 'rb') as f:
                        reference_base64 = base64.b64encode(f.read()).decode('utf-8')
                    print("🎨 [GEMINI] Reference image encoded")
                except Exception as e:
                    print(f"⚠️ [GEMINI] Failed to encode reference image: {e}")
            
            # Build complete prompt
            full_prompt = self._build_prompt(user_prompt, has_reference=bool(reference_image_path), is_color_render=is_color_render)
            
            # Prepare REST API request
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            print(f"🌐 [GEMINI] REST URL: {url}")
            
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Client': 'python-blender-addon',
            }
            
            # Build parts array - REFERENCE IMAGE FIRST!
            parts = [{"text": full_prompt}]
            
            # Add reference image FIRST if available (for aspect ratio priority)
            if reference_base64:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": reference_base64
                    }
                })
                print(f"🔄 [GEMINI] Reference image added FIRST for aspect ratio priority")
            
            # Add depth image SECOND
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": image_base64
                }
            })
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 32768,
                    "candidateCount": 1
                }
            }
            
            print(f"📦 [GEMINI] REST payload size: ~{len(str(payload))} chars")
            print(f"🖼️ [GEMINI] Depth image data size: {len(image_base64)} chars")
            if reference_base64:
                print(f"🎨 [GEMINI] Reference image data size: {len(reference_base64)} chars")
            
            # Make REST request
            print("🚀 [GEMINI] Sending REST request...")
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            
            print(f"📡 [GEMINI] Response status: {response.status_code}")
            
            if response.status_code == 403:
                raise GeminiAPIError("API key invalid or quota exceeded. Check your Google AI Studio account.")
            elif response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 'unknown')
                raise GeminiAPIError(f"Rate limit exceeded. Retry after: {retry_after} seconds.")
            elif response.status_code == 400:
                print(f"📝 [GEMINI] Error details: {response.text}")
                raise GeminiAPIError(f"Bad request (400): {response.text}")
            elif response.status_code != 200:
                raise GeminiAPIError(f"API request failed with status {response.status_code}: {response.text}")
            
            # Parse REST response
            result = response.json()
            print(f"🔍 [GEMINI] Response keys: {list(result.keys())}")
            
            if 'candidates' not in result or not result['candidates']:
                print("❌ [GEMINI] No candidates in response")
                raise GeminiAPIError("No image generated. The model may have rejected the request.")
            
            candidate = result['candidates'][0]
            print(f"🎯 [GEMINI] Candidate keys: {list(candidate.keys())}")
            
            if 'content' not in candidate:
                print("❌ [GEMINI] No content in candidate")
                print(f"🔍 [GEMINI] Full candidate: {candidate}")
                raise GeminiAPIError("Invalid response format - no content in candidate")
            
            parts = candidate['content']['parts'] 
            print(f"🧩 [GEMINI] Found {len(parts)} parts in response")
            
            # Find image part with detailed logging
            for i, part in enumerate(parts):
                print(f"🔍 [GEMINI] Part {i}: {list(part.keys())}")
                
                if 'text' in part:
                    text_content = part['text'][:200] if part['text'] else "None"
                    print(f"📝 [GEMINI] Part {i} text: {text_content}...")
                
                # Check both possible formats: inline_data and inlineData
                inline_data_key = None
                if 'inline_data' in part:
                    inline_data_key = 'inline_data'
                elif 'inlineData' in part:
                    inline_data_key = 'inlineData'
                
                if inline_data_key:
                    print(f"🖼️ [GEMINI] Part {i} has {inline_data_key}!")
                    inline_data = part[inline_data_key]
                    print(f"🔍 [GEMINI] {inline_data_key} keys: {list(inline_data.keys())}")
                    
                    # Check both possible data field names
                    data_key = None
                    if 'data' in inline_data:
                        data_key = 'data'
                    elif 'bytes' in inline_data:
                        data_key = 'bytes'
                    
                    if data_key:
                        data_len = len(inline_data[data_key]) if inline_data[data_key] else 0
                        mime_type = inline_data.get('mime_type', inline_data.get('mimeType', 'image/jpeg'))
                        print(f"📊 [GEMINI] Image data found: {data_len} chars, type: {mime_type}")
                        
                        if data_len > 0:
                            image_data = base64.b64decode(inline_data[data_key])
                            print(f"✅ [GEMINI] REST image decoded: {len(image_data)} bytes")
                            return image_data, mime_type
                        else:
                            print(f"⚠️ [GEMINI] {inline_data_key}.{data_key} is empty")
                    else:
                        print(f"⚠️ [GEMINI] No 'data' or 'bytes' in {inline_data_key}")
                        print(f"🔍 [GEMINI] Available fields: {list(inline_data.keys())}")
            
            # Detailed fallback info
            text_parts = [part.get('text', '') for part in parts if 'text' in part]
            if text_parts:
                full_text = ' '.join(text_parts)
                print(f"📝 [GEMINI] Full model text response ({len(full_text)} chars):")
                print(f"📝 [GEMINI] {full_text[:500]}...")
                
                # Check if text suggests the model can't generate images
                if any(word in full_text.lower() for word in ['cannot', "can't", 'unable', 'sorry', 'text-based']):
                    print("⚠️ [GEMINI] Model seems to indicate it cannot generate images")
                
                return self._create_placeholder_image(f"Model response: {full_text}")
            
            print("❌ [GEMINI] No image or text found in any part")
            print(f"🔍 [GEMINI] Full parts structure: {parts}")
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
        """Create a placeholder image with text info"""
        try:
            print("🎨 [GEMINI] Creating text-based placeholder image...")
            
            # Simple 100x100 colored PNG
            width, height = 100, 100
            
            # Create a simple blue square PNG
            png_data = self._create_simple_png(width, height, (0, 100, 200))  # Blue
            
            print(f"✅ [GEMINI] Placeholder created: {width}x{height} blue square")
            print(f"📝 [GEMINI] Original text: {text_response[:100]}...")
            
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

def get_api_key() -> Optional[str]:
    """Get API key from environment variable or addon preferences"""
    # Try environment variable first
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if api_key:
        return api_key
    
    # Try addon preferences
    import bpy
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if hasattr(prefs, 'api_key') and prefs.api_key.strip():
            return prefs.api_key.strip()
    except:
        pass
    
    # Try scene properties
    try:
        if hasattr(bpy.context.scene, 'gemini_render') and bpy.context.scene.gemini_render.api_key.strip():
            return bpy.context.scene.gemini_render.api_key.strip()
    except:
        pass
    
    return None