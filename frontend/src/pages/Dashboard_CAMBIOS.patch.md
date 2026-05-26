# Cambios mínimos en `frontend/src/pages/Dashboard.tsx`

No reemplaces todo el Dashboard. Solo agrega estos cambios para mostrar el aviso de corte a 5000 registros.

## 1) En `firstPageData`, agrega los campos nuevos

Busca este bloque dentro de `onSubmit`:

```tsx
let firstPageData: ReportData = {
  columns: res.columns,
  rows: res.rows,
  page: res.page,
  page_size: res.page_size,
  row_count: res.row_count,
  total_count: res.total_count ?? null,
  total_pages: res.total_pages ?? null,
};
```

Reemplázalo por:

```tsx
let firstPageData: ReportData = {
  columns: res.columns,
  rows: res.rows,
  page: res.page,
  page_size: res.page_size,
  row_count: res.row_count,
  total_count: res.total_count ?? null,
  display_total_count: res.display_total_count ?? null,
  total_pages: res.total_pages ?? null,
  max_result_window: res.max_result_window ?? null,
  max_result_window_exceeded: res.max_result_window_exceeded ?? false,
  result_message: res.result_message ?? null,
};
```

## 2) Cambia el texto de cantidad de filas

Busca el texto:

```tsx
{t
  ? `Reporte cargado${
      t.total_count != null ? ` · ${t.total_count} filas` : ""
    }`
  : "Cargando reporte..."}
```

Reemplázalo por:

```tsx
{t
  ? `Reporte cargado${
      t.display_total_count != null
        ? ` · mostrando ${t.display_total_count} de ${t.total_count ?? t.display_total_count} filas`
        : t.total_count != null
          ? ` · ${t.total_count} filas`
          : ""
    }`
  : "Cargando reporte..."}
```

## 3) Debajo de ese encabezado, antes de la tabla, agrega el aviso

Busca el cierre de este bloque:

```tsx
<div className="flex items-center p-4">
  ...
</div>

<div className="overflow-x-auto w-full">
```

Inserta entre ambos:

```tsx
{t?.max_result_window_exceeded && (
  <div className="mx-4 mb-4 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200 px-4 py-3 text-sm">
    <span className="font-bold">Resultado recortado:</span>{" "}
    {t.result_message ??
      `La vista se limitó a ${t.max_result_window ?? 5000} registros. La exportación descarga el conjunto completo permitido.`}
  </div>
)}
```

Con esto, la UI mantiene paginación normal, pero si la consulta supera el límite visual, avisa al usuario que se cortó la navegación a 5000 registros.
