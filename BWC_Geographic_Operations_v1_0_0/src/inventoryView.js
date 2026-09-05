export const inventoryFields = [
  ["model", "Model"], ["disposition", "Disposition"], ["assignmentState", "Assignment state"],
  ["deviceHome", "Device Home"], ["component", "Component"], ["regionAor", "Mapped AOR"],
];
export const emptyInventoryFilters = { search: "", model: "", disposition: "", assignmentState: "", deviceHome: "", regionAor: "", exceptionsOnly: false, page: 1 };

export function inventoryQuery(filters, component) {
  const query = { ...filters, component: component === "All Components" ? "" : component, pageSize: 50 };
  query.search = query.search.trim();
  return query;
}

export function illustrativeInventoryView(rows, query) {
  const selected = rows.filter((row) =>
    inventoryFields.every(([key]) => !query[key] || (row[key] || "") === query[key]) &&
    (!query.exceptionsOnly || row.needsReview) &&
    (!query.search || Object.values(row).join(" ").toLowerCase().includes(query.search.toLowerCase()))
  ).sort((a, b) => (a.serialNumber || "").localeCompare(b.serialNumber || ""));
  const totalPages = Math.max(1, Math.ceil(selected.length / query.pageSize));
  const page = Math.min(query.page, totalPages);
  return { mode: "illustrative", total: selected.length, scopeTotal: rows.length, page, pageSize: query.pageSize, totalPages,
    rows: selected.slice((page - 1) * query.pageSize, page * query.pageSize),
    facets: Object.fromEntries(inventoryFields.map(([key]) => [key, [...new Set(rows.map((row) => row[key]).filter(Boolean))].sort()])),
  };
}
