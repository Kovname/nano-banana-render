"""
Beta API client for Nanode Blender addon.
Communicates with the Nanode Beta Server instead of Google API directly.
No Google API key is stored or used on the client side.
"""

import json
import base64
from typing import Optional, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


def _get_server_url() -> str:
    """Get the production server URL."""
    return "https://api.nanode.tech"


def _get_token() -> str:
    """Get the beta token from addon preferences."""
    import bpy
    prefs = bpy.context.preferences.addons.get("nano_banana_render")
    if prefs and hasattr(prefs.preferences, "beta_token"):
        return prefs.preferences.beta_token.strip()
    return ""


def _get_hwid() -> str:
    """Get the hardware ID from addon preferences."""
    import bpy
    prefs = bpy.context.preferences.addons.get("nano_banana_render")
    if prefs and hasattr(prefs.preferences, "hwid"):
        val = prefs.preferences.hwid
        if not val:
            from . import get_hwid_stable
            val = get_hwid_stable()
            prefs.preferences.hwid = val
        return val
    from . import get_hwid_stable
    return get_hwid_stable()


def _get_eu_format() -> bool:
    """Check if the user consented to European format data collection."""
    import bpy
    prefs = bpy.context.preferences.addons.get("nano_banana_render")
    if prefs and hasattr(prefs.preferences, "eu_format"):
        return prefs.preferences.eu_format
    return True


def _post(endpoint: str, data: dict, timeout: int = 120) -> dict:
    """POST JSON to server endpoint. Returns parsed response."""
    url = f"{_get_server_url()}{endpoint}"
    payload = json.dumps(data).encode("utf-8")

    req = urllib_request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        # Parse server error message
        try:
            body = json.loads(e.read().decode("utf-8"))
            detail = body.get("detail", str(e))
        except (ValueError, UnicodeDecodeError):
            detail = str(e)
        raise BetaAPIError(e.code, detail)
    except URLError as e:
        raise BetaAPIError(0, f"Cannot connect to server: {e.reason}")
    except Exception as e:
        raise BetaAPIError(0, f"Network error: {str(e)}")


def _get(endpoint: str, timeout: int = 10) -> dict:
    """GET from server endpoint. Returns parsed response."""
    url = f"{_get_server_url()}{endpoint}"
    req = urllib_request.Request(url, method="GET")

    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            detail = body.get("detail", str(e))
        except (ValueError, UnicodeDecodeError):
            detail = str(e)
        raise BetaAPIError(e.code, detail)
    except URLError as e:
        raise BetaAPIError(0, f"Cannot connect to server: {e.reason}")
    except Exception as e:
        raise BetaAPIError(0, f"Network error: {str(e)}")


class BetaAPIError(Exception):
    """Error from the beta server."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


# ─── Public API ───────────────────────────────────────────────

def generate(
    prompt: str,
    model: str,
    input_image_path: str,
    reference_image_path: Optional[str] = None,
    mask_image_path: Optional[str] = None,
    gen_type: str = "render_depth",
    width: int = 1024,
    height: int = 1024,
    user_prompt: Optional[str] = None,
) -> Tuple[bytes, int, int]:
    """
    Generate an AI image via the beta server.

    Args:
        prompt: Full system prompt sent to the AI
        model: Model name (e.g. 'gemini-3-pro-image-preview')
        input_image_path: Path to the input render / depth map
        reference_image_path: Optional style reference image path
        mask_image_path: Optional inpaint mask path
        gen_type: 'render_depth', 'render_eevee', or 'inpaint'
        width: Generation width limit
        height: Generation height limit
        user_prompt: The user's original prompt text (before system template)

    Returns:
        (...)
    """
    token = _get_token()
    if not token:
        raise BetaAPIError(401, "No beta token configured. Go to Edit → Preferences → Add-ons → Nano Banana")

    # Encode images to base64
    with open(input_image_path, "rb") as f:
        input_b64 = base64.b64encode(f.read()).decode("utf-8")

    ref_b64 = None
    if reference_image_path:
        try:
            with open(reference_image_path, "rb") as f:
                ref_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"[BETA API] Failed to read reference image: {e}")

    mask_b64 = None
    if mask_image_path:
        try:
            with open(mask_image_path, "rb") as f:
                mask_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"[BETA API] Failed to read mask image: {e}")

    hwid = _get_hwid()

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

    data = {
        "token": token,
        "prompt": prompt,
        "user_prompt": user_prompt,
        "model": model,
        "input_image": input_b64,
        "reference_image": ref_b64,
        "mask_image": mask_b64,
        "gen_type": gen_type,
        "width": width,
        "height": height,
        "hwid": hwid,
        "addon_version": addon_version,
        "blender_version": blender_version,
    }

    print(f"[BETA API] Sending generation request ({gen_type}, model={model})")
    resp = _post("/generate", data, timeout=120)

    # Decode the returned image
    image_bytes = base64.b64decode(resp["image"])
    generation_id = resp.get("generation_id", 0)
    balance = resp.get("balance", 0)

    print(f"[BETA API] Generation #{generation_id} received, balance: {balance}")
    return image_bytes, generation_id, balance


def get_balance() -> int:
    """Fetch remaining generations/credits from server."""
    token = _get_token()
    if not token:
        return -1

    try:
        resp = _get(f"/balance/{token}")
        return resp.get("balance", 0)
    except BetaAPIError:
        return -1


def get_balance_info() -> dict:
    """Fetch balance + feedback_given flag from server."""
    token = _get_token()
    if not token:
        return {"balance": -1, "feedback_given": False}

    try:
        resp = _get(f"/balance/{token}")
        return {
            "balance": resp.get("balance", 0),
            "feedback_given": resp.get("feedback_given", False),
        }
    except BetaAPIError:
        return {"balance": -1, "feedback_given": False}


def get_credit_info() -> dict:
    """Get full balance info including user_type, pricing, store_url."""
    token = _get_token()
    if not token:
        return {"balance": -1, "user_type": "unknown"}

    try:
        resp = _get(f"/balance/{token}")
        return resp
    except BetaAPIError:
        return {"balance": -1, "user_type": "unknown"}


def send_rating(generation_id: int, rating: str) -> bool:
    """Send a like/dislike rating for a generation."""
    token = _get_token()
    if not token:
        return False

    hwid = _get_hwid()

    try:
        _post("/rate", {
            "token": token,
            "generation_id": generation_id,
            "rating": rating,
            "hwid": hwid,
        }, timeout=10)
        print(f"[BETA API] Rated generation #{generation_id}: {rating}")
        return True
    except BetaAPIError as e:
        print(f"[BETA API] Rating failed: {e.message}")
        return False


def send_feedback(text: str) -> int:
    """Submit feedback text. Returns new balance (or -1 on error)."""
    token = _get_token()
    if not token:
        raise BetaAPIError(401, "No beta token configured")

    hwid = _get_hwid()

    resp = _post("/feedback", {
        "token": token,
        "text": text,
        "hwid": hwid,
    }, timeout=10)

    new_balance = resp.get("balance", 0)
    print(f"[BETA API] Feedback submitted, +{resp.get('bonus', 50)} gens, balance: {new_balance}")
    return new_balance
