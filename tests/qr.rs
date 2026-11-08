//! Exercise the shipped QR WebAssembly protocol with an independent decoder.
use immuknow::{
    compiler::{Compiler, Request},
    resources,
};
use quircs::{EccLevel, Eci, Quirc};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};

#[test]
fn wasm_matrix_and_runs_decode_to_the_original_utf8_with_requested_correction() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    // Version 1 capacities in byte mode at each error-correction level.
    let levels = [
        ("l", EccLevel::L, 17),
        ("m", EccLevel::M, 14),
        ("q", EccLevel::Q, 11),
        ("h", EccLevel::H, 7),
    ];
    let mut cases = Vec::new();
    for (level, ecc, capacity) in levels {
        cases.push(("a".repeat(capacity), level, ecc, Some(1)));
        cases.push(("a".repeat(capacity + 1), level, ecc, Some(2)));
        cases.push((
            "https://example.org/été?nom=Zoë".to_string(),
            level,
            ecc,
            None,
        ));
    }
    cases.push(("a".repeat(2953), "l", EccLevel::L, Some(40)));
    cases.push(("a".repeat(1273), "h", EccLevel::H, Some(40)));
    let pairs = cases
        .iter()
        .map(|(text, level, _, _)| {
            format!(
                "({}, {})",
                serde_json::to_string(text).unwrap(),
                serde_json::to_string(level).unwrap()
            )
        })
        .collect::<Vec<_>>()
        .join(", ");
    let typst = format!(
        r##"
#let encoder = plugin("typst/vendor/qr/qr.wasm")
#let as-array(b) = range(b.len()).map(i => b.at(i))
#let cases = ({pairs},)
#metadata(cases.map(pair => (
  as-array(encoder.encode(bytes(pair.at(0)), bytes(pair.at(1)))),
  as-array(encoder.encode_runs(bytes(pair.at(0)), bytes(pair.at(1)))),
  str(encoder.encode_svg(bytes(pair.at(0)), bytes(pair.at(1)), bytes("#005568")).slice(1))
))) <immuknow-report>
QR probe
"##
    );
    fs::write(temp.path().join("probe.typ"), typst).unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let request = Request {
        inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
        notice: json!({}),
        timestamp: 1_750_000_000,
    };
    let compiled = compiler
        .run(&request)
        .expect("QR probe must compile through shipped plugin");
    let reports = compiled.reports.expect("QR probe metadata");
    let matrix_cases = reports[0].as_array().expect("one list of QR matrices");
    assert_eq!(matrix_cases.len(), cases.len());
    for (value, (text, level, ecc, expected_version)) in matrix_cases.iter().zip(cases) {
        let arrays = value.as_array().unwrap();
        let bytes = |v: &Value| -> Vec<u8> {
            v.as_array()
                .unwrap()
                .iter()
                .map(|x| u8::try_from(x.as_u64().unwrap()).unwrap())
                .collect()
        };
        let matrix = bytes(&arrays[0]);
        let runs = bytes(&arrays[1]);
        let size = usize::from(matrix[0]);
        assert_eq!(matrix.len(), 1 + size * size);
        assert_eq!(usize::from(runs[0]), size);
        assert_eq!((runs.len() - 1) % 3, 0);
        let mut reconstructed = vec![0; size * size];
        for run in runs[1..].chunks_exact(3) {
            let (row, start, end) = (
                usize::from(run[0]),
                usize::from(run[1]),
                usize::from(run[2]),
            );
            assert!(row < size && start < end && end <= size);
            for column in start..end {
                assert_eq!(reconstructed[row * size + column], 0, "overlapping runs");
                reconstructed[row * size + column] = 1;
            }
        }
        assert_eq!(
            reconstructed,
            matrix[1..],
            "run representation differs from matrix"
        );
        // The SVG must paint precisely the same cells, including version 40.
        let svg = arrays[2].as_str().unwrap();
        assert!(svg.contains(&format!("viewBox=\"0 0 {} {}\"", size + 8, size + 8)));
        assert!(svg.contains("fill=\"#005568\""));
        let path = svg
            .split_once(" d=\"")
            .unwrap()
            .1
            .split_once('"')
            .unwrap()
            .0;
        let mut painted = vec![0; size * size];
        for segment in path.split('M').skip(1) {
            let (x, remaining) = segment.split_once(' ').unwrap();
            let (y, remaining) = remaining.split_once('h').unwrap();
            let (width, remaining) = remaining.split_once("v1h-").unwrap();
            let width: usize = width.parse().unwrap();
            assert_eq!(remaining, format!("{width}z"));
            let x = x.parse::<usize>().unwrap() - 4;
            let y = y.parse::<usize>().unwrap() - 4;
            assert!(y < size && width > 0 && x + width <= size);
            for column in x..x + width {
                assert_eq!(painted[y * size + column], 0);
                painted[y * size + column] = 1;
            }
        }
        assert_eq!(painted, matrix[1..], "SVG geometry differs from matrix");
        // Rasterize with a four-module quiet zone. Quircs detects and decodes
        // independently; no PDF renderer or QR encoder is involved here.
        let scale = 5;
        let width = (size + 8) * scale;
        let mut pixels = vec![255u8; width * width];
        for y in 0..size {
            for x in 0..size {
                let cell = matrix[1 + y * size + x];
                assert!(cell <= 1);
                if cell == 1 {
                    for dy in 0..scale {
                        for dx in 0..scale {
                            pixels[((y + 4) * scale + dy) * width + (x + 4) * scale + dx] = 0;
                        }
                    }
                }
            }
        }
        let mut decoder = Quirc::default();
        let decoded = decoder
            .identify(width, width, &pixels)
            .map(|code| code.unwrap().decode().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(decoded.len(), 1, "level {level}");
        let result = &decoded[0];
        assert_eq!(result.payload, text.as_bytes());
        assert_eq!(result.ecc_level, ecc);
        if let Some(version) = expected_version {
            assert_eq!(result.version, version, "level {level}");
        }
        if !text.is_ascii() {
            assert_eq!(result.eci, Some(Eci::Utf8));
        }
    }
}

#[test]
fn styled_codes_accept_marker_colours_and_reject_invalid_options() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    let path = temp.path().join("probe.typ");
    let source = r##"
#import "typst/src/qr.typ": qr-code
#set page(width: 8cm, height: auto, margin: 5mm)
#let notice = (row_key: "row-1", client_id: "fictional")
#for shape in ("square", "dots", "rounded", "separated") {
  for corner in ("square", "rounded") {
    qr-code(notice, url: "https://example.org/update", width: 3cm,
      module-shape: shape, corner-style: corner,
      corner-foreground: rgb("176b78"), alignment-foreground: rgb("7a2048"))
  }
}
#qr-code(notice, url: "https://example.org/update", width: 3cm,
  logo: rect(width: 100%, height: 100%, fill: black), logo-size: 10%,
  module-shape: "separated", corner-foreground: rgb("176b78"))
#for foreground in (black, luma(15%), rgb("176b78"), cmyk(80%, 10%, 0%, 60%)) {
  qr-code(notice, url: "https://example.org/été?nom=Zoë", foreground: foreground)
}
#metadata((styles: 13)) <immuknow-report>
"##;
    fs::write(&path, source).unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let request = Request {
        inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
        notice: json!({}),
        timestamp: 1_750_000_000,
    };
    let compiled = compiler.run(&request).expect("all QR styles must compile");
    assert!(!compiled.pdf.is_empty());
    assert_eq!(compiled.reports.unwrap()[0]["styles"], 13);

    for (option, message) in [
        (
            "corner-foreground: 1",
            "QR corner-foreground must be a colour or auto",
        ),
        (
            "alignment-foreground: 1",
            "QR alignment-foreground must be a colour or auto",
        ),
        ("module-shape: \"unknown\"", "QR module-shape must be"),
    ] {
        fs::write(&path, format!(
            "#import \"typst/src/qr.typ\": qr-code\n#qr-code((row_key: \"row-1\", client_id: \"fictional\"), url: \"https://example.org/update\", {option})"
        )).unwrap();
        // New compiler so cached source bytes cannot hide a changed fixture.
        let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
        let error = compiler
            .run(&request)
            .err()
            .expect("invalid styling must fail");
        assert!(error.to_string().contains(message), "{error}");
    }
}
