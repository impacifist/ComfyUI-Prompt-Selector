import importlib.util
import json
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location("prompt_selector", Path(__file__).parents[1] / "__init__.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class PromptSelectorTests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads(module.DEFAULT_LIBRARY)
        self.node = module.PromptSelector()

    def test_empty_library_outputs_empty_strings(self):
        self.assertEqual(self.node.select(module.DEFAULT_LIBRARY), ("", ""))

    def test_visible_draft_is_output_exactly(self):
        self.state["draft"] = {"name": "카메라 🎥", "text": "  {left|right}\n한글\n", "tags": ""}
        self.assertEqual(self.node.select(json.dumps(self.state)), ("  {left|right}\n한글\n", "카메라 🎥"))

    def test_edits_override_saved_text_without_mutating_it(self):
        self.state["entries"] = [{"id": "one", "name": "saved", "text": "old", "tags": "", "favorite": False}]
        self.state["selected_id"] = "one"
        self.state["draft"] = {"name": "saved", "text": "new", "tags": ""}
        raw = json.dumps(self.state)
        self.assertEqual(self.node.select(raw), ("new", "saved"))
        self.assertEqual(json.loads(raw)["entries"][0]["text"], "old")

    def test_bad_json_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "invalid library JSON"):
            self.node.select("{")

    def test_unsupported_versions_fail(self):
        for version in (2, True, "1"):
            with self.subTest(version=version):
                self.state["version"] = version
                with self.assertRaisesRegex(ValueError, "unsupported library version"):
                    self.node.select(json.dumps(self.state))

    def test_duplicate_ids_fail(self):
        entry = {"id": "one", "name": "n", "text": "t", "tags": "", "favorite": False}
        self.state["entries"] = [entry, entry]
        with self.assertRaisesRegex(ValueError, "duplicate prompt ID"):
            self.node.select(json.dumps(self.state))

    def test_missing_selection_fails(self):
        self.state["selected_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "selected prompt is missing"):
            self.node.select(json.dumps(self.state))

    def test_invalid_editor_type_fails(self):
        self.state["draft"]["text"] = ["not text"]
        with self.assertRaisesRegex(ValueError, "invalid editor contents"):
            self.node.select(json.dumps(self.state))

    def test_malformed_selection_has_actionable_error(self):
        for selection in ([], {}, 1, True):
            with self.subTest(selection=selection):
                self.state["selected_id"] = selection
                with self.assertRaisesRegex(ValueError, "selected prompt is missing"):
                    self.node.select(json.dumps(self.state))

    def test_dynamic_prompts_disabled_and_registration(self):
        self.assertFalse(self.node.INPUT_TYPES()["required"]["library_json"][1]["dynamicPrompts"])
        self.assertIs(module.NODE_CLASS_MAPPINGS["PromptSelector"], module.PromptSelector)
        self.assertEqual(module.NODE_DISPLAY_NAME_MAPPINGS["PromptSelector"], "Prompt Selector")


if __name__ == "__main__":
    unittest.main()
