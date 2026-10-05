export function emptyState() {
    return { version: 1, entries: [], selected_id: null,
        draft: { name: "", text: "", tags: "" }, deleted: null };
}

function validFields(value, keys) {
    return value && typeof value === "object" && !Array.isArray(value)
        && keys.every((key) => typeof value[key] === "string");
}

function readEntry(entry) {
    if (!validFields(entry, ["id", "name", "text", "tags"]) || !entry.id
        || typeof entry.favorite !== "boolean") {
        throw new Error("올바르지 않은 프롬프트 항목입니다.");
    }
    return { id: entry.id, name: entry.name, text: entry.text,
        tags: entry.tags, favorite: entry.favorite };
}

export function parseState(raw) {
    const value = JSON.parse(raw);
    if (!value || value.version !== 1 || !Array.isArray(value.entries)) {
        throw new Error("지원하지 않는 Prompt Selector 파일 형식입니다.");
    }
    const entries = value.entries.map(readEntry);
    const ids = new Set(entries.map((entry) => entry.id));
    if (ids.size !== entries.length) throw new Error("프롬프트 ID가 중복되었습니다.");
    if (value.selected_id !== null && !ids.has(value.selected_id)) {
        throw new Error("선택한 프롬프트를 찾을 수 없습니다.");
    }
    if (!validFields(value.draft, ["name", "text", "tags"])) {
        throw new Error("편집 내용이 올바르지 않습니다.");
    }
    const deleted = value.deleted == null ? null : readEntry(value.deleted);
    if (deleted && ids.has(deleted.id)) throw new Error("삭제 복구 항목의 ID가 중복되었습니다.");
    return { version: 1, entries, selected_id: value.selected_id,
        draft: { name: value.draft.name, text: value.draft.text, tags: value.draft.tags }, deleted };
}

export function selectedEntry(state) {
    return state.entries.find((entry) => entry.id === state.selected_id);
}

export function isDirty(state) {
    const saved = selectedEntry(state) || { name: "", text: "", tags: "" };
    return ["name", "text", "tags"].some((key) => saved[key] !== state.draft[key]);
}

export function draftOf(entry) {
    return { name: entry.name, text: entry.text, tags: entry.tags };
}

export function uniqueName(entries, base) {
    const used = new Set(entries.map((entry) => entry.name.trim().toLocaleLowerCase()));
    let name = base.trim() || "Untitled";
    for (let index = 2; used.has(name.toLocaleLowerCase()); index++) name = `${base.trim() || "Untitled"} (${index})`;
    return name;
}

export function saveDraft(state, id, asNew = false) {
    const name = state.draft.name.trim();
    if (!name) throw new Error("프롬프트 이름을 입력하세요.");
    const target = asNew ? null : state.selected_id;
    if (state.entries.some((entry) => entry.id !== target
        && entry.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase())) {
        throw new Error("같은 이름이 있습니다. 다른 이름으로 저장하세요.");
    }
    const entry = { id: target || id, ...state.draft, name,
        favorite: target ? selectedEntry(state).favorite : false };
    const entries = target ? state.entries.map((old) => old.id === target ? entry : old) : [...state.entries, entry];
    return { ...state, entries, selected_id: entry.id, draft: draftOf(entry) };
}

export function addDraft(state, id) {
    if (!state.draft.name.trim()) throw new Error("프롬프트 이름을 입력하세요.");
    return saveDraft({ ...state, draft: { ...state.draft,
        name: uniqueName(state.entries, state.draft.name) } }, id, true);
}

const nameCollator = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });

export function sortEntries(entries, order) {
    if (order !== "asc" && order !== "desc") return [...entries];
    const direction = order === "desc" ? -1 : 1;
    return [...entries].sort((a, b) => direction * nameCollator.compare(a.name, b.name));
}

export function mergeLibrary(state, incoming, newId) {
    const entries = [...state.entries];
    for (const item of incoming.entries) {
        entries.push({ ...item, id: newId(), name: uniqueName(entries, item.name) });
    }
    return { ...state, entries };
}

export function filterEntries(state, query, favoritesOnly) {
    const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return state.entries.filter((entry) => (!favoritesOnly || entry.favorite)
        && words.every((word) => `${entry.name}\n${entry.tags}\n${entry.text}`.toLocaleLowerCase().includes(word)));
}

export function applySharedLibrary(state, entries, deleted) {
    const selected = entries.find((entry) => entry.id === state.selected_id);
    const draft = selected && !isDirty(state) ? draftOf(selected) : state.draft;
    return { ...state, entries, deleted, selected_id: selected?.id || null, draft };
}

// Join legacy node-local libraries without discarding conflicting saved copies.
export function joinLibraries(states, newId) {
    const entries = [];
    const mapped = states.map((state) => {
        let selected_id = state.selected_id;
        for (const entry of state.entries) {
            const sameId = entries.find((item) => item.id === entry.id);
            if (sameId && ["name", "text", "tags", "favorite"].every((key) => sameId[key] === entry[key])) continue;
            const copy = { ...entry, id: sameId ? newId() : entry.id,
                name: uniqueName(entries, entry.name) };
            entries.push(copy);
            if (entry.id === state.selected_id) selected_id = copy.id;
        }
        return { ...state, selected_id };
    });
    return mapped.map((state, index) => {
        const selected = entries.find((entry) => entry.id === state.selected_id);
        let deleted = state.deleted;
        const collision = deleted && entries.find((entry) => entry.id === deleted.id);
        if (collision) {
            deleted = ["name", "text", "tags", "favorite"].every((key) => collision[key] === deleted[key])
                ? null : { ...deleted, id: newId() };
        }
        return { ...state, entries,
            draft: selected && !isDirty(states[index]) ? draftOf(selected) : state.draft,
            deleted };
    });
}
