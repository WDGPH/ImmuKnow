//! Small brace-placeholder formatter shared by passwords and artifact names.
use anyhow::{Result, bail, ensure};

pub(crate) fn expand(
    template: &str,
    mut value: impl FnMut(&str) -> Result<String>,
) -> Result<String> {
    let mut chars = template.chars().peekable();
    let mut out = String::with_capacity(template.len());
    while let Some(ch) = chars.next() {
        match ch {
            '{' if chars.next_if_eq(&'{').is_some() => {
                out.push('{');
            }
            '}' if chars.next_if_eq(&'}').is_some() => {
                out.push('}');
            }
            '{' => {
                let mut field = String::new();
                let mut closed = false;
                for ch in chars.by_ref() {
                    if ch == '}' {
                        closed = true;
                        break;
                    }
                    field.push(ch);
                }
                ensure!(closed, "Unclosed template placeholder");
                out.push_str(&value(&field)?);
            }
            '}' => bail!("Unmatched closing brace in template"),
            ch => out.push(ch),
        }
    }
    Ok(out)
}
