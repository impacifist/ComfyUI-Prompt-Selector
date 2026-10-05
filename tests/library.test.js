import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { emptyState, parseState, isDirty, saveDraft, mergeLibrary, filterEntries,
    applySharedLibrary, joinLibraries, addDraft, sortEntries } from "../web/library.js";

function saved(id = "a", name = "First") {
    const state = emptyState();
    state.draft = { name, text: "원본\n{left|right} 🎥", tags: "카메라, wide" };
    return saveDraft(state, id);
}

test("save then update keeps identity and favorite", () => {
    const state = saved();
    state.entries[0].favorite = true;
    state.draft.text = "edited";
    assert.equal(isDirty(state), true);
    const updated = saveDraft(state, "unused");
    assert.equal(updated.entries.length, 1);
    assert.equal(updated.entries[0].id, "a");
    assert.equal(updated.entries[0].text, "edited");
    assert.equal(updated.entries[0].favorite, true);
    assert.equal(isDirty(updated), false);
    assert.notEqual(state.entries[0].text, "edited");
});

test("add always creates a new entry, numbers duplicate names and preserves the original", () => {
    const state = saved();
    state.entries[0].favorite = true;
    state.draft = { name: " first ", text: "new content", tags: "new tag" };
    const added = addDraft(state, "b");
    assert.equal(added.entries.length, 2);
    assert.equal(added.selected_id, "b");
    assert.equal(added.entries[1].name, "first (2)");
    assert.equal(added.entries[1].text, "new content");
    assert.equal(added.entries[1].favorite, false);
    assert.deepEqual(added.entries[0], state.entries[0]);
    assert.equal(state.draft.name, " first ");
    assert.throws(() => addDraft(emptyState(), "c"), /이름을 입력/);
});

test("update rejects another saved name without changing either entry", () => {
    const state = addDraft(saved(), "b");
    state.draft.name = "First";
    const before = JSON.stringify(state);
    assert.throws(() => saveDraft(state, "unused"), /같은 이름/);
    assert.equal(JSON.stringify(state), before);
});

test("English and Korean names sort naturally without changing registration order or state", () => {
    const names = ["Zulu", "banana10", "하늘", "apple", "나무", "banana2", "가방"];
    const entries = names.map((name, index) => ({ id: String(index), name }));
    const ascending = sortEntries(entries, "asc").map(entry => entry.name);
    assert.deepEqual(ascending.filter(name => /^[a-z]/i.test(name)), ["apple", "banana2", "banana10", "Zulu"]);
    assert.deepEqual(ascending.filter(name => /^[가-힣]/.test(name)), ["가방", "나무", "하늘"]);
    assert.deepEqual(sortEntries(entries, "desc").map(entry => entry.name), [...ascending].reverse());
    assert.deepEqual(sortEntries(entries, "insertion").map(entry => entry.name), names);
    assert.deepEqual(entries.map(entry => entry.name), names);
});

test("workflow round trip preserves Unicode, draft, selection and deletion", () => {
    const state = saved();
    state.draft.text += " unsaved";
    state.deleted = { ...state.entries[0], id: "deleted" };
    assert.deepEqual(parseState(JSON.stringify(state)), state);
});

test("serialized copies do not alias entries and drafts", () => {
    const original = saved();
    const clone = parseState(JSON.stringify(original));
    clone.entries[0].text = "changed";
    clone.draft.name = "changed";
    assert.notEqual(original.entries[0].text, clone.entries[0].text);
    assert.notEqual(original.draft.name, clone.draft.name);
});

test("shared updates refresh clean selections but preserve other selections and dirty drafts", () => {
    const local = saved();
    const changed = { ...local.entries[0], text: "saved elsewhere" };
    const entries = [changed, { ...changed, id: "b", name: "Second" }];
    const clean = applySharedLibrary(local, entries, null);
    assert.equal(clean.selected_id, "a");
    assert.equal(clean.draft.text, "saved elsewhere");
    local.draft.text = "typing here";
    const dirty = applySharedLibrary(local, entries, null);
    assert.equal(dirty.selected_id, "a");
    assert.equal(dirty.draft.text, "typing here");
    const blank = applySharedLibrary(emptyState(), entries, null);
    assert.equal(blank.selected_id, null);
    assert.equal(blank.draft.text, "");
});

test("remote deletion preserves editor text and permits saving it as a new entry", () => {
    const local = saved();
    const deleted = applySharedLibrary(local, [], local.entries[0]);
    assert.equal(deleted.selected_id, null);
    assert.deepEqual(deleted.draft, local.draft);
    assert.deepEqual(parseState(JSON.stringify(deleted)), deleted);
    assert.equal(saveDraft(deleted, "new").entries[0].text, local.draft.text);
});

test("legacy join preserves conflicting IDs, unique names, selection and unsaved drafts", () => {
    const first = saved();
    const second = saved();
    second.entries[0].text = "different saved version";
    second.draft.text = "unsaved local version";
    const third = saved("c");
    let counter = 0;
    const joined = joinLibraries([first, second, third, emptyState()], () => `new-${++counter}`);
    assert.equal(joined[0].entries.length, 3);
    assert.equal(joined[1].selected_id, "new-1");
    assert.equal(joined[1].draft.text, "unsaved local version");
    assert.equal(joined[2].draft.name, "First (3)");
    assert.deepEqual(joined[3].draft, emptyState().draft);
    for (const state of joined) parseState(JSON.stringify(state));
    assert.deepEqual(joinLibraries(joined, () => { throw new Error("unexpected duplication"); }), joined);
});

test("identical clone libraries join once and deleted IDs never collide with live entries", () => {
    const first = saved();
    const second = emptyState();
    second.deleted = first.entries[0];
    const joined = joinLibraries([first, first, second], () => "unused");
    assert.equal(joined[0].entries.length, 1);
    assert.equal(joined[2].deleted, null);
    assert.equal(joined[2].selected_id, null);
});

test("joining preserves a different deleted copy with the same legacy ID", () => {
    const first = saved();
    const second = emptyState();
    second.deleted = { ...first.entries[0], text: "only remaining deleted copy" };
    const joined = joinLibraries([first, second], () => "recovered");
    assert.equal(joined[1].deleted.id, "recovered");
    assert.equal(joined[1].deleted.text, "only remaining deleted copy");
    parseState(JSON.stringify(joined[1]));
});

test("empty and duplicate names rejected before mutation", () => {
    const state = saved();
    const snapshot = JSON.stringify(state);
    assert.throws(() => saveDraft(state, "b", true), /같은 이름/);
    assert.equal(JSON.stringify(state), snapshot);
    state.draft.name = "   ";
    assert.throws(() => saveDraft(state, "b"), /이름을 입력/);
});

test("import merges with fresh IDs and unique names without changing editor", () => {
    const state = saved();
    state.draft.text = "unsaved local draft";
    const incoming = saved();
    const merged = mergeLibrary(state, incoming, () => "new-id");
    assert.equal(merged.entries.length, 2);
    assert.equal(merged.entries[1].id, "new-id");
    assert.equal(merged.entries[1].name, "First (2)");
    assert.deepEqual(merged.draft, state.draft);
    assert.equal(merged.selected_id, "a");
    assert.equal(incoming.entries[0].id, "a");
});

test("search uses name, tags, content and favorite filter", () => {
    const state = saved();
    assert.equal(filterEntries(state, "first 카메라 🎥", false).length, 1);
    assert.equal(filterEntries(state, "", true).length, 0);
    state.entries[0].favorite = true;
    assert.equal(filterEntries(state, "WIDE", true).length, 1);
    assert.equal(filterEntries(state, "missing", false).length, 0);
});

test("unknown schema, malformed entries and duplicate IDs rejected", () => {
    assert.throws(() => parseState('{"version":2}'));
    assert.throws(() => parseState("null"));
    const state = saved();
    state.entries.push(state.entries[0]);
    assert.throws(() => parseState(JSON.stringify(state)), /중복/);
    state.entries.pop();
    state.entries[0].text = {};
    assert.throws(() => parseState(JSON.stringify(state)), /올바르지/);
});

test("dangling selections and deleted ID collisions rejected", () => {
    const state = saved();
    state.selected_id = "missing";
    assert.throws(() => parseState(JSON.stringify(state)), /찾을 수/);
    state.selected_id = "a";
    state.deleted = state.entries[0];
    assert.throws(() => parseState(JSON.stringify(state)), /중복/);
});

test("HTML text is preserved as plain data", () => {
    const state = saved();
    state.draft.text = '<img src=x onerror="alert(1)">';
    assert.equal(parseState(JSON.stringify(state)).draft.text, state.draft.text);
});

test("bundled starter presets import through the real selector format without changing the draft", () => {
    const incoming = parseState(readFileSync(new URL("../presets/starter-prompts.json", import.meta.url), "utf8"));
    const local = saved();
    let id = 0;
    const merged = mergeLibrary(local, incoming, () => `imported-${++id}`);
    assert.deepEqual(merged.draft, local.draft);
    assert.equal(merged.entries.length, local.entries.length + incoming.entries.length);
    assert.equal(new Set(merged.entries.map(entry => entry.id)).size, merged.entries.length);
    assert.equal(merged.entries[1].text, incoming.entries[0].text);
});
