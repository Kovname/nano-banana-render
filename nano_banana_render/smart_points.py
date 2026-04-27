"""
Smart Points — region-specific AI editing for the Image Editor.
No PIL dependency — uses numpy + Blender for composite generation.
"""

import bpy
import gpu
import math
import numpy as np
from bpy.types import Operator, PropertyGroup
from bpy.props import (
    StringProperty, FloatProperty, FloatVectorProperty,
    IntProperty, CollectionProperty, BoolProperty,
)
from gpu_extras.batch import batch_for_shader

# ── Palette ──────────────────────────────────────────────
POINT_COLORS = [
    (1.0, 0.2, 0.2, 1.0),   # red
    (0.2, 0.6, 1.0, 1.0),   # blue
    (0.2, 0.9, 0.3, 1.0),   # green
    (1.0, 0.7, 0.0, 1.0),   # amber
    (0.8, 0.3, 1.0, 1.0),   # purple
    (0.0, 0.9, 0.9, 1.0),   # cyan
    (1.0, 0.4, 0.7, 1.0),   # pink
    (0.6, 0.4, 0.2, 1.0),   # brown
    (0.5, 1.0, 0.5, 1.0),   # lime
    (1.0, 0.5, 0.3, 1.0),   # orange
    (0.4, 0.4, 1.0, 1.0),   # indigo
    (0.9, 0.9, 0.2, 1.0),   # yellow
]

MARKER_RADIUS_PX = 10

# ── 3×5 bitmap font for digits (no PIL needed) ──────────
_DIGITS = {
    '0': ["###", "# #", "# #", "# #", "###"],
    '1': [" # ", "## ", " # ", " # ", "###"],
    '2': ["###", "  #", "###", "#  ", "###"],
    '3': ["###", "  #", "###", "  #", "###"],
    '4': ["# #", "# #", "###", "  #", "  #"],
    '5': ["###", "#  ", "###", "  #", "###"],
    '6': ["###", "#  ", "###", "# #", "###"],
    '7': ["###", "  #", "  #", "  #", "  #"],
    '8': ["###", "# #", "###", "# #", "###"],
    '9': ["###", "# #", "###", "  #", "###"],
}


def _stamp_number(pixels, x0, y0, number, color, w, h, scale=2, ch=4):
    """Stamp a number into pixel array using bitmap font."""
    text = str(number)
    cursor_x = x0
    for ch_chr in text:
        rows = _DIGITS.get(ch_chr, _DIGITS['0'])
        for row_i, row in enumerate(rows):
            for col_i, c in enumerate(row):
                if c == '#':
                    for dy in range(scale):
                        for dx in range(scale):
                            px = cursor_x + col_i * scale + dx
                            py = y0 - row_i * scale - dy + len(rows) * scale // 2
                            if 0 <= px < w and 0 <= py < h:
                                idx = (py * w + px) * ch
                                pixels[idx] = color[0]
                                pixels[idx+1] = color[1]
                                pixels[idx+2] = color[2]
                                if ch == 4:
                                    pixels[idx+3] = 1.0
        cursor_x += (len(rows[0]) + 1) * scale


# ── PropertyGroup ────────────────────────────────────────

class SmartPointItem(PropertyGroup):
    pos_x: FloatProperty(name="X", default=0.5, min=0.0, max=1.0)
    pos_y: FloatProperty(name="Y", default=0.5, min=0.0, max=1.0)
    prompt: StringProperty(name="Prompt", default="", maxlen=300)
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=4,
                               default=(1.0, 0.2, 0.2, 1.0), min=0.0, max=1.0)
    number: IntProperty(name="Number", default=1)


# ── GPU overlay ──────────────────────────────────────────

_draw_handler = None


def _draw_point_marker(shader, pt, px, py):
    """Draw a single smart point marker with ring and number."""
    col_fill = (pt.color[0], pt.color[1], pt.color[2], 0.35)
    col_ring = (pt.color[0], pt.color[1], pt.color[2], 1.0)

    # Filled circle
    verts = [(px, py)]
    for i in range(25):
        a = 2 * math.pi * i / 24
        verts.append((px + MARKER_RADIUS_PX * math.cos(a),
                      py + MARKER_RADIUS_PX * math.sin(a)))
    
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
    shader.bind()
    shader.uniform_float("color", col_fill)
    batch.draw(shader)

    # Ring
    ring = []
    for i in range(25):
        a = 2 * math.pi * i / 24
        ring.append((px + MARKER_RADIUS_PX * math.cos(a),
                     py + MARKER_RADIUS_PX * math.sin(a)))
    
    gpu.state.line_width_set(2.5)
    batch2 = batch_for_shader(shader, 'LINE_STRIP', {"pos": ring})
    shader.uniform_float("color", col_ring)
    batch2.draw(shader)
    gpu.state.line_width_set(1.0)

    # Number label
    import blf
    blf.size(0, 16)
    blf.position(0, px + MARKER_RADIUS_PX + 4, py - 5, 0)
    blf.color(0, *col_ring)
    blf.draw(0, str(pt.number))

def _draw_callback():
    context = bpy.context
    if not hasattr(context, 'window_manager'):
        return
    wm = context.window_manager
    if not hasattr(wm, 'nano_banana_editor'):
        return
    props = wm.nano_banana_editor
    if not hasattr(props, 'smart_points') or len(props.smart_points) == 0:
        return
    area = context.area
    if not area or area.type != 'IMAGE_EDITOR':
        return

    # Find image and region transform
    sima = next((s for s in area.spaces if s.type == 'IMAGE_EDITOR'), None)
    if not sima or not sima.image:
        return

    img = sima.image
    if img.size[0] == 0 or img.size[1] == 0:
        return

    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if not region:
        return

    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    for pt in props.smart_points:
        # Blender's view_to_region flawlessly converts the 0..1 image coordinates back to exact screen pixels
        px, py = region.view2d.view_to_region(pt.pos_x, pt.pos_y, clip=False)
        _draw_point_marker(shader, pt, px, py)

    gpu.state.blend_set('NONE')


def ensure_draw_handler():
    global _draw_handler
    if _draw_handler is not None:
        return
    _draw_handler = bpy.types.SpaceImageEditor.draw_handler_add(
        _draw_callback, (), 'WINDOW', 'POST_PIXEL')


def remove_draw_handler():
    global _draw_handler
    if _draw_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_draw_handler, 'WINDOW')
        _draw_handler = None


# ── Composite builder (numpy only, no PIL) ───────────────

def _draw_marker_on_pixels(pixels, w, h, ch, cx, cy, color, r_in, r_out):
    """Draw a single marker (fill + outline) onto the pixel array."""
    y0 = max(0, int(cy - r_out - 2))
    y1 = min(h, int(cy + r_out + 2))
    x0 = max(0, int(cx - r_out - 2))
    x1 = min(w, int(cx + r_out + 2))

    for y in range(y0, y1):
        for x in range(x0, x1):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            if dist <= r_out + 1.0:
                idx = (y * w + x) * ch
                
                # Calculate alpha for smooth anti-aliasing
                if dist <= r_in:
                    # Inner fill (semi-transparent in UI, let's make it 80% opaque for visibility)
                    alpha = 0.8
                    blend = alpha
                    pixels[idx] = pixels[idx] * (1-blend) + color[0] * blend
                    pixels[idx+1] = pixels[idx+1] * (1-blend) + color[1] * blend
                    pixels[idx+2] = pixels[idx+2] * (1-blend) + color[2] * blend
                elif dist <= r_out:
                    # White outline with anti-aliasing on the outer edge
                    edge_alpha = min(1.0, r_out - dist + 0.5)
                    edge_alpha = max(0.0, edge_alpha)
                    pixels[idx] = pixels[idx] * (1-edge_alpha) + 1.0 * edge_alpha
                    pixels[idx+1] = pixels[idx+1] * (1-edge_alpha) + 1.0 * edge_alpha
                    pixels[idx+2] = pixels[idx+2] * (1-edge_alpha) + 1.0 * edge_alpha
                
                if ch == 4:
                    pixels[idx+3] = 1.0

def build_composite(image, points):
    """Draw numbered markers on *image* pixels → save to temp PNG.
    Returns (path, temp_dir) or (None, None)."""
    import tempfile, os

    try:
        w, h = image.size
        if w <= 0 or h <= 0:
            return None, None

        ch = image.channels
        # 1D array for foolproof indexing
        pixels = np.array(image.pixels[:], dtype=np.float32)

        import math
        marker_r = max(8, w // 80)  # slightly larger
        outline_w = max(2, marker_r // 4)
        r_out = marker_r + outline_w
        r_in = marker_r

        for pt in points:
            cx = int(pt.pos_x * w)
            cy = int(pt.pos_y * h)
            color = [pt.color[0], pt.color[1], pt.color[2]]

            print(f"[SMART POINTS] Drawing marker {pt.number} at cx={cx}, cy={cy} (pos={pt.pos_x:.4f},{pt.pos_y:.4f})")

            # Bounds check — skip points that landed outside the image
            if cx < 0 or cx >= w or cy < 0 or cy >= h:
                print(f"[SMART POINTS] WARNING: marker {pt.number} is out of bounds, skipping")
                continue

            _draw_marker_on_pixels(pixels, w, h, ch, cx, cy, color, r_in, r_out)

            # Draw the number nicely next to it
            _stamp_number(pixels, cx + int(r_out) + 4, cy, pt.number, color, w, h, scale=max(2, marker_r // 3), ch=ch)

        # Save via temporary Blender image
        temp_dir = tempfile.mkdtemp(prefix="nano_banana_sp_")
        composite_path = os.path.join(temp_dir, "composite_guide.png")

        tmp_name = "__sp_composite_tmp__"
        if tmp_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[tmp_name])

        tmp_img = bpy.data.images.new(tmp_name, w, h, alpha=(ch == 4))
        tmp_img.colorspace_settings.name = image.colorspace_settings.name
        tmp_img.pixels.foreach_set(pixels)
        tmp_img.update()  # REQUIRED: flush python pixels to Blender's internal buffer
        tmp_img.filepath_raw = composite_path
        tmp_img.file_format = 'PNG'
        tmp_img.save()
        bpy.data.images.remove(tmp_img)

        print(f"[SMART POINTS] Composite saved: {composite_path}")
        return composite_path, temp_dir

    except Exception as e:
        print(f"[SMART POINTS] Composite build failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def build_prompt(points):
    """Build combined JSON-schema prompt for Gemini with two-image workflow."""
    import json

    instructions = [f"Point {pt.number}: {pt.prompt.strip()}" for pt in points]

    schema = {
        "role": "Precision Image Editor",
        "task_explanation": (
            "You are provided with TWO images. "
            "IMAGE 1 is the original, clean photograph. THIS IS YOUR BASE IMAGE. "
            "IMAGE 2 is the exact same image but with brightly colored UI markers (circles with numbers inside) overlaid on it. "
            "These markers are NOT part of the scene. They are just laser pointers telling you WHERE to look."
        ),
        "MANDATORY_CONSTRAINTS": [
            "NEVER OUTPUT THE MARKERS. The colored circles and numbers from Image 2 MUST NOT exist in your final image.",
            "Your output must look like a natural photograph. If there is a floating colored circle with a number in your output, YOU HAVE FAILED.",
            "Modify Image 1 ONLY at the locations indicated by the markers in Image 2.",
            "Do NOT hallucinate or create new objects unless specifically asked. You are primarily modifying the material, color, or properties of EXISTING objects.",
            "Preserve the original lighting, shadows, and composition of Image 1 in all unedited areas."
        ],
        "execution_steps": [
            "Step 1: Look at Image 2 to find the colored markers (Point 1, Point 2, etc.).",
            "Step 2: Identify the underlying object or surface at those exact coordinates.",
            "Step 3: Apply the user's instructions to those specific objects on Image 1.",
            "Step 4: Ensure the final image is completely clean of any UI elements, circles, or numbers."
        ],
        "point_instructions": instructions,
    }
    return f"PROMPT_SCHEMA:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"


# get_original_image removed — composite is now always built on the
# current image (the one being sent as original.png), not history[0].


# ── Operators ────────────────────────────────────────────

class SmartPointOTAdd(Operator):
    """Click on the image to place a new Smart Point"""
    bl_idname = "nano_banana.smart_point_add"
    bl_label = "Add Smart Point"
    bl_options = {'REGISTER', 'INTERNAL'}

    def invoke(self, context, event):
        if context.area.type != 'IMAGE_EDITOR':
            self.report({'WARNING'}, "Must be in Image Editor")
            return {'CANCELLED'}
        sima = context.space_data
        if not sima or not sima.image:
            self.report({'WARNING'}, "Open an image first")
            return {'CANCELLED'}
        ensure_draw_handler()
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set("Click on image to place Smart Point (Esc to cancel)")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            context.area.header_text_set(None)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            sima = context.space_data
            img = sima.image
            if not img:
                context.area.header_text_set(None)
                return {'CANCELLED'}
            region = context.region
            _, _ = img.size
            img_x, img_y = region.view2d.region_to_view(
                event.mouse_region_x, event.mouse_region_y)
            # Blender Image Editor maps the entire image to 0.0 .. 1.0 in view2d space
            nx = max(0.0, min(1.0, float(img_x)))
            ny = max(0.0, min(1.0, float(img_y)))

            props = context.window_manager.nano_banana_editor
            idx = len(props.smart_points)
            color = POINT_COLORS[idx % len(POINT_COLORS)]

            pt = props.smart_points.add()
            pt.pos_x = nx
            pt.pos_y = ny
            pt.number = idx + 1
            pt.color = color

            context.area.tag_redraw()
            context.area.header_text_set(None)
            self.report({'INFO'}, f"Point {pt.number} placed")
            return {'FINISHED'}
        return {'PASS_THROUGH'}


class SmartPointOTDelete(Operator):
    """Delete a Smart Point"""
    bl_idname = "nano_banana.smart_point_delete"
    bl_label = "Delete Smart Point"
    bl_options = {'REGISTER', 'INTERNAL'}
    index: IntProperty()

    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        pts = props.smart_points
        if 0 <= self.index < len(pts):
            pts.remove(self.index)
            for i, p in enumerate(pts):
                p.number = i + 1
                p.color = POINT_COLORS[i % len(POINT_COLORS)]
        if len(pts) == 0:
            remove_draw_handler()
        context.area.tag_redraw()
        return {'FINISHED'}


class SmartPointOTClearAll(Operator):
    """Remove all Smart Points"""
    bl_idname = "nano_banana.smart_point_clear"
    bl_label = "Clear All Points"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        props = context.window_manager.nano_banana_editor
        props.smart_points.clear()
        remove_draw_handler()
        context.area.tag_redraw()
        return {'FINISHED'}


# ── Panel draw (called from image_editor.py) ─────────────

def draw_smart_points_ui(layout, props):
    """Draw point list + add button inside the toggle box."""
    row = layout.row()
    row.scale_y = 1.3
    row.operator("nano_banana.smart_point_add", text="Add Point", icon='ADD')

    points = props.smart_points
    if len(points) == 0:
        return

    for i, pt in enumerate(points):
        pt_box = layout.box()
        hdr = pt_box.row(align=True)
        hdr.prop(pt, "color", text="")
        hdr.label(text=f"Point {pt.number}")
        op = hdr.operator("nano_banana.smart_point_delete", text="", icon='TRASH')
        op.index = i
        pt_box.prop(pt, "prompt", text="")

    row = layout.row()
    row.operator("nano_banana.smart_point_clear", text="Clear All", icon='X')


# ── Registration ─────────────────────────────────────────

classes = (
    SmartPointItem,
    SmartPointOTAdd,
    SmartPointOTDelete,
    SmartPointOTClearAll,
)
