# 🍌 Nano Banana Render

**AI Render Engine for Blender** — not just an addon, a whole new render engine.

Nano Banana integrates directly into Blender as a **standalone render engine** alongside Cycles and Eevee. Select it from the render engine dropdown and start generating photorealistic images from simple blockouts, depth maps, or existing renders — powered by **Google Gemini AI**.

<p align="center">
  <a href="https://nanode.tech">🌐 nanode.tech</a> •
  <a href="https://github.com/kovname/nano-banana-render/releases">📦 Download</a> •
  <a href="https://github.com/kovname/nano-banana-render/issues">🐛 Report Bug</a>
</p>

[![Version](https://img.shields.io/badge/Version-2.5.0_Beta-FFC107.svg?logo=github&logoColor=white)](https://github.com/kovname/nano-banana-render/releases)
[![Blender](https://img.shields.io/badge/Blender-4.5%2B%7C5.0%2B-orange?logo=blender)](https://www.blender.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/kovname/nano-banana-render/total?color=brightgreen)](https://github.com/kovname/nano-banana-render/releases)

---

> [IMPORTANT]
> **This is a beta release.** We are currently waiting for payment system approval. In the meantime, all users receive **100 free credits on signup** — no credit card required. We'd love your help testing! If you find bugs or have ideas, please use the **Feedback button** inside the addon (and earn **+50 bonus credits** for submission!).

---

## ☁️ Supported by Google Cloud for Startups

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/5/51/Google_Cloud_logo.svg" width="200" alt="Google Cloud">
</p>

This project is proudly supported by the **Google Cloud for Startups** program. Their generous cloud credits make it possible for us to run the AI infrastructure and offer free credits to testers during this beta period. A huge thank you to Google Cloud for believing in independent creators and open-source tools! 🙏

---

## What Is Nanode?

We've completely rebuilt the architecture. Nanode is no longer a typical N-panel addon — **Nano Banana** now registers as a **full render engine** in Blender, just like Cycles or Eevee. Select it from the render engine dropdown, press **F12**, and render with AI.

Inside the engine you can choose between different AI models:

| Model | Based On | Best For |
| :--- | :--- | :--- |
| **Nano Banana** | Gemini 2.5 Flash | Fast drafts, iteration |
| **Nano Banana 2** | Gemini 3.1 Flash | Balanced speed & quality |
| **Nano Banana Pro** | Gemini 3 Pro | Maximum quality renders |

Press **F12** and render just like you would with Cycles — except the AI generates the final image.

---

## Core Features

### 🎬 Render Engine (3D View)
- **Depth Map Render (Mist)** — Block out shapes, let AI create photorealistic results
- **Regular Render (Eevee I2I)** — Enhance Eevee/Cycles renders with AI
- **Style Transfer** — Apply the look of any reference image to your scene
- **Resolution Control** — 1K, 2K, or 4K with automatic aspect ratio preservation

### ✏️ AI Image Editor (Editor Studio)
- **Inpainting** — Draw a mask, describe what to add
- **Object Integration** — Place reference objects with matched lighting
- **Full Image Edit** — Change mood, time of day, weather with a prompt
- **History System** — Jump back to any previous state

### 🔐 Account & Credits
- **Google Login** — One-click sign in, no API keys to manage
- **Credit System** — 100 free credits on signup, earn more via feedback
- **Secure** — All generation happens on our servers, nothing stored locally

---

## Getting Started

### 1. Install the Addon

1. Download the latest `.zip` from [Releases](https://github.com/kovname/nano-banana-render/releases)
2. In Blender: `Edit > Preferences > Add-ons > Install...` → select the zip
3. Enable **Nanode AI Render Engine**

### 2. Create an Account

1. In the addon's Render panel, click **Login with Google**
2. Sign in with your Google account — you'll receive **100 free credits** instantly
3. The addon auto-connects to Blender, you're ready to render

### 3. Your First Render

1. Select **Nano Banana** (or Pro) from the render engine dropdown
2. Set up your scene with basic geometry
3. Write a prompt describing your desired result
4. Press **F12** or click **Generate AI Render**
5. Open the result in the **Image Editor** to refine with AI edits

---

## Examples

### 1. Depth Map Mode

Turn blockouts into art using Mist Pass

**With Style Reference**
Uses geometry + reference image style
| Depth Input | Style Reference | Result |
| :---: | :---: | :---: |
| <img src="docs/images/depth_input.png" height="300"> | <img src="docs/images/style_ref.png" height="300"> | <img src="docs/images/depth_style_result.png" height="300"> |

**Without Style Reference**
Uses geometry + text prompt only
| Depth Input | Text Prompt | Result |
| :---: | :---: | :---: |
| <img src="docs/images/depth_input_2.png" height="300"> | "Make it ultra realistic, like a photo taken on an iPhone" | <img src="docs/images/depth_prompt_result.png" height="300"> |

### 2. Regular Render Mode

Enhance existing Eevee/Cycles renders

**With Style Reference**
Transfer style while keeping exact composition
| Original Render | Style Reference | Result |
| :---: | :---: | :---: |
| <img src="docs/images/reg_render.png" height="300"> | <img src="docs/images/reg_style.png" height="300"> | <img src="docs/images/reg_style_result.png" height="300"> |

**Without Style Reference**
Change lighting/mood with text
| Step | Content |
| :--- | :--- |
| **Original** | <img src="docs/images/reg_render_2.png" width="100%"> |
| **Prompt** | "Make the scene photorealistic with dark atmospheric lighting, a stormy sky, wet rock textures, and replace the character with a knight." |
| **Result** | <img src="docs/images/reg_prompt_result.png" width="100%"> |

### 3. AI Editor Studio

Post-processing magic

**Inpainting (Add Object)**
Draw mask + Prompt
| Original | Mask | Prompt | Result |
| :---: | :---: | :---: | :---: |
| <img src="docs/images/edit_orig.png" height="200"> | <img src="docs/images/edit_mask.png" height="200"> | "Add a red car" | <img src="docs/images/edit_result.png" height="200"> |

**Object Integration**
Draw mask + Reference Image + Prompt
| Original | Mask | Reference Object | Result |
| :---: | :---: | :---: | :---: |
| <img src="docs/images/edit_result.png" height="200"> | <img src="docs/images/int_mask.png" height="200"> | <img src="docs/images/int_ref.png" height="200"> | <img src="docs/images/int_result.png" height="200"> |

**Full Image Edit**
Prompt only (no mask)
| Original | Prompt | Result |
| :---: | :---: | :---: |
| <img src="docs/images/int_result.png" height="300"> | "Make it night time, raining" | <img src="docs/images/full_result.png" height="300"> |

---

## Feedback & Bug Reports

Found a bug? Have an idea? We need your help to make this better!

- **In-addon Feedback** — Click the 💬 **Feedback** button in the editor panel. You'll earn **+50 credits** for your first submission!
- **GitHub Issues** — [Open an issue](https://github.com/kovname/nano-banana-render/issues) for detailed bug reports
- **Email** — Reach us at **contact@nanode.tech**

Every piece of feedback helps shape the future of Nano Banana. We read everything. 🍌

---

## Roadmap

There is **a lot** of exciting stuff ahead. This beta is just the beginning — we're working on new features, better models, and tighter Blender integration. Stay tuned!

---

## Support the Project

If you find Nanode useful, the best way to support us is:

⭐ **[Star this repo](https://github.com/kovname/nano-banana-render)** — it helps others discover the project and motivates us to keep building!

---

<div align="center">

**Made with 🍌 by [Kovname](https://github.com/kovname)**

Thank you to everyone testing the beta — your feedback is invaluable.

[⭐ Star](https://github.com/kovname/nano-banana-render) • [📦 Download](https://github.com/kovname/nano-banana-render/releases) • [🐛 Issues](https://github.com/kovname/nano-banana-render/issues) • [🌐 nanode.tech](https://nanode.tech)

</div>
