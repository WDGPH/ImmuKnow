//! Shared files shipped inside the executable, so installed tools need no checkout.
use anyhow::{Context, Result, ensure};
use include_dir::{Dir, include_dir};
use serde_json::{Value, json};
use std::{fs, path::Path};

static RESOURCES: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/resources");

fn collect(dir: &Dir<'_>, files: &mut Vec<Value>) {
    for file in dir.files() {
        files.push(json!({"path":file.path().to_string_lossy().replace('\\', "/"), "sha256":crate::hash(file.contents())}));
    }
    for child in dir.dirs() {
        collect(child, files);
    }
}

/// Identity of all embedded files, ordered by path; the digest covers that list.
pub fn identity() -> Value {
    let mut files = Vec::new();
    collect(&RESOURCES, &mut files);
    files.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    let digest =
        crate::hash(&serde_json::to_vec(&files).expect("resource identity is serializable"));
    json!({"sha256":digest,"files":files})
}
fn export(dir: &Dir<'_>, output: &Path) -> Result<()> {
    for file in dir.files() {
        let dest = output.join(file.path());
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        if dest.exists() {
            ensure!(
                fs::read(&dest).with_context(|| format!("Cannot read {}", dest.display()))?
                    == file.contents(),
                "Resource already exists with different contents: {}",
                dest.display()
            );
        } else {
            fs::write(&dest, file.contents())
                .with_context(|| format!("Cannot write {}", dest.display()))?;
        }
    }
    for child in dir.dirs() {
        export(child, output)?;
    }
    Ok(())
}
/// Export the schemas, Typst library, and file hashes. Project settings are separate.
/// Existing identical files are accepted; differing files are never overwritten.
pub fn materialize(output: &Path) -> Result<()> {
    fs::create_dir_all(output)?;
    export(&RESOURCES, output)?;
    let manifest = output.join("resource-manifest.json");
    let bytes = serde_json::to_vec_pretty(&identity())?;
    if manifest.exists() {
        ensure!(
            fs::read(&manifest)? == bytes,
            "Resource manifest already exists with different contents: {}",
            manifest.display()
        );
    } else {
        fs::write(manifest, bytes)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn export_preserves_existing_files() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        materialize(tmp.path())?;
        assert!(tmp.path().join("schemas/rendering.json").is_file());
        assert_eq!(
            serde_json::from_slice::<Value>(&fs::read(tmp.path().join("resource-manifest.json"))?)?,
            identity()
        );
        materialize(tmp.path())?;
        fs::write(tmp.path().join("schemas/rendering.json"), b"changed")?;
        assert!(materialize(tmp.path()).is_err());
        Ok(())
    }
}
