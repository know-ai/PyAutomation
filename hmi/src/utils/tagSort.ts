export type SortableTag = {
  name?: string;
  value?: string;
  label?: string;
};

function tagId(tag: SortableTag): string {
  return tag.name ?? tag.value ?? "";
}

/**
 * Selected tags first (insertion order), then the rest alphabetically
 * (es-ES, case-insensitive). Search/filter is applied by the caller
 * before this sort; both groups remain in the result.
 */
export function sortTagsWithSelectedFirst<T extends SortableTag>(
  allTags: T[],
  selectedTags: string[]
): T[] {
  if (selectedTags.length === 0) {
    return [...allTags].sort((a, b) =>
      tagId(a).localeCompare(tagId(b), "es-ES", { sensitivity: "base" })
    );
  }

  const selectedSet = new Set(selectedTags);
  const selected: T[] = [];
  const unselected: T[] = [];
  const byId = new Map(allTags.map((tag) => [tagId(tag), tag]));

  for (const name of selectedTags) {
    const tag = byId.get(name);
    if (tag) selected.push(tag);
  }

  for (const tag of allTags) {
    if (!selectedSet.has(tagId(tag))) unselected.push(tag);
  }

  unselected.sort((a, b) =>
    tagId(a).localeCompare(tagId(b), "es-ES", { sensitivity: "base" })
  );

  return [...selected, ...unselected];
}

export function firstUnselectedIndex<T extends SortableTag>(
  sorted: T[],
  selectedTags: string[]
): number {
  if (selectedTags.length === 0) return 0;
  const selectedSet = new Set(selectedTags);
  return sorted.findIndex((tag) => !selectedSet.has(tagId(tag)));
}
