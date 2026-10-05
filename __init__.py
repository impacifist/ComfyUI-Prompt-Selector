"""Workflow-local prompt library. No filesystem or network access at execution."""

import json

DEFAULT_LIBRARY = json.dumps({
    "version": 1,
    "entries": [],
    "selected_id": None,
    "draft": {"name": "", "text": "", "tags": ""},
    "deleted": None,
})


def read_library(library_json: str) -> dict:
    try:
        state = json.loads(library_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Prompt Selector: invalid library JSON.") from exc
    if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
        raise ValueError("Prompt Selector: unsupported library version.")
    entries = state.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Prompt Selector: entries must be a list.")
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) for key in ("id", "name", "text", "tags")
        ) or type(entry.get("favorite")) is not bool:
            raise ValueError("Prompt Selector: invalid prompt entry.")
        if not entry["id"] or entry["id"] in ids:
            raise ValueError("Prompt Selector: empty or duplicate prompt ID.")
        ids.add(entry["id"])
    selected_id = state.get("selected_id")
    if selected_id is not None and (not isinstance(selected_id, str) or selected_id not in ids):
        raise ValueError("Prompt Selector: selected prompt is missing.")
    draft = state.get("draft")
    if not isinstance(draft, dict) or not all(
        isinstance(draft.get(key), str) for key in ("name", "text", "tags")
    ):
        raise ValueError("Prompt Selector: invalid editor contents.")
    return state


class PromptSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"library_json": ("STRING", {
            "default": DEFAULT_LIBRARY,
            "multiline": False,
            "dynamicPrompts": False,
            "tooltip": "Prompt library stored inside this workflow.",
        })}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "name")
    FUNCTION = "select"
    CATEGORY = "Prompt Selector"
    DESCRIPTION = "Create, select and edit prompts directly in the workflow. Outputs the visible editor text."

    def select(self, library_json: str) -> tuple[str, str]:
        draft = read_library(library_json)["draft"]
        return draft["text"], draft["name"]


NODE_CLASS_MAPPINGS = {
    "PromptSelector": PromptSelector,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptSelector": "Prompt Selector",
}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
