import { describe, expect, it } from "vitest";
import { zipSync } from "fflate";
import { exportProject, importProject } from "../src/archive-core";
import { encoder, MAX_FILE, safePath } from "../src/project";

const template = "templates/overdue_diseases_v1.en.typ";
const source = encoder.encode("\uFEFF// accented é\r\n#let columns = 2\r\n");
const metadata = encoder.encode(
  JSON.stringify({
    schemaVersion: 1,
    compilerVersion: "0.15.1",
    packageVersion: "0.1.0",
    template,
  }),
);
const project = () => ({ [template]: source, "immuknow-project.json": metadata });
describe("portable project archive", () => {
  it("retains exact source bytes including BOM and CRLF", async () => {
    const zip = await exportProject({ [template]: source }, template);
    const restored = importProject(zip);
    expect(restored.template).toBe(template);
    expect(restored.files[template]).toEqual(source);
  });
  it.each([
    "../outside.typ",
    "/absolute.typ",
    "C:/file.typ",
    "templates/../file.typ",
    "templates\\file.typ",
    "__proto__",
    "templates//file.typ",
  ])("rejects unsafe path %s", (name) => {
    expect(() => safePath(name)).toThrow();
    expect(() => importProject(zipSync({ ...project(), [name]: encoder.encode("x") }))).toThrow();
  });
  it("rejects duplicates that collide on portable filesystems", () => {
    expect(() =>
      importProject(
        zipSync({ ...project(), "templates/OTHER.typ": source, "templates/other.typ": source }),
      ),
    ).toThrow(/Duplicate/);
  });
  it("rejects an oversized expanded entry before inflation", () => {
    expect(() =>
      importProject(zipSync({ ...project(), "templates/large.typ": new Uint8Array(MAX_FILE + 1) })),
    ).toThrow(/expanded size/);
  });
  it("rejects symlink attributes", () => {
    const zip = zipSync(project());
    const view = new DataView(zip.buffer);
    for (let index = 0; index < zip.length - 46; index++)
      if (view.getUint32(index, true) === 0x02014b50) {
        view.setUint32(index + 38, 0xa1ff << 16, true);
        break;
      }
    expect(() => importProject(zip)).toThrow(/linked/);
  });
  it("rejects corrupt CRC evidence", () => {
    const zip = zipSync(project());
    const view = new DataView(zip.buffer);
    for (let index = 0; index < zip.length - 46; index++)
      if (view.getUint32(index, true) === 0x02014b50) {
        view.setUint32(index + 16, 0, true);
        break;
      }
    expect(() => importProject(zip)).toThrow(/Corrupt/);
  });
  it("rejects runtime payload replacement and missing project metadata", () => {
    expect(() => importProject(zipSync({ [template]: source }))).toThrow(
      /complete ImmuKnow project/,
    );
    expect(() =>
      importProject(zipSync({ ...project(), "data/notice.json": encoder.encode("{}") })),
    ).toThrow(/Runtime data/);
  });
});
