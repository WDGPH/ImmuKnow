import schema from "../../immuknow/templates/lib/immuknow/report-v2.json";
import validators from "../generated/render-contract.js";
const { validatePayload, validateReport } = validators;
import type { Notice, RenderSummary } from "./types";

function sameData(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (
    !left ||
    !right ||
    typeof left !== "object" ||
    typeof right !== "object" ||
    Array.isArray(left) !== Array.isArray(right)
  )
    return false;
  const fields = Object.entries(left);
  return (
    fields.length === Object.keys(right).length &&
    fields.every(
      ([key, value]) =>
        Object.hasOwn(right, key) && sameData(value, (right as Record<string, unknown>)[key]),
    )
  );
}

export function validateNotice(value: unknown): asserts value is Notice {
  if (!validatePayload(value))
    throw new Error(
      `Notice data has an invalid field: ${validatePayload.errors?.[0]?.instancePath || "notice"}`,
    );
  const notice = value as Notice;
  if (notice.template !== `${notice.version_id}.${notice.language}.typ`)
    throw new Error("Notice filename differs from its version or language.");
}

export function validateSummary(value: unknown, notice: Notice): asserts value is RenderSummary {
  if (!validateReport(value))
    throw new Error(
      `Render evidence has an invalid field: ${validateReport.errors?.[0]?.instancePath || "report"}`,
    );
  const summary = value as RenderSummary;
  validateNotice(summary.notice);
  if (Object.entries(summary.identity).some(([key, value]) => value !== notice[key]))
    throw new Error("Render evidence does not belong to the selected source row and notice");
  if (!sameData(summary.notice, notice))
    throw new Error("Render evidence used data that differs from the prepared notice");
  function bounds(value: Record<string, unknown>) {
    for (const [key, number] of Object.entries(value))
      if ((key === "page" || key.endsWith("_page")) && Number(number) > summary.page_count)
        throw new Error("Render evidence refers to a page outside this notice");
    if (Number(value.first_page ?? 0) > Number(value.last_page ?? summary.page_count))
      throw new Error("Render evidence has a reversed page range");
  }
  const rules = new Map(schema.$defs.check.properties.code.oneOf.map((item) => [item.const, item]));
  for (const [name, placed] of Object.entries(summary.components)) {
    const measurements = summary.measurements[name] ?? [];
    const absent = summary.checks.filter((item) => item.code === `component.${name}.absent`);
    if (Boolean(measurements.length) !== placed || absent.length !== (placed ? 0 : 1))
      throw new Error(`Render evidence contradicts the placed ${name} component`);
    for (const value of measurements) {
      bounds(value);
      if (
        "row_key" in value &&
        (value.client_id !== notice.client_id || value.row_key !== notice.row_key)
      )
        throw new Error(`Placed ${name} evidence belongs to a different source row`);
      if ("source_matches" in value && !value.source_matches)
        throw new Error(`Placed ${name} content used changed notice data`);
    }
  }
  for (const check of summary.checks) {
    bounds({ ...check });
    bounds(check.measurements ?? {});
    const allowed = rules.get(check.code)?.["x-components"] ?? [];
    if (
      (allowed.length && !allowed.includes(check.component ?? "")) ||
      (!allowed.length && check.component !== undefined)
    )
      throw new Error("Render check names the wrong component");
    if (check.code.startsWith("component.")) {
      if (check.status !== "not_applicable" || check.page !== undefined)
        throw new Error("An absent component must be reported as not applicable");
    } else if (
      allowed.length &&
      (!summary.components[check.component as string] || check.page === undefined)
    )
      throw new Error("Render check is missing its placed component or page");
  }
}
