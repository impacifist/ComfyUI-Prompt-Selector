"""Check editor sizing against an isolated ComfyUI on port 8198."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8198")
    parser.add_argument("--artifacts", required=True)
    args = parser.parse_args()
    if urlsplit(args.url).netloc != "127.0.0.1:8198":
        raise SystemExit("Use the isolated test server on port 8198 only.")
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for vue in (False, True):
                context = browser.new_context(viewport={"width": 1600, "height": 1600})
                context.route("**/*", lambda route: route.continue_()
                              if route.request.url.startswith(args.url + "/") else route.abort())
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(args.url, wait_until="domcontentloaded")
                page.wait_for_function(
                    "Boolean(window.app?.graph && window.LiteGraph?.registered_node_types?.PromptSelector)",
                    timeout=60000,
                )
                page.evaluate("""async vue => {
                    await app.ui.settings.setSettingValue('Comfy.VueNodes.Enabled', vue);
                    await app.loadGraphData({version: 0.4, nodes: [], links: [], groups: [], config: {}, extra: {}});
                    window.resizeNode = LiteGraph.createNode('PromptSelector');
                    resizeNode.pos = [70, 70];
                    app.graph.add(resizeNode);
                    app.canvas.ds.scale = 1;
                    app.canvas.ds.offset = [0, 0];
                    app.canvas.setDirty(true, true);
                }""", vue)
                root = page.locator(".prompt-selector")
                editor = root.locator("textarea")
                expect(editor).to_be_visible()
                editor.fill("Resize regression\n한글 draft")
                original = page.evaluate("resizeNode.widgets[0].value")
                sizes = []
                for width, height in ((600, 800), (600, 1250), (450, 800), (650, 1400)):
                    allocation = page.evaluate("""([width, height]) => {
                        resizeNode.setSize([width, height]);
                        app.canvas.setDirty(true, true);
                        const widget = resizeNode.widgets.find(w => w.name === 'prompt_selector_editor');
                        return {height: widget.computedHeight, bottom: widget.y + widget.computedHeight,
                            nodeHeight: resizeNode.size[1]};
                    }""", [width, height])
                    # Resizing must invalidate the old allocation before the next render.
                    assert abs(allocation["bottom"] - allocation["nodeHeight"]) < 2, allocation
                    page.wait_for_function("""() => {
                        const widget = resizeNode.widgets.find(w => w.name === 'prompt_selector_editor');
                        return Math.abs(widget.element.getBoundingClientRect().width - (resizeNode.size[0] - 20)) < 10;
                    }""")
                    if height >= 1250:
                        page.wait_for_function("document.querySelector('.prompt-selector textarea').clientHeight > 400")
                    sizes.append({"width": width, "height": height, "editor": editor.bounding_box()["height"]})
                workflow = page.evaluate("app.graph.serialize()")
                page.evaluate("""async workflow => {
                    await app.loadGraphData(workflow);
                    window.resizeNode = app.graph._nodes[0];
                }""", workflow)
                expect(editor).to_have_value("Resize regression\n한글 draft")
                page.wait_for_function("document.querySelector('.prompt-selector textarea').clientHeight > 400")
                for height in (800, 1300, 800, 1250):
                    page.evaluate("h => { resizeNode.setSize([600, h]); app.canvas.setDirty(true, true); }", height)
                page.wait_for_function("document.querySelector('.prompt-selector textarea').clientHeight > 400")
                assert page.evaluate("resizeNode.widgets[0].value") == original
                assert not errors, errors
                results.append({"vue": vue, "sizes": sizes, "reload_and_rapid_resize": "pass"})
                page.screenshot(path=str(artifacts / ("vue.png" if vue else "canvas.png")))
                context.close()
        finally:
            browser.close()
    (artifacts / "resize-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
