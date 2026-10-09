import { createTypstCompiler } from '@myriaddreamin/typst.ts/compiler';
import { loadFonts } from '@myriaddreamin/typst.ts/options.init';
import * as wrapper from '../vendor/compiler/typst_ts_web_compiler.js';
import wasmUrl from '../vendor/compiler/typst_ts_web_compiler_bg.wasm?url';

const base = import.meta.env.BASE_URL;
addEventListener('unhandledrejection', event => {
  postMessage({ error: String(event.reason) });
});
postMessage({ phase: 'Loading fonts and compiler' });
const compiler = createTypstCompiler();
const fontNames = await fetch(`${base}generated/fonts/manifest.json`).then(r => r.json());
await compiler.init({
  getWrapper: async () => wrapper,
  getModule: () => wasmUrl,
  beforeBuild: [loadFonts(Object.keys(fontNames).map(name => `${base}generated/fonts/${name}`), { assets: false })],
});

// Assert the version from the running WASM, rather than an npm label.
postMessage({ phase: 'Checking compiler version' });
compiler.addSource('/version.typ', '#assert(sys.version == version(0, 15, 1), message: "Browser compiler must be Typst 0.15.1")\n#set text(font: "FreeSans")\n#repr(sys.version)');
const version = await compiler.compile({ mainFilePath: '/version.typ', format: 1, diagnostics: 'full' });
if (!version.result) throw new Error(JSON.stringify(version));

const cases = await fetch(`${base}generated/proof.json`).then(r => r.json());
const results = [];
for (const item of cases) {
  postMessage({ phase: `Compiling ${item.name}` });
  compiler.resetShadow();
  for (const [path, data] of Object.entries(item.files)) {
    compiler.mapShadow(path, Uint8Array.from(atob(data as string), c => c.charCodeAt(0)));
  }
  const result = await compiler.compile({ mainFilePath: item.mainFilePath, inputs: item.inputs, format: 1, diagnostics: 'full' });
  if (!result.result) throw new Error(`${item.name}: ${JSON.stringify(result)}`);
  results.push({ name: item.name, pdf: result.result });
}
postMessage({ results });
