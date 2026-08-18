import { useEffect, useState } from "react";
import { getPlantNodes } from "../services/health";
import { getHistorianCatalog } from "../services/tags";

export function usePlantAreas(): string[] {
  const [areas, setAreas] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const collected = new Set<string>();
      try {
        const nodes = await getPlantNodes();
        nodes.forEach((node) => {
          if (node.area) collected.add(node.area);
        });
      } catch (_e) {
        // Catalog fallback below.
      }
      if (collected.size === 0) {
        try {
          const tags = await getHistorianCatalog();
          tags.forEach((tag) => {
            if (tag.area) collected.add(String(tag.area));
          });
        } catch (_e) {
          // Selector stays plant-wide if topology is unavailable.
        }
      }
      if (!cancelled) {
        setAreas([...collected].sort((a, b) => a.localeCompare(b)));
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return areas;
}
