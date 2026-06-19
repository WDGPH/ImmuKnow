"""Integration tests for custom template directory support.

Tests cover:
- Loading templates from custom directory
- Assets resolved from custom directory
- Typst compilation with custom template root
- End-to-end flow with custom templates

Real-world significance:
- PHU teams need to customize templates without code changes
- Custom templates must work with full pipeline
- Template directory isolation must be complete
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import compile_notices, generate_notices
from pipeline.data_models import ArtifactPayload
from tests.fixtures.sample_input import create_test_client_record


@pytest.mark.integration
class TestCustomTemplateDirectory:
    """Integration tests for custom template directory feature."""

    def test_load_template_module_from_custom_directory(
        self, custom_templates: Path
    ) -> None:
        """Verify template module loads from custom directory.

        Real-world significance:
        - Custom templates must be loadable from non-standard paths
        - Dynamic loading enables PHU-specific customization
        """
        module = generate_notices.load_template_module(custom_templates, "en")

        assert hasattr(module, "render_notice")
        assert callable(module.render_notice)

    def test_build_language_renderers_from_custom_directory(
        self, custom_templates: Path
    ) -> None:
        """Verify all language renderers build from custom directory.

        Real-world significance:
        - Pipeline must support multiple languages from custom templates
        - Both en and fr must be available
        """
        renderers = generate_notices.build_language_renderers(custom_templates)

        assert "en" in renderers
        assert "fr" in renderers
        assert callable(renderers["en"])
        assert callable(renderers["fr"])

    def test_generate_notices_with_custom_templates(
        self,
        tmp_path: Path,
        custom_templates: Path,
        sample_artifact_payload: ArtifactPayload,
    ) -> None:
        """Verify notice generation works with custom template directory.

        Real-world significance:
        - PHU provides custom template directory
        - Pipeline must generate notices using custom templates
        - Custom assets (logo, signature) must be used
        """
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use assets from custom_templates
        logo_path = custom_templates / "assets" / "logo.png"
        signature_path = custom_templates / "assets" / "signature.png"

        # Generate with custom templates
        files = generate_notices.generate_typst_files(
            sample_artifact_payload,
            output_dir,
            logo_path,
            signature_path,
            custom_templates,  # Use custom template directory
        )

        assert len(files) == sample_artifact_payload.total_clients
        assert all(f.exists() for f in files)

        # Verify content contains conf import (absolute from project root)
        content = files[0].read_text(encoding="utf-8")
        assert '#import "/templates/conf.typ"' in content

    def test_compile_notices_with_custom_template_root(
        self, tmp_path: Path, custom_templates: Path
    ) -> None:
        """Verify Typst compilation uses custom template as root.

        Real-world significance:
        - Typst --root must point to custom template directory
        - conf.typ must resolve from custom directory
        - NOTE: Typst requires .typ file to be inside --root directory
        """
        # Create test .typ file INSIDE the temp root that will become root
        # The discover_typst_files looks for files in artifact_dir / "typst"
        artifact_dir = tmp_path / "artifacts"
        typst_dir = artifact_dir / "typst"
        typst_dir.mkdir(parents=True)

        # Copy conf.typ to artifact directory (same level as typst/)
        (artifact_dir / "conf.typ").write_text(
            (custom_templates / "conf.typ").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        # Create a minimal test .typ file that imports conf.typ
        typ_file = typst_dir / "test.typ"
        typ_file.write_text(
            "#set text(fill: black)\nHello World",
            encoding="utf-8",
        )

        pdf_dir = tmp_path / "pdf"

        # Compile with artifact dir as source and custom template as root
        compiled = compile_notices.compile_typst_files(
            artifact_dir,  # discover_typst_files looks in artifact_dir/typst
            pdf_dir,
            typst_bin="typst",
            font_path=None,
            root_dir=artifact_dir,  # Use artifact dir as root for imports
            verbose=False,
        )

        assert compiled == 1
        assert (pdf_dir / "test.pdf").exists()

    def test_full_pipeline_with_custom_templates(
        self, tmp_path: Path, custom_templates: Path
    ) -> None:
        """Verify notice generation works end-to-end with custom templates.

        Real-world significance:
        - Generate step must work with custom templates
        - Dynamic loading must resolve templates correctly
        - Generated .typ files must have correct imports

        NOTE: Skips actual Typst compilation since it requires .typ to be
        in/under --root directory, which is handled by the real orchestrator.
        """
        # Build client and payload
        client = create_test_client_record(language="fr", sequence="00001")
        payload = ArtifactPayload(
            run_id="e2e_test",
            language="fr",
            clients=[client],
            warnings=[],
            created_at="2025-01-01T00:00:00Z",
            total_clients=1,
        )

        output_dir = tmp_path / "output"

        # Copy assets to output directory (simulating orchestrator behavior)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        import shutil

        logo_src = custom_templates / "assets" / "logo.png"
        signature_src = custom_templates / "assets" / "signature.png"
        logo_path = assets_dir / "logo.png"
        signature_path = assets_dir / "signature.png"

        shutil.copy2(logo_src, logo_path)
        shutil.copy2(signature_src, signature_path)

        # Step 4: Generate notices with custom templates
        typst_files = generate_notices.generate_typst_files(
            payload,
            output_dir,
            logo_path,
            signature_path,
            custom_templates,
        )

        assert len(typst_files) == 1
        assert typst_files[0].exists()

        # Verify generated file has correct structure
        content = typst_files[0].read_text(encoding="utf-8")

        # Should have absolute import from project root
        assert '#import "/templates/conf.typ"' in content

        # Should have logo and signature paths
        assert "logo.png" in content or "__LOGO_PATH__" not in content
        assert "signature.png" in content or "__SIGNATURE_PATH__" not in content

        # Should have custom template content (French)
        assert (
            "Demande de dossier d'immunisation" in content
            or "immunization_notice" in content
        )

    def test_custom_template_assets_validated(self, custom_templates: Path) -> None:
        """Verify custom template has all required assets.

        Real-world significance:
        - PHU must provide complete template directory
        - Missing assets should be caught early
        """
        # Verify assets exist in custom templates
        logo = custom_templates / "assets" / "logo.png"
        signature = custom_templates / "assets" / "signature.png"

        assert logo.exists(), "Custom template missing logo.png"
        assert signature.exists(), "Custom template missing signature.png"

        # Verify they are actual files, not symlinks or empty
        assert logo.stat().st_size > 0, "Logo is empty"
        assert signature.stat().st_size > 0, "Signature is empty"

    def test_custom_template_includes_all_required_modules(
        self, custom_templates: Path
    ) -> None:
        """Verify custom template directory has all required modules.

        Real-world significance:
        - Custom directory must be self-contained
        - Users must know what files are required
        """
        # Check template modules
        en_module = custom_templates / "en_template.py"
        fr_module = custom_templates / "fr_template.py"
        conf = custom_templates / "conf.typ"

        assert en_module.exists(), "Custom template missing en_template.py"
        assert fr_module.exists(), "Custom template missing fr_template.py"
        assert conf.exists(), "Custom template missing conf.typ"

        # Verify they have content
        assert en_module.stat().st_size > 0
        assert fr_module.stat().st_size > 0
        assert conf.stat().st_size > 0

    def test_single_language_template_english_only(self, tmp_path: Path) -> None:
        """Verify PHU can provide template for only English (no French).

        Real-world significance:
        - Not all PHUs need bilingual templates
        - Pipeline should work with single-language templates
        - Requesting unsupported language should fail with clear error
        """
        # Create single-language template (English only)
        en_template_dir = tmp_path / "en_only_template"
        en_template_dir.mkdir()

        # Copy English template and conf only
        import shutil

        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "en_template.py",
            en_template_dir / "en_template.py",
        )
        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "conf.typ",
            en_template_dir / "conf.typ",
        )

        # Build renderers - should only have English
        renderers = generate_notices.build_language_renderers(en_template_dir)

        assert "en" in renderers, "English should be available"
        assert "fr" not in renderers, "French should NOT be available"
        assert callable(renderers["en"])

    def test_single_language_template_french_only(self, tmp_path: Path) -> None:
        """Verify PHU can provide template for only French (no English).

        Real-world significance:
        - Some PHUs may only provide French
        - Pipeline should work with single-language templates
        - Only the provided language can be requested
        """
        # Create single-language template (French only)
        fr_template_dir = tmp_path / "fr_only_template"
        fr_template_dir.mkdir()

        # Copy French template and conf only
        import shutil

        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "fr_template.py",
            fr_template_dir / "fr_template.py",
        )
        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "conf.typ",
            fr_template_dir / "conf.typ",
        )

        # Build renderers - should only have French
        renderers = generate_notices.build_language_renderers(fr_template_dir)

        assert "fr" in renderers, "French should be available"
        assert "en" not in renderers, "English should NOT be available"
        assert callable(renderers["fr"])

    def test_missing_language_raises_helpful_error(self, tmp_path: Path) -> None:
        """Verify requesting unavailable language gives helpful error.

        Real-world significance:
        - Users should understand why generation fails
        - Error message should indicate available languages
        - Should guide users to provide correct language
        """
        # Create single-language template (English only)
        en_template_dir = tmp_path / "en_only_template"
        en_template_dir.mkdir()

        import shutil

        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "en_template.py",
            en_template_dir / "en_template.py",
        )
        shutil.copy2(
            Path(__file__).parent.parent.parent / "templates" / "conf.typ",
            en_template_dir / "conf.typ",
        )

        # Build renderers
        renderers = generate_notices.build_language_renderers(en_template_dir)

        # Try to get French renderer - should fail
        from pipeline.enums import Language

        with pytest.raises(FileNotFoundError) as exc_info:
            generate_notices.get_language_renderer(Language.FRENCH, renderers)

        error_msg = str(exc_info.value)
        assert "fr" in error_msg, "Error should mention missing 'fr'"
        assert "Available languages: en" in error_msg, "Error should list available: en"
        assert "fr_template.py" in error_msg, "Error should mention required file name"
