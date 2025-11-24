# 🍌 Nano Banana Pro Render

**Professional AI Rendering & Editing Suite for Blender**

Transform your Blender scenes into stunning photorealistic images using the latest **Google Gemini 3 Pro** AI. Now with full **4K support**, **Inpainting**, and a dedicated **Image Editor** workflow.

[![Blender](https://img.shields.io/badge/Blender-4.5%2B-orange?logo=blender)](https://www.blender.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0.0-green.svg)](https://github.com/kovname/nano-banana-render/releases)

---

## What's New in v2.0

### AI Image Editor & Inpainting

A complete post-processing studio right inside Blender's Image Editor.

- **Inpainting**: Draw directly on your image to add or remove objects.
- **Reference Integration**: Select an area and load a photo to seamlessly place specific objects (e.g., "put this chair here").
- **AI Editing**: Change materials, lighting, or details with simple text prompts.
- **Seamless Integration**: Works instantly on your renders or any loaded image.

### 4K Resolution Support

Generate and edit images in crystal clear detail.

- **Native 4K Generation**: Create stunning high-res renders from the start.
- **Smart Upscaling**: Edit standard images and output them in 4K.
- **Auto-Detection**: The AI automatically detects your input size and matches it.

### Powered by Gemini 3 Pro

Using Google's latest vision model for:

- Superior prompt understanding
- Accurate lighting and physics
- Incredible texture detail

---

## Interface

### The Render Panel & Editor Studio

|            Render Panel             |             Editor Studio             |
| :---------------------------------: | :-----------------------------------: |
| <img src="docs/images/ui_main.png"> | <img src="docs/images/ui_editor.png"> |

_Simple controls for generation, powerful tools for editing._

---

## Core Features

### 1. The Render Engine (3D View)

Turn simple geometry into finished art.

- **Depth Map Render (Mist)**: Use a simple mist pass to define geometry, let AI handle the rest. Perfect for rapid concepting from blockouts.
- **Regular Render (Image-to-Image)**: Enhance your existing Eevee/Cycles renders with AI magic. Use a prompt to change the style, lighting, or details of your scene while keeping the original composition.
- **Style Transfer**: Apply the exact look/feel of _any_ reference image to your scene.

### 2. The Studio (Image Editor)

Refine and perfect your results.

- **Object Integration**: Add people, furniture, or effects that perfectly match your scene's lighting.
- **Iterative Workflow**: Make change after change until it's perfect.
- **History System**: Never lose a version. Jump back to any previous state instantly.

---

## Workflow Guide

### Part 1: Generating the Base

_Located in 3D View > N-Panel > Nano Banana Pro_

1.  **Set Up Scene**: Block out your shapes. No need for complex materials.
2.  **Choose Resolution**: Select **1K**, **2K**, or **4K**.
3.  **Add Style (Optional)**: Load a reference image to define the mood.
4.  **Render**: Click "Generate AI Render".

### Part 2: Refining & Inpainting

_Located in Image Editor > N-Panel > Nano Banana Pro Edit_

1.  **Open Image**: Your render automatically opens here.
2.  **Inpaint (Optional)**:
    - Click **"Inpainting"**.
    - Click **"Draw"** and paint over the area you want to change.
    - Type a prompt (e.g., "add a red sports car").
    - Click **"Render"**.
3.  **Integrate Object (Optional)**:
    - Enable **"Reference Image"** and load a photo of an object (e.g., a specific chair).
    - Use **"Inpainting"** to draw a mask where you want it.
    - Prompt: "Integrate this object here".
    - Click **"Render"**.
4.  **Edit Whole Image**:
    - Type a prompt (e.g., "make it night time", "add rain").
    - Click **"Apply AI Edit"**.

---

## Examples

### 1. Depth Map Mode

Turn blockouts into art using Mist Pass

**With Style Reference**
Uses geometry + reference image style
| Depth Input | Style Reference | Result |
| :---: | :---: | :---: |
| <img src="docs/images/depth_input.png" width="250"> | <img src="docs/images/style_ref.png" width="250"> | <img src="docs/images/depth_style_result.png" width="250"> |

**Without Style Reference**
Uses geometry + text prompt only
| Depth Input | Text Prompt | Result |
| :---: | :---: | :---: |
| <img src="docs/images/depth_input_2.png" width="250"> | "Make it ultra realistic, like a photo taken on an iPhone" | <img src="docs/images/depth_prompt_result.png" width="250"> |

### 2. Regular Render Mode

Enhance existing Eevee/Cycles renders

**With Style Reference**
Transfer style while keeping exact composition
| Original Render | Style Reference | Result |
| :---: | :---: | :---: |
| <img src="docs/images/reg_render.png" width="250"> | <img src="docs/images/reg_style.png" width="250"> | <img src="docs/images/reg_style_result.png" width="250"> |

**Without Style Reference**
Change lighting/mood with text
| Original Render | Text Prompt | Result |
| :---: | :---: | :---: |
| <img src="docs/images/reg_render_2.png" width="250"> | "Make a sketch on paper with a regular pencil." | <img src="docs/images/reg_prompt_result.png" width="250"> |

### 3. AI Editor Studio

Post-processing magic

**Inpainting (Add Object)**
Draw mask + Prompt
| Original | Mask | Prompt | Result |
| :---: | :---: | :---: | :---: |
| <img src="docs/images/edit_orig.png" width="200"> | <img src="docs/images/edit_mask.png" width="200"> | "Add a red car" | <img src="docs/images/edit_result.png" width="200"> |

**Object Integration**
Draw mask + Reference Image + Prompt
| Original | Mask | Reference Object | Result |
| :---: | :---: | :---: | :---: |
| <img src="docs/images/edit_result.png" width="200"> | <img src="docs/images/int_mask.png" width="200"> | <img src="docs/images/int_ref.png" width="200"> | <img src="docs/images/int_result.png" width="200"> |

**Full Image Edit**
Prompt only (no mask)
| Original | Prompt | Result |
| :---: | :---: | :---: |
| <img src="docs/images/int_result.png" width="250"> | "Make it night time, raining" | <img src="docs/images/full_result.png" width="250"> |

---

## Installation & Setup

1.  **Get API Key**: Visit [Google AI Studio](https://aistudio.google.com/) and create a free API key.
2.  **Download**: Get the latest `.zip` from [Releases](https://github.com/kovname/nano-banana-render/releases).
3.  **Install**: In Blender, go to `Edit > Preferences > Add-ons > Install...` and select the zip.
4.  **Configure**: Paste your API key in the addon preferences.

> **Note**: Google provides a generous free tier for the Gemini API, but you **must enable billing** in Google Cloud Console to access the Gemini 3 Pro model used by this addon.

---

## Contributing

Found a bug? Want a feature? [Open an issue!](https://github.com/kovname/nano-banana-render/issues)

Share your renders and let's make this better together!

---

<div align="center">

**Made with 🍌 by Kovname**

[Star](https://github.com/kovname/nano-banana-render) • [Download](https://github.com/kovname/nano-banana-render/releases) • [Issues](https://github.com/kovname/nano-banana-render/issues)

</div>
