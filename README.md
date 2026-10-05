# ComfyUI Prompt Selector

A reusable prompt library inside a ComfyUI node. Save variations, update existing prompts, search and sort your collection, and share the saved list between nodes in the same workflow.

[한국어 사용 설명](README.ko.md)

![Prompt Selector with public demo prompts](docs/images/prompt-library.png)

Screenshots use a separate test session and the bundled public examples. The current node interface is in Korean.

## Features

- **Save adds; Update edits.** Save a variation directly without first creating an empty prompt. Duplicate names receive a numeric suffix.
- Search names, tags, and prompt text; filter favorites.
- Sort by insertion order, name ascending (A–Z / 가–하), or descending.
- Share saved entries between Prompt Selector nodes in the **same workflow**, while each node keeps its own selection and unsaved edits.
- Duplicate, delete, and restore the last deleted entry.
- Export/import JSON libraries and copy prompt text.
- Output the current editor text and name as `STRING` values. No model, API account, or additional Python dependency is required.

## Install

Download this repository as a ZIP and extract its contents into:

```text
ComfyUI/custom_nodes/ComfyUI-Prompt-Selector/
├── __init__.py
└── web/
```

Restart ComfyUI and reload the browser. Add **Prompt Selector → Prompt Selector** from the node menu. See the [official custom-node installation guide](https://docs.comfy.org/installation/install_custom_node) for your ComfyUI installation layout.

## Quick start

1. Add a Prompt Selector node and type a name, optional comma-separated tags, and prompt text.
2. Click **저장 (Save)** to add a new entry. Select an existing entry and click **수정 (Update)** to replace it.
3. Connect `prompt` to a compatible string input. For example, convert the text widget of CLIP Text Encode to an input and connect it. The `name` output provides the editor name.
4. Save the ComfyUI workflow to retain the library.

Load [the basic example workflow](examples/basic-prompt-selector.json) to inspect the output with ComfyUI's built-in PreviewAny node. It runs without a generation model. Import [starter-prompts.json](presets/starter-prompts.json) through **JSON 가져오기** to add the demonstration collection to another workflow.

| UI label | Behavior |
| --- | --- |
| 저장 | Add current editor contents as a new entry |
| 수정 | Replace the selected saved entry |
| 새 프롬프트 | Clear the editor to start a blank draft |
| 복제 | Duplicate the current prompt |
| 목록 정렬 | Change list display order |
| 즐겨찾기 / ★ | Toggle an entry favorite / filter favorites |
| 삭제 / 삭제 복구 | Delete an entry / restore the last deletion |
| JSON 내보내기 / JSON 가져오기 | Export the library / append imported entries |
| 텍스트 복사 | Copy current prompt text |

Ctrl/Cmd+S inside the editor performs **Save**, adding an entry. Use **Update** to edit an existing entry. Save the workflow through ComfyUI separately.

## Use it effectively

Keep reusable camera, lighting, style, or negative prompts under descriptive names and tags. Save a new variation when comparing results; update an entry when correcting the original. Two selectors can use the same saved collection while choosing different prompts for different branches.

![Two selectors sharing a library with independent selections](docs/images/shared-workflow.png)

Try [the shared-library workflow](examples/shared-library.json). Sharing is local to one workflow graph; separate workflows, browser tabs, and users do not automatically synchronize. Transfer collections with JSON export/import. Import appends entries rather than replacing the library.

## Storage and output details

- **Current editor contents are the output**, including unsaved changes. Selecting a saved entry fills the editor.
- The library is embedded in workflow JSON. Saved library edits synchronize across nodes; each node retains its own selection and unsaved draft.
- Sorting changes the displayed order and is saved per node in the workflow.
- Workflow files and JSON exports can contain the entire library, drafts, and the last deleted entry. Review their contents before sharing; a generated file that embeds workflow metadata can carry this information too.
- The node passes text through unchanged. It does not generate prompts, expand wildcards, combine separate nodes' strings, or guarantee a particular generation model's syntax.

## Development

The runtime uses ComfyUI and browser APIs only. Run standalone checks with Python and Node.js:

```sh
python -m unittest discover -s tests -p "test_*.py"
node --test tests/library.test.js
node --check web/prompt_selector.js
```

Browser verification requires Playwright and a separate local ComfyUI test instance. See [screenshot provenance](docs/SCREENSHOTS.md).

## License

Released under the [MIT License](LICENSE). Copyright (c) 2026 ComfyUI Prompt Selector contributors.
