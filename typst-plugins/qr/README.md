# QR codes for Typst

This small Rust library turns a link into QR code data for the shared Typst
library. It is built as WebAssembly so the same code works in Core and Studio.
The ready-built file is shipped at `resources/typst/vendor/qr/qr.wasm`.
People running ImmuKnow do not need to build it or install Rust.

To change or rebuild it, see the [QR developer guide](../../docs/developer_guide/qr.md).
QR colours, size and links are controlled by the notice template.
