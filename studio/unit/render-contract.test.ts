import { expect, test } from "vitest";
import cases from "../../tests/fixtures/render-contract.json";
import { validateNotice, validateSummary } from "../src/render-contract";

for (const sample of cases.cases) {
  test(`shared rendering contract: ${sample.name}`, () => {
    const values = structuredClone({ payload: cases.payload, report: cases.report });
    for (const change of sample.changes) {
      let target: unknown = values[change.target as keyof typeof values];
      for (const key of change.path.slice(0, -1))
        target = (target as Record<string | number, unknown>)[key];
      const key = change.path.at(-1) as string | number;
      if ("remove" in change && change.remove) {
        if (Array.isArray(target)) target.splice(Number(key), 1);
        else delete (target as Record<string | number, unknown>)[key];
      } else if ("value" in change)
        (target as Record<string | number, unknown>)[key] = change.value;
    }
    const validate = () => {
      validateNotice(values.payload);
      validateSummary(values.report, values.payload);
    };
    if (sample.valid) expect(validate).not.toThrow();
    else expect(validate).toThrow();
  });
}

test("nonfinite measurements are refused", () => {
  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const report = structuredClone(cases.report);
    report.measurements.header[0].title_height_pt = value;
    validateNotice(cases.payload);
    expect(() => validateSummary(report, cases.payload)).toThrow();
    const changedSource = structuredClone(cases.report);
    changedSource.notice.client_data.age = value;
    expect(() => validateSummary(changedSource, cases.payload)).toThrow();
  }
});
