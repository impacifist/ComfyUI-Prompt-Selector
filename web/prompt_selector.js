import { app } from "../../scripts/app.js";
import { emptyState, parseState, selectedEntry, isDirty, draftOf, uniqueName,
    saveDraft, addDraft, sortEntries, mergeLibrary, filterEntries, applySharedLibrary, joinLibraries } from "./library.js";

const controllers = new WeakMap();
const newId = () => Array.from(crypto.getRandomValues(new Uint32Array(4)), (n) => n.toString(16).padStart(8, "0")).join("");
const pendingGraphs = new WeakSet();

function graphEditors(graph) {
    return (graph?._nodes || []).filter((node) => node.comfyClass === "PromptSelector")
        .map((node) => controllers.get(node)).filter((controller) => controller?.read());
}

function scheduleJoin(graph) {
    if (!graph || pendingGraphs.has(graph)) return;
    pendingGraphs.add(graph);
    queueMicrotask(() => {
        pendingGraphs.delete(graph);
        const editors = graphEditors(graph);
        const states = joinLibraries(editors.map((editor) => editor.read()), newId);
        editors.forEach((editor, index) => editor.write(states[index]));
    });
}

function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text) item.textContent = text;
    return item;
}

function installEditor(node) {
    const storage = node.widgets?.find((widget) => widget.name === "library_json");
    if (!storage || controllers.has(node)) return;
    // Keep the backend widget in its original slot for workflow/API serialization.
    storage.type = "hidden";
    storage.hidden = true;
    storage.computeSize = () => [0, -4];
    storage.draw = () => {};
    let state;
    let invalid = false;
    let favoritesOnly = false;
    const root = element("div", "prompt-selector");
    const heading = element("div", "ps-heading");
    const count = element("span", "ps-count");
    heading.append(element("strong", "", "Prompt Library"), count);
    const searchRow = element("div", "ps-row");
    const search = element("input");
    search.type = "search";
    search.placeholder = "이름 · 태그 · 내용 검색";
    search.setAttribute("aria-label", "프롬프트 검색");
    const favorites = element("button", "", "★");
    favorites.title = "즐겨찾기만 보기";
    favorites.setAttribute("aria-label", favorites.title);
    favorites.setAttribute("aria-pressed", "false");
    searchRow.append(search, favorites);
    const sortLabel = element("label", "", "목록 정렬");
    const sortOrder = element("select");
    sortOrder.setAttribute("aria-label", "목록 정렬");
    for (const [value, label] of [["insertion", "등록순"], ["asc", "이름 오름차순 (A → Z · 가 → 하)"],
        ["desc", "이름 내림차순 (Z → A · 하 → 가)"]]) {
        const option = element("option", "", label);
        option.value = value;
        sortOrder.append(option);
    }
    sortLabel.append(sortOrder);
    const list = element("select", "ps-list");
    list.size = 4;
    list.setAttribute("aria-label", "저장된 프롬프트");
    const nameLabel = element("label", "", "이름");
    const nameInput = element("input");
    nameInput.placeholder = "예: 고정 카메라";
    nameLabel.append(nameInput);
    const tagsLabel = element("label", "", "태그");
    const tagsInput = element("input");
    tagsInput.placeholder = "쉼표로 구분: 카메라, 인물, 배경";
    tagsLabel.append(tagsInput);
    const editorLabel = element("label", "ps-editor-label", "프롬프트 · 아래 내용이 그대로 출력됩니다");
    const editor = element("textarea");
    editor.placeholder = "프롬프트를 입력하거나 목록에서 선택하세요.";
    editor.spellcheck = false;
    editorLabel.append(editor);
    const actions = element("div", "ps-actions");
    const files = element("div", "ps-actions ps-footer");
    const status = element("div", "ps-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const help = element("div", "ps-help", "같은 워크플로의 Prompt Selector끼리 저장 목록을 공유합니다. 선택과 미저장 편집은 각 노드에 유지됩니다. 보관하려면 워크플로도 저장하세요.");
    const fileInput = element("input");
    fileInput.type = "file";
    fileInput.accept = ".json,application/json";
    fileInput.hidden = true;
    root.append(heading, searchRow, sortLabel, list, nameLabel, tagsLabel, editorLabel, actions, files, status, help, fileInput);

    function message(text, error = false) {
        status.textContent = text;
        status.dataset.error = String(error);
    }

    function transaction(next, text) {
        // Validate before modifying the only persisted copy.
        const serialized = JSON.stringify(next);
        const checked = parseState(serialized);
        const libraryChanged = JSON.stringify([state.entries, state.deleted]) !== JSON.stringify([checked.entries, checked.deleted]);
        const deletionChanged = JSON.stringify(state.deleted) !== JSON.stringify(checked.deleted);
        node.graph?.beforeChange?.();
        app.canvas?.emitBeforeChange?.();
        try {
            write(checked);
            if (libraryChanged) {
                for (const peer of graphEditors(node.graph)) {
                    if (peer !== controllers.get(node)) {
                        const previous = peer.read();
                        const deleted = deletionChanged ? checked.deleted : previous.deleted;
                        peer.write(applySharedLibrary(previous, checked.entries, deleted));
                    }
                }
            }
        } finally {
            node.graph?.afterChange?.();
            app.canvas?.emitAfterChange?.();
            node.setDirtyCanvas?.(true, true);
        }
        render();
        if (text) message(text);
    }

    function button(parent, label, handler, className = "") {
        const item = element("button", className, label);
        item.type = "button";
        item.addEventListener("click", () => {
            if (invalid) return;
            try { handler(); } catch (error) { message(error.message, true); }
        });
        parent.append(item);
        return item;
    }

    function discardAllowed() {
        return !isDirty(state) || window.confirm("목록에 저장하지 않은 편집 내용이 있습니다. 이 내용을 버리고 계속할까요?");
    }

    const save = button(actions, "저장", () => {
        transaction(addDraft(state, newId()), "새 항목으로 저장했습니다. 같은 이름에는 번호를 붙입니다.");
    }, "ps-primary");
    save.title = "현재 편집 내용을 새 항목으로 추가 (Ctrl/Cmd+S)";
    const update = button(actions, "수정", () => {
        if (!selectedEntry(state)) return;
        transaction(saveDraft(state, newId()), "선택한 프롬프트를 수정했습니다. 공유 목록에도 반영됩니다.");
    });
    update.title = "선택한 기존 항목을 현재 편집 내용으로 갱신";
    button(actions, "새 프롬프트", () => {
        if (!discardAllowed()) return;
        transaction({ ...state, selected_id: null, draft: emptyState().draft });
        nameInput.focus();
    });
    button(actions, "복제", () => {
        const copy = { ...state, selected_id: null,
            draft: { ...state.draft, name: uniqueName(state.entries, `${state.draft.name.trim() || "Untitled"} 복사`) } };
        transaction(saveDraft(copy, newId()), "복사본을 저장했습니다.");
    });
    const favorite = button(actions, "☆ 즐겨찾기", () => {
        const selected = selectedEntry(state);
        transaction({ ...state, entries: state.entries.map((entry) => entry.id === selected.id
            ? { ...entry, favorite: !entry.favorite } : entry) });
    });
    const remove = button(actions, "삭제", () => {
        const selected = selectedEntry(state);
        if (!window.confirm(`“${selected.name}”을 목록에서 삭제할까요?${isDirty(state) ? " 저장하지 않은 편집 내용도 버립니다." : ""}\n최근 삭제 항목은 복구할 수 있습니다.`)) return;
        transaction({ ...state, entries: state.entries.filter((entry) => entry.id !== selected.id),
            deleted: selected, selected_id: null, draft: emptyState().draft }, "삭제했습니다. ‘삭제 복구’로 마지막 항목을 되돌릴 수 있습니다.");
    }, "ps-danger");
    const restore = button(files, "삭제 복구", () => {
        const restored = { ...state.deleted, name: uniqueName(state.entries, state.deleted.name) };
        transaction({ ...state, entries: [...state.entries, restored], deleted: null }, "삭제한 항목을 목록에 복구했습니다.");
    });
    button(files, "JSON 내보내기", () => {
        const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = element("a");
        anchor.href = url;
        anchor.download = "prompt-selector-library.json";
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        message("목록과 현재 편집 내용을 JSON으로 내보냈습니다.");
    });
    button(files, "JSON 가져오기", () => fileInput.click());
    button(files, "텍스트 복사", () => {
        navigator.clipboard.writeText(state.draft.text).then(() => message("프롬프트를 복사했습니다."))
            .catch(() => message("복사가 차단되었습니다. 편집창에서 직접 선택해 복사하세요.", true));
    });

    function renderList() {
        const order = node.properties?.prompt_selector_sort;
        sortOrder.value = order === "asc" || order === "desc" ? order : "insertion";
        const entries = sortEntries(filterEntries(state, search.value, favoritesOnly), sortOrder.value);
        list.replaceChildren();
        for (const entry of entries) {
            const option = element("option", "", `${entry.favorite ? "★ " : ""}${entry.name}`);
            option.value = entry.id;
            option.title = entry.tags;
            list.append(option);
        }
        list.value = state.selected_id || "";
        count.textContent = `${entries.length} / ${state.entries.length}`;
    }

    function render() {
        renderList();
        // Do not reset selection/caret while typing (including Korean IME).
        if (nameInput.value !== state.draft.name) nameInput.value = state.draft.name;
        if (tagsInput.value !== state.draft.tags) tagsInput.value = state.draft.tags;
        if (editor.value !== state.draft.text) editor.value = state.draft.text;
        const selected = selectedEntry(state);
        favorite.disabled = !selected;
        favorite.textContent = selected?.favorite ? "★ 즐겨찾기" : "☆ 즐겨찾기";
        favorite.setAttribute("aria-pressed", String(Boolean(selected?.favorite)));
        remove.disabled = !selected;
        restore.disabled = !state.deleted;
        update.disabled = !selected;
        update.textContent = selected && isDirty(state) ? "수정 *" : "수정";
        message(isDirty(state) ? "편집 중 · 저장: 새 항목 추가 / 수정: 선택한 항목 갱신"
            : selected ? `선택됨: ${selected.name}` : "새 프롬프트를 작성하거나 저장된 항목을 선택하세요.");
    }

    function reload() {
        try {
            state = parseState(storage.value);
            invalid = false;
            root.querySelectorAll("input, textarea, select, button").forEach((item) => { item.disabled = false; });
            render();
        } catch (error) {
            invalid = true;
            // Never silently replace a corrupt or newer library with an empty one.
            root.querySelectorAll("input, textarea, select, button").forEach((item) => { item.disabled = true; });
            message(`${error.message} 원본 워크플로의 데이터는 유지됩니다.`, true);
        }
    }

    function write(next) {
        const serialized = JSON.stringify(next);
        state = parseState(serialized);
        if (storage.value !== serialized) {
            storage.value = serialized;
            storage.callback?.(serialized);
            node.setDirtyCanvas?.(true, true);
        }
        render();
    }

    search.addEventListener("input", renderList);
    sortOrder.addEventListener("change", () => {
        node.graph?.beforeChange?.();
        app.canvas?.emitBeforeChange?.();
        try {
            node.properties ||= {};
            node.properties.prompt_selector_sort = sortOrder.value;
        } finally {
            node.graph?.afterChange?.();
            app.canvas?.emitAfterChange?.();
            node.setDirtyCanvas?.(true, true);
        }
        renderList();
    });
    favorites.addEventListener("click", () => {
        favoritesOnly = !favoritesOnly;
        favorites.setAttribute("aria-pressed", String(favoritesOnly));
        renderList();
    });
    list.addEventListener("change", () => {
        const next = state.entries.find((entry) => entry.id === list.value);
        if (!next || next.id === state.selected_id) return;
        if (!discardAllowed()) { renderList(); return; }
        transaction({ ...state, selected_id: next.id, draft: draftOf(next) });
    });
    for (const [input, field] of [[nameInput, "name"], [tagsInput, "tags"], [editor, "text"]]) {
        input.addEventListener("input", () => transaction({ ...state, draft: { ...state.draft, [field]: input.value } }));
    }
    fileInput.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        fileInput.value = "";
        if (!file) return;
        try {
            if (file.size > 5 * 1024 * 1024) throw new Error("가져오기 파일은 5 MB 이하로 나누어 주세요.");
            const incoming = parseState(await file.text());
            if (!node.graph || invalid) return;
            // Imported drafts are preserved as a new entry, never overwrite the current editor.
            if (isDirty(incoming)) {
                incoming.draft.name = uniqueName(incoming.entries, incoming.draft.name || "가져온 편집 내용");
                incoming.entries.push({ ...incoming.draft, id: newId(), favorite: false });
            }
            transaction(mergeLibrary(state, incoming, newId), `${incoming.entries.length}개를 추가했습니다. 기존 항목은 유지됩니다.`);
        } catch (error) { message(`가져오기 실패: ${error.message}`, true); }
    });
    root.addEventListener("keydown", (event) => {
        // Keep text editing shortcuts away from canvas delete/copy/paste handlers.
        event.stopPropagation();
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            save.click();
        }
    });
    root.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
    // Frontend 1.52.7 reuses stale Vue DOM on undo unless this UI-only render key changes.
    const widget = node.addDOMWidget("prompt_selector_editor", `PROMPT_SELECTOR_EDITOR_${newId()}`, root, {
        serialize: false, hideOnZoom: false, getMinHeight: () => 650,
        afterResize: () => {
            // Refresh the DOM allocation even when the canvas has cached the old layout.
            if (node.graph) node.arrange?.();
        },
    });
    widget.serialize = false;
    widget.options.serialize = false;
    const previousConfigure = node.onConfigure;
    node.onConfigure = function (...args) {
        const result = previousConfigure?.apply(this, args);
        reload();
        return result;
    };
    const previousAdded = node.onAdded;
    node.onAdded = function (...args) {
        const result = previousAdded?.apply(this, args);
        scheduleJoin(this.graph);
        return result;
    };
    node.setSize([Math.max(node.size[0], 450), Math.max(node.size[1], 745)]);
    controllers.set(node, { reload, read: () => invalid ? null : state, write });
    reload();
    scheduleJoin(node.graph);
}

app.registerExtension({
    name: "PromptSelector.Library",
    setup() {
        const link = element("link");
        link.rel = "stylesheet";
        link.href = new URL("./prompt_selector.css", import.meta.url).href;
        document.head.append(link);
    },
    nodeCreated(node) {
        if (node.comfyClass === "PromptSelector") installEditor(node);
    },
    loadedGraphNode(node) {
        controllers.get(node)?.reload();
        if (node.comfyClass === "PromptSelector") scheduleJoin(node.graph);
    },
});
