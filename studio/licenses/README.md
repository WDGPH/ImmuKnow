# Retained dependency notices

Some Rust crate archives omit their repository's license file. These upstream
texts are retained for reproducible attribution:

- `roman-numerals-rs.txt`: roman-numerals 3.1.0 source commit
  `ec81337f99d8b557a6fce10f674c054050551444`, `LICENCE.rst`, from
  https://github.com/AA-Turner/roman-numerals.
- `seahash.txt`: MIT license from
  https://gitlab.redox-os.org/redox-os/seahash/-/raw/master/LICENSE;
  the pinned seahash 4.1.0 crate declares MIT but omits this file.

`notices.py` includes original authors and repositories from Cargo metadata.
For crates offering Apache-2.0 whose archives omit license text, it retains
that selected license alternative. Installed Node package license files and
normal WASM compiler dependency notices are assembled into the static site.
Node-only optional native canvas bindings are not shipped by the browser build.
FreeFont retains its full separate copyright/license file alongside the fonts.
