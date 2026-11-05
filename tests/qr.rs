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
        r#"
#let encoder = plugin("typst/vendor/qr/qr.wasm")
#let as-array(b) = range(b.len()).map(i => b.at(i))
#let cases = ({pairs},)
#metadata(cases.map(pair => (
  as-array(encoder.encode(bytes(pair.at(0)), bytes(pair.at(1)))),
  as-array(encoder.encode_runs(bytes(pair.at(0)), bytes(pair.at(1))))
))) <immuknow-report>
QR probe
"#
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
