"""Exercise pane handles in a real browser against an isolated ComfyUI only."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def drag(page, handle, delta):
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + delta, steps=12)
    page.mouse.up()


def height(locator):
    return locator.evaluate("element => element.offsetHeight")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8198")
    parser.add_argument("--artifacts", required=True)
    args = parser.parse_args()
    if urlsplit(args.url).netloc != "127.0.0.1:8198":
        raise SystemExit("Use the isolated test server on port 8198 only.")
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parents[1] / "web"
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for vue in (False, True):
                context = browser.new_context(viewport={"width": 1800, "height": 1800})
                context.route("**/*", lambda route: route.continue_()
                              if urlsplit(route.request.url).netloc == "127.0.0.1:8198" else route.abort())
                # Preview the candidate files without replacing the active installation.
                context.route("**/extensions/ComfyUI-Prompt-Selector/*", lambda route: route.fulfill(
                    path=str(source / Path(urlsplit(route.request.url).path).name),
                    content_type="text/css; charset=utf-8" if route.request.url.endswith(".css")
                    else "application/javascript; charset=utf-8"))
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
                    window.paneNode = LiteGraph.createNode('PromptSelector');
                    paneNode.pos = [40, 40];
                    app.graph.add(paneNode);
                    paneNode.setSize([600, 1150]);
                    const storage = paneNode.widgets.find(w => w.name === 'library_json');
                    const state = JSON.parse(storage.value);
                    state.entries = Array.from({length: 30}, (_, i) => ({id: `demo-${i}`,
                        name: `Camera direction ${i + 1}`, tags: 'demo', text: `Camera ${i + 1}`, favorite: false}));
                    state.selected_id = 'demo-0';
                    state.draft = {name: 'Camera direction 1', tags: 'demo', text: 'Unsaved draft\\n한글 유지'};
                    storage.value = JSON.stringify(state);
                    paneNode.onConfigure({});
                    paneNode.widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'true';
                    app.canvas.ds.scale = 1;
                    app.canvas.ds.offset = [0, 0];
                    app.canvas.setDirty(true, true);
                }""", vue)
                root = page.locator('.prompt-selector[data-test-primary="true"]')
                listing = root.locator(".ps-list")
                editor = root.locator(".ps-editor-label")
                list_handle = root.get_by_role("separator", name="목록 높이 조절")
                editor_handle = root.get_by_role("separator", name="입력창 높이 조절")
                expect(list_handle).to_be_visible()
                expect(root.locator(".ps-list option")).to_have_count(30)
                original = page.evaluate("paneNode.widgets[0].value")
                position = page.evaluate("[...paneNode.pos]")
                checks = []

                before = height(listing)
                drag(page, list_handle, 180)
                assert abs(height(listing) - before - 180) <= 2
                checks.append("list grows with a real mouse drag")
                before = height(editor)
                drag(page, editor_handle, 120)
                assert abs(height(editor) - before - 120) <= 2
                list_height = height(listing)
                drag(page, editor_handle, -80)
                assert abs(height(editor) - before - 40) <= 2
                assert height(listing) == list_height
                editor_height = height(editor)
                drag(page, list_handle, -100)
                assert abs(height(listing) - list_height + 100) <= 2
                assert height(editor) == editor_height
                checks.append("both panes shrink and resize independently")

                for scale in (0.5, 1.25):
                    page.evaluate("scale => { app.canvas.ds.scale = scale; app.canvas.setDirty(true, true); }", scale)
                    page.wait_for_function("""scale => {
                        const list = document.querySelector('[data-test-primary] .ps-list');
                        return Math.abs(list.getBoundingClientRect().height / list.offsetHeight - scale) < .01;
                    }""", arg=scale)
                    before = height(listing)
                    drag(page, list_handle, 60 * scale)
                    assert abs(height(listing) - before - 60) <= 2
                    before = height(editor)
                    drag(page, editor_handle, -20 * scale)
                    assert abs(height(editor) - before + 20) <= 2
                checks.append("drag distance follows canvas zoom at 50% and 125%")
                page.evaluate("() => { app.canvas.ds.scale = 1; app.canvas.setDirty(true, true); }")
                page.wait_for_function("""() => {
                    const list = document.querySelector('[data-test-primary] .ps-list');
                    return Math.abs(list.getBoundingClientRect().height / list.offsetHeight - 1) < .01;
                }""")

                before = height(listing)
                list_handle.press("ArrowDown")
                assert height(listing) == before + 20
                list_handle.press("ArrowUp")
                assert height(listing) == before
                checks.append("keyboard resizing")
                before = height(editor)
                drag(page, editor_handle, 60)
                page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Undo')")
                page.evaluate("""() => {
                    window.paneNode = app.graph._nodes[0];
                    paneNode.widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'true';
                }""")
                page.wait_for_function("""expected => {
                    return document.querySelector('[data-test-primary] .ps-editor-label')?.offsetHeight === expected;
                }""", arg=before)
                page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Redo')")
                page.evaluate("""() => {
                    window.paneNode = app.graph._nodes[0];
                    paneNode.widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'true';
                }""")
                page.wait_for_function("""expected => {
                    return document.querySelector('[data-test-primary] .ps-editor-label')?.offsetHeight === expected;
                }""", arg=before + 60)
                page.evaluate("window.paneNode = app.graph._nodes[0]")
                checks.append("undo and redo restore pane sizes")

                sizes = [height(listing), height(editor)]
                workflow = page.evaluate("app.graph.serialize()")
                page.evaluate("""async workflow => {
                    await app.loadGraphData(workflow);
                    window.paneNode = app.graph._nodes[0];
                    paneNode.widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'true';
                }""", workflow)
                expect(root.locator("textarea")).to_have_value("Unsaved draft\n한글 유지")
                assert [height(listing), height(editor)] == sizes
                assert page.evaluate("paneNode.widgets[0].value") == original
                assert page.evaluate("[...paneNode.pos]") == position
                checks.append("workflow reload preserves sizes, selection, draft and node position")

                page.evaluate("""() => {
                    const clone = paneNode.clone();
                    clone.pos = [800, 40];
                    app.graph.add(clone);
                    window.paneClone = clone;
                    clone.widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'false';
                }""")
                clone_root = page.locator('.prompt-selector[data-test-primary="false"]')
                expect(clone_root.get_by_role("separator", name="목록 높이 조절")).to_be_visible()
                drag(page, clone_root.get_by_role("separator", name="목록 높이 조절"), 60)
                assert height(listing) == sizes[0]
                assert height(clone_root.locator(".ps-list")) == sizes[0] + 60
                checks.append("cloned nodes keep independent pane preferences")

                drag(page, list_handle, 100)
                list_handle.dblclick()
                assert height(listing) == 100
                editor_handle.press("Home")
                assert page.evaluate("paneNode.properties.prompt_selector_editor_height") is None
                for _ in range(5):
                    list_handle.press("ArrowUp")
                assert height(listing) == 80
                for _ in range(40):
                    editor_handle.press("ArrowUp")
                assert height(editor) == 125
                checks.append("default reset and minimum heights")

                list_handle.press("ArrowDown")
                before = height(listing)
                box = list_handle.bounding_box()
                x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x, y + 50, steps=5)
                list_handle.evaluate("e => e.dispatchEvent(new PointerEvent('pointercancel', {pointerId: 1, bubbles: true}))")
                page.mouse.up()
                assert height(listing) == before
                assert page.evaluate("paneNode.widgets[0].value") == original
                checks.append("cancelled pointer gesture restores the previous size")

                node_height = page.evaluate("paneNode.size[1]")
                drag(page, list_handle, 700)
                root.get_by_role("button", name="수정 *", exact=True).scroll_into_view_if_needed()
                expect(root.get_by_role("button", name="수정 *", exact=True)).to_be_in_viewport()
                assert (root.evaluate("e => e.scrollHeight > e.clientHeight")
                        or page.evaluate("paneNode.size[1]") > node_height)
                assert page.evaluate("paneNode.widgets[0].value") == original
                checks.append("large panes keep action buttons reachable by scrolling or automatic node growth")
                list_handle.press("Home")
                drag(page, list_handle, 200)
                page.screenshot(path=str(artifacts / ("vue-panes.png" if vue else "canvas-panes.png")))
                assert not errors, errors
                results.append({"vue": vue, "checks": checks, "page_errors": errors})
                context.close()
        finally:
            browser.close()
    (artifacts / "pane-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
