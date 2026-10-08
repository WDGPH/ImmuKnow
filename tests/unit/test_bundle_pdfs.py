"""Unit tests for bundle_pdfs module - PDF bundling for distribution.

Tests cover:
- Bundle grouping strategies (size, school, board)
- Bundle manifest generation
- Error handling for empty bundles
- Bundle metadata tracking

Real-world significance:
- Step 7 of pipeline (optional): groups PDFs into bundles by school/size
- Enables efficient shipping of notices to schools and districts
- Bundling strategy affects how notices are organized for distribution
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import bundle_pdfs
from pipeline.data_models import PdfRecord
from pipeline.enums import BundleStrategy, BundleType
from pipeline.utils import deserialize_client_record
from tests.fixtures import sample_input


def artifact_to_dict(artifact) -> dict:
    clients_dicts = [
        {
            "sequence": client.sequence,
            "client_id": client.client_id,
            "language": client.language,
            "person": client.person,
            "school": client.school,
            "board": client.board,
            "contact": client.contact,
            "vaccines_due": client.vaccines_due,
            "vaccines_due_list": client.vaccines_due_list,
            "received": list(client.received) if client.received else [],
            "metadata": client.metadata,
            "qr": client.qr,
        }
        for client in artifact.clients
    ]

    return {
        "run_id": artifact.run_id,
        "language": artifact.language,
        "clients": clients_dicts,
        "warnings": artifact.warnings,
        "created_at": artifact.created_at,
        "input_file": artifact.input_file,
        "total_clients": artifact.total_clients,
    }


def client_lookup(artifact: dict) -> dict:
    """Select canonical clients for grouping fixtures."""
    return {
        (client["sequence"], client["client_id"]): client
        for client in artifact["clients"]
    }


def create_test_pdf(path: Path, num_pages: int = 1) -> None:
    """Create a minimal test PDF file using PyPDF utilities."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f)


def make_pdf_records(clients: dict, output_dir: Path) -> list[PdfRecord]:
    """Pair canonical client records with the PDFs created by a test."""
    from pypdf import PdfReader

    pdf_dir = output_dir / "pdf_individual"
    return [
        PdfRecord(
            sequence=sequence,
            client_id=client_id,
            pdf_path=pdf_dir / f"en_notice_{sequence}_{client_id}.pdf",
            page_count=len(
                PdfReader(pdf_dir / f"en_notice_{sequence}_{client_id}.pdf").pages
            ),
            client=deserialize_client_record(client),
        )
        for (sequence, client_id), client in sorted(clients.items())
    ]


@pytest.mark.unit
class TestChunked:
    def test_chunked_splits_into_equal_sizes(self) -> None:
        items = [1, 2, 3, 4, 5, 6]
        chunks = list(bundle_pdfs.chunked(items, 2))
        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5, 6]

    def test_chunked_handles_uneven_sizes(self) -> None:
        items = [1, 2, 3, 4, 5]
        chunks = list(bundle_pdfs.chunked(items, 2))
        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5]

    def test_chunked_single_chunk(self) -> None:
        items = [1, 2, 3]
        chunks = list(bundle_pdfs.chunked(items, 10))
        assert len(chunks) == 1
        assert chunks[0] == [1, 2, 3]

    def test_chunked_zero_size_raises_error(self) -> None:
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="chunk size must be positive"):
            list(bundle_pdfs.chunked(items, 0))

    def test_chunked_negative_size_raises_error(self) -> None:
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="chunk size must be positive"):
            list(bundle_pdfs.chunked(items, -1))


@pytest.mark.unit
class TestSlugify:
    def test_slugify_removes_special_characters(self) -> None:
        assert bundle_pdfs.slugify("School #1") == "school_1"
        assert bundle_pdfs.slugify("District (East)") == "district_east"

    def test_slugify_lowercases_string(self) -> None:
        assert bundle_pdfs.slugify("NORTH DISTRICT") == "north_district"

    def test_slugify_condenses_multiple_underscores(self) -> None:
        assert bundle_pdfs.slugify("School   &   #$  Name") == "school_name"

    def test_slugify_strips_leading_trailing_underscores(self) -> None:
        assert bundle_pdfs.slugify("___school___") == "school"

    def test_slugify_empty_or_whitespace_returns_unknown(self) -> None:
        assert bundle_pdfs.slugify("") == "unknown"
        assert bundle_pdfs.slugify("   ") == "unknown"


@pytest.mark.unit
class TestEnsureIds:
    def test_ensure_ids_passes_when_all_ids_present(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=2, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        # Should not raise
        bundle_pdfs.ensure_ids(
            records, attr="school", log_path=tmp_path / "preprocess.log"
        )

    def test_ensure_ids_raises_for_missing_identifiers(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        # Remove school ID
        artifact_dict["clients"][0]["school"]["id"] = None

        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        client = artifact.clients[0]
        pdf_path = pdf_dir / f"en_notice_{client.sequence}_{client.client_id}.pdf"
        create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        with pytest.raises(ValueError, match="Missing school"):
            bundle_pdfs.ensure_ids(
                records, attr="school", log_path=tmp_path / "preprocess.log"
            )


@pytest.mark.unit
class TestGroupRecords:
    def test_group_records_by_school(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=4, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Modify second client to have different school
        artifact_dict["clients"][1]["school"]["id"] = "school_b"

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        grouped = bundle_pdfs.group_records(records, "school")

        assert len(grouped) >= 1  # At least one group

    def test_group_records_sorted_by_key(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=3, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Assign different school IDs
        artifact_dict["clients"][0]["school"]["id"] = "zebra_school"
        artifact_dict["clients"][1]["school"]["id"] = "alpha_school"
        artifact_dict["clients"][2]["school"]["id"] = "beta_school"

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        grouped = bundle_pdfs.group_records(records, "school")
        keys = list(grouped.keys())

        assert keys == sorted(keys)


@pytest.mark.unit
class TestPlanBundles:
    def test_plan_bundles_size_based(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=5, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=2,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert len(plans) == 3  # 5 records / 2 per bundle = 3 bundles
        assert plans[0].bundle_type == BundleType.SIZE_BASED
        assert len(plans[0].clients) == 2
        assert len(plans[2].clients) == 1

    def test_plan_bundles_school_grouped(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=6, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Assign 2 schools, 3 clients each
        for i, client in enumerate(artifact.clients):
            artifact_dict["clients"][i]["school"]["id"] = (
                "school_a" if i < 3 else "school_b"
            )
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=2,
            bundle_strategy=BundleStrategy.SCHOOL,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert all(p.bundle_type == BundleType.SCHOOL_GROUPED for p in plans)
        assert all(p.bundle_identifier in ["school_a", "school_b"] for p in plans)

    def test_plan_bundles_board_grouped(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=4, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        for i, client in enumerate(artifact.clients):
            artifact_dict["clients"][i]["board"]["id"] = (
                "board_x" if i < 2 else "board_y"
            )
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=1,
            bundle_strategy=BundleStrategy.BOARD,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert all(p.bundle_type == BundleType.BOARD_GROUPED for p in plans)

    def test_plan_bundles_returns_empty_for_zero_bundle_size(
        self, tmp_path: Path
    ) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=3, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=0,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert plans == []


@pytest.mark.unit
class TestMergePdfFiles:
    def test_merge_pdf_files_combines_pages(self, tmp_path: Path) -> None:
        pdf_paths = []
        for i in range(3):
            pdf_path = tmp_path / f"page{i}.pdf"
            create_test_pdf(pdf_path, num_pages=2)
            pdf_paths.append(pdf_path)

        output = tmp_path / "merged.pdf"
        bundle_pdfs.merge_pdf_files(pdf_paths, output)

        assert output.exists()

    def test_merge_pdf_files_produces_valid_pdf(self, tmp_path: Path) -> None:
        pdf_paths = []
        for i in range(2):
            pdf_path = tmp_path / f"page{i}.pdf"
            create_test_pdf(pdf_path, num_pages=1)
            pdf_paths.append(pdf_path)

        output = tmp_path / "merged.pdf"
        bundle_pdfs.merge_pdf_files(pdf_paths, output)

        assert output.exists()
        assert output.stat().st_size > 0


@pytest.mark.unit
class TestWriteBundle:
    def test_write_bundle_creates_pdf_and_manifest(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=2, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        combined_dir = tmp_path / "pdf_combined"
        metadata_dir = tmp_path / "metadata"
        combined_dir.mkdir()
        metadata_dir.mkdir()

        plan = bundle_pdfs.BundlePlan(
            bundle_type=BundleType.SIZE_BASED,
            bundle_identifier=None,
            bundle_number=1,
            total_bundles=1,
            clients=records,
        )

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=2,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        artifact_path = tmp_path / "artifacts" / "preprocessed_clients_test.json"
        result = bundle_pdfs.write_bundle(
            config,
            plan,
            combined_dir=combined_dir,
            metadata_dir=metadata_dir,
            artifact_path=artifact_path,
        )

        assert result.pdf_path.exists()
        assert result.manifest_path.exists()

    def test_write_bundle_manifest_contains_metadata(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test_run"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        client = artifact.clients[0]
        seq = client.sequence
        cid = client.client_id
        pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
        create_test_pdf(pdf_path, num_pages=1)

        clients = client_lookup(artifact_dict)
        records = make_pdf_records(clients, tmp_path)

        combined_dir = tmp_path / "pdf_combined"
        metadata_dir = tmp_path / "metadata"
        combined_dir.mkdir()
        metadata_dir.mkdir()

        plan = bundle_pdfs.BundlePlan(
            bundle_type=BundleType.SIZE_BASED,
            bundle_identifier=None,
            bundle_number=1,
            total_bundles=1,
            clients=records,
        )

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=1,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test_run",
        )

        artifact_path = tmp_path / "artifacts" / "preprocessed_clients_test_run.json"
        result = bundle_pdfs.write_bundle(
            config,
            plan,
            combined_dir=combined_dir,
            metadata_dir=metadata_dir,
            artifact_path=artifact_path,
        )

        with open(result.manifest_path) as f:
            manifest = json.load(f)

        assert manifest["run_id"] == "test_run"
        assert manifest["language"] == "en"
        assert manifest["bundle_type"] == "size_based"
        assert manifest["total_clients"] == 1
        assert "sha256" in manifest
        assert "clients" in manifest


@pytest.mark.unit
class TestBundlePdfs:
    def test_bundle_pdfs_returns_empty_when_disabled(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=2, run_id="test"
        )
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        artifact_path = artifact_dir / "preprocessed_clients_test.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact_to_dict(artifact), f)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=0,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        results = bundle_pdfs.bundle_pdfs(config)

        assert results == []

    def test_bundle_pdfs_raises_for_missing_artifact(self, tmp_path: Path) -> None:
        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="nonexistent",
        )

        with pytest.raises(FileNotFoundError, match="Preprocessed artifact not found"):
            bundle_pdfs.bundle_pdfs(config)

    def test_bundle_pdfs_requires_explicit_render_jobs(self, tmp_path: Path) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, language="en", run_id="test"
        )
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        artifact_path = artifact_dir / "preprocessed_clients_test.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact_to_dict(artifact), f)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        with pytest.raises(FileNotFoundError, match="render_jobs.json"):
            bundle_pdfs.bundle_pdfs(config)

    def test_bundle_pdfs_rejects_uncompiled_nonempty_cohort(
        self, tmp_path: Path
    ) -> None:
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        artifact_path = artifact_dir / "preprocessed_clients_test.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact_to_dict(artifact), f)
        (artifact_dir / "render_jobs.json").write_text(
            json.dumps({"run_id": "test", "total_clients": 1, "jobs": []})
        )

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        with pytest.raises(ValueError, match="every expected notice exactly once"):
            bundle_pdfs.bundle_pdfs(config)
