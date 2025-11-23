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

### The Render Panel

_Simple, powerful controls for generating your base image._

![Main Interface](docs/images/ui_main.png)

### The Editor Studio

_A complete post-processing suite with Inpainting and History._

![Editor Interface](docs/images/ui_editor.png)

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

_Turn blockouts into art using Mist Pass_

**With Style Reference**
_Uses geometry + reference image style_
| Depth Input | Style Reference | Result |
| :---: | :---: | :---: |
| ![depth](docs/images/depth_input.png) | ![style](docs/images/style_ref.png) | ![result](docs/images/depth_style_result.png) |

**Without Style Reference**
_Uses geometry + text prompt only_
| Depth Input | Text Prompt | Result |
| :---: | :---: | :---: |
| ![depth](docs/images/depth_input_2.png) | _"A futuristic sci-fi city, neon lights"_ | ![result](docs/images/depth_prompt_result.png) |

### 2. Regular Render Mode

_Enhance existing Eevee/Cycles renders_

**With Style Reference**
_Transfer style while keeping exact composition_
| Original Render | Style Reference | Result |
| :---: | :---: | :---: |
| ![render](docs/images/reg_render.png) | ![style](docs/images/reg_style.png) | ![result](docs/images/reg_style_result.png) |

**Without Style Reference**
_Change lighting/mood with text_
| Original Render | Text Prompt | Result |
| :---: | :---: | :---: |
| ![render](docs/images/reg_render_2.png) | _"Make it look like a sketch"_ | ![result](docs/images/reg_prompt_result.png) |

### 3. AI Editor Studio

_Post-processing magic_

**Inpainting (Add Object)**
_Draw mask + Prompt_
| Original | Mask | Prompt | Result |
| :---: | :---: | :---: | :---: |
| ![orig](docs/images/edit_orig.png) | ![mask](docs/images/edit_mask.png) | _"Add a red car"_ | ![res](docs/images/edit_result.png) |

**Object Integration**
_Draw mask + Reference Image + Prompt_
| Original | Mask | Reference Object | Result |
| :---: | :---: | :---: | :---: |
| ![orig](docs/images/int_orig.png) | ![mask](docs/images/int_mask.png) | ![ref](docs/images/int_ref.png) | ![res](docs/images/int_result.png) |

**Full Image Edit**
_Prompt only (no mask)_
| Original | Prompt | Result |
| :---: | :---: | :---: |
| ![orig](docs/images/full_orig.png) | _"Make it night time, raining"_ | ![res](docs/images/full_result.png) |

---

## Installation & Setup

1.  **Get API Key**: Visit [Google AI Studio](https://aistudio.google.com/) and create a free API key.
2.  **Download**: Get the latest `.zip` from [Releases](https://github.com/kovname/nano-banana-render/releases).
3.  **Install**: In Blender, go to `Edit > Preferences > Add-ons > Install...` and select the zip.
4.  **Configure**: Paste your API key in the addon preferences.

> **Note**: Google provides a generous free tier for the Gemini API, but you may need to enable billing in Google Cloud Console to access the highest rate limits.

---

## Contributing

Found a bug? Want a feature? [Open an issue!](https://github.com/kovname/nano-banana-render/issues)

Share your renders and let's make this better together!

---

<div align="center">

**Made with 🍌 by Kovname**

[Star](https://github.com/kovname/nano-banana-render) • [Download](https://github.com/kovname/nano-banana-render/releases) • [Issues](https://github.com/kovname/nano-banana-render/issues)

</div>
