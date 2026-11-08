//! Prepare client information, compile notices, and save PDFs with a review report.
pub mod bundles;
pub mod compiler;
pub mod input;
pub mod pdf;
pub mod pipeline;
pub mod policy;
pub mod pool;
pub mod report;
pub mod resources;
pub mod validation;
use anyhow::Result;
use serde::{
    Deserialize,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fmt, fs, io::Write, path::Path};

// serde_json's ordinary Value map accepts repeated fields. Reject them recursively.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON with unique fields")
            }
            fn visit_map<M: MapAccess<'de>>(
                self,
                mut m: M,
            ) -> std::result::Result<Unique, M::Error> {
                let mut out = serde_json::Map::new();
                while let Some((k, v)) = m.next_entry::<String, Unique>()? {
                    if out.contains_key(&k) {
                        return Err(de::Error::custom(format!("Repeated JSON field: {k}")));
                    }
                    out.insert(k, v.0);
                }
                Ok(Unique(Value::Object(out)))
            }
            fn visit_seq<S: SeqAccess<'de>>(
                self,
                mut s: S,
            ) -> std::result::Result<Unique, S::Error> {
                let mut out = vec![];
                while let Some(v) = s.next_element::<Unique>()? {
                    out.push(v.0);
                }
                Ok(Unique(json!(out)))
            }
            fn visit_str<E: de::Error>(self, s: &str) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(s)))
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
        }
        d.deserialize_any(V)
    }
}
pub fn read_json<T: serde::de::DeserializeOwned>(p: &Path) -> Result<T> {
    let v: Unique = serde_json::from_slice(&fs::read(p)?)?;
    Ok(serde_json::from_value(v.0)?)
}
pub fn atomic(p: &Path, bytes: &[u8]) -> Result<()> {
    atomic_write(p, |writer| {
        writer.write_all(bytes)?;
        Ok(())
    })
}
pub(crate) fn atomic_write(
    p: &Path,
    write: impl FnOnce(&mut fs::File) -> Result<()>,
) -> Result<()> {
    let temp = p.with_extension("partial");
    let mut writer = fs::File::create(&temp)?;
    write(&mut writer)?;
    drop(writer);
    fs::rename(temp, p)?;
    Ok(())
}
pub fn hash(bytes: &[u8]) -> String {
    hex_digest(&Sha256::digest(bytes))
}
fn hex_digest(digest: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(64);
    for byte in digest {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

/// Hash bytes accepted by the underlying writer, including successful short writes.
pub(crate) struct HashingWriter<W> {
    inner: W,
    digest: Sha256,
}
impl<W> HashingWriter<W> {
    pub(crate) fn new(inner: W) -> Self {
        Self {
            inner,
            digest: Sha256::new(),
        }
    }
    pub(crate) fn into_digest(self) -> String {
        hex_digest(&self.digest.finalize())
    }
}
impl<W: Write> Write for HashingWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        let written = self.inner.write(bytes)?;
        self.digest.update(&bytes[..written]);
        Ok(written)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        self.inner.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn digest_counts_only_successful_short_writes() {
        struct ShortWriter(usize);
        impl Write for ShortWriter {
            fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
                if self.0 == 0 {
                    return Err(std::io::Error::other("injected write failure"));
                }
                let count = bytes.len().min(2).min(self.0);
                self.0 -= count;
                Ok(count)
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let mut writer = HashingWriter::new(ShortWriter(5));
        assert!(writer.write_all(b"abcdefgh").is_err());
        assert_eq!(writer.into_digest(), hash(b"abcde"));
    }

    #[test]
    fn failed_streamed_write_keeps_the_previous_file() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("run.json");
        fs::write(&path, b"previous record").unwrap();
        let result = atomic_write(&path, |writer| {
            writer.write_all(b"partial replacement")?;
            anyhow::bail!("injected serialization failure")
        });
        assert!(result.is_err());
        assert_eq!(fs::read(&path).unwrap(), b"previous record");
    }
}
