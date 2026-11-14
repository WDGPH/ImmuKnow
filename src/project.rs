//! Generic project setup; authored settings and sample records belong to the project.
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Sample {
    csv: String,
    template: String,
}

/// Resolve the project's selected fictional sample, without allowing outside paths.
pub fn sample_paths(project: &Path, include_template: bool) -> Result<(PathBuf, Option<PathBuf>)> {
    let selection = project.join("sample.json");
    let sample: Sample = crate::read_json(&selection)
        .context("Cannot read sample.json (csv and template required)")?;
    let root = project
        .canonicalize()
        .context("Cannot open project folder")?;
    let resolve = |value: &str| -> Result<PathBuf> {
        let relative = Path::new(value);
        ensure!(
            !value.is_empty()
                && !value.contains(['\\', ':'])
                && !relative.is_absolute()
                && relative
                    .components()
                    .all(|part| matches!(part, Component::Normal(_) | Component::CurDir)),
            "Sample paths must be relative paths inside the project: {value}"
        );
        let path = root.join(relative).canonicalize()
            .with_context(|| format!("Sample file is missing: {value}; supply sample.json or include fictional client data"))?;
        ensure!(
            path.starts_with(&root) && path.is_file(),
            "Sample path must be a file inside the project: {value}"
        );
        Ok(path)
    };
    Ok((
        resolve(&sample.csv)?,
        if include_template {
            Some(resolve(&sample.template)?)
        } else {
            None
        },
    ))
}

/// Resolve a sample override using the project's templates directory and containment boundary.
pub fn sample_template(project: &Path, template: &Path) -> Result<PathBuf> {
    ensure!(
        !template
            .components()
            .any(|part| matches!(part, Component::ParentDir)),
        "Sample template must stay inside the project"
    );
    let root = project
        .canonicalize()
        .context("Cannot open project folder")?;
    let path = if template.is_absolute() {
        template.to_path_buf()
    } else {
        root.join("templates").join(template)
    };
    let path = path
        .canonicalize()
        .context("Selected sample template is missing")?;
    ensure!(
        path.starts_with(&root) && path.is_file(),
        "Sample template must be a file inside the project"
    );
    Ok(path)
}

fn tree(root: &Path) -> Result<BTreeMap<PathBuf, Vec<u8>>> {
    fn visit(root: &Path, relative: &Path, files: &mut BTreeMap<PathBuf, Vec<u8>>) -> Result<()> {
        let path = root.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        ensure!(
            !metadata.is_symlink(),
            "Shared library must not contain symbolic links: {}",
            path.display()
        );
        if metadata.is_dir() {
            for entry in fs::read_dir(&path)? {
                visit(root, &relative.join(entry?.file_name()), files)?;
            }
        } else {
            ensure!(
                metadata.is_file(),
                "Unsupported shared library path: {}",
                path.display()
            );
            files.insert(relative.to_path_buf(), fs::read(&path)?);
        }
        Ok(())
    }
    let mut files = BTreeMap::new();
    visit(root, Path::new(""), &mut files)?;
    Ok(files)
}

fn templates(project: &Path) -> Result<PathBuf> {
    let templates = project.join("templates");
    ensure!(
        !templates.is_symlink() && templates.is_dir(),
        "Project templates folder is missing or linked"
    );
    let lib = templates.join("lib");
    ensure!(
        !lib.is_symlink() && (!lib.exists() || lib.is_dir()),
        "Project templates/lib must be an unlinked directory"
    );
    Ok(templates)
}

/// Compare complete library trees; no authored files are changed by a check.
pub fn check_library(project: &Path) -> Result<()> {
    let templates = templates(project)?;
    let scratch = tempfile::tempdir()?;
    crate::resources::materialize(scratch.path())?;
    let current = tree(&templates.join("lib/immuknow"))
        .context("Shared library is missing or unreadable; run immuknow project sync")?;
    ensure!(
        current == tree(&scratch.path().join("typst"))?,
        "Shared library differs from this executable; run immuknow project sync --replace"
    );
    Ok(())
}

/// Install a complete library, retaining the previous tree if replacement fails.
pub fn sync_library(project: &Path, replace: bool) -> Result<()> {
    let templates = templates(project)?;
    let staging = tempfile::Builder::new()
        .prefix(".sync-lib-")
        .tempdir_in(project)?;
    crate::resources::materialize(staging.path())?;
    let source = staging.path().join("typst");
    let target = templates.join("lib/immuknow");
    ensure!(
        !target.is_symlink(),
        "Shared library must not be a symbolic link"
    );
    if target.exists() {
        let current = tree(&target)?;
        if current == tree(&source)? {
            return Ok(());
        }
        ensure!(
            replace,
            "Shared library differs; run immuknow project sync --replace to refresh it"
        );
    }
    fs::create_dir_all(templates.join("lib"))?;
    let previous = staging.path().join("previous");
    if target.exists() {
        fs::rename(&target, &previous)?;
    }
    if let Err(error) = fs::rename(&source, &target) {
        if previous.exists()
            && let Err(restore) = fs::rename(&previous, &target)
        {
            let retained = staging.keep();
            anyhow::bail!(
                "Could not install library ({error}) or restore it ({restore}); previous files retained in {}",
                retained.display()
            );
        }
        return Err(error.into());
    }
    Ok(())
}
