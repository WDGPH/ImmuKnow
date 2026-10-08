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
from tests.fixtures import sample_input


def artifact_to_dict(artifact) -> dict:
    """Convert ArtifactPayload to dict for JSON serialization."""
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


def create_test_pdf(path: Path, num_pages: int = 1) -> None:
    """Create a minimal test PDF file using PyPDF utilities."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f)


@pytest.mark.unit
class TestChunked:
    """Unit tests for chunked utility function."""

    def test_chunked_splits_into_equal_sizes(self) -> None:
        """Verify chunked splits sequence into equal-sized chunks.

        Real-world significance:
        - Chunking ensures bundles don't exceed max_size limit
        """
        items = [1, 2, 3, 4, 5, 6]
        chunks = list(bundle_pdfs.chunked(items, 2))
        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5, 6]

    def test_chunked_handles_uneven_sizes(self) -> None:
        """Verify chunked handles sequences not evenly divisible.

        Real-world significance:
        - Last bundle may be smaller than bundle_size
        """
        items = [1, 2, 3, 4, 5]
        chunks = list(bundle_pdfs.chunked(items, 2))
        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5]

    def test_chunked_single_chunk(self) -> None:
        """Verify chunked with size >= len(items) produces single chunk.

        Real-world significance:
        - Small bundles fit in one chunk
        """
        items = [1, 2, 3]
        chunks = list(bundle_pdfs.chunked(items, 10))
        assert len(chunks) == 1
        assert chunks[0] == [1, 2, 3]

    def test_chunked_zero_size_raises_error(self) -> None:
        """Verify chunked raises error for zero or negative size.

        Real-world significance:
        - Invalid bundle_size should fail explicitly
        """
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="chunk size must be positive"):
            list(bundle_pdfs.chunked(items, 0))

    def test_chunked_negative_size_raises_error(self) -> None:
        """Verify chunked raises error for negative size.

        Real-world significance:
        - Negative bundle_size is invalid
        """
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="chunk size must be positive"):
            list(bundle_pdfs.chunked(items, -1))


@pytest.mark.unit
class TestSlugify:
    """Unit tests for slugify utility function."""

    def test_slugify_removes_special_characters(self) -> None:
        """Verify slugify removes non-alphanumeric characters.

        Real-world significance:
        - School/board names may contain special characters unsafe for filenames
        """
        assert bundle_pdfs.slugify("School #1") == "school_1"
        assert bundle_pdfs.slugify("District (East)") == "district_east"

    def test_slugify_lowercases_string(self) -> None:
        """Verify slugify converts to lowercase.

        Real-world significance:
        - Consistent filename convention
        """
        assert bundle_pdfs.slugify("NORTH DISTRICT") == "north_district"

    def test_slugify_condenses_multiple_underscores(self) -> None:
        """Verify slugify removes redundant underscores.

        Real-world significance:
        - Filenames don't have confusing multiple underscores
        """
        assert bundle_pdfs.slugify("School   &   #$  Name") == "school_name"

    def test_slugify_strips_leading_trailing_underscores(self) -> None:
        """Verify slugify removes leading/trailing underscores.

        Real-world significance:
        - Filenames start/end with alphanumeric characters
        """
        assert bundle_pdfs.slugify("___school___") == "school"

    def test_slugify_empty_or_whitespace_returns_unknown(self) -> None:
        """Verify slugify returns 'unknown' for empty/whitespace strings.

        Real-world significance:
        - Missing school/board name doesn't break filename generation
        """
        assert bundle_pdfs.slugify("") == "unknown"
        assert bundle_pdfs.slugify("   ") == "unknown"


@pytest.mark.unit
class TestLoadArtifact:
    """Unit tests for load_artifact function."""

    def test_load_artifact_reads_preprocessed_file(self, tmp_path: Path) -> None:
        """Verify load_artifact reads preprocessed artifact JSON.

        Real-world significance:
        - Bundling step depends on artifact created by preprocess step
        """
        run_id = "test_001"
        artifact = sample_input.create_test_artifact_payload(
            num_clients=2, run_id=run_id
        )
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        artifact_path = artifact_dir / f"preprocessed_clients_{run_id}.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact_to_dict(artifact), f)

        loaded = bundle_pdfs.load_artifact(tmp_path, run_id)

        assert loaded["run_id"] == run_id
        assert isinstance(loaded["clients"], list)
        assert len(loaded["clients"]) == 2

    def test_load_artifact_missing_file_raises_error(self, tmp_path: Path) -> None:
        """Verify load_artifact raises error for missing artifact.

        Real-world significance:
        - Bundling cannot proceed without preprocessing artifact
        """
        with pytest.raises(FileNotFoundError, match="not found"):
            bundle_pdfs.load_artifact(tmp_path, "nonexistent_run")


@pytest.mark.unit
class TestBuildClientLookup:
    """Unit tests for build_client_lookup function."""

    def test_build_client_lookup_creates_dict(self) -> None:
        """Verify build_client_lookup creates (sequence, client_id) keyed dict.

        Real-world significance:
        - Lookup allows fast PDF-to-client metadata association
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=3, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        lookup = bundle_pdfs.build_client_lookup(artifact_dict)

        assert len(lookup) == 3
        # Verify keys are (sequence, client_id) tuples
        for key in lookup.keys():
            assert isinstance(key, tuple)
            assert len(key) == 2

    def test_build_client_lookup_preserves_client_data(self) -> None:
        """Verify build_client_lookup preserves full client dict values.

        Real-world significance:
        - Downstream code needs complete client metadata
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        lookup = bundle_pdfs.build_client_lookup(artifact_dict)

        client = artifact_dict["clients"][0]
        sequence = client["sequence"]
        client_id = client["client_id"]
        key = (sequence, client_id)

        assert lookup[key] == client


@pytest.mark.unit
class TestDiscoverPdfs:
    """Unit tests for discover_pdfs function."""

    def test_discover_pdfs_finds_language_specific_files(self, tmp_path: Path) -> None:
        """Verify discover_pdfs finds PDFs with correct language prefix.

        Real-world significance:
        - Bundling only processes PDFs in requested language
        """
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Create test PDFs
        (pdf_dir / "en_notice_00001_client1.pdf").write_bytes(b"test")
        (pdf_dir / "en_notice_00002_client2.pdf").write_bytes(b"test")
        (pdf_dir / "fr_notice_00001_client1.pdf").write_bytes(b"test")

        en_pdfs = bundle_pdfs.discover_pdfs(tmp_path, "en")
        fr_pdfs = bundle_pdfs.discover_pdfs(tmp_path, "fr")

        assert len(en_pdfs) == 2
        assert len(fr_pdfs) == 1

    def test_discover_pdfs_returns_sorted_order(self, tmp_path: Path) -> None:
        """Verify discover_pdfs returns files in sorted order.

        Real-world significance:
        - Consistent PDF ordering for reproducible bundles
        """
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        (pdf_dir / "en_notice_00003_client3.pdf").write_bytes(b"test")
        (pdf_dir / "en_notice_00001_client1.pdf").write_bytes(b"test")
        (pdf_dir / "en_notice_00002_client2.pdf").write_bytes(b"test")

        pdfs = bundle_pdfs.discover_pdfs(tmp_path, "en")
        names = [p.name for p in pdfs]

        assert names == [
            "en_notice_00001_client1.pdf",
            "en_notice_00002_client2.pdf",
            "en_notice_00003_client3.pdf",
        ]

    def test_discover_pdfs_missing_directory_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Verify discover_pdfs returns empty list for missing directory.

        Real-world significance:
        - No PDFs generated means nothing to bundle
        """
        pdfs = bundle_pdfs.discover_pdfs(tmp_path, "en")
        assert pdfs == []


@pytest.mark.unit
class TestBuildPdfRecords:
    """Unit tests for build_pdf_records function."""

    def test_build_pdf_records_creates_records_with_metadata(
        self, tmp_path: Path
    ) -> None:
        """Verify build_pdf_records creates PdfRecord for each PDF.

        Real-world significance:
        - Records capture PDF metadata needed for bundling
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=2, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Create test PDFs
        for client in artifact.clients:
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=2)

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        assert len(records) == 2
        for record in records:
            assert isinstance(record, PdfRecord)
            assert record.page_count == 2

    def test_build_pdf_records_sorted_by_sequence(self, tmp_path: Path) -> None:
        """Verify build_pdf_records returns records sorted by sequence.

        Real-world significance:
        - Consistent bundle ordering
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=3, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Create PDFs in reverse order
        for client in reversed(artifact.clients):
            seq = client.sequence
            cid = client.client_id
            pdf_path = pdf_dir / f"en_notice_{seq}_{cid}.pdf"
            create_test_pdf(pdf_path, num_pages=1)

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        sequences = [r.sequence for r in records]
        assert sequences == sorted(sequences)

    def test_build_pdf_records_skips_invalid_filenames(self, tmp_path: Path) -> None:
        """Verify build_pdf_records logs and skips malformed PDF filenames.

        Real-world significance:
        - Invalid PDFs don't crash bundling, only logged as warning
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Create valid PDF
        client = artifact.clients[0]
        pdf_path = pdf_dir / f"en_notice_{client.sequence}_{client.client_id}.pdf"
        create_test_pdf(pdf_path, num_pages=1)

        # Create invalid PDF filename
        (pdf_dir / "invalid_name.pdf").write_bytes(b"test")

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        assert len(records) == 1  # Only valid PDF counted

    def test_build_pdf_records_missing_client_metadata_raises_error(
        self, tmp_path: Path
    ) -> None:
        """Verify build_pdf_records raises error for orphaned PDF.

        Real-world significance:
        - PDF without matching client metadata indicates data corruption
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dict = artifact_to_dict(artifact)
        pdf_dir = tmp_path / "pdf_individual"
        pdf_dir.mkdir()

        # Create PDF for non-existent client
        create_test_pdf(pdf_dir / "en_notice_00099_orphan_client.pdf", num_pages=1)

        clients = bundle_pdfs.build_client_lookup(artifact_dict)

        with pytest.raises(KeyError, match="No client metadata"):
            bundle_pdfs.build_pdf_records(tmp_path, "en", clients)


@pytest.mark.unit
class TestEnsureIds:
    """Unit tests for ensure_ids validation function."""

    def test_ensure_ids_passes_when_all_ids_present(self, tmp_path: Path) -> None:
        """Verify ensure_ids passes when all clients have school IDs.

        Real-world significance:
        - School/board identifiers required for grouped bundling
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        # Should not raise
        bundle_pdfs.ensure_ids(
            records, attr="school", log_path=tmp_path / "preprocess.log"
        )

    def test_ensure_ids_raises_for_missing_identifiers(self, tmp_path: Path) -> None:
        """Verify ensure_ids raises error if any client lacks identifier.

        Real-world significance:
        - Cannot group by school if school ID is missing
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        with pytest.raises(ValueError, match="Missing school"):
            bundle_pdfs.ensure_ids(
                records, attr="school", log_path=tmp_path / "preprocess.log"
            )


@pytest.mark.unit
class TestGroupRecords:
    """Unit tests for group_records function."""

    def test_group_records_by_school(self, tmp_path: Path) -> None:
        """Verify group_records groups records by specified key.

        Real-world significance:
        - School-based bundling requires grouping by school identifier
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        grouped = bundle_pdfs.group_records(records, "school")

        assert len(grouped) >= 1  # At least one group

    def test_group_records_sorted_by_key(self, tmp_path: Path) -> None:
        """Verify group_records returns groups sorted by key.

        Real-world significance:
        - Consistent bundle ordering across runs
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        grouped = bundle_pdfs.group_records(records, "school")
        keys = list(grouped.keys())

        assert keys == sorted(keys)


@pytest.mark.unit
class TestPlanBundles:
    """Unit tests for plan_bundles function."""

    def test_plan_bundles_size_based(self, tmp_path: Path) -> None:
        """Verify plan_bundles creates size-based bundles.

        Real-world significance:
        - Default bundling strategy chunks PDFs by fixed size
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
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
        """Verify plan_bundles creates school-grouped bundles.

        Real-world significance:
        - School-based bundling groups records by school first
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
            bundle_size=2,
            bundle_strategy=BundleStrategy.SCHOOL,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert all(p.bundle_type == BundleType.SCHOOL_GROUPED for p in plans)
        assert all(p.bundle_identifier in ["school_a", "school_b"] for p in plans)

    def test_plan_bundles_board_grouped(self, tmp_path: Path) -> None:
        """Verify plan_bundles creates board-grouped bundles.

        Real-world significance:
        - Board-based bundling groups by board identifier
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
            bundle_size=1,
            bundle_strategy=BundleStrategy.BOARD,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert all(p.bundle_type == BundleType.BOARD_GROUPED for p in plans)

    def test_plan_bundles_returns_empty_for_zero_bundle_size(
        self, tmp_path: Path
    ) -> None:
        """Verify plan_bundles returns empty list when bundle_size is 0.

        Real-world significance:
        - Bundling disabled (bundle_size=0) skips grouping
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
            bundle_size=0,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        plans = bundle_pdfs.plan_bundles(config, records, tmp_path / "preprocess.log")

        assert plans == []


@pytest.mark.unit
class TestMergePdfFiles:
    """Unit tests for merge_pdf_files function."""

    def test_merge_pdf_files_combines_pages(self, tmp_path: Path) -> None:
        """Verify merge_pdf_files combines PDFs into single file.

        Real-world significance:
        - Multiple per-client PDFs merged into single bundle PDF
        """
        pdf_paths = []
        for i in range(3):
            pdf_path = tmp_path / f"page{i}.pdf"
            create_test_pdf(pdf_path, num_pages=2)
            pdf_paths.append(pdf_path)

        output = tmp_path / "merged.pdf"
        bundle_pdfs.merge_pdf_files(pdf_paths, output)

        assert output.exists()

    def test_merge_pdf_files_produces_valid_pdf(self, tmp_path: Path) -> None:
        """Verify merged PDF is readable and valid.

        Real-world significance:
        - Bundle PDFs must be valid for downstream processing
        """
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
    """Unit tests for write_bundle function."""

    def test_write_bundle_creates_pdf_and_manifest(self, tmp_path: Path) -> None:
        """Verify write_bundle creates both merged PDF and manifest JSON.

        Real-world significance:
        - Bundle operation produces both PDF and metadata
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

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
            language="en",
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
        """Verify manifest JSON contains required bundle metadata.

        Real-world significance:
        - Manifest records bundle composition for audit/tracking
        """
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

        clients = bundle_pdfs.build_client_lookup(artifact_dict)
        records = bundle_pdfs.build_pdf_records(tmp_path, "en", clients)

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
            language="en",
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
    """Unit tests for main bundle_pdfs orchestration function."""

    def test_bundle_pdfs_returns_empty_when_disabled(self, tmp_path: Path) -> None:
        """Verify bundle_pdfs returns empty list when bundle_size <= 0.

        Real-world significance:
        - Bundling is optional feature (skip if disabled in config)
        """
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
            language="en",
            bundle_size=0,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        results = bundle_pdfs.bundle_pdfs(config)

        assert results == []

    def test_bundle_pdfs_raises_for_missing_artifact(self, tmp_path: Path) -> None:
        """Verify bundle_pdfs raises error if artifact missing.

        Real-world significance:
        - Bundling cannot proceed without preprocessing step
        """
        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="nonexistent",
        )

        with pytest.raises(FileNotFoundError, match="Expected artifact"):
            bundle_pdfs.bundle_pdfs(config)

    def test_bundle_pdfs_requires_explicit_render_jobs(self, tmp_path: Path) -> None:
        """A language label cannot substitute for the list of expected notices."""
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
            language="fr",  # Mismatch!
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        with pytest.raises(FileNotFoundError, match="render_jobs.json"):
            bundle_pdfs.bundle_pdfs(config)

    def test_bundle_pdfs_rejects_uncompiled_nonempty_cohort(
        self, tmp_path: Path
    ) -> None:
        """A nonempty cohort without compiled notices is a failure, not empty success."""
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test"
        )
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        artifact_path = artifact_dir / "preprocessed_clients_test.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact_to_dict(artifact), f)

        config = bundle_pdfs.BundleConfig(
            output_dir=tmp_path,
            language="en",
            bundle_size=5,
            bundle_strategy=BundleStrategy.SIZE,
            run_id="test",
        )

        with pytest.raises(FileNotFoundError, match="render_jobs.json"):
            bundle_pdfs.bundle_pdfs(config)
