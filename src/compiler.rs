//! Persistent compilation with official Typst and project-local imports.
use chrono::{DateTime, Datelike, Timelike, Utc};
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::Arc;
use typst::diag::{FileError, FileResult, Warned};
use typst::foundations::{
    Bytes, Datetime, Dict, Duration, IntoValue, Label, NativeElement, Selector,
};
use typst::introspection::Introspector;
use typst::pdf::AttachElem;
use typst::syntax::{FileId, RootedPath, Source, VirtualPath, VirtualRoot};
use typst::text::{Font, FontBook};
use typst::utils::LazyHash;
use typst::{Library, LibraryExt, World};
use typst_kit::datetime::Time;
use typst_kit::diagnostics::{DiagnosticFormat, DiagnosticWorld};
use typst_kit::files::{FileLoader, FileStore, FsRoot};
use typst_kit::fonts::{self, FontStore};
use typst_layout::PagedDocument;

pub struct Request {
    pub inputs: BTreeMap<String, String>,
    pub notice: serde_json::Value,
    pub timestamp: i64,
}
pub struct Compiled {
    pub pdf: Vec<u8>,
    pub reports: Result<serde_json::Value, String>,
    pub diagnostics: String,
    pub pages: usize,
}
struct Loader {
    root: FsRoot,
    entry: FileId,
    active: FileId,
    notice: Bytes,
}
impl FileLoader for Loader {
    fn load(&self, id: FileId) -> FileResult<Bytes> {
        if id == self.entry {
            return Ok(Bytes::new(
                "#include sys.inputs.at(\"immuknow-template-path\")\n".as_bytes(),
            ));
        }
        if id == self.active {
            return Ok(self.notice.clone());
        }
        match id.root() {
            VirtualRoot::Project => self.root.load(id.vpath()),
            VirtualRoot::Package(_) => Err(FileError::Other(Some(
                "Package imports are not supported; use project-relative paths".into(),
            ))),
        }
    }
}
pub struct Compiler {
    library: LazyHash<Library>,
    files: FileStore<Loader>,
    fonts: Arc<FontStore>,
    now: Time,
}
impl World for Compiler {
    fn library(&self) -> &LazyHash<Library> {
        &self.library
    }
    fn book(&self) -> &LazyHash<FontBook> {
        self.fonts.book()
    }
    fn main(&self) -> FileId {
        self.files.loader().entry
    }
    fn source(&self, id: FileId) -> FileResult<Source> {
        self.files.source(id)
    }
    fn file(&self, id: FileId) -> FileResult<Bytes> {
        self.files.file(id)
    }
    fn font(&self, index: usize) -> Option<Font> {
        self.fonts.font(index)
    }
    fn today(&self, offset: Option<Duration>) -> Option<Datetime> {
        self.now.today(offset)
    }
}
impl DiagnosticWorld for Compiler {
    fn name(&self, id: FileId) -> String {
        id.vpath().get_with_slash().to_string()
    }
}
impl Compiler {
    pub fn fonts() -> Arc<FontStore> {
        let mut fonts = FontStore::new();
        // Match stock CLI discovery order and its two ignore-font settings.
        if std::env::var("TYPST_IGNORE_SYSTEM_FONTS").as_deref() != Ok("true") {
            fonts.extend(fonts::system());
        }
        if std::env::var("TYPST_IGNORE_EMBEDDED_FONTS").as_deref() != Ok("true") {
            fonts.extend(fonts::embedded());
        }
        if let Some(paths) = std::env::var_os("TYPST_FONT_PATHS") {
            for path in std::env::split_paths(&paths) {
                fonts.extend(fonts::scan(&path));
            }
        }
        Arc::new(fonts)
    }
    pub fn new(root: PathBuf, fonts: Arc<FontStore>) -> Self {
        let id =
            |path| RootedPath::new(VirtualRoot::Project, VirtualPath::new(path).unwrap()).intern();
        Self {
            library: LazyHash::new(Library::builder().build()),
            files: FileStore::new(Loader {
                root: FsRoot::new(root),
                entry: id("/__immuknow_entry__.typ"),
                active: id("/__immuknow_active__.json"),
                notice: Bytes::new([]),
            }),
            fonts,
            now: Time::fixed_timestamp(0).unwrap(),
        }
    }
    pub fn run(&mut self, request: &Request) -> Result<Compiled, String> {
        // The compiler is reused across rows, but cached files must not retain
        // the previous row's virtual JSON or project file contents.
        self.files.reset();
        self.files.loader_mut().notice =
            Bytes::new(serde_json::to_vec(&request.notice).map_err(|e| e.to_string())?);
        let mut inputs = request.inputs.clone();
        inputs.insert("data".into(), "/__immuknow_active__.json".into());
        let inputs: Dict = inputs
            .into_iter()
            .map(|(key, value)| (key.into(), value.into_value()))
            .collect();
        self.library = LazyHash::new(Library::builder().with_inputs(inputs).build());
        self.now = Time::fixed_timestamp(request.timestamp).map_err(|e| e.to_string())?;
        let Warned { output, warnings } = typst::compile::<PagedDocument>(self);
        let mut buffer = codespan_reporting::term::termcolor::Buffer::no_color();
        let errors = output.as_ref().err().map_or(&[][..], |errors| &errors[..]);
        typst_kit::diagnostics::emit(
            &mut buffer,
            self,
            errors.iter().chain(warnings.iter()),
            DiagnosticFormat::Human,
        )
        .map_err(|e| e.to_string())?;
        let diagnostics = String::from_utf8(buffer.into_inner()).map_err(|e| e.to_string())?;
        let document = match output {
            Ok(document) => document,
            Err(_) => {
                return Err(diagnostics);
            }
        };
        if document
            .introspector()
            .query(&AttachElem::ELEM.select())
            .iter()
            .any(|item| {
                item.to_packed::<AttachElem>()
                    .unwrap()
                    .path
                    .derived
                    .as_str()
                    == "immuknow-evidence.json"
            })
        {
            return Err("immuknow-evidence.json is reserved for internal render evidence".into());
        }
        // Evidence extraction can fail independently of PDF export; return both
        // outcomes so the caller can retain a usable original for review.
        let reports = (|| -> Result<serde_json::Value, String> {
            let selector = Selector::Label(
                Label::new(typst::utils::PicoStr::intern("immuknow-report")).unwrap(),
            );
            let values = document
                .introspector()
                .query(&selector)
                .iter()
                .map(|item| item.field_by_name("value"))
                .collect::<Result<Vec<_>, _>>()
                .map_err(|e| e.to_string())?;
            serde_json::to_value(values).map_err(|e| e.to_string())
        })();
        let dt: DateTime<Utc> =
            DateTime::from_timestamp(request.timestamp, 0).ok_or("Invalid timestamp")?;
        let date = Datetime::from_ymd_hms(
            dt.year(),
            dt.month() as u8,
            dt.day() as u8,
            dt.hour() as u8,
            dt.minute() as u8,
            dt.second() as u8,
        )
        .ok_or("Invalid timestamp")?;
        let options = typst_pdf::PdfOptions {
            timestamp: Some(typst_pdf::Timestamp::new_utc(date)),
            ..Default::default()
        };
        let pdf =
            typst_pdf::pdf(&document, &options).map_err(|e| format!("PDF export failed: {e:?}"))?;
        Ok(Compiled {
            pdf,
            reports,
            diagnostics,
            pages: document.pages().len(),
        })
    }
}
