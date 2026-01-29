# Security: API Key Setup

## ⚠️ Important: Protecting Your API Key

Your Google Gemini API key is sensitive and should **never** be committed to version control or shared.

## Recommended Setup (Environment Variables)

### Option 1: Using Environment Variables (Recommended)

1. **Create a `.env` file** in the project root (it's already in `.gitignore`):
   ```
   GEMINI_API_KEY=your_actual_api_key_here
   ```

2. **Set the environment variable** before running Blender:

   **Windows (Command Prompt):**
   ```cmd
   set GEMINI_API_KEY=your_api_key_here
   blender.exe
   ```

   **Windows (PowerShell):**
   ```powershell
   $env:GEMINI_API_KEY="your_api_key_here"
   & "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
   ```

   **macOS/Linux:**
   ```bash
   export GEMINI_API_KEY=your_api_key_here
   blender
   ```

3. **Using python-dotenv (Optional)**:
   ```bash
   pip install python-dotenv
   ```
   If installed, the addon will automatically load `.env` files.

### Option 2: Addon Preferences

You can still enter the API key in Blender's addon preferences:
- Go to **Edit > Preferences > Add-ons**
- Search for "Nano Banana Pro Render"
- Enter your API key in the preferences panel

This stores the key in Blender's `preferences.blend`, not in your project files.

### Option 3: Scene Properties (Not Recommended)

You can enter the API key directly in the panel, but **do not save** your blend file after entering it, as the key will be embedded in the file.

## Priority Order

The addon checks for your API key in this order:
1. **Environment variable** (`GEMINI_API_KEY`)
2. **Addon preferences** (stored in Blender)
3. **Scene properties** (the UI panel)

## Safety Guidelines

✅ **DO:**
- Store API keys in environment variables
- Use `.env` files locally (never commit them)
- Use addon preferences for one-off keys
- Rotate your API key periodically

❌ **DON'T:**
- Commit `.blend` files with API keys to Git
- Share your API key in messages or screenshots
- Store keys in unencrypted files in shared locations
- Leave API keys in scene properties when saving

## Getting Your API Key

1. Visit [Google AI Studio](https://aistudio.google.com/apikey)
2. Click "Create API Key"
3. Copy the key and use one of the setup methods above

For more info: https://ai.google.dev/tutorials/setup
