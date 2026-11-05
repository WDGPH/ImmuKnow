//! Check the local Markdown references and the documented public CLI.
use std::{
    fs,
    path::{Path, PathBuf},
};

fn markdown_files(dir: &Path, out: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(dir).unwrap() {
        let entry = entry.unwrap();
        if entry.file_type().unwrap().is_dir() {
            markdown_files(&entry.path(), out);
        } else if entry.path().extension().is_some_and(|x| x == "md") {
            out.push(entry.path());
        }
    }
}
#[test]
fn local_documentation_links_and_cli_commands() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let readme = fs::read_to_string(root.join("README.md")).unwrap();
    for command in [
        "immuknow run",
        "immuknow prepare",
        "immuknow resources",
        "immuknow rebundle",
    ] {
        assert!(
            readme.contains(command),
            "README missing public command: {command}"
        );
    }
    let mut files = vec![root.join("README.md")];
    markdown_files(&root.join("docs"), &mut files);
    let all_docs = files
        .iter()
        .map(|file| fs::read_to_string(file).unwrap())
        .collect::<Vec<_>>()
        .join("\n");
    let schema: serde_json::Value = serde_json::from_slice(
        &fs::read(root.join("resources/schemas/input_schema.json")).unwrap(),
    )
    .unwrap();
    for name in ["client_id", "first_name", "last_name", "date_of_birth"] {
        assert!(
            schema["fields"]
                .as_array()
                .unwrap()
                .iter()
                .any(|f| f["name"] == name),
            "missing schema field {name}"
        );
        assert!(
            all_docs.contains(name),
            "documentation missing input field {name}"
        );
    }
    let publishing_config = fs::read_to_string(root.join("mkdocs.yml")).unwrap();
    for file in files {
        let source = fs::read_to_string(&file).unwrap();
        for include in source
            .lines()
            .filter(|line| line.trim_start().starts_with("--8<--"))
        {
            let target = include.split('"').nth(1).expect("quoted Markdown include");
            assert!(
                root.join(target).is_file(),
                "missing documentation include: {target}"
            );
            assert!(
                publishing_config.contains("pymdownx.snippets"),
                "Markdown includes require the snippets publishing extension"
            );
        }
        let mut in_code = false;
        for line in source.lines() {
            if line.trim_start().starts_with("```") {
                in_code = !in_code;
                continue;
            }
            if in_code {
                continue;
            }
            let mut remaining = line;
            while let Some(start) = remaining.find("](") {
                remaining = &remaining[start + 2..];
                let Some(end) = remaining.find(')') else {
                    break;
                };
                let target = remaining[..end].trim().trim_matches(['<', '>']);
                remaining = &remaining[end + 1..];
                let path = target.split('#').next().unwrap_or("");
                if path.is_empty()
                    || path.contains("://")
                    || path.starts_with("mailto:")
                    || path.starts_with('/')
                {
                    continue;
                }
                let path = path.split_whitespace().next().unwrap_or("");
                assert!(
                    file.parent().unwrap().join(path).exists(),
                    "{} links to missing {path}",
                    file.display()
                );
            }
        }
    }
}
