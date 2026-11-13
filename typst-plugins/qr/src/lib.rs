use qrcodegen::{QrCode, QrCodeEcc, QrSegment, Version};
use std::fmt::Write;
use wasm_minimal_protocol::{initiate_protocol, wasm_func};

initiate_protocol!();

/// Return the matrix width followed by one byte (0 or 1) per cell, in row order.
#[wasm_func]
pub fn encode(text: &[u8], correction: &[u8]) -> Result<Vec<u8>, String> {
    let qr = make_qr(text, correction)?;
    let size = qr.size();
    let mut result = Vec::with_capacity((size * size + 1) as usize);
    result.push(size as u8);
    for row in 0..size {
        for column in 0..size {
            result.push(u8::from(qr.get_module(column, row)));
        }
    }
    Ok(result)
}

/// Return the width followed by dark horizontal runs: row, start, exclusive end.
#[wasm_func]
pub fn encode_runs(text: &[u8], correction: &[u8]) -> Result<Vec<u8>, String> {
    let qr = make_qr(text, correction)?;
    let size = qr.size();
    let mut result = vec![size as u8];
    for row in 0..size {
        let mut column = 0;
        while column < size {
            if !qr.get_module(column, row) {
                column += 1;
                continue;
            }
            let start = column;
            while column < size && qr.get_module(column, row) {
                column += 1;
            }
            result.extend_from_slice(&[row as u8, start as u8, column as u8]);
        }
    }
    Ok(result)
}

/// Return the matrix width, then a single-path SVG with a four-module quiet zone.
#[wasm_func]
pub fn encode_svg(text: &[u8], correction: &[u8], foreground: &[u8]) -> Result<Vec<u8>, String> {
    let foreground =
        std::str::from_utf8(foreground).map_err(|_| "QR colour must be hexadecimal RGB or RGBA")?;
    if !matches!(foreground.len(), 7 | 9)
        || !foreground.starts_with('#')
        || !foreground[1..].bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err("QR colour must be hexadecimal RGB or RGBA".into());
    }
    let qr = make_qr(text, correction)?;
    let size = qr.size();
    let total = size + 8;
    let mut result = String::with_capacity((size * size * 4) as usize);
    write!(result, "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {total} {total}\"><path fill=\"{foreground}\" d=\"").unwrap();
    for row in 0..size {
        let mut column = 0;
        while column < size {
            if !qr.get_module(column, row) {
                column += 1;
                continue;
            }
            let start = column;
            while column < size && qr.get_module(column, row) {
                column += 1;
            }
            write!(
                result,
                "M{} {}h{}v1h-{}z",
                start + 4,
                row + 4,
                column - start,
                column - start
            )
            .unwrap();
        }
    }
    result.push_str("\"/></svg>");
    let mut bytes = Vec::with_capacity(result.len() + 1);
    bytes.push(size as u8);
    bytes.extend_from_slice(result.as_bytes());
    Ok(bytes)
}

fn make_qr(text: &[u8], correction: &[u8]) -> Result<QrCode, String> {
    let text = std::str::from_utf8(text).map_err(|_| "QR destination must be UTF-8")?;
    let correction = match correction {
        b"l" => QrCodeEcc::Low,
        b"m" => QrCodeEcc::Medium,
        b"q" => QrCodeEcc::Quartile,
        b"h" => QrCodeEcc::High,
        _ => return Err("QR error-correction must be l, m, q or h".into()),
    };
    let mut segments = QrSegment::make_segments(text);
    if !text.is_ascii() {
        segments.insert(0, QrSegment::make_eci(26));
    }
    let qr = QrCode::encode_segments_advanced(
        &segments,
        correction,
        Version::MIN,
        Version::MAX,
        None,
        false,
    )
    .map_err(|_| "QR destination is too long for the requested error correction")?;
    Ok(qr)
}
