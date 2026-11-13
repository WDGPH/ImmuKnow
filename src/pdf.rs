//! Whole-document encryption and visual bundles that preserve source page trees.
use anyhow::{Result, ensure};
use lopdf::encryption::crypt_filters::{Aes256CryptFilter, CryptFilter};
use lopdf::{Document, EncryptionState, EncryptionVersion, Object, Permissions, dictionary};
use std::{
    collections::BTreeMap,
    fs,
    io::{self, BufWriter, Write},
    path::Path,
    sync::Arc,
};

pub fn inspect(bytes: &[u8]) -> Result<usize> {
    let doc = Document::load_mem(bytes)?;
    ensure!(!doc.is_encrypted(), "Original must be unencrypted");
    let pages = doc.get_pages().len();
    ensure!(pages > 0, "PDF has no pages");
    Ok(pages)
}
pub(crate) fn encrypt_with_hash(
    source: &Path,
    destination: &Path,
    password: &str,
) -> Result<String> {
    ensure!(
        !password.trim().is_empty(),
        "Password facts are unavailable"
    );
    let mut doc = Document::load(source)?;
    let pages = doc.get_pages().len();
    ensure!(
        !doc.is_encrypted() && pages > 0,
        "Invalid encryption source"
    );
    let key: [u8; 32] = rand::random();
    let filter = b"StdCF".to_vec();
    let state = EncryptionState::try_from(EncryptionVersion::V5 {
        encrypt_metadata: true,
        crypt_filters: BTreeMap::from([(
            filter.clone(),
            Arc::new(Aes256CryptFilter) as Arc<dyn CryptFilter>,
        )]),
        file_encryption_key: &key,
        stream_filter: filter.clone(),
        string_filter: filter,
        owner_password: password,
        user_password: password,
        permissions: Permissions::all(),
    })?;
    // Match qpdf/pikepdf's PDF1.7 extension8 representation of R6.
    if doc.version.as_str() < "1.7" {
        doc.version = "1.7".into();
    }
    let mut extensions = doc
        .catalog()?
        .get(b"Extensions")
        .ok()
        .map(|value| {
            doc.dereference(value)
                .and_then(|(_, value)| value.as_dict().cloned())
        })
        .transpose()?
        .unwrap_or_default();
    extensions.set(
        "ADBE",
        dictionary! {"BaseVersion"=>Object::Name(b"1.7".to_vec()), "ExtensionLevel"=>8},
    );
    doc.catalog_mut()?.set("Extensions", extensions);
    doc.encrypt(&state)?;
    check_encryption_settings(&doc)?;
    // R6's Unicode preparation can map nonempty input (e.g. a soft hyphen)
    // to empty bytes. Reject that without repeating password authentication.
    ensure!(
        !lopdf::encryption::PasswordAlgorithm::try_from(&doc)?
            .sanitize_password(password)?
            .is_empty(),
        "Password is empty after PDF password preparation"
    );
    ensure!(
        doc.get_pages().len() == pages,
        "Encryption changed page count"
    );
    let partial = destination.with_extension("partial.pdf");
    let result = (|| -> Result<String> {
        // Encryption is applied above; the pinned writer reports serialization,
        // write and buffer-flush failures. Password round trips belong in tests.
        let digest = save_hashed(&mut doc, fs::File::create(&partial)?)?;
        fs::rename(&partial, destination)?;
        Ok(digest)
    })();
    if partial.exists() {
        fs::remove_file(&partial)?;
    }
    result
}

fn check_encryption_settings(doc: &Document) -> Result<()> {
    let details = doc.get_encrypted()?;
    ensure!(
        details.get(b"V")?.as_i64()? == 5
            && details.get(b"R")?.as_i64()? == 6
            && details.get(b"Length")?.as_i64()? == 256,
        "Wrong encryption settings"
    );
    let filters = details.get(b"CF")?.as_dict()?.get(b"StdCF")?.as_dict()?;
    ensure!(
        details.get(b"Filter")?.as_name()? == b"Standard"
            && details.get(b"StmF")?.as_name()? == b"StdCF"
            && details.get(b"StrF")?.as_name()? == b"StdCF"
            && filters.get(b"CFM")?.as_name()? == b"AESV3",
        "Wrong AES encryption filters"
    );
    Ok(())
}

// Resolve names while their source catalog is available. Keeping full arrays
// preserves /XYZ coordinates and zoom, and prevents cross-notice name collisions.
fn resolve_named_links(doc: &mut Document) -> Result<()> {
    fn destination(doc: &Document, value: &Object) -> Result<Object> {
        let (_, value) = doc.dereference(value)?;
        match value {
            Object::Array(_) => Ok(value.clone()),
            Object::Dictionary(d) => Ok(doc.dereference(d.get(b"D")?)?.1.clone()),
            _ => anyhow::bail!("Invalid named PDF destination"),
        }
    }
    fn tree(
        doc: &Document,
        value: &Object,
        names: &mut BTreeMap<Vec<u8>, Object>,
        depth: usize,
    ) -> Result<()> {
        ensure!(depth < 64, "Destination name tree is too deep");
        let d = doc.dereference(value)?.1.as_dict()?;
        if let Ok(kids) = d.get_deref(b"Kids", doc) {
            for kid in kids.as_array()? {
                tree(doc, kid, names, depth + 1)?;
            }
        }
        if let Ok(entries) = d.get_deref(b"Names", doc) {
            let entries = entries.as_array()?;
            let (pairs, remainder) = entries.as_chunks::<2>();
            ensure!(remainder.is_empty(), "Invalid destination name tree");
            for [name, value] in pairs {
                names.insert(name.as_str()?.to_vec(), destination(doc, value)?);
            }
        }
        Ok(())
    }
    let mut names = BTreeMap::new();
    let catalog = doc.catalog()?;
    if let Ok(legacy) = catalog.get_deref(b"Dests", doc) {
        for (name, value) in legacy.as_dict()?.iter() {
            names.insert(name.clone(), destination(doc, value)?);
        }
    }
    if let Ok(root) = catalog.get_deref(b"Names", doc)
        && let Ok(dests) = root.as_dict()?.get(b"Dests")
    {
        tree(doc, dests, &mut names, 0)?;
    }
    let aliases: BTreeMap<_, _> = doc
        .objects
        .iter()
        .filter_map(|(id, value)| match value {
            Object::Name(n) | Object::String(n, _) => Some((*id, n.clone())),
            _ => None,
        })
        .collect();
    fn rewrite(
        value: &mut Object,
        names: &BTreeMap<Vec<u8>, Object>,
        aliases: &BTreeMap<lopdf::ObjectId, Vec<u8>>,
    ) -> Result<()> {
        fn link(
            value: &mut Object,
            names: &BTreeMap<Vec<u8>, Object>,
            aliases: &BTreeMap<lopdf::ObjectId, Vec<u8>>,
        ) -> Result<()> {
            let key = match &*value {
                Object::Name(n) | Object::String(n, _) => Some(n.as_slice()),
                Object::Reference(id) => aliases.get(id).map(Vec::as_slice),
                _ => None,
            };
            if let Some(key) = key {
                *value = names
                    .get(key)
                    .ok_or_else(|| anyhow::anyhow!("Unresolved internal PDF destination"))?
                    .clone();
            }
            Ok(())
        }
        let dict = match value {
            Object::Dictionary(d) => Some(d),
            Object::Stream(s) => Some(&mut s.dict),
            _ => None,
        };
        if let Some(d) = dict {
            if let Ok(target) = d.get_mut(b"Dest") {
                link(target, names, aliases)?;
            }
            if d.get(b"S").and_then(Object::as_name).ok() == Some(b"GoTo".as_slice()) {
                link(d.get_mut(b"D")?, names, aliases)?;
            }
            for (_, child) in d.iter_mut() {
                rewrite(child, names, aliases)?;
            }
        } else if let Object::Array(a) = value {
            for child in a {
                rewrite(child, names, aliases)?;
            }
        }
        Ok(())
    }
    for value in doc.objects.values_mut() {
        rewrite(value, &names, &aliases)?;
    }
    Ok(())
}

pub(crate) fn merge_with_hash(
    paths: &[impl AsRef<Path>],
    destination: &Path,
) -> Result<(usize, String)> {
    let mut merged = Document::with_version("1.7");
    let pages_root = merged.new_object_id();
    let mut kids: Vec<Object> = vec![];
    let mut count = 0;
    for path in paths {
        let mut source = Document::load(path)?;
        ensure!(!source.is_encrypted(), "Cannot bundle encrypted originals");
        // Retain original /Pages trees so inherited resources/boxes/rotation survive.
        ensure!(
            matches!(
                source.version.as_str(),
                "1.0" | "1.1" | "1.2" | "1.3" | "1.4" | "1.5" | "1.6" | "1.7" | "2.0"
            ),
            "Unsupported PDF version"
        );
        if source.version > merged.version {
            merged.version = source.version.clone();
        }
        ensure!(
            !source.catalog()?.has(b"AcroForm"),
            "PDF bundles do not support forms"
        );
        resolve_named_links(&mut source)?;
        source.renumber_objects_with(merged.max_id + 1);
        let catalog = source.catalog()?;
        let root = catalog.get(b"Pages")?.as_reference()?;
        count += source.get_pages().len();
        source
            .get_object_mut(root)?
            .as_dict_mut()?
            .set("Parent", pages_root);
        // Tagged merging is outside the verified contract.
        // Remove dangling document-level parent-tree keys rather than claim valid tags.
        for object in source.objects.values_mut() {
            if let Ok(d) = object.as_dict_mut() {
                d.remove(b"StructParents");
                d.remove(b"StructParent");
            }
        }
        merged.max_id = merged.max_id.max(source.max_id);
        merged.objects.extend(source.objects);
        kids.push(root.into());
    }
    merged.objects.insert(
        pages_root,
        Object::Dictionary(dictionary! {"Type"=>"Pages","Kids"=>kids,"Count"=>count as i64}),
    );
    let catalog = merged.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages_root});
    merged.trailer.set("Root", catalog);
    merged.prune_objects();
    ensure!(
        merged.get_pages().len() == count,
        "Bundle page count mismatch"
    );
    let digest = save_hashed(&mut merged, fs::File::create(destination)?)?;
    Ok((count, digest))
}

fn save_hashed(doc: &mut Document, output: impl Write) -> io::Result<String> {
    // save_to is unbuffered. Coalesce serialization writes before hashing them.
    let mut writer = BufWriter::new(crate::HashingWriter::new(output));
    doc.save_to(&mut writer)?;
    writer.flush()?;
    Ok(writer
        .into_inner()
        .map_err(|error| error.into_error())?
        .into_digest())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn page() -> Document {
        let mut d = Document::with_version("1.7");
        let pages = d.new_object_id();
        let p = d.add_object(dictionary! {"Type"=>"Page","Parent"=>pages});
        d.objects.insert(pages,Object::Dictionary(dictionary!{"Type"=>"Pages","Kids"=>vec![Object::Reference(p)],"Count"=>1,"MediaBox"=>vec![0.into(),0.into(),100.into(),200.into()]}));
        let c = d.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages});
        d.trailer.set("Root", c);
        d
    }
    #[test]
    fn saved_digest_requires_successful_flush() {
        struct FlushFailure;
        impl Write for FlushFailure {
            fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
                Ok(bytes.len())
            }
            fn flush(&mut self) -> io::Result<()> {
                Err(io::Error::other("injected flush failure"))
            }
        }
        let error = save_hashed(&mut page(), FlushFailure).unwrap_err();
        assert_eq!(error.to_string(), "injected flush failure");
    }

    #[test]
    fn password_and_inherited_pages() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let source = dir.path().join("source.pdf");
        page().save(&source)?;
        let encrypted = dir.path().join("encrypted.pdf");
        let digest = encrypt_with_hash(&source, &encrypted, "héllo-世界")?;
        assert_eq!(digest, crate::hash(&fs::read(&encrypted)?));
        assert!(
            Document::load(&encrypted)?
                .authenticate_password("wrong")
                .is_err()
        );
        let bundle = dir.path().join("bundle.pdf");
        let (pages, digest) = merge_with_hash(&[&source, &source], &bundle)?;
        assert_eq!(pages, 2);
        assert_eq!(digest, crate::hash(&fs::read(&bundle)?));
        let d = Document::load(bundle)?;
        for id in d.get_pages().values() {
            let parent = d.get_dictionary(*id)?.get(b"Parent")?.as_reference()?;
            assert!(d.get_dictionary(parent)?.has(b"MediaBox"));
        }
        Ok(())
    }
    #[test]
    fn protected_copies_round_trip_and_use_fresh_randomness() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let source = dir.path().join("source.pdf");
        let mut original = page();
        let content = original.add_object(lopdf::Stream::new(
            dictionary! {},
            b"BT /F1 12 Tf (fictional notice) Tj ET".to_vec(),
        ));
        let page_id = *original.get_pages().values().next().unwrap();
        original
            .get_dictionary_mut(page_id)?
            .set("Contents", content);
        let info = original
            .add_object(dictionary! {"Title" => Object::string_literal("Fictional notice")});
        original.trailer.set("Info", info);
        original.save(&source)?;
        for (index, password) in ["20150102", "héllo-世界"].into_iter().enumerate() {
            let destination = dir.path().join(format!("encrypted-{index}.pdf"));
            encrypt_with_hash(&source, &destination, password)?;
            let locked = Document::load(&destination)?;
            // The passwordless loader tries an empty password. Keeping /Encrypt
            // therefore establishes that this output refuses empty access.
            assert!(locked.is_encrypted());
            let settings = locked.get_encrypted()?;
            assert_eq!(settings.get(b"V")?.as_i64()?, 5);
            assert_eq!(settings.get(b"R")?.as_i64()?, 6);
            assert_eq!(settings.get(b"Length")?.as_i64()?, 256);
            assert_eq!(settings.get(b"Filter")?.as_name()?, b"Standard");
            for key in [b"StmF", b"StrF"] {
                assert_eq!(settings.get(key)?.as_name()?, b"StdCF");
            }
            assert_eq!(
                settings
                    .get(b"CF")?
                    .as_dict()?
                    .get(b"StdCF")?
                    .as_dict()?
                    .get(b"CFM")?
                    .as_name()?,
                b"AESV3"
            );
            assert!(
                Document::load_with_options(
                    &destination,
                    lopdf::LoadOptions::with_password("wrong")
                )
                .is_err()
            );
            let readable = Document::load_with_options(
                &destination,
                lopdf::LoadOptions::with_password(password),
            )?;
            assert!(readable.was_encrypted() && !readable.is_encrypted());
            assert_eq!(readable.get_pages(), original.get_pages());
            assert_eq!(
                readable.get_object(content)?.as_stream()?.content,
                original.get_object(content)?.as_stream()?.content
            );
            assert_eq!(
                readable.get_dictionary(info)?.get(b"Title")?.as_str()?,
                b"Fictional notice"
            );
            let another = dir.path().join(format!("another-{index}.pdf"));
            encrypt_with_hash(&source, &another, password)?;
            assert_ne!(fs::read(&destination)?, fs::read(&another)?);
        }
        let rejected = dir.path().join("rejected.pdf");
        for password in ["", " \t\n", "\u{00ad}", "\u{2060}"] {
            assert!(encrypt_with_hash(&source, &rejected, password).is_err());
            assert!(!rejected.exists());
        }
        // A failed write is never reported as a protected copy.
        assert!(
            encrypt_with_hash(
                &source,
                &dir.path().join("missing/encrypted.pdf"),
                "20150102"
            )
            .is_err()
        );
        Ok(())
    }
    #[test]
    fn merged_named_and_direct_links_keep_per_source_destinations() -> Result<()> {
        let dir = tempfile::tempdir()?;
        for version in ["1.7", "2.0"] {
            let mut doc = Document::with_version(version);
            let pages = doc.new_object_id();
            let first = doc.add_object(dictionary! {"Type"=>"Page", "Parent"=>pages});
            let second = doc.add_object(dictionary! {"Type"=>"Page", "Parent"=>pages});
            doc.objects.insert(pages, Object::Dictionary(dictionary! {"Type"=>"Pages", "Kids"=>vec![Object::Reference(first),Object::Reference(second)], "Count"=>2, "MediaBox"=>vec![0.into(),0.into(),100.into(),200.into()]}));
            let dest = Object::Array(vec![
                second.into(),
                Object::Name(b"XYZ".to_vec()),
                20.into(),
                30.into(),
                Object::Real(1.5),
            ]);
            let named = doc.add_object(dictionary! {"Type"=>"Annot", "Subtype"=>"Link", "Rect"=>vec![0.into(),0.into(),20.into(),20.into()], "A"=>dictionary! {"S"=>"GoTo", "D"=>Object::string_literal("target")}});
            let direct = doc.add_object(dictionary! {"Type"=>"Annot", "Subtype"=>"Link", "Rect"=>vec![0.into(),20.into(),20.into(),40.into()], "Dest"=>dest.clone()});
            let external = doc.add_object(dictionary! {"Type"=>"Annot", "Subtype"=>"Link", "Rect"=>vec![0.into(),40.into(),20.into(),60.into()], "A"=>dictionary! {"S"=>"URI", "URI"=>Object::string_literal("https://example.org/")}});
            doc.get_dictionary_mut(first)?.set(
                "Annots",
                vec![
                    Object::Reference(named),
                    Object::Reference(direct),
                    Object::Reference(external),
                ],
            );
            let catalog = doc.add_object(dictionary! {"Type"=>"Catalog", "Pages"=>pages, "Names"=>dictionary! {"Dests"=>dictionary! {"Names"=>vec![Object::string_literal("target"),dest]}}});
            doc.trailer.set("Root", catalog);
            let source = dir.path().join(format!("{version}.pdf"));
            let output = dir.path().join(format!("merged-{version}.pdf"));
            doc.save(&source)?;
            assert_eq!(merge_with_hash(&[&source, &source], &output)?.0, 4);
            let merged = Document::load(output)?;
            assert_eq!(merged.version, version);
            let pages: Vec<_> = merged.get_pages().into_values().collect();
            assert_eq!(pages.len(), 4);
            for offset in [0, 2] {
                let annotations = merged
                    .get_dictionary(pages[offset])?
                    .get(b"Annots")?
                    .as_array()?;
                let named = merged.get_dictionary(annotations[0].as_reference()?)?;
                let action = named.get(b"A")?.as_dict()?;
                let named_dest = action.get(b"D")?.as_array()?;
                let direct = merged
                    .get_dictionary(annotations[1].as_reference()?)?
                    .get(b"Dest")?
                    .as_array()?;
                for dest in [named_dest, direct] {
                    assert_eq!(dest[0].as_reference()?, pages[offset + 1]);
                    assert_eq!(dest[1].as_name()?, b"XYZ");
                    assert_eq!(dest[2].as_i64()?, 20);
                    assert_eq!(dest[3].as_i64()?, 30);
                    assert_eq!(dest[4].as_float()?, 1.5);
                }
                let external = merged
                    .get_dictionary(annotations[2].as_reference()?)?
                    .get(b"A")?
                    .as_dict()?;
                assert_eq!(external.get(b"URI")?.as_str()?, b"https://example.org/");
            }
        }
        Ok(())
    }
}
