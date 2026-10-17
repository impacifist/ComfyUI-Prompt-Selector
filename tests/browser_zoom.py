"""Check DOM widget zoom in an isolated CPU-only ComfyUI session."""

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfy", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "test-artifacts/zoom"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prompt-selector-zoom-") as temporary:
        runtime = Path(temporary)
        plugin = runtime / "custom_nodes/ComfyUI-Prompt-Selector"
        shutil.copytree(root, plugin, ignore=shutil.ignore_patterns(
            ".git", "test-artifacts", "dist", "__pycache__", ".ruff_cache"))
        if args.baseline:
            original = subprocess.check_output(
                ["git", "show", "v1.1.0:web/prompt_selector.js"], cwd=root)
            (plugin / "web/prompt_selector.js").write_bytes(original)
        command = [str(args.python.resolve()), "main.py", "--cpu", "--listen", "127.0.0.1",
                   "--port", "8198", "--base-directory", str(runtime),
                   "--disable-all-custom-nodes", "--whitelist-custom-nodes",
                   "ComfyUI-Prompt-Selector", "--disable-api-nodes", "--disable-auto-launch"]
        try:
            with urlopen("http://127.0.0.1:8198/system_stats", timeout=1):
                raise RuntimeError("Port 8198 is already occupied; no existing server will be changed.")
        except OSError:
            pass
        with (artifacts / "server.log").open("wb") as log:
            process = subprocess.Popen(command, cwd=args.comfy, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError("Isolated server exited; see test-artifacts/zoom/server.log")
                    try:
                        with urlopen("http://127.0.0.1:8198/object_info/PromptSelector", timeout=1) as response:
                            assert "PromptSelector" in json.load(response)
                        break
                    except OSError:
                        time.sleep(.5)
                else:
                    raise TimeoutError("Isolated server did not become ready")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    try:
                        page = browser.new_page(viewport={"width": 1440, "height": 1080})
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.route("**/*", lambda route: route.continue_()
                                   if route.request.url.startswith("http://127.0.0.1:8198")
                                   else route.abort())
                        page.goto("http://127.0.0.1:8198")
                        page.wait_for_function("window.comfyAPI?.app?.app", timeout=60000)
                        page.evaluate("async () => { window.app = (await import('./scripts/app.js')).app; }")
                        page.wait_for_function("!!window.LiteGraph?.registered_node_types?.PromptSelector", timeout=60000)
                        expect(page.locator("#splash-loader")).not_to_be_visible(timeout=60000)
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1500)  # Let ComfyUI finish initial workflow restoration.
                        results = []
                        for vue in (False, True):
                            page.evaluate("async value => await app.ui.settings.setSettingValue('Comfy.VueNodes.Enabled', value)", vue)
                            page.evaluate("""async () => {
                              await app.loadGraphData({version: 0.4, nodes: [], links: [], groups: [], config: {}, extra: {}});
                              window.zoomNode = LiteGraph.createNode('PromptSelector');
                              zoomNode.pos = [100, 100]; app.graph.add(zoomNode);
                            }""")
                            editor = page.locator(".prompt-selector textarea")
                            page.evaluate("() => { app.canvas.ds.changeScale(1); app.canvas.ds.offset = [0,0]; app.canvas.setDirty(true,true); }")
                            expect(editor).to_be_visible()
                            editor.fill("Zoom regression: keep this unsaved draft.")
                            page.wait_for_timeout(500)
                            normal_width = editor.bounding_box()["width"]
                            before = page.evaluate("zoomNode.widgets.find(w => w.name === 'library_json').value")
                            for scale in (1, .4, .1, .05, .1, .4, 1):
                                page.evaluate("scale => { app.canvas.ds.changeScale(scale); app.canvas.ds.offset = [30, 20]; app.canvas.setDirty(true,true); }", scale)
                                page.wait_for_timeout(250)
                                visible = editor.is_visible()
                                diagnostic = page.evaluate("""() => ({
                                  scale: app.canvas.ds.scale, lowQuality: app.canvas.low_quality,
                                  minFont: app.canvas.min_font_size_for_lod,
                                  hideOnZoom: zoomNode.widgets.find(w => w.name === 'prompt_selector_editor').options.hideOnZoom
                                })""")
                                results.append({"vue": vue, "scale": scale, "visible": visible, "diagnostic": diagnostic})
                                if args.baseline and scale <= .1 and not vue:
                                    expect(editor).to_be_visible()
                                if not args.baseline:
                                    if scale <= .1 and not vue:
                                        expect(editor).not_to_be_visible()
                                    elif scale <= .1 and vue:
                                        # Vue owns its LOD and does not use Canvas hideOnZoom.
                                        # It must scale the editor, rather than leave a full-size overlay.
                                        box = editor.bounding_box()
                                        assert box is None or box["width"] < normal_width * .3, box
                                    elif scale == 1:
                                        expect(editor).to_be_visible()
                                assert page.evaluate("zoomNode.widgets.find(w => w.name === 'library_json').value") == before
                            expect(editor).to_have_value("Zoom regression: keep this unsaved draft.")
                            page.screenshot(path=str(artifacts / f"zoom-restored-{'vue' if vue else 'canvas'}.png"))
                        assert not errors, errors
                        report = {"baseline": args.baseline, "results": results, "page_errors": errors}
                        (artifacts / ("baseline.json" if args.baseline else "patched.json")).write_text(
                            json.dumps(report, indent=2), encoding="utf-8")
                        print(json.dumps(report))
                    finally:
                        browser.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
