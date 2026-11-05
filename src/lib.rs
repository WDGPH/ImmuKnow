//! Native notice preparation, warm Typst compilation and verified delivery.
pub mod compiler;
pub mod delivery;
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
use std::{fmt, fs, path::Path};

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
    let temp = p.with_extension("partial");
    fs::write(&temp, bytes)?;
    fs::rename(temp, p)?;
    Ok(())
}
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
