# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

<!-- insertion marker -->
## [v1.1.0](https://github.com/WDGPH/ImmuKnow/releases/tag/v1.1.0) - 2026-08-27

<small>[Compare with v1.0.0](https://github.com/WDGPH/ImmuKnow/compare/v1.0.0...v1.1.0)</small>

### Added

- Notice versioning (assignment manifest mode): a new optional mode that maps each client to a specific notice version and language via a JSON assignment manifest. When `--notice-assignments <file>` is provided and `config/notice_versions.yaml` exists, the pipeline dispatches each client to the correct template and language individually - enabling a single run to produce overdue, affirmative, and informational notices in mixed languages. When the catalog file is absent, the pipeline behaves identically to before.
- Example `config/notice_versions.yaml` with `overdue_standard_v1` and `affirmative_schedule_v1`.

### Changed

- Switch input schema from fuzzy matching / data normalization to enforced Frictionless schema validation. Add schema page to mkdocs.
- Minimize required columns by deriving where possible.
- Adopt `lower_snake_case` column naming.
- Check client information completeness during preprocessing: records missing `first_name`, `last_name`, `date_of_birth`, `client_id`, `school_name`, `overdue_disease`, or `imms_given` are logged and written to `output/incomplete_clients.csv`; like the address completeness check, by default incomplete records are dropped before further processing.
- Address and client info completeness checks able to be toggled to drop or retain incomplete records (e.g. students with incomplete address may still receive their notice through email).

## [v1.0.0](https://github.com/WDGPH/ImmuKnow/releases/tag/v1.0.0) - 2026-08-13

<small>[Compare with v0.3.0](https://github.com/WDGPH/ImmuKnow/compare/v0.3.0...v1.0.0)</small>

### Added

- **PHIX school validation**: new `validate_phix` module cross-references schools and daycares in the input against the PHIX facility reference list for the selected PHU. Matches are classified `exact` when the normalized name is found in the PHU mapping and the facility IDs match. Configurable via `parameters.yaml` ([#195](https://github.com/WDGPH/ImmuKnow/pull/195)).
- Bundle PHIX facility reference mapping (`config/phix_mapping.json`) with the package ([#195](https://github.com/WDGPH/ImmuKnow/pull/195)).
- Add next-dose information to output: dose numbers in the overdue disease list, with a config flag to toggle dose info and validity markers on/off ([#192](https://github.com/WDGPH/ImmuKnow/pull/192)).
- Add option to remove the border around the client information box in templates ([#156](https://github.com/WDGPH/ImmuKnow/pull/156)).
- Add MkDocs documentation site with user guide, API reference, architecture overview, pipeline step reference, and developer guide, deployed via GitHub Actions.

### Changed

- Rename project from "Immunization Charts (python Version)" to **ImmuKnow** in README and documentation.
- Merge `ensure_required_columns` into `normalize_dataframe` to eliminate a redundant preprocessing pass ([#190](https://github.com/WDGPH/ImmuKnow/pull/190)).
- Expand and restructure test suite: renamed test modules, added E2E smoke test with encryption enabled, consolidated integration contract tests ([#161](https://github.com/WDGPH/ImmuKnow/pull/161)).
- Update Typst to v0.14.2 in GitHub Actions CI.
- Multiple dependency updates (automated via Dependabot).

### Fixed

- Resolve type checker errors flagged by `ty` ([#160](https://github.com/WDGPH/ImmuKnow/pull/160)).
- Fix `over_16` logic in test suite.

### Security

- Remove contributor names and email addresses from committed files ([#182](https://github.com/WDGPH/ImmuKnow/pull/182)).

## [v0.3.0](https://github.com/WDGPH/immunization-charts-python/releases/tag/v0.3.0) - 2026-01-09

<small>[Compare with first commit](https://github.com/WDGPH/immunization-charts-python/compare/03e764568766269de71e0fef45cf0f390295cef3...v0.3.0)</small>

### Added

- Adding changes to immunization table for proper translation ([8e1869d](https://github.com/WDGPH/immunization-charts-python/commit/8e1869d4acee3ef060eceb06dddeb1b59ab56260) by kassyray).
- Adding logo size ([4e40f42](https://github.com/WDGPH/immunization-charts-python/commit/4e40f42bcb0a0bc53b014f4c9c438b43a65dc025) by kassyray).
- Adding submodules to gitignore ([ecce168](https://github.com/WDGPH/immunization-charts-python/commit/ecce168c2a527b5fd9efe4bd0cb5866acf06f724) by kassyray).
- Adding address missingness checker #115 ([64b8107](https://github.com/WDGPH/immunization-charts-python/commit/64b8107e72fc5311cc8e4e1fc2d4bcc584920ce9) by kassyray).
- Adding row with incomplete address to the testing dataset for #115 ([9930335](https://github.com/WDGPH/immunization-charts-python/commit/9930335e853d46985e5833f5ddee9a18b95cea5c) by kassyray).
- Add unit tests for map_columns function to verify exact and inexact column name mappings ([d1fe172](https://github.com/WDGPH/immunization-charts-python/commit/d1fe1728bc6d5906569e4f1dccb0e52c8060bdd1) by kassyray).
- Add threshold constant and update normalization logic in preprocess module ([25c962a](https://github.com/WDGPH/immunization-charts-python/commit/25c962ae7fc48347a6913accd6613b47ac7f1034) by kassyray).
- Add unit tests for normalize and filter_columns functions in preprocess module ([26ca2d4](https://github.com/WDGPH/immunization-charts-python/commit/26ca2d457ce61ecfcb90b999d2f96526fcf17e12) by kassyray).
- Add tests for custom template directory support, covering loading, assets, and compilation. Catch remaining issues with custom directories. ([248357f](https://github.com/WDGPH/immunization-charts-python/commit/248357fecde560d13fdf98470df69bea63261b37) by Justin Angevaare).
- Add template directory parameter to compilation functions ([097bca2](https://github.com/WDGPH/immunization-charts-python/commit/097bca20727c3d751e22b9be53f467a9216d24b6) by Justin Angevaare).
- Added rapidfuzz ([fa0b163](https://github.com/WDGPH/immunization-charts-python/commit/fa0b16394f1d2b356c50b41d6f00e532a64896e7) by kassyray).
- Add docstring to map_columns function for clarity on parameters and behavior - cherry picked column mapper from another branch to clean up. #107 ([1483cba](https://github.com/WDGPH/immunization-charts-python/commit/1483cbac19e62d051adb8d0e72403dd0d57c2102) by kassyray).
- Add template directory argument and validation in orchestrator ([1b7ba28](https://github.com/WDGPH/immunization-charts-python/commit/1b7ba280f9b3687989c0a33ed78f8358caf7c84d) by Justin Angevaare).
- Adding specific instructions about naming PHUs. Closes #45. ([7a3f026](https://github.com/WDGPH/immunization-charts-python/commit/7a3f0267c2f8e385b32e0588e6df75b56b15124a) by kassyray).
- Added information about tools used and code coverage to documentation #100 ([f1c17e8](https://github.com/WDGPH/immunization-charts-python/commit/f1c17e8309723d735f6d6551127c308a1b80b4c0) by kassyray).
- Add envelope_window_height parameter to client_info_tbl functions and update table row height #70 ([9c472c6](https://github.com/WDGPH/immunization-charts-python/commit/9c472c6aa62bc539a3fb8835fb33cf05306dde1f) by kassyray).
- Added additional test for page_count type in test_validate_pdfs.py (assertion in test_validation_includes_measurements) ([25bd931](https://github.com/WDGPH/immunization-charts-python/commit/25bd931a530a381e5f2065be432150a036f51e61) by TiaTuinstra).
- Add childcare center designation to English and French template client info functions ([f0d768e](https://github.com/WDGPH/immunization-charts-python/commit/f0d768ef2b79152425f9e52bf08e64bad737bbe7) by kassyray).
- Add school_type parameter to client_info_tbl_en and client_info_tbl_fr functions ([6007937](https://github.com/WDGPH/immunization-charts-python/commit/60079373047b710576e1fb0c6b97f1cad69900b2) by kassyray).

### Fixed

- Fixes #90 ([9ef462e](https://github.com/WDGPH/immunization-charts-python/commit/9ef462e9ef80a92faa53cbafacf26cc88d942fbc) by kassyray).

### Changed

- Changes to size so that french translation is formatted more nicely in header ([89db891](https://github.com/WDGPH/immunization-charts-python/commit/89db8915cf1cf1db2e5737c04ce573cd19c69986) by kassyray).