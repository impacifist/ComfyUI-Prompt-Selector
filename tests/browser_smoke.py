"""Run only against an isolated ComfyUI with an empty test user directory."""

import argparse
import json
from pathlib import Path
import sys
import time

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8198")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--vue", action="store_true")
    args = parser.parse_args()
    if not args.url.startswith("http://127.0.0.1:8198"):
        raise SystemExit("Use the isolated test server on port 8198 only.")
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(args.url)
                      else route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(args.url, wait_until="domcontentloaded")
            page.wait_for_function("Boolean(window.app?.graph && window.LiteGraph?.registered_node_types?.PromptSelector)", timeout=60000)
            page.evaluate("async (enabled) => await app.ui.settings.setSettingValue('Comfy.VueNodes.Enabled', enabled)", args.vue)
            page.evaluate("""async () => {
                await app.loadGraphData({version: 0.4, nodes: [], links: [], groups: [], config: {}, extra: {}});
                const node = LiteGraph.createNode('PromptSelector');
                node.pos = [100, 70];
                app.graph.add(node);
                window.testNode = node;
                window.primaryNodeId = node.id;
                app.canvas.ds.scale = 1;
                app.canvas.ds.offset = [0, 0];
                app.canvas.setDirty(true, true);
            }""")
            root = page.locator(".prompt-selector").first
            expect(root).to_be_visible(timeout=15000)
            name = root.get_by_label("이름", exact=True)
            editor = root.locator("textarea")
            listing = root.get_by_label("저장된 프롬프트", exact=True)
            expect(root.get_by_role("button", name="수정", exact=True)).to_be_disabled()
            name.fill("고정 카메라 🎥")
            editor.fill("Keep the camera steady.\n{left|right} 한글")
            root.get_by_role("button", name="저장", exact=True).click()
            expect(listing.locator("option")).to_have_count(1)
            checks.append("create and save Unicode multiline prompt")
            editor.fill("Updated camera text.\n한글")
            root.get_by_role("button", name="수정 *", exact=True).click()
            expect(listing.locator("option")).to_have_count(1)
            root.get_by_role("button", name="☆ 즐겨찾기", exact=True).click()
            expect(listing.locator("option")).to_have_text(["★ 고정 카메라 🎥"])
            checks.append("update in place and favorite")
            root.get_by_role("button", name="복제", exact=True).click()
            expect(listing.locator("option")).to_have_count(2)
            checks.append("duplicate with unique name")
            editor.fill("Unsaved draft survives workflow reopen.")
            page.once("dialog", lambda dialog: dialog.dismiss())
            listing.select_option(index=0)
            expect(editor).to_have_value("Unsaved draft survives workflow reopen.")
            checks.append("cancel switching preserves draft")
            workflow = page.evaluate("app.graph.serialize()")
            (artifacts / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
            prompt = page.evaluate("async () => (await app.graphToPrompt()).output")
            inputs = next(value["inputs"] for value in prompt.values() if value["class_type"] == "PromptSelector")
            assert list(inputs) == ["library_json"], inputs.keys()
            assert json.loads(inputs["library_json"])["draft"]["text"] == "Unsaved draft survives workflow reopen."
            (artifacts / "api-input.json").write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
            checks.append("API serializes only the backend STRING widget")
            source_id = next(key for key, value in prompt.items() if value["class_type"] == "PromptSelector")
            prompt["9001"] = {"class_type": "PreviewAny", "inputs": {"source": [source_id, 0]}}
            prompt["9002"] = {"class_type": "PreviewAny", "inputs": {"source": [source_id, 1]}}
            response = context.request.post(args.url + "/prompt", data={"prompt": prompt})
            assert response.ok, response.text()
            prompt_id = response.json()["prompt_id"]
            history = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                history = context.request.get(args.url + "/history/" + prompt_id).json().get(prompt_id)
                if history:
                    break
                page.wait_for_timeout(100)
            assert history, "PreviewAny execution did not complete within 15 seconds"
            assert history["status"]["status_str"] == "success", history["status"]
            assert history["outputs"]["9001"]["text"] == ["Unsaved draft survives workflow reopen."]
            assert history["outputs"]["9002"]["text"] == ["고정 카메라 🎥 복사"]
            checks.append("ComfyUI execution delivers exact prompt and name to PreviewAny")
            page.evaluate("async (workflow) => { await app.loadGraphData(workflow); window.testNode = app.graph._nodes[0]; }", workflow)
            expect(editor).to_have_value("Unsaved draft survives workflow reopen.")
            expect(listing.locator("option")).to_have_count(2)
            checks.append("real workflow serialize and reload preserves library and draft")
            page.once("dialog", lambda dialog: dialog.dismiss())
            root.get_by_role("button", name="삭제", exact=True).click()
            expect(listing.locator("option")).to_have_count(2)
            page.once("dialog", lambda dialog: dialog.accept())
            root.get_by_role("button", name="삭제", exact=True).click()
            expect(listing.locator("option")).to_have_count(1)
            page.mouse.click(1150, 800)
            page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Undo')")
            expect(listing.locator("option")).to_have_count(2)
            page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Redo')")
            expect(listing.locator("option")).to_have_count(1)
            page.evaluate("window.testNode = app.graph._nodes[0]")
            checks.append("ComfyUI undo and redo restore library state")
            root.get_by_role("button", name="삭제 복구", exact=True).click()
            expect(listing.locator("option")).to_have_count(2)
            checks.append("delete cancel, delete confirm and restore")
            listing.select_option(index=0)
            root.get_by_label("프롬프트 검색").fill("missing")
            expect(listing.locator("option")).to_have_count(0)
            expect(editor).to_have_value("Updated camera text.\n한글")
            root.get_by_label("프롬프트 검색").fill("")
            checks.append("search filtering does not change output")
            snapshot = page.evaluate("testNode.widgets[0].value")
            root.locator('input[type="file"]').set_input_files({"name": "invalid.json", "mimeType": "application/json", "buffer": b'{"version":999}'})
            expect(root.locator(".ps-status")).to_contain_text("가져오기 실패")
            assert page.evaluate("testNode.widgets[0].value") == snapshot
            checks.append("invalid import leaves state untouched")
            root.locator('input[type="file"]').set_input_files({"name": "valid.json", "mimeType": "application/json", "buffer": snapshot.encode("utf-8")})
            expect(listing.locator("option")).to_have_count(4)
            expect(editor).to_have_value("Updated camera text.\n한글")
            checks.append("import merges without overwriting current draft")
            with page.expect_download() as download:
                root.get_by_role("button", name="JSON 내보내기", exact=True).click()
            download.value.save_as(artifacts / "export.json")
            exported = json.loads((artifacts / "export.json").read_text(encoding="utf-8"))
            assert len(exported["entries"]) == 4
            checks.append("JSON export")
            page.evaluate("""() => {
                const clone = testNode.clone(); clone.pos = [650, 70]; app.graph.add(clone);
                window.testClone = clone;
            }""")
            clone_root = page.locator(".prompt-selector").nth(1)
            expect(clone_root.locator("textarea")).to_have_value("Updated camera text.\n한글")
            clone_root.locator("textarea").fill("Independent clone")
            expect(editor).to_have_value("Updated camera text.\n한글")
            checks.append("clone draft stays local until saved")
            clone_root.get_by_role("button", name="수정 *", exact=True).click()
            expect(editor).to_have_value("Independent clone")
            checks.append("saving a clone updates the other clean selected editor")
            editor.fill("Keep this unsaved draft")
            clone_root.locator("textarea").fill("Second shared update")
            clone_root.get_by_role("button", name="수정 *", exact=True).click()
            expect(editor).to_have_value("Keep this unsaved draft")
            assert page.evaluate("JSON.parse(testNode.widgets[0].value).entries.find(e => e.id === JSON.parse(testClone.widgets[0].value).selected_id).text") == "Second shared update"
            checks.append("saved list updates while another node's draft is preserved")
            page.evaluate("""() => {
                const node = LiteGraph.createNode('PromptSelector');
                node.pos = [1100, 70]; app.graph.add(node); window.testNew = node;
            }""")
            page.wait_for_function("JSON.parse(testNew.widgets[0].value).entries.length === 4")
            assert page.evaluate("JSON.parse(testNew.widgets[0].value).draft.text") == ""
            checks.append("new same-type node receives shared library with its own empty editor")
            page.once("dialog", lambda dialog: dialog.accept())
            clone_root.get_by_role("button", name="삭제", exact=True).click()
            expect(listing.locator("option")).to_have_count(3)
            expect(editor).to_have_value("Keep this unsaved draft")
            assert page.evaluate("JSON.parse(testNode.widgets[0].value).selected_id") is None
            page.mouse.click(1000, 900)
            page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Undo')")
            page.wait_for_function("app.graph._nodes.filter(n => n.comfyClass === 'PromptSelector').every(n => JSON.parse(n.widgets[0].value).entries.length === 4)")
            expect(editor).to_have_value("Keep this unsaved draft")
            page.evaluate("async () => await app.extensionManager.command.execute('Comfy.Redo')")
            page.wait_for_function("app.graph._nodes.filter(n => n.comfyClass === 'PromptSelector').every(n => JSON.parse(n.widgets[0].value).entries.length === 3)")
            checks.append("undo and redo update every peer library together")
            clone_root.get_by_role("button", name="삭제 복구", exact=True).click()
            expect(listing.locator("option")).to_have_count(4)
            checks.append("shared deletion and restore preserve peer drafts and valid selection")
            shared_workflow = page.evaluate("app.graph.serialize()")
            page.evaluate("async w => await app.loadGraphData(w)", shared_workflow)
            expect(editor).to_have_value("Keep this unsaved draft")
            expect(listing.locator("option")).to_have_count(4)
            checks.append("shared library and independent drafts survive workflow reload")
            legacy = json.loads(json.dumps(shared_workflow))
            state = json.loads(legacy["nodes"][1]["widgets_values"][0])
            state["entries"][0]["text"] = "Legacy conflicting saved content"
            legacy["nodes"][1]["widgets_values"][0] = json.dumps(state)
            page.evaluate("async w => await app.loadGraphData(w)", legacy)
            page.wait_for_function("app.graph._nodes.every(n => JSON.parse(n.widgets[0].value).entries.length === 5)")
            assert page.evaluate("JSON.parse(app.graph._nodes[0].widgets[0].value).entries.some(e => e.text === 'Legacy conflicting saved content')")
            expect(editor).to_have_value("Keep this unsaved draft")
            checks.append("legacy conflicting saved copies merge without losing drafts or entries")
            page.once("dialog", lambda dialog: dialog.accept())
            listing.select_option(index=0)
            before_add = page.evaluate("JSON.parse(app.graph.getNodeById(primaryNodeId).widgets[0].value)")
            editor.fill("Added without clearing or pressing new")
            root.get_by_role("button", name="저장", exact=True).click()
            expect(listing.locator("option")).to_have_count(6)
            after_add = page.evaluate("JSON.parse(app.graph.getNodeById(primaryNodeId).widgets[0].value)")
            assert after_add["entries"][:5] == before_add["entries"]
            assert after_add["selected_id"] != before_add["selected_id"]
            assert after_add["draft"]["text"] == "Added without clearing or pressing new"
            expect(clone_root.get_by_label("저장된 프롬프트").locator("option")).to_have_count(6)
            checks.append("save from a selected entry appends and shares a new uniquely named entry")
            editor.fill("Updated through the new update button")
            root.get_by_role("button", name="수정 *", exact=True).click()
            after_update = page.evaluate("JSON.parse(app.graph.getNodeById(primaryNodeId).widgets[0].value)")
            assert after_update["selected_id"] == after_add["selected_id"]
            assert len(after_update["entries"]) == 6
            assert after_update["entries"][-1]["text"] == "Updated through the new update button"
            checks.append("update changes the selected entry without adding one")
            for entry_name in ["Zulu", "apple", "banana", "하늘", "가방"]:
                name.fill(entry_name)
                editor.fill("Sorting example")
                root.get_by_role("button", name="저장", exact=True).click()
            editor.fill("Unsaved while sorting")
            before_sort = page.evaluate("app.graph.getNodeById(primaryNodeId).widgets[0].value")
            order = root.get_by_label("목록 정렬", exact=True)
            order.select_option("asc")
            ascending = listing.locator("option").all_text_contents()
            assert [x for x in ascending if x in ["Zulu", "apple", "banana"]] == ["apple", "banana", "Zulu"]
            assert [x for x in ascending if x in ["하늘", "가방"]] == ["가방", "하늘"]
            expect(editor).to_have_value("Unsaved while sorting")
            assert page.evaluate("app.graph.getNodeById(primaryNodeId).widgets[0].value") == before_sort
            expect(clone_root.get_by_label("목록 정렬", exact=True)).to_have_value("insertion")
            order.select_option("desc")
            assert listing.locator("option").all_text_contents() == list(reversed(ascending))
            root.get_by_label("프롬프트 검색").fill("Zulu")
            expect(listing.locator("option")).to_have_text(["Zulu"])
            expect(editor).to_have_value("Unsaved while sorting")
            root.get_by_label("프롬프트 검색").fill("")
            checks.append("English and Korean sorting preserves draft selection registration order and peer preferences")
            sorted_workflow = page.evaluate("app.graph.serialize()")
            page.evaluate("async w => await app.loadGraphData(w)", sorted_workflow)
            # Clicking nodes changes graph/DOM order; identify the original editor by its node ID.
            page.evaluate("app.graph.getNodeById(primaryNodeId).widgets.find(w => w.name === 'prompt_selector_editor').element.dataset.testPrimary = 'true'")
            root = page.locator('.prompt-selector[data-test-primary="true"]')
            editor = root.locator("textarea")
            listing = root.get_by_label("저장된 프롬프트", exact=True)
            order = root.get_by_label("목록 정렬", exact=True)
            expect(order).to_have_value("desc")
            expect(editor).to_have_value("Unsaved while sorting")
            order.select_option("insertion")
            expected_names = [("★ " if e["favorite"] else "") + e["name"] for e in json.loads(before_sort)["entries"]]
            expect(listing.locator("option")).to_have_text(expected_names)
            checks.append("sort preference survives workflow reopen and registration order remains available")
            editor.press("Control+s")
            expect(listing.locator("option")).to_have_count(12)
            checks.append("Ctrl+S adds a new entry like the save button")
            page.screenshot(path=str(artifacts / "prompt-selector.png"), full_page=True)
            assert not errors, errors
            (artifacts / "browser-results.json").write_text(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
            sys.stdout.write(json.dumps({"passed": len(checks), "vue": args.vue, "checks": checks}, ensure_ascii=False) + "\n")
        except Exception:
            page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
            sys.stdout.write(json.dumps({"completed": checks, "page_errors": errors, "url": page.url,
                                        "status": page.locator(".ps-status").all_text_contents(),
                                        "diagnostic": page.evaluate("""() => ({focus: document.activeElement?.tagName,
                                            counts: app.graph._nodes.filter(n => n.comfyClass === 'PromptSelector').map(n =>
                                                JSON.parse(n.widgets.find(w => w.name === 'library_json').value).entries.length)})""")}, ensure_ascii=False) + "\n")
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
