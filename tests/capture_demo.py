"""Capture public demo data only, on a dedicated local test server."""
import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8198')
    args = parser.parse_args()
    if args.url != 'http://127.0.0.1:8198':
        raise SystemExit('Use the isolated test server on port 8198 only.')
    root = Path(__file__).resolve().parents[1]
    images = root / 'docs' / 'images'
    examples = root / 'examples'
    images.mkdir(parents=True, exist_ok=True)
    examples.mkdir(parents=True, exist_ok=True)
    library = json.loads((root / 'presets' / 'starter-prompts.json').read_text(encoding='utf-8'))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1640, 'height': 1200}, device_scale_factor=1)
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(args.url) else route.abort())
        page = context.new_page()
        page.goto(args.url, wait_until='domcontentloaded')
        page.wait_for_function("Boolean(window.app?.graph && window.LiteGraph?.registered_node_types?.PromptSelector)")
        awaitable = "async () => await app.ui.settings.setSettingValue('Comfy.VueNodes.Enabled', false)"
        page.evaluate(awaitable)
        page.evaluate("""async (library) => {
            await app.loadGraphData({version: 0.4, nodes: [], links: [], groups: [], config: {}, extra: {}});
            const node = LiteGraph.createNode('PromptSelector');
            node.pos = [80, 170]; app.graph.add(node); node.setSize([540, 820]);
            node.properties.prompt_selector_sort = 'asc';
            const state = structuredClone(library);
            const entry = state.entries.find(e => e.id === 'camera-push');
            state.selected_id = entry.id;
            state.draft = {name: entry.name, text: entry.text, tags: entry.tags};
            node.widgets.find(w => w.name === 'library_json').value = JSON.stringify(state);
            node.onConfigure();
            window.demoNode = node;
            app.canvas.ds.scale = 1; app.canvas.ds.offset = [0, 0]; app.canvas.setDirty(true, true);
        }""", library)
        editor = page.locator('.prompt-selector').first
        expect(editor).to_be_visible()
        expect(editor.locator('textarea')).to_have_value(library['entries'][1]['text'])
        page.wait_for_timeout(350)
        editor.screenshot(path=str(images / 'prompt-library.png'))
        editor.get_by_label('프롬프트 검색', exact=True).fill('camera')
        expect(editor.get_by_label('저장된 프롬프트').locator('option')).to_have_count(2)
        editor.screenshot(path=str(images / 'search-and-sort.png'))
        editor.get_by_label('프롬프트 검색', exact=True).fill('')
        page.evaluate("""() => {
            const preview = LiteGraph.createNode('PreviewAny');
            preview.title = 'Preview · Camera prompt'; preview.pos = [760, 130];
            app.graph.add(preview); demoNode.connect(0, preview, 0);
            preview.setSize([550, 320]);
        }""")
        workflow = page.evaluate('app.graph.serialize()')
        (examples / 'basic-prompt-selector.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
        page.evaluate("""(library) => {
            demoNode.title = 'Prompt Selector · Camera'; demoNode.pos = [90, 180]; demoNode.setSize([480, 820]);
            const existingPreview = app.graph._nodes.find(n => n.type === 'PreviewAny');
            existingPreview.pos = [1700, 180]; existingPreview.setSize([460, 300]);
            const second = LiteGraph.createNode('PromptSelector');
            second.title = 'Prompt Selector · Lighting'; second.pos = [640, 180];
            app.graph.add(second); second.setSize([480, 820]);
            const state = structuredClone(library);
            const entry = state.entries.find(e => e.id === 'light-window');
            state.selected_id = entry.id;
            state.draft = {name: entry.name, text: entry.text, tags: entry.tags};
            second.widgets.find(w => w.name === 'library_json').value = JSON.stringify(state);
            second.onConfigure(); second.properties.prompt_selector_sort = 'asc'; second.onConfigure();
            const preview = LiteGraph.createNode('PreviewAny');
            preview.title = 'Preview · Lighting prompt'; preview.pos = [1700, 610];
            app.graph.add(preview); second.connect(0, preview, 0); preview.setSize([460, 260]);
            app.canvas.setDirty(true, true);
        }""", library)
        expect(page.locator('.prompt-selector')).to_have_count(2)
        prompt = page.evaluate('async () => (await app.graphToPrompt()).output')
        response = context.request.post(args.url+'/prompt', data={'prompt': prompt})
        assert response.ok, response.text()
        prompt_id = response.json()['prompt_id']
        deadline = time.monotonic()+15
        history = None
        while time.monotonic()<deadline:
            history = context.request.get(args.url+'/history/'+prompt_id).json().get(prompt_id)
            if history:
                break
            page.wait_for_timeout(100)
        assert history and history['status']['status_str']=='success'
        page.wait_for_timeout(350)
        page.evaluate('document.activeElement?.blur()')
        page.mouse.move(1500, 1100)
        boxes = [item.bounding_box() for item in page.locator('.prompt-selector').all()]
        left = min(box['x'] for box in boxes)-12
        top = min(box['y'] for box in boxes)-87
        right = max(box['x']+box['width'] for box in boxes)+12
        bottom = max(box['y']+box['height'] for box in boxes)+12
        page.screenshot(path=str(images / 'shared-workflow.png'), clip={'x':left, 'y':top, 'width':right-left, 'height':bottom-top})
        workflow = page.evaluate('app.graph.serialize()')
        for node in workflow['nodes']:
            assert node['type'] in ('PromptSelector','PreviewAny')
            if node['type']=='PromptSelector':
                state = json.loads(node['widgets_values'][0])
                assert state['entries']==library['entries'] and state['deleted'] is None
        (examples / 'shared-library.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Captured 3 screenshots and 2 example workflows using only bundled starter prompts.')
        browser.close()


if __name__=='__main__':
    main()
