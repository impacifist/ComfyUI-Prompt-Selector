# v1.1.1 — Low-zoom editor compatibility

In Canvas node mode, Prompt Selector now uses ComfyUI's native low-zoom placeholder instead of forcing its HTML editor to stay visible at every zoom level. This reduces HTML overlays when viewing a large workflow. Zooming back in restores the editor without changing the library, selected prompt or unsaved draft. Vue node mode retains its own editor scaling behavior.

- Uses the supported `hideOnZoom` DOM-widget option; no ComfyUI core patches or custom transform hooks.
- Keeps independent list/editor resize handles and workflow-shared libraries.
- Adds an isolated browser regression check for Canvas low-zoom hiding, Vue editor scaling and draft preservation across zoom-out/zoom-in cycles.

This addresses Prompt Selector's low-zoom behavior. It does not claim to fix all ComfyUI canvas rendering issues or other extensions.

Validated on ComfyUI frontend 1.55.17: 10 Python tests, 18 JavaScript tests, JavaScript syntax and Ruff checks passed. An isolated CPU-only ComfyUI session compared v1.1.0 with the updated widget: at 10% zoom the old Canvas editor remained visible, while the updated editor hid and returned at 100% with its unsaved draft unchanged. Vue scaling and draft retention also passed. No models or paid APIs were used.

Reproduce the browser check with Playwright installed:

```sh
python tests/browser_zoom.py --comfy /path/to/ComfyUI --python /path/to/comfy-python
```

The script refuses to use port 8198 if occupied and starts only its own temporary CPU-only server. Add `--baseline` to check the v1.1.0 frontend from the repository tag.

Update the node pack and hard-refresh the browser with Ctrl+F5. Restart ComfyUI if you also changed installed node packs.
