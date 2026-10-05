# Public demo provenance

All images in `images/` are real UI captures from a separate local ComfyUI test instance on port 8198, using a fresh Playwright browser context and an empty graph. They do not show the user's working session. The capture script loads only `presets/starter-prompts.json`, a neutral public demonstration collection.

- `prompt-library.png`: the node editor with a saved camera prompt.
- `search-and-sort.png`: the same editor filtered by `camera`, with name sorting selected.
- `shared-workflow.png`: two nodes selecting different prompts from the same collection.

The example workflows contain only PromptSelector and ComfyUI's built-in PreviewAny nodes. They require no model downloads. The capture script checks the shared example's embedded entries against the bundled collection before writing it. It also submits the text-only graph and verifies successful execution.

To reproduce, install the node in a dedicated test ComfyUI instance on `http://127.0.0.1:8198`, install Playwright and Chromium in your development environment, then run `python tests/capture_demo.py`. This overwrites the public demo images and example workflows in this repository. The script rejects other server URLs and blocks browser requests outside that local server.

The UI was captured in Canvas mode. These images show actual behavior, not generated mockups. Private library exports, local test-server state, caches, and original working workflows are excluded from the share package.
