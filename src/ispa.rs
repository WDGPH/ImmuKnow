//! ISPA disease scope for supplied overdue diseases; upstream systems assess whether doses are overdue.
//! Keep in step with `resources/typst/src/ispa.typ`, which remains the fallback for notices
//! prepared without this classification.
//! https://www.ontario.ca/page/vaccines-children-school
//! https://www.ontario.ca/laws/regulation/900645 (Table 1)
use chrono::{Datelike, NaiveDate};
use serde_json::{Value, json};
use std::collections::BTreeSet;

const ALWAYS: &[&str] = &[
    "Diphtheria",
    "Tetanus",
    "Polio",
    "Measles",
    "Mumps",
    "Rubella",
    "Pertussis",
];

pub struct Classification {
    pub status: &'static str,
    pub overdue: Vec<Value>,
    pub undetermined: Vec<String>,
    /// Facts whose absence left a disease undetermined: `date_of_birth` or `date_as_of`.
    pub missing: BTreeSet<&'static str>,
}

impl Classification {
    pub fn notice_value(&self) -> Value {
        json!({
            "status": self.status,
            "overdue_diseases": self.overdue,
            "undetermined_diseases": self.undetermined,
        })
    }
}

fn ymd(y: i32, m: u32, d: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(y, m, d).unwrap()
}

/// `Some(in_scope)`, or `Err(missing fact)` when the cohort cannot be decided.
fn in_scope(
    disease: &str,
    birth: Option<NaiveDate>,
    as_of: Option<NaiveDate>,
) -> Result<bool, &'static str> {
    if ALWAYS.contains(&disease) {
        return Ok(true);
    }
    match disease {
        "Varicella" => Ok(birth.ok_or("date_of_birth")? >= ymd(2010, 1, 1)),
        "Meningococcal" => {
            let born = birth.ok_or("date_of_birth")?;
            if born >= ymd(2004, 9, 1) {
                return Ok(true);
            }
            if born < ymd(1997, 1, 1) {
                return Ok(false);
            }
            // Earlier eligible cohorts enter the requirement at age 12.
            let as_of = as_of.ok_or("date_as_of")?;
            Ok((as_of.year(), as_of.month(), as_of.day())
                >= (born.year() + 12, born.month(), born.day()))
        }
        _ => Ok(false),
    }
}

pub fn classify(
    overdue: &[Value],
    birth: Option<NaiveDate>,
    as_of: Option<NaiveDate>,
) -> Classification {
    let mut result = Classification {
        status: "no_ispa_overdue",
        overdue: vec![],
        undetermined: vec![],
        missing: BTreeSet::new(),
    };
    for entry in overdue {
        let disease = entry["disease"].as_str().unwrap_or("");
        match in_scope(disease, birth, as_of) {
            Ok(true) => result.overdue.push(entry.clone()),
            Ok(false) => {}
            Err(missing) => {
                result.missing.insert(missing);
                if !result.undetermined.iter().any(|d| d == disease) {
                    result.undetermined.push(disease.to_owned());
                }
            }
        }
    }
    result.status = if !result.overdue.is_empty() {
        "ispa_overdue"
    } else if !result.undetermined.is_empty() {
        "ispa_unknown"
    } else {
        "no_ispa_overdue"
    };
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn date(text: &str) -> Option<NaiveDate> {
        Some(NaiveDate::parse_from_str(text, "%Y-%m-%d").unwrap())
    }
    fn diseases(names: &[&str]) -> Vec<Value> {
        names
            .iter()
            .map(|d| json!({"disease": d, "dose": null}))
            .collect()
    }
    fn scoped(names: &[&str], birth: &str, as_of: &str) -> Vec<String> {
        classify(&diseases(names), date(birth), date(as_of))
            .overdue
            .iter()
            .map(|e| e["disease"].as_str().unwrap().to_owned())
            .collect()
    }

    #[test]
    fn always_scoped_diseases_need_no_dates() {
        let c = classify(&diseases(&["Measles", "Hepatitis B"]), None, None);
        assert_eq!(c.status, "ispa_overdue");
        assert_eq!(c.overdue, diseases(&["Measles"]));
        assert!(c.undetermined.is_empty() && c.missing.is_empty());
    }

    #[test]
    fn varicella_starts_with_the_2010_cohort() {
        assert!(scoped(&["Varicella"], "2009-12-31", "2026-11-01").is_empty());
        assert_eq!(
            scoped(&["Varicella"], "2010-01-01", "2026-11-01"),
            ["Varicella"]
        );
    }

    #[test]
    fn meningococcal_cohort_boundaries() {
        let m = &["Meningococcal"];
        assert!(scoped(m, "1996-12-31", "2026-11-01").is_empty());
        assert_eq!(scoped(m, "2004-09-01", "2005-01-01"), ["Meningococcal"]);
        // 2004-08-31 is in the age-12 cohort.
        assert!(scoped(m, "2004-08-31", "2016-08-30").is_empty());
        assert_eq!(scoped(m, "2004-08-31", "2016-08-31"), ["Meningococcal"]);
        assert!(scoped(m, "1997-01-01", "2008-12-31").is_empty());
        assert_eq!(scoped(m, "1997-01-01", "2009-01-01"), ["Meningococcal"]);
    }

    #[test]
    fn leap_day_birthdays_compare_like_iso_text() {
        let m = &["Meningococcal"];
        assert!(scoped(m, "2000-02-29", "2012-02-28").is_empty());
        assert_eq!(scoped(m, "2000-02-29", "2012-02-29"), ["Meningococcal"]);
        assert_eq!(scoped(m, "2000-02-29", "2013-02-28"), ["Meningococcal"]);
    }

    #[test]
    fn missing_facts_leave_diseases_undetermined() {
        let c = classify(&diseases(&["Varicella", "Varicella"]), None, None);
        assert_eq!(c.status, "ispa_unknown");
        assert_eq!(c.undetermined, ["Varicella"]);
        assert_eq!(c.missing, BTreeSet::from(["date_of_birth"]));

        let c = classify(&diseases(&["Meningococcal"]), date("2000-05-01"), None);
        assert_eq!(c.status, "ispa_unknown");
        assert_eq!(c.missing, BTreeSet::from(["date_as_of"]));
    }

    #[test]
    fn a_scoped_disease_settles_status_despite_undetermined_ones() {
        let c = classify(&diseases(&["Meningococcal", "Tetanus"]), None, None);
        assert_eq!(c.status, "ispa_overdue");
        assert_eq!(c.overdue, diseases(&["Tetanus"]));
        assert_eq!(c.undetermined, ["Meningococcal"]);
    }

    #[test]
    fn nothing_in_scope() {
        for overdue in [vec![], diseases(&["Hepatitis B", "HPV"])] {
            let c = classify(&overdue, date("2012-01-01"), date("2026-11-01"));
            assert_eq!(c.status, "no_ispa_overdue");
            assert!(c.overdue.is_empty() && c.undetermined.is_empty());
        }
    }

    #[test]
    fn scoped_entries_keep_dose_details() {
        let entry = json!({"disease": "Polio", "dose": null, "dose_raw": "x"});
        let c = classify(
            &[entry.clone(), json!({"disease": "Polio", "dose": 2})],
            None,
            None,
        );
        assert_eq!(c.overdue, [entry, json!({"disease": "Polio", "dose": 2})]);
    }
}
