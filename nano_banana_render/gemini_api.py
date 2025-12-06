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
                self.model = "gemini-3-pro-image-preview"
                self.use_sdk = True
            except Exception as e:
                print(f"⚠️ [GEMINI] SDK setup failed: {e}, falling back to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
        else:
            if not GENAI_AVAILABLE:
                print(
                    "🔄 [GEMINI] google-genai SDK not available, using REST API fallback"
                )
            elif not PIL_AVAILABLE:
                print(
                    "🔄 [GEMINI] PIL not available, using REST API fallback (SDK requires PIL)"
                )
            self.use_sdk = False
            self._setup_rest_fallback()

    def _setup_rest_fallback(self):
        """Setup REST API fallback"""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "models/gemini-3-pro-image-preview"

    def _build_prompt(
        self,
        user_prompt: str,
        has_reference: bool = False,
        is_color_render: bool = False,
    ) -> str:
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
                    "4. Match aspect ratio of reference image\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below OVERRIDES everything else for CONTENT decisions.\n"
                    "- If user says 'make it red', MAKE IT RED, even if Reference is blue.\n"
                    "- Reference Image is for STYLE only. User Prompt is for CONTENT.\n"
                    "- CONFLICT RESOLUTION: User Prompt > Reference Image Style > Depth Map\n"
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
                    "3. Choose appropriate materials, colors, and lighting\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below is your PRIMARY INSTRUCTION.\n"
                    "- You MUST follow the user's description for materials, colors, and lighting.\n"
                    "- The Depth Map provides the SHAPE, the User Prompt provides the LOOK.\n"
                )

        # ПРОМПТ ДЛЯ COLOR RENDER (EEVEE) - с трансформацией
        else:
            if has_reference:
                base_prompt = (
                    "You are receiving TWO images:\n\n"
                    "IMAGE 1 (3D Render - YOUR STRUCTURE SOURCE):\n"
                    "- This is the GEOMETRY and LAYOUT you must preserve\n"
                    "- Use this EXCLUSIVELY for object positions and composition\n"
                    "- IGNORE its bad materials and lighting\n"
                    "- This defines WHAT is in the scene\n\n"
                    "IMAGE 2 (Style Reference - YOUR VISUAL GUIDE):\n"
                    "- This is the STYLE source (materials, lighting, colors)\n"
                    "- DO NOT copy objects from here, only their 'look'\n"
                    "- Apply this style to the geometry of IMAGE 1\n"
                    "- This defines HOW the scene looks\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below OVERRIDES everything else for CONTENT decisions.\n"
                    "- If user says 'black background', MAKE IT BLACK, even if Reference Image has a detailed background.\n"
                    "- If user says 'add neon lights', ADD THEM, even if Reference Image is dark.\n"
                    "- Reference Image is for STYLE (how things look), User Prompt is for CONTENT (what things are).\n"
                    "- CONFLICT RESOLUTION: User Prompt > Reference Image Style > Input Render\n\n"
                    "YOUR TASK - AGGRESSIVE TRANSFORMATION:\n"
                    "1. Keep ONLY the composition/layout from IMAGE 1 (Depth/Structure)\n"
                    "2. COMPLETELY REPLACE materials, lighting, colors with IMAGE 2's style (UNLESS User Prompt says otherwise)\n"
                    "3. Make materials look like IMAGE 2 (if metallic there → metallic here)\n"
                    "4. Match IMAGE 2's lighting direction, intensity, and color temperature\n"
                    "5. Use IMAGE 2's color palette - forget IMAGE 1's colors\n"
                    "6. Replicate IMAGE 2's atmosphere, depth, and mood\n"
                    "7. Think: 'IMAGE 1 is the skeleton, IMAGE 2 is the skin'\n\n"
                    "CRITICAL - DON'T BE CONSERVATIVE:\n"
                    "- If IMAGE 1 is blue but IMAGE 2 is warm → make it WARM\n"
                    "- If IMAGE 1 is flat but IMAGE 2 has depth → add DEPTH\n"
                    "- If IMAGE 1 is simple but IMAGE 2 is detailed → add DETAILS\n"
                    "- TRANSFORM aggressively, don't just 'improve' IMAGE 1\n"
                    "- STRICTLY FOLLOW IMAGE 1's GEOMETRY/LAYOUT. Do not add objects from IMAGE 2.\n"
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
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below is your PRIMARY INSTRUCTION for the transformation.\n"
                    "- If user says 'make it cyberpunk', use cyberpunk materials/lighting.\n"
                    "- If user says 'add rain', add rain.\n"
                    "- The input render provides the COMPOSITION, the User Prompt provides the STYLE/CONTENT.\n\n"
                    "CRITICAL MINDSET:\n"
                    "- Think: 'This is a SKETCH, not the final image'\n"
                    "- Your goal: 'Student work' → 'Professional portfolio piece'\n"
                    "- Be BOLD with changes - the input is intentionally low quality\n"
                    "- Don't preserve bad materials or flat lighting\n"
                    "- Make every surface, light, and color DRAMATICALLY better\n"
                    "- Aim for: movie VFX quality or high-end product photography\n"
                )

        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER PROMPT (EXECUTE THIS): {user_prompt.strip()}"
        else:
            return base_prompt

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """
        Generate image from depth map and prompt using official SDK
        Optionally uses reference image for style/materials
        is_color_render: True if using regular Eevee render, False for depth map (mist)
        width, height: Output resolution
        Returns: (image_data, format)
        """
        if self.use_sdk:
            return self._generate_with_sdk(
                depth_image_path,
                user_prompt,
                reference_image_path,
                is_color_render,
                width,
                height,
            )
        else:
            return self._generate_with_rest(
                depth_image_path,
                user_prompt,
                reference_image_path,
                is_color_render,
                width,
                height,
            )

    def _generate_with_sdk(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
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
                return self._generate_with_rest(
                    depth_image_path,
                    user_prompt,
                    reference_image_path,
                    is_color_render,
                    width,
                    height,
                )

            # Build complete prompt
            full_prompt = self._build_prompt(
                user_prompt,
                has_reference=bool(reference_image_path),
                is_color_render=is_color_render,
            )
            print(f"📝 [GEMINI] Prompt: {full_prompt[:100]}...")

            # Load depth image using PIL
            print(f"🖼️ [GEMINI] Loading depth image: {depth_image_path}")
            depth_image = Image.open(depth_image_path)
            print(
                f"📏 [GEMINI] Depth image size: {depth_image.size}, mode: {depth_image.mode}"
            )

            # Prepare contents for the API call
            # CRITICAL CHANGE: Depth image MUST be before reference to ensure structure is prioritized
            contents = [full_prompt]

            # Add depth image (Structure)
            contents.append(depth_image)

            # Add reference image (Style) if provided
            if reference_image_path:
                print(f"🎨 [GEMINI] Loading reference image: {reference_image_path}")
                try:
                    reference_image = Image.open(reference_image_path)
                    contents.append(reference_image)
                    print(
                        f"📏 [GEMINI] Reference image size: {reference_image.size}, mode: {reference_image.mode}"
                    )
                    print(
                        "🔄 [GEMINI] Reference image sent LAST to prioritize depth structure"
                    )
                except Exception as e:
                    print(
                        f"⚠️ [GEMINI] Failed to load reference image, continuing without it: {e}"
                    )

            print("🚀 [GEMINI] Sending request to official API...")
            print(f"🎯 [GEMINI] Model: {self.model}")
            print(f"📏 [GEMINI] Target Resolution: {width}x{height}")

            # Make the API call
            # Use correct ImageConfig structure based on user documentation

            # Map resolution to string format expected by API
            resolution_str = "1K"
            if width >= 4096 or height >= 4096:
                resolution_str = "4K"
            elif width >= 2048 or height >= 2048:
                resolution_str = "2K"

            print(
                f"📏 [GEMINI] Mapped {width}x{height} to API resolution: {resolution_str}"
            )

            # Determine aspect ratio string
            # 1:1 is default, but we can try to be specific if needed
            # For now we'll stick to resolution control

            # Make the API call
            # User suggests using 'image_config' with 'image_size'

            # Map resolution to string format expected by API
            resolution_str = "1K"
            if width >= 4096 or height >= 4096:
                resolution_str = "4K"
            elif width >= 2048 or height >= 2048:
                resolution_str = "2K"

            print(
                f"📏 [GEMINI] SDK Mapped {width}x{height} to API resolution: {resolution_str}"
            )

            # Try to construct config with image_config
            # We use a dictionary for the inner config to avoid import errors if ImageConfig isn't found
            # The SDK often accepts dicts for config objects

            # We need to construct the config object carefully
            # If types.GenerateContentConfig accepts **kwargs, we might be able to pass image_config

            try:
                # Try to use the structure the user found
                config = types.GenerateContentConfig(
                    temperature=0.8,
                    candidate_count=1,
                    response_modalities=["IMAGE"],
                )

                # Manually set image_config if possible, or pass as dict if the SDK supports it
                # Since we can't easily check the type definition at runtime without crashing,
                # we'll try to set it as an attribute or pass it in constructor if we could

                # Let's try creating it as a dict first, as some SDK versions allow this
                # But self.client.models.generate_content expects a config object usually

                # Let's try to find ImageConfig in types
                if hasattr(types, "ImageConfig"):
                    print("[GEMINI] Found types.ImageConfig, using it")
                    # Import and use find_closest_ratio for aspect ratio
                    from . import aspect_ratio_utils

                    aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)
                    print(f"[GEMINI] Calculated aspect ratio: {aspect_ratio}")
                    img_conf = types.ImageConfig(
                        image_size=resolution_str, aspect_ratio=aspect_ratio
                    )
                    # Re-create config with image_config
                    config = types.GenerateContentConfig(
                        temperature=0.8,
                        candidate_count=1,
                        response_modalities=["IMAGE"],
                        image_config=img_conf,
                    )
                else:
                    print(
                        "[GEMINI] types.ImageConfig not found, trying generic dict approach or ImageGenerationConfig fallback"
                    )
                    # Fallback to what we had or try a dict approach if supported
                    # If the user is right, there MUST be a way to pass this

                    # Let's try to pass a raw dictionary as config, many python SDKs support this
                    from . import aspect_ratio_utils

                    aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)
                    config = {
                        "temperature": 0.8,
                        "candidateCount": 1,
                        "responseModalities": ["IMAGE"],
                        "imageConfig": {
                            "imageSize": resolution_str,
                            "aspectRatio": aspect_ratio,
                        },
                    }
                    print(
                        f"[GEMINI] Using dictionary config with imageConfig, aspect ratio: {aspect_ratio}"
                    )

            except Exception as e:
                print(f"⚠️ [GEMINI] Config setup failed: {e}")
                # Fallback to simple config
                config = types.GenerateContentConfig(
                    temperature=0.8, candidate_count=1, response_modalities=["IMAGE"]
                )

            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=config
            )

            print("✅ [GEMINI] Response received, processing parts...")

            # Process response parts
            if not response.candidates or not response.candidates[0].content.parts:
                print("❌ [GEMINI] No content parts in response")
                raise GeminiAPIError(
                    "No image generated. The model may have rejected the request."
                )

            parts = response.candidates[0].content.parts
            print(f"🧩 [GEMINI] Found {len(parts)} parts in response")

            # Find image part
            for i, part in enumerate(parts):
                print(
                    f"🔍 [GEMINI] Part {i}: text={part.text is not None}, inline_data={part.inline_data is not None}"
                )

                if part.text is not None:
                    print(f"📝 [GEMINI] Text part: {part.text[:100]}...")

                if part.inline_data is not None:
                    print("🖼️ [GEMINI] Found inline_data - extracting image...")

                    # Convert to PIL Image and then to bytes
                    image = Image.open(BytesIO(part.inline_data.data))
                    print(
                        f"✅ [GEMINI] Image extracted: {image.size}, mode: {image.mode}"
                    )

                    # Ensure RGB mode
                    if image.mode not in ("RGB", "RGBA"):
                        print(f"[GEMINI] Converting {image.mode} to RGB")
                        image = image.convert("RGB")

                    # Convert to PNG bytes (standard sRGB)
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format="PNG")
                    image_data = img_byte_arr.getvalue()

                    print(
                        f"💾 [GEMINI] Image converted to PNG: {len(image_data)} bytes"
                    )
                    return image_data, "image/png"

            # If no image found, create placeholder
            print("🎨 [GEMINI] No image part found, creating placeholder...")
            text_parts = [part.text for part in parts if part.text is not None]
            if text_parts:
                return self._create_placeholder_image(
                    f"Model response: {' '.join(text_parts)}"
                )
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
            return self._generate_with_rest(
                depth_image_path, user_prompt, reference_image_path, is_color_render
            )

    def _generate_with_rest(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_image_path: str = None,
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
    ) -> Tuple[bytes, str]:
        """Generate image using REST API fallback"""
        try:
            if reference_image_path:
                print(
                    "🔄 [GEMINI] Using REST API fallback with depth + style reference"
                )
            else:
                print("🔄 [GEMINI] Using REST API fallback")

            # Encode depth image to base64
            with open(depth_image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Encode reference image if provided
            reference_base64 = None
            if reference_image_path:
                try:
                    with open(reference_image_path, "rb") as f:
                        reference_base64 = base64.b64encode(f.read()).decode("utf-8")
                    print("🎨 [GEMINI] Reference image encoded")
                except Exception as e:
                    print(f"⚠️ [GEMINI] Failed to encode reference image: {e}")

            # Build complete prompt
            full_prompt = self._build_prompt(
                user_prompt,
                has_reference=bool(reference_image_path),
                is_color_render=is_color_render,
            )

            # Calculate aspect ratio using utility
            from . import aspect_ratio_utils

            aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)
            print(f"📐 [GEMINI] Calculated aspect ratio: {aspect_ratio}")

            # Prepare REST API request
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            print(f"🌐 [GEMINI] REST URL: {url}")

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Client": "python-blender-addon",
            }

            # Build parts array
            parts = [{"text": full_prompt}]

            # Add depth image (Structure) - FIRST image
            parts.append(
                {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            )

            # Add reference image (Style) - SECOND image
            if reference_base64:
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": reference_base64,
                        }
                    }
                )
                print(
                    f"🔄 [GEMINI] Reference image added LAST to prioritize depth structure"
                )

            # Map resolution to string format expected by API
            resolution_str = "1K"
            if width >= 4096 or height >= 4096:
                resolution_str = "4K"
            elif width >= 2048 or height >= 2048:
                resolution_str = "2K"

            print(
                f"📏 [GEMINI] REST Mapped {width}x{height} to API resolution: {resolution_str}"
            )

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution_str,
                        "aspectRatio": aspect_ratio,
                    },
                },
            }

            print(f"📦 [GEMINI] REST payload size: ~{len(str(payload))} chars")
            print(f"🖼️ [GEMINI] Depth image data size: {len(image_base64)} chars")
            if reference_base64:
                print(
                    f"🎨 [GEMINI] Reference image data size: {len(reference_base64)} chars"
                )

            # Make REST request
            print("🚀 [GEMINI] Sending REST request...")
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            print(f"📡 [GEMINI] Response status: {response.status_code}")

            if response.status_code == 403:
                raise GeminiAPIError(
                    "API key invalid or quota exceeded. Check your Google AI Studio account."
                )
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                raise GeminiAPIError(
                    f"Rate limit exceeded. Retry after: {retry_after} seconds."
                )
            elif response.status_code == 400:
                print(f"📝 [GEMINI] Error details: {response.text}")
                raise GeminiAPIError(f"Bad request (400): {response.text}")
            elif response.status_code != 200:
                raise GeminiAPIError(
                    f"API request failed with status {response.status_code}: {response.text}"
                )

            # Parse REST response
            result = response.json()
            print(f"🔍 [GEMINI] Response keys: {list(result.keys())}")

            if "candidates" not in result or not result["candidates"]:
                print("❌ [GEMINI] No candidates in response")
                raise GeminiAPIError(
                    "No image generated. The model may have rejected the request."
                )

            candidate = result["candidates"][0]
            print(f"🎯 [GEMINI] Candidate keys: {list(candidate.keys())}")

            if "content" not in candidate:
                print("❌ [GEMINI] No content in candidate")
                print(f"🔍 [GEMINI] Full candidate: {candidate}")
                raise GeminiAPIError(
                    "Invalid response format - no content in candidate"
                )

            parts = candidate["content"]["parts"]
            print(f"🧩 [GEMINI] Found {len(parts)} parts in response")

            # Find image part with detailed logging
            for i, part in enumerate(parts):
                print(f"🔍 [GEMINI] Part {i}: {list(part.keys())}")

                if "text" in part:
                    text_content = part["text"][:200] if part["text"] else "None"
                    print(f"📝 [GEMINI] Part {i} text: {text_content}...")

                # Check both possible formats: inline_data and inlineData
                inline_data_key = None
                if "inline_data" in part:
                    inline_data_key = "inline_data"
                elif "inlineData" in part:
                    inline_data_key = "inlineData"

                if inline_data_key:
                    print(f"🖼️ [GEMINI] Part {i} has {inline_data_key}!")
                    inline_data = part[inline_data_key]
                    print(
                        f"🔍 [GEMINI] {inline_data_key} keys: {list(inline_data.keys())}"
                    )

                    # Check both possible data field names
                    data_key = None
                    if "data" in inline_data:
                        data_key = "data"
                    elif "bytes" in inline_data:
                        data_key = "bytes"

                    if data_key:
                        data_len = (
                            len(inline_data[data_key]) if inline_data[data_key] else 0
                        )
                        mime_type = inline_data.get(
                            "mime_type", inline_data.get("mimeType", "image/jpeg")
                        )
                        print(
                            f"📊 [GEMINI] Image data found: {data_len} chars, type: {mime_type}"
                        )

                        if data_len > 0:
                            image_data = base64.b64decode(inline_data[data_key])
                            print(
                                f"✅ [GEMINI] REST image decoded: {len(image_data)} bytes"
                            )
                            return image_data, mime_type
                        else:
                            print(f"⚠️ [GEMINI] {inline_data_key}.{data_key} is empty")
                    else:
                        print(f"⚠️ [GEMINI] No 'data' or 'bytes' in {inline_data_key}")
                        print(
                            f"🔍 [GEMINI] Available fields: {list(inline_data.keys())}"
                        )

            # Detailed fallback info
            text_parts = [part.get("text", "") for part in parts if "text" in part]
            if text_parts:
                full_text = " ".join(text_parts)
                print(f"📝 [GEMINI] Full model text response ({len(full_text)} chars):")
                print(f"📝 [GEMINI] {full_text[:500]}...")

                # Check if text suggests the model can't generate images
                if any(
                    word in full_text.lower()
                    for word in ["cannot", "can't", "unable", "sorry", "text-based"]
                ):
                    print(
                        "⚠️ [GEMINI] Model seems to indicate it cannot generate images"
                    )

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
        ihdr_data = struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)  # RGB, 8-bit
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr_chunk = (
            struct.pack(">I", len(ihdr_data))
            + b"IHDR"
            + ihdr_data
            + struct.pack(">I", ihdr_crc)
        )

        # Image data
        raw_data = b""
        r, g, b = color
        for y in range(height):
            raw_data += b"\x00"  # No filter
            for x in range(width):
                raw_data += struct.pack("BBB", r, g, b)  # RGB pixel

        # IDAT chunk
        compressed_data = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF
        idat_chunk = (
            struct.pack(">I", len(compressed_data))
            + b"IDAT"
            + compressed_data
            + struct.pack(">I", idat_crc)
        )

        # IEND chunk
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

        return png_signature + ihdr_chunk + idat_chunk + iend_chunk

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
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
                has_reference=bool(reference_image_path),
            )

            if self.use_sdk:
                return self._edit_with_sdk(
                    image_path,
                    full_prompt,
                    mask_path,
                    reference_image_path,
                    width,
                    height,
                )
            else:
                return self._edit_with_rest(
                    image_path,
                    full_prompt,
                    mask_path,
                    reference_image_path,
                    width,
                    height,
                )

        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Image edit failed: {str(e)}")

    def _build_edit_prompt(
        self, user_prompt: str, has_mask: bool = False, has_reference: bool = False
    ) -> str:
        """Build prompt for image editing"""

        # Special finalization mode
        if user_prompt == "[FINALIZE_COMPOSITE]":
            base_prompt = (
                "COMPOSITE FINALIZATION - Unify entire image into seamless photorealistic result:\n\n"
                "CRITICAL CONTEXT:\n"
                "This image was created through multiple compositing steps (adding objects, inpainting, etc.).\n"
                "Your task: Make it look like ONE UNIFIED PHOTOGRAPH, not a collage.\n"
                "Remove ALL visible seams, color mismatches, lighting inconsistencies.\n\n"
                "COMMON PROBLEMS TO FIX:\n"
                "1. Objects have different color temperatures (some warm, some cool)\n"
                "2. Brightness mismatches between added objects and original scene\n"
                "3. Contrast differences (some areas too contrasty, others too flat)\n"
                "4. Shadow inconsistencies (direction or hardness doesn't match)\n"
                "5. Visible compositing edges or halos around objects\n"
                "6. Objects don't feel grounded in the scene\n"
                "7. Overall image lacks cohesion - looks like separate pieces\n\n"
                "YOUR TASK - PROFESSIONAL COLOR GRADING & UNIFICATION:\n"
                "STEP 1 - ANALYZE ENTIRE COMPOSITION:\n"
                "- Identify which areas look 'off' or disconnected\n"
                "- Find color temperature conflicts\n"
                "- Detect brightness/contrast mismatches\n"
                "- Look for unnatural edges or transitions\n\n"
                "STEP 2 - UNIFIED LIGHTING:\n"
                "- Establish ONE dominant light direction for entire scene\n"
                "- Make ALL objects respect this light direction\n"
                "- Unify shadow hardness across all elements\n"
                "- Add missing ambient occlusion between objects\n"
                "- Strengthen contact shadows where objects meet surfaces\n\n"
                "STEP 3 - COLOR HARMONY:\n"
                "- Choose ONE color temperature for the entire scene\n"
                "- Grade ALL objects to match this temperature\n"
                "- Create unified color palette - no outliers\n"
                "- Add subtle color spill between neighboring elements\n"
                "- Match saturation levels across all objects\n\n"
                "STEP 4 - CONTRAST & EXPOSURE:\n"
                "- Unify exposure - no objects too bright or too dark\n"
                "- Match contrast levels between all elements\n"
                "- Balance highlights and shadows across scene\n"
                "- Create cohesive tonal range\n\n"
                "STEP 5 - SEAMLESS INTEGRATION:\n"
                "- Blend ALL visible compositing edges\n"
                "- Remove halos, color fringing, or artifacts\n"
                "- Add atmospheric perspective if needed (distant = hazier)\n"
                "- Unify sharpness/blur across scene\n"
                "- Add subtle film grain or noise uniformly\n\n"
                "STEP 6 - GROUNDING & REALISM:\n"
                "- Ensure all objects cast appropriate shadows\n"
                "- Add reflections where needed (floors, mirrors, glossy surfaces)\n"
                "- Create subtle light bounce between objects\n"
                "- Add depth cues (foreground sharper, background softer)\n"
                "- Make everything feel 'heavy' and physically present\n\n"
                "REAL-WORLD EXAMPLE:\n"
                "BEFORE: Room with added furniture - chair too warm, table too bright, \n"
                "        plant has harsh shadows while room has soft shadows, visible edge around lamp\n"
                "AFTER FINALIZATION:\n"
                "  → ALL objects color-graded to match room's cool daylight\n"
                "  → Chair brightness reduced to match room exposure\n"
                "  → ALL shadows softened to match ambient lighting\n"
                "  → Lamp edge blended perfectly\n"
                "  → Added contact shadows under all furniture\n"
                "  → Slight color spill from wooden floor onto chair legs\n"
                "  → Unified film grain over entire image\n"
                "  → Result: Looks like ONE photograph, not composite\n\n"
                "CRITICAL SUCCESS CRITERIA:\n"
                "✅ Image looks like ONE unified photograph\n"
                "✅ ALL objects respect same lighting direction\n"
                "✅ Consistent color temperature throughout\n"
                "✅ Matched contrast and exposure across all elements\n"
                "✅ NO visible compositing edges or seams\n"
                "✅ Shadows are consistent (direction, hardness, color)\n"
                "✅ Every object feels grounded and physically present\n"
                "✅ Overall color harmony - no jarring mismatches\n"
                "✅ Professional photorealistic result\n"
                "CRITICAL RULES:\n"
                "❌ NEVER leave color temperature conflicts\n"
                "❌ NEVER ignore exposure mismatches\n"
                "❌ NEVER skip shadow unification\n"
                "❌ NEVER leave visible compositing edges\n"
                "❌ NEVER keep objects that look 'pasted on'\n"
                "❌ NEVER leave lighting direction conflicts\n\n"
                "REMEMBER:\n"
                "You are a PROFESSIONAL COLORIST doing final grade.\n"
                "This is the LAST STEP before client delivery.\n"
                "Make it PERFECT - unified, seamless, photorealistic.\n"
                "Goal: Viewer should NEVER suspect this was composited.\n"
            )
            return base_prompt

        if has_mask and has_reference:
            base_prompt = (
                "🎯 CRITICAL: READ USER'S PROMPT FIRST!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"USER'S INSTRUCTION (DO THIS EXACTLY!):\n"
                f'"{user_prompt}"\n'
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "YOUR TASK - SIMPLE AND DIRECT:\n"
                "1. Read user's prompt above - THIS IS WHAT YOU MUST DO!\n"
                "2. Look at IMAGE 1 (reference) - find the object user wants\n"
                "3. Look at IMAGE 3 (mask - colored area) - this is WHERE to place it\n"
                "4. Look at IMAGE 2 (scene with sketch) - ERASE the sketch\n"
                "5. Place object from IMAGE 1 into the colored area from IMAGE 3\n"
                "6. Follow user's prompt for HOW to place it (sitting/standing/facing/etc)\n"
                "7. Relight object to match scene lighting\n\n"
                "WHAT YOU HAVE:\n"
                "• IMAGE 1 (REFERENCE) = The object user wants to add\n"
                "• IMAGE 2 (SCENE) = Where to add it (has colored sketch showing location)\n"
                "• IMAGE 3 (MASK) = Exact colored area for placement\n"
                "• USER PROMPT = Tells you WHAT and HOW\n\n"
                "CRITICAL RULES:\n"
                "🔴 RULE #1: USER'S PROMPT IS LAW - Follow it EXACTLY!\n"
                "🔴 RULE #2: Place object in colored area from IMAGE 3 (mask)\n"
                "🔴 RULE #3: ERASE sketch completely - replace with real object\n"
                "🔴 RULE #4: Relight object to match IMAGE 2's lighting\n\n"
                "SIMPLE EXAMPLE:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "USER PROMPT: 'добавь мужчину на траве в обведённом кругу'\n"
                "\n"
                "WHAT YOU DO:\n"
                "1. Look at IMAGE 1 → find the man\n"
                "2. Look at IMAGE 3 → see the colored circle on grass\n"
                "3. Look at IMAGE 2 → see the sketch circle (erase it!)\n"
                "4. Place man from IMAGE 1 into circle area\n"
                "5. Make him ON THE GRASS (user said 'на траве')\n"
                "6. Erase colored circle sketch\n"
                "7. Relight man to match outdoor lighting\n"
                "8. Cast shadow on grass\n"
                "9. DONE - man is now on grass in that spot!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "HOW TO DO IT:\n"
                "STEP 1 - READ USER PROMPT (at the top!):\n"
                "  → What object? (e.g., 'мужчину', 'chair', 'car')\n"
                "  → Where? (e.g., 'на траве', 'at desk', 'in corner')\n"
                "  → How? (e.g., 'standing', 'sitting', 'facing camera')\n\n"
                "STEP 2 - FIND OBJECT IN IMAGE 1:\n"
                "  → Identify the object user wants\n"
                "  → Remember its shape, textures, details\n"
                "  → Ignore its background\n\n"
                "STEP 3 - FIND LOCATION:\n"
                "  → IMAGE 3 (mask) shows colored area = exact spot\n"
                "  → IMAGE 2 shows sketch = rough guide (erase it!)\n\n"
                "STEP 4 - PLACE OBJECT:\n"
                "  → Put object in colored area (from IMAGE 3)\n"
                "  → Follow user's prompt (orientation, pose, etc.)\n"
                "  → ERASE sketch completely\n\n"
                "STEP 5 - MAKE IT REALISTIC:\n"
                "  → Relight object to match IMAGE 2's lighting\n"
                "  → Adjust colors to match scene\n"
                "  → Cast shadows (direction must match scene)\n"
                "  → Blend edges smoothly\n\n"
                "MORE EXAMPLES:\n"
                "Example 1 - 'Поставь этот стул в углу у окна':\n"
                "  → Find chair in IMAGE 1\n"
                "  → Place it in corner near window (colored area from IMAGE 3)\n"
                "  → Erase colored sketch\n"
                "  → Relight with window light\n"
                "  → Cast shadow\n"
                "  → DONE!\n\n"
                "Example 2 - 'Add this person sitting at the desk':\n"
                "  → Find person in IMAGE 1\n"
                "  → Place at desk (colored area)\n"
                "  → Make them SITTING (user said so!)\n"
                "  → Erase sketch\n"
                "  → Relight with office lights\n"
                "  → DONE!\n\n"
                "Example 3 - 'добавь мужчину на траве в обведённом кругу':\n"
                "  → Find man in IMAGE 1\n"
                "  → Place ON GRASS in circle area (IMAGE 3)\n"
                "  → Erase circle sketch\n"
                "  → Relight with outdoor lighting\n"
                "  → Cast shadow on grass\n"
                "  → DONE!\n\n"
                "WHAT YOU MUST DO:\n"
                "✅ Follow user's prompt EXACTLY\n"
                "✅ Place object in colored area (IMAGE 3)\n"
                "✅ ERASE sketch completely\n"
                "✅ Relight object to match scene\n"
                "✅ Cast shadows\n"
                "✅ Make it look photorealistic\n\n"
                "WHAT YOU MUST NOT DO:\n"
                "❌ NEVER ignore user's prompt\n"
                "❌ NEVER place object in wrong spot\n"
                "❌ NEVER keep sketch visible\n"
                "❌ NEVER forget shadows\n\n"
                "FINAL REMINDER:\n"
                "🔴 USER PROMPT (at top) = YOUR PRIMARY INSTRUCTION!\n"
                "🔴 Read it carefully and do EXACTLY what it says!\n"
                "🔴 If user says 'на траве' → place on grass!\n"
                "🔴 If user says 'sitting' → make them sit!\n"
                "🔴 If user says 'в обведённом кругу' → place in circled area!\n\n"
            )
        elif has_mask:
            base_prompt = (
                "INPAINTING TASK - Replace sketch with photorealistic content:\n\n"
                "CONTEXT:\n"
                "User drew a rough SKETCH on their image to show where they want NEW content.\n"
                "The sketch is UGLY and TEMPORARY - it's just a guide.\n"
                "Your job: ERASE the sketch, CREATE beautiful realistic content in that spot.\n\n"
                "IMAGE 1 (PHOTO WITH SKETCH OVERLAY):\n"
                "- Original photo/render with user's sketch drawn on top\n"
                "- Sketch colors show LOCATION and rough SHAPE only\n"
                "- Sketch is NOT the final look - it will be DELETED\n\n"
                "IMAGE 2 (MASK - WHERE TO EDIT):\n"
                "- Black areas = DON'T TOUCH (keep original)\n"
                "- Colored areas = SKETCH LOCATION (delete sketch, add new content)\n\n"
                "STEP-BY-STEP PROCESS:\n"
                "1. Look at IMAGE 1 - see the ugly sketch user drew\n"
                "2. Look at IMAGE 2 - see WHERE the sketch is\n"
                "3. Read user's PROMPT - understand WHAT to create\n"
                "4. COMPLETELY ERASE the sketch from those areas\n"
                "5. CREATE photorealistic content matching the prompt\n"
                "6. Match original image's lighting, shadows, perspective, style\n"
                "7. Blend edges perfectly (no visible seams)\n\n"
                "REAL EXAMPLES:\n"
                "Example 1:\n"
                "  - User draws RED CIRCLE\n"
                "  - Prompt: 'add sunset light through window'\n"
                "  - You do: DELETE red circle → CREATE realistic warm sunlight rays\n"
                "  - Final: Beautiful sunset light, NO red circle visible\n\n"
                "Example 2:\n"
                "  - User draws BLUE BLOB\n"
                "  - Prompt: 'add water puddle on floor'\n"
                "  - You do: DELETE blue blob → CREATE realistic water with reflections\n"
                "  - Final: Real water puddle, NO blue blob visible\n\n"
                "Example 3:\n"
                "  - User draws GREEN SCRIBBLES\n"
                "  - Prompt: 'add plant in vase'\n"
                "  - You do: DELETE green scribbles → CREATE detailed plant with leaves\n"
                "  - Final: Beautiful plant, NO scribbles visible\n\n"
                "CRITICAL RULES:\n"
                "❌ NEVER keep the sketch visible\n"
                "❌ NEVER 'improve' the sketch - DELETE it completely\n"
                "❌ NEVER leave construction lines, rough shapes, or color blobs\n"
                "✅ ALWAYS erase sketch 100% before creating new content\n"
                "✅ ALWAYS create photorealistic result\n"
                "✅ ALWAYS match original image lighting and style\n"
                "✅ ALWAYS blend seamlessly at edges\n"
                "✅ ALWAYS follow user's text prompt for WHAT to create\n\n"
                "REMEMBER:\n"
                "Sketch = temporary guide (like construction lines in drawing)\n"
                "Final image = professional result with NO sketch traces\n"
                "User drew sketch to show LOCATION + rough IDEA\n"
                "You create PHOTOREALISTIC version and REMOVE sketch completely\n"
            )
        elif has_reference:
            base_prompt = (
                "PHOTOREALISTIC OBJECT INTEGRATION - Seamlessly blend reference into scene:\n\n"
                "CRITICAL CONTEXT:\n"
                "User is NOT asking for simple copy-paste! They want PHOTOREALISTIC INTEGRATION.\n"
                "The object from reference must look like it was PHOTOGRAPHED in the target scene.\n"
                "This requires ADVANCED color grading, lighting match, shadow casting, and perspective correction.\n\n"
                "IMAGE 1 (REFERENCE - SOURCE OBJECT):\n"
                "- Contains the object/person to integrate into IMAGE 2\n"
                "- Extract its SHAPE and STRUCTURE (what it is)\n"
                "- IGNORE its original lighting, colors, and background\n"
                "- Think: 'I need this OBJECT, but I'll RELIGHT it for the new scene'\n\n"
                "IMAGE 2 (TARGET SCENE - DESTINATION):\n"
                "- This is your PRIMARY reference for visual style\n"
                "- Analyze: lighting direction, color temperature, shadow hardness, ambient light\n"
                "- The object from IMAGE 1 must MATCH this scene's lighting 100%\n\n"
                "YOUR TASK - PROFESSIONAL COMPOSITING:\n"
                "STEP 1 - LIGHTING ANALYSIS (IMAGE 2):\n"
                "- Light direction: Where are shadows pointing? (e.g., left side, top-right)\n"
                "- Light hardness: Sharp shadows = hard light, soft shadows = diffuse light\n"
                "- Color temperature: Warm (orange/yellow) or cool (blue/white)?\n"
                "- Ambient light: How bright are shadow areas?\n"
                "- Reflections: Are there glossy surfaces? What do they reflect?\n\n"
                "STEP 2 - OBJECT EXTRACTION (IMAGE 1):\n"
                "- Identify the object shape, structure, materials\n"
                "- Forget its current lighting - you will RELIGHT it\n"
                "- Preserve textures and material properties (metal, wood, fabric, etc.)\n\n"
                "STEP 3 - INTEGRATION (CRITICAL!):\n"
                "A. RELIGHTING:\n"
                "   - Apply IMAGE 2's light direction to the object\n"
                "   - Match light color temperature exactly\n"
                "   - Create shadows that match IMAGE 2's shadow style\n"
                "   - Add ambient occlusion in contact areas\n"
                "B. COLOR GRADING:\n"
                "   - Adjust object's colors to match IMAGE 2's color palette\n"
                "   - If IMAGE 2 is warm → warm the object's colors\n"
                "   - If IMAGE 2 is desaturated → reduce object's saturation\n"
                "   - Match overall brightness/exposure\n"
                "C. SHADOWS:\n"
                "   - Cast shadows from object onto IMAGE 2's surfaces\n"
                "   - Shadow direction MUST match IMAGE 2's existing shadows\n"
                "   - Shadow softness MUST match IMAGE 2's shadow hardness\n"
                "   - Add contact shadows (dark areas where object touches surface)\n"
                "D. PERSPECTIVE:\n"
                "   - Match camera angle from IMAGE 2\n"
                "   - Scale object appropriately for scene\n"
                "   - Ensure ground plane alignment\n"
                "E. REFLECTIONS & AMBIENT:\n"
                "   - If object is glossy → reflect IMAGE 2's environment\n"
                "   - Add ambient light bounce from IMAGE 2's surfaces\n"
                "   - Color spill: nearby colored surfaces affect object colors\n\n"
                "STEP 4 - FINAL BLEND:\n"
                "- Edge softness: match IMAGE 2's sharpness/blur\n"
                "- Atmospheric perspective: distant objects are hazier\n"
                "- Depth of field: match IMAGE 2's focus plane\n"
                "- Film grain/noise: match IMAGE 2's texture\n\n"
                "REAL-WORLD EXAMPLE:\n"
                "IMAGE 1: Photo of a red chair (photographed outdoors, bright daylight)\n"
                "IMAGE 2: Dark moody interior with warm tungsten lights from left\n"
                "USER: 'Add the chair by the window'\n"
                "WRONG (copy-paste): Bright red chair with daylight look = looks fake!\n"
                "RIGHT (professional integration):\n"
                "  → Chair shape preserved\n"
                "  → BUT relit with warm tungsten light from left\n"
                "  → Red color adjusted to warm/darker tone matching room\n"
                "  → Soft shadow cast to the right (opposite of light)\n"
                "  → Contact shadow under chair legs (ambient occlusion)\n"
                "  → Slight warm color spill from wooden floor onto chair base\n"
                "  → Chair looks like it was PHOTOGRAPHED in this room\n\n"
                "CRITICAL SUCCESS CRITERIA:\n"
                "✅ Object MUST look like it was PHOTOGRAPHED in IMAGE 2's scene\n"
                "✅ Lighting on object MUST match IMAGE 2 exactly (direction, color, hardness)\n"
                "✅ Object colors MUST be color-graded to match IMAGE 2's palette\n"
                "✅ Shadows MUST be cast correctly with right direction and softness\n"
                "✅ No visible compositing edges - perfect blend\n"
                "✅ Viewer should NOT be able to tell it's from different photo\n"
                "CRITICAL MISTAKES TO AVOID:\n"
                "❌ NEVER keep object's original lighting from IMAGE 1\n"
                "❌ NEVER keep object's original colors unchanged\n"
                "❌ NEVER forget to cast shadows onto IMAGE 2's surfaces\n"
                "❌ NEVER ignore IMAGE 2's light direction\n"
                "❌ NEVER make it look like a PNG sticker pasted on\n"
                "❌ NEVER create lighting conflicts (e.g., shadows wrong direction)\n\n"
                "REMEMBER:\n"
                "You are a PROFESSIONAL COMPOSITOR, not a copy-paste tool.\n"
                "The object must be RELIT, COLOR-GRADED, and SHADOWED to match the target scene.\n"
                "Final result should be INDISTINGUISHABLE from a real photograph.\n"
                "OLD STYLE TRANSFER PROMPT (for reference, DON'T use this):\n"
                "You are receiving TWO images:\n\n"
                "IMAGE 1 (Style Reference - YOUR PRIMARY GUIDE):\n"
                "- This is your MAIN reference for ALL visual aspects\n"
                "- COPY AGGRESSIVELY: lighting setup, material types, color palette, texture quality, mood, atmosphere\n"
                "- Study this image's visual language and REPLICATE it completely\n"
                "- This shows the TARGET result you must achieve\n\n"
                "IMAGE 2 (Original Image - ONLY for composition):\n"
                "- Use EXCLUSIVELY for object positions, layout, scene structure\n"
                "- IGNORE its colors, materials, lighting, and current style\n"
                "- Treat current look as TEMPORARY - will be completely replaced\n"
                "- Keep ONLY the composition, everything else changes\n\n"
                "YOUR TASK - AGGRESSIVE STYLE TRANSFORMATION:\n"
                "1. Keep ONLY composition/layout/objects from IMAGE 2\n"
                "2. COMPLETELY REPLACE materials with IMAGE 1's style:\n"
                "   - If IMAGE 1 has metallic materials → make IMAGE 2's objects metallic\n"
                "   - If IMAGE 1 has matte surfaces → make IMAGE 2's objects matte\n"
                "   - If IMAGE 1 has wood texture → apply wood-like materials\n"
                "3. COMPLETELY REPLACE lighting with IMAGE 1's setup:\n"
                "   - Match light direction, intensity, color temperature\n"
                "   - Copy shadow hardness/softness\n"
                "   - Replicate ambient lighting mood\n"
                "4. COMPLETELY REPLACE colors with IMAGE 1's palette:\n"
                "   - If IMAGE 1 is warm (orange/red) → make IMAGE 2 warm\n"
                "   - If IMAGE 1 is cool (blue/cyan) → make IMAGE 2 cool\n"
                "   - Match color saturation and vibrancy\n"
                "5. REPLICATE atmosphere and mood:\n"
                "   - If IMAGE 1 is dramatic → make IMAGE 2 dramatic\n"
                "   - If IMAGE 1 is soft/gentle → make IMAGE 2 soft/gentle\n"
                "   - Copy depth, detail level, visual complexity\n\n"
                "CRITICAL - BE AGGRESSIVE, NOT CONSERVATIVE:\n"
                "❌ DON'T just 'slightly adjust' IMAGE 2\n"
                "❌ DON'T preserve IMAGE 2's current colors/materials\n"
                "❌ DON'T be subtle or gentle with changes\n"
                "✅ COMPLETELY TRANSFORM to match IMAGE 1's style\n"
                "✅ Think: 'IMAGE 1 is the goal, IMAGE 2 is just a layout template'\n"
                "✅ If IMAGE 1 is blue but IMAGE 2 is red → make it BLUE\n"
                "✅ If IMAGE 1 is dark but IMAGE 2 is bright → make it DARK\n"
                "✅ If IMAGE 1 is detailed but IMAGE 2 is simple → add DETAILS\n\n"
                "EXAMPLE:\n"
                "- IMAGE 1: Warm sunset photo with golden light, soft shadows, rich textures\n"
                "- IMAGE 2: Cool blue render with flat lighting\n"
                "- YOUR RESULT: Keep IMAGE 2's objects/layout BUT with:\n"
                "  → Golden sunset lighting from IMAGE 1\n"
                "  → Warm orange/red colors from IMAGE 1\n"
                "  → Soft shadows and rich textures from IMAGE 1\n"
                "  → Final looks like IMAGE 1's style applied to IMAGE 2's composition\n\n"
                "REMEMBER:\n"
                "Style reference (IMAGE 1) = your visual TARGET\n"
                "Original image (IMAGE 2) = composition template ONLY\n"
                "AGGRESSIVELY copy IMAGE 1's visual style to IMAGE 2's layout\n"
            )
        else:
            base_prompt = (
                "You are REFINING and IMPROVING an existing image:\n\n"
                "ORIGINAL IMAGE:\n"
                "- This is the base image you'll improve\n"
                "- Keep main composition, subjects, layout\n\n"
                "YOUR TASK:\n"
                "1. Understand current image\n"
                "2. Apply user's improvement instructions\n"
                "3. Keep overall composition intact\n"
                "4. Make changes feel natural and cohesive\n"
                "5. Enhance quality while preserving intent\n"
            )

        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER'S EDIT INSTRUCTIONS:\n{user_prompt.strip()}"
        else:
            return base_prompt

    def _edit_with_sdk(
        self,
        image_path: str,
        prompt: str,
        mask_path: str = None,
        reference_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit image using SDK"""
        try:
            if not PIL_AVAILABLE:
                print("[GEMINI] PIL not available, switching to REST")
                self.use_sdk = False
                self._setup_rest_fallback()
                return self._edit_with_rest(
                    image_path, prompt, mask_path, reference_path, width, height
                )

            print("[GEMINI] Loading images for editing...")

            # Load original image
            original_image = Image.open(image_path)
            print(
                f"[GEMINI] Original image: {original_image.size}, mode: {original_image.mode}"
            )

            # Build contents - order matters!
            # CRITICAL: For style transfer, reference comes FIRST!
            contents = [prompt]

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
                if mask_image.mode != "L":
                    mask_image = mask_image.convert("L")
                contents.append(mask_image)
                print(f"[GEMINI] Mask image LAST: {mask_image.size}")

            print(f"[GEMINI] Sending edit request to {self.model}...")
            print(
                f"[GEMINI] Order: prompt → {'reference → ' if reference_path else ''}original → {'mask' if mask_path else ''}"
            )

            # Determine resolution
            resolution_str = "1K"

            if width > 0 and height > 0:
                # User forced resolution
                if width >= 4096 or height >= 4096:
                    resolution_str = "4K"
                elif width >= 2048 or height >= 2048:
                    resolution_str = "2K"
                print(
                    f"📏 [GEMINI] Edit Resolution (Forced): {width}x{height} -> {resolution_str}"
                )
            else:
                # Auto-detect from input
                w, h = original_image.size
                if w >= 4096 or h >= 4096:
                    resolution_str = "4K"
                elif w >= 2048 or h >= 2048:
                    resolution_str = "2K"
                print(
                    f"📏 [GEMINI] Edit Resolution (Auto): {w}x{h} -> {resolution_str}"
                )

            # Configure generation with resolution
            try:
                # Try to use the structure that worked for generation
                if hasattr(types, "ImageConfig"):
                    # Import aspect ratio utils
                    from . import aspect_ratio_utils

                    aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)
                    print(f"📐 [GEMINI] Edit aspect ratio: {aspect_ratio}")

                    img_conf = types.ImageConfig(
                        image_size=resolution_str,
                        aspect_ratio=aspect_ratio,
                    )
                    config = types.GenerateContentConfig(
                        temperature=0.7,
                        candidate_count=1,
                        response_modalities=["IMAGE"],
                        image_config=img_conf,
                    )
                else:
                    # Dictionary fallback
                    config = {
                        "temperature": 0.7,
                        "candidateCount": 1,
                        "responseModalities": ["IMAGE"],
                        "imageConfig": {
                            "imageSize": resolution_str,
                            "aspectRatio": aspect_ratio,
                        },
                    }
                    print("[GEMINI] Using dictionary config for edit")
            except Exception as e:
                print(f"⚠️ [GEMINI] Edit config setup failed: {e}")
                config = types.GenerateContentConfig(
                    temperature=0.7, candidate_count=1, response_modalities=["IMAGE"]
                )

            # Make API call
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=config
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
                    if image.mode not in ("RGB", "RGBA"):
                        print(f"[GEMINI] Converting {image.mode} to RGB")
                        image = image.convert("RGB")

                    # Convert to PNG (standard sRGB)
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format="PNG")
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

    def _edit_with_rest(
        self,
        image_path: str,
        prompt: str,
        mask_path: str = None,
        reference_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """Edit image using REST API"""
        try:
            print("[GEMINI] Editing with REST API...")

            # Encode images
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Build parts - order matters!
            # CRITICAL: Reference FIRST for style transfer priority
            parts = [{"text": prompt}]

            # Add reference FIRST if provided (style priority)
            if reference_path:
                with open(reference_path, "rb") as f:
                    reference_base64 = base64.b64encode(f.read()).decode("utf-8")
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": reference_base64,
                        }
                    }
                )
                print("[GEMINI] Reference image added FIRST (style priority)")

            # Add original image SECOND
            parts.append(
                {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            )
            print("[GEMINI] Original image added SECOND")

            # Add mask if provided (LAST)
            if mask_path:
                with open(mask_path, "rb") as f:
                    mask_base64 = base64.b64encode(f.read()).decode("utf-8")
                parts.append(
                    {"inline_data": {"mime_type": "image/png", "data": mask_base64}}
                )
                print("[GEMINI] Mask image added")

            # Make REST request
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Client": "python-blender-addon",
            }

            # Determine resolution
            resolution_str = "1K"

            if width > 0 and height > 0:
                # User forced resolution
                if width >= 4096 or height >= 4096:
                    resolution_str = "4K"
                elif width >= 2048 or height >= 2048:
                    resolution_str = "2K"
                print(
                    f"📏 [GEMINI] REST Edit Resolution (Forced): {width}x{height} -> {resolution_str}"
                )
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
                            print(
                                f"📏 [GEMINI] REST Edit Resolution (Auto): {w}x{h} -> {resolution_str}"
                            )
                except Exception as e:
                    print(f"⚠️ [GEMINI] Could not detect image size for REST: {e}")

            # Calculate aspect ratio
            from . import aspect_ratio_utils

            aspect_ratio = aspect_ratio_utils.find_closest_ratio(width, height)
            print(f"📐 [GEMINI] REST Edit aspect ratio: {aspect_ratio}")

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.7,  # Lower temperature for more faithful edits
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution_str,
                        "aspectRatio": aspect_ratio,
                    },
                },
            }

            print("[GEMINI] Sending REST edit request...")
            response = requests.post(url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                raise GeminiAPIError(
                    f"Edit request failed: {response.status_code} - {response.text}"
                )

            # Parse response (same as generate_with_rest)
            result = response.json()

            if "candidates" not in result or not result["candidates"]:
                raise GeminiAPIError("No candidates in edit response")

            parts = result["candidates"][0]["content"]["parts"]

            # Find image part
            for part in parts:
                inline_data_key = (
                    "inline_data"
                    if "inline_data" in part
                    else "inlineData" if "inlineData" in part else None
                )

                if inline_data_key:
                    inline_data = part[inline_data_key]
                    data_key = (
                        "data"
                        if "data" in inline_data
                        else "bytes" if "bytes" in inline_data else None
                    )

                    if data_key and inline_data[data_key]:
                        image_data = base64.b64decode(inline_data[data_key])
                        mime_type = inline_data.get(
                            "mime_type", inline_data.get("mimeType", "image/png")
                        )
                        print(
                            f"[GEMINI] Edited image: {len(image_data)} bytes, format: {mime_type}"
                        )

                        # Verify image is not corrupted
                        if PIL_AVAILABLE:
                            try:
                                from PIL import Image as PILImage
                                from io import BytesIO

                                test_img = PILImage.open(BytesIO(image_data))
                                print(
                                    f"[GEMINI] Image verified: {test_img.size}, mode: {test_img.mode}"
                                )

                                # Convert to RGB if needed (to fix black/white issue)
                                if test_img.mode not in ("RGB", "RGBA"):
                                    print(
                                        f"[GEMINI] Converting from {test_img.mode} to RGB"
                                    )
                                    test_img = test_img.convert("RGB")

                                    # Re-encode to PNG (standard sRGB)
                                    output = BytesIO()
                                    test_img.save(output, format="PNG")
                                    image_data = output.getvalue()
                                    print(
                                        f"[GEMINI] Converted image: {len(image_data)} bytes"
                                    )
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
    """Get API key from environment variable or addon preferences"""
    # Try environment variable first
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        return api_key

    # Try addon preferences
    import bpy

    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if hasattr(prefs, "api_key") and prefs.api_key.strip():
            return prefs.api_key.strip()
    except:
        pass

    # Try scene properties
    try:
        if (
            hasattr(bpy.context.scene, "gemini_render")
            and bpy.context.scene.gemini_render.api_key.strip()
        ):
            return bpy.context.scene.gemini_render.api_key.strip()
    except:
        pass

    return None
