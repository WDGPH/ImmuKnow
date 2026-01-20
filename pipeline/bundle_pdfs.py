"""Bundle per-client PDFs into combined files with manifests.

This module combines individual per-client PDFs into bundled files with
accompanying manifest records. It can be invoked as a CLI tool or imported for
unit testing. Bundling supports three modes:

* Size-based (default): bundle the clients into fixed-size groups, i.e., 100 per bundle.
* School-based: group the clients by school code then bundle the clients into fixed-sized groups
* Board-based: group the clients by board code then bundle the clients into fixed-sized groups

Each bundle produces a merged PDF inside ``output/pdf_combined`` and a manifest JSON
record inside ``output/metadata`` that captures critical metadata for audits.

**Input Contract:**
- Reads individual PDF files from output/pdf_individual/
- Reads client metadata from preprocessed artifact JSON
- Assumes bundle_size > 0 in config (bundling is optional; disabled when bundle_size=0)

**Output Contract:**
- Writes merged PDF files to output/pdf_combined/
- Writes bundle manifest JSON to output/metadata/
- Returns list of created bundle files

**Error Handling:**
- Configuration errors (invalid bundle_size, group_by) raise immediately (infrastructure)
- Per-bundle errors (PDF merge failure) log and continue (optional feature)
- Pipeline completes even if some bundles fail to create (optional step)

**Validation Contract:**

What this module validates:
- Bundle size is positive (bundle_size > 0)
- Group-by strategy is valid (size, school, board, or None)
- PDF files can be discovered and merged
- Manifest records have required metadata

What this module assumes (validated upstream):
- PDF files are valid and readable (validated by count_pdfs step)
- Client metadata in artifact is complete (validated by preprocessing step)
- Output directory can be created (general I/O)

Note: This is an optional step. Per-bundle errors are logged but don't halt pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, TypeVar

from pypdf import PdfReader, PdfWriter

from .config_loader import load_config
from .data_models import PdfRecord
from .enums import BundleStrategy, BundleType

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@dataclass(frozen=True)
class BundleConfig:
    """Configuration for PDF bundling operation.

    Attributes
    ----------
    output_dir : Path
        Root output directory containing pipeline artifacts
    language : str
        Language code ('en' or 'fr')
    bundle_size : int
        Maximum number of clients per bundle (0 disables bundling)
    bundle_strategy : BundleStrategy
        Strategy for grouping PDFs into bundles
    run_id : str
        Pipeline run identifier
    """

    output_dir: Path
    language: str
    bundle_size: int
    bundle_strategy: BundleStrategy
    run_id: str


@dataclass(frozen=True)
class BundlePlan:
    """Plan for a single bundle of PDFs.

    Attributes
    ----------
    bundle_type : BundleType
        Type/strategy used for this bundle
    bundle_identifier : str | None
        School or board code if bundle was grouped, None for size-based
    bundle_number : int
        Sequential bundle number
    total_bundles : int
        Total number of bundles in this operation
    clients : List[PdfRecord]
        List of PDFs and metadata in this bundle
    """

    bundle_type: BundleType
    bundle_identifier: str | None
    bundle_number: int
    total_bundles: int
    clients: List[PdfRecord]


@dataclass(frozen=True)
class BundleResult:
    """Result of a completed bundle operation.

    Attributes
    ----------
    pdf_path : Path
        Path to the merged PDF file
    manifest_path : Path
        Path to the JSON manifest file
    bundle_plan : BundlePlan
        The plan used to create this bundle
    """

    pdf_path: Path
    manifest_path: Path
    bundle_plan: BundlePlan


PDF_PATTERN = re.compile(
    r"^(?P<lang>[a-z]{2})_notice_(?P<sequence>\d{5})_(?P<client_id>.+)\.pdf$"
)


def bundle_pdfs_with_config(
    output_dir: Path,
    language: str,
    run_id: str,
    config_path: Path | None = None,
) -> List[BundleResult]:
    """Bundle PDFs using configuration from parameters.yaml.

    Parameters
    ----------
    output_dir : Path
        Root output directory containing pipeline artifacts.
    language : str
        Language prefix to bundle ('en' or 'fr').
    run_id : str
        Pipeline run identifier to locate preprocessing artifacts.
    config_path : Path, optional
        Path to parameters.yaml. If not provided, uses default location.

    Returns
    -------
    List[BundleResult]
        List of bundle results created.
    """
    config = load_config(config_path)

    bundling_config = config.get("bundling", {})
    bundle_size = bundling_config.get("bundle_size", 0)
    group_by = bundling_config.get("group_by", None)

    bundle_strategy = BundleStrategy.from_string(group_by)

    config_obj = BundleConfig(
        output_dir=output_dir.resolve(),
        language=language,
        bundle_size=bundle_size,
        bundle_strategy=bundle_strategy,
        run_id=run_id,
    )

    return bundle_pdfs(config_obj)


def main(
    output_dir: Path, language: str, run_id: str, config_path: Path | None = None
) -> List[BundleResult]:
    """Main entry point for PDF bundling.

    Parameters
    ----------
    output_dir : Path
        Root output directory containing pipeline artifacts.
    language : str
        Language prefix to bundle ('en' or 'fr').
    run_id : str
        Pipeline run identifier.
    config_path : Path, optional
        Path to parameters.yaml configuration file.

    Returns
    -------
    List[BundleResult]
        List of bundles created.
    """
    results = bundle_pdfs_with_config(output_dir, language, run_id, config_path)
    if results:
        print(f"Created {len(results)} bundles in {output_dir / 'pdf_combined'}")
    else:
        print("No bundles created.")
    return results


T = TypeVar("T")


def chunked(iterable: Sequence[T], size: int) -> Iterator[List[T]]:
    """Split an iterable into fixed-size chunks.

    Parameters
    ----------
    iterable : Sequence[T]
        Sequence to chunk.
    size : int
        Maximum number of items per chunk (must be positive).

    Returns
    -------
    Iterator[List[T]]
        Iterator yielding lists of up to `size` items.

    Raises
    ------
    ValueError
        If size is not positive.

    Examples
    --------
    >>> list(chunked([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for index in range(0, len(iterable), size):
        yield list(islice(iterable, index, index + size))


def slugify(value: str) -> str:
    """Convert a string to a URL-safe slug format.

    Converts spaces and special characters to underscores, removes consecutive
    underscores, and lowercases the result. Used for generating bundle filenames
    from school/board names.

    Parameters
    ----------
    value : str
        String to slugify (e.g., school or board name).

    Returns
    -------
    str
        Slugified string, or 'unknown' if value is empty/whitespace.

    Examples
    --------
    >>> slugify("Lincoln High School")
    'lincoln_high_school'
    >>> slugify("Bd. Métropolitain")
    'bd_m_tropolitain'
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return re.sub(r"_+", "_", cleaned).strip("_").lower() or "unknown"


def load_artifact(output_dir: Path, run_id: str) -> Dict[str, object]:
    """Load the preprocessed artifact JSON from the output directory.

    Parameters
    ----------
    output_dir : Path
        Root output directory containing artifacts.
    run_id : str
        Pipeline run identifier matching the artifact filename.

    Returns
    -------
    Dict[str, object]
        Parsed preprocessed artifact with clients and metadata.

    Raises
    ------
    FileNotFoundError
        If the preprocessed artifact file does not exist.
    """
    artifact_path = output_dir / "artifacts" / f"preprocessed_clients_{run_id}.json"
    if not artifact_path.exists():
        raise FileNotFoundError(f"Preprocessed artifact not found at {artifact_path}")
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return payload


def build_client_lookup(
    artifact: Dict[str, object],
) -> Dict[tuple[str, str], dict]:
    """Build a lookup table from artifact clients dict.

    Parameters
    ----------
    artifact : Dict[str, object]
        Preprocessed artifact dictionary

    Returns
    -------
    Dict[tuple[str, str], dict]
        Lookup table keyed by (sequence, client_id)
    """
    clients_obj = artifact.get("clients", [])
    clients = clients_obj if isinstance(clients_obj, list) else []
    lookup: Dict[tuple[str, str], dict] = {}
    for client in clients:
        sequence = client.get("sequence")  # type: ignore[attr-defined]
        client_id = client.get("client_id")  # type: ignore[attr-defined]
        lookup[(sequence, client_id)] = client  # type: ignore[typeddict-item]
    return lookup


def discover_pdfs(output_dir: Path, language: str) -> List[Path]:
    """Discover all individual PDF files for a given language.

    Discovers non-encrypted PDF files only. Encrypted PDFs (with _encrypted suffix)
    are excluded from bundling since bundling operates on the original unencrypted PDFs.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    language : str
        Language prefix to match (e.g., 'en' or 'fr').

    Returns
    -------
    List[Path]
        Sorted list of non-encrypted PDF file paths matching the language, or empty list
        if pdf_individual directory doesn't exist.
    """
    pdf_dir = output_dir / "pdf_individual"
    if not pdf_dir.exists():
        return []
    # Exclude encrypted PDFs (those with _encrypted suffix)
    all_pdfs = pdf_dir.glob(f"{language}_notice_*.pdf")
    return sorted([p for p in all_pdfs if not p.stem.endswith("_encrypted")])


def build_pdf_records(
    output_dir: Path, language: str, clients: Dict[tuple[str, str], dict]
) -> List[PdfRecord]:
    """Build a list of PdfRecord objects from discovered PDF files.

    Discovers PDFs, extracts metadata from filenames, looks up client data,
    and constructs PdfRecord objects with page counts and client metadata.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    language : str
        Language prefix to filter PDFs.
    clients : Dict[tuple[str, str], dict]
        Lookup table of client data keyed by (sequence, client_id).

    Returns
    -------
    List[PdfRecord]
        Sorted list of PdfRecord objects by sequence.

    Raises
    ------
    KeyError
        If a PDF filename has no matching client in the lookup table.
    """
    pdf_paths = discover_pdfs(output_dir, language)
    records: List[PdfRecord] = []
    for pdf_path in pdf_paths:
        match = PDF_PATTERN.match(pdf_path.name)
        if not match:
            LOG.warning("Skipping unexpected PDF filename: %s", pdf_path.name)
            continue
        sequence = match.group("sequence")
        client_id = match.group("client_id")
        key = (sequence, client_id)
        if key not in clients:
            raise KeyError(f"No client metadata found for PDF {pdf_path.name}")
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        records.append(
            PdfRecord(
                sequence=sequence,
                client_id=client_id,
                pdf_path=pdf_path,
                page_count=page_count,
                client=clients[key],
            )
        )
    return sorted(records, key=lambda record: record.sequence)


def ensure_ids(records: Sequence[PdfRecord], *, attr: str, log_path: Path) -> None:
    missing = [record for record in records if not record.client[attr].get("id")]
    if missing:
        sample = missing[0]
        raise ValueError(
            "Missing {attr} for client {client} (sequence {sequence});\n"
            "Cannot bundle without identifiers. See {log_path} for preprocessing warnings.".format(
                attr=attr.replace("_", " "),
                client=sample.client_id,
                sequence=sample.sequence,
                log_path=log_path,
            )
        )


def group_records(records: Sequence[PdfRecord], key: str) -> Dict[str, List[PdfRecord]]:
    grouped: Dict[str, List[PdfRecord]] = {}
    for record in records:
        identifier = record.client[key]["id"]
        grouped.setdefault(identifier, []).append(record)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def plan_bundles(
    config: BundleConfig, records: List[PdfRecord], log_path: Path
) -> List[BundlePlan]:
    """Plan how to group PDFs into bundles based on configuration.

    Parameters
    ----------
    config : BundleConfig
        Bundling configuration including strategy and bundle size
    records : List[PdfRecord]
        List of PDF records to bundle
    log_path : Path
        Path to logging file

    Returns
    -------
    List[BundlePlan]
        List of bundle plans
    """
    if config.bundle_size <= 0:
        return []

    plans: List[BundlePlan] = []

    if config.bundle_strategy == BundleStrategy.SCHOOL:
        ensure_ids(records, attr="school", log_path=log_path)
        grouped = group_records(records, "school")
        for identifier, items in grouped.items():
            total_bundles = (len(items) + config.bundle_size - 1) // config.bundle_size
            for index, chunk in enumerate(chunked(items, config.bundle_size), start=1):
                plans.append(
                    BundlePlan(
                        bundle_type=BundleType.SCHOOL_GROUPED,
                        bundle_identifier=identifier,
                        bundle_number=index,
                        total_bundles=total_bundles,
                        clients=chunk,
                    )
                )
        return plans

    if config.bundle_strategy == BundleStrategy.BOARD:
        ensure_ids(records, attr="board", log_path=log_path)
        grouped = group_records(records, "board")
        for identifier, items in grouped.items():
            total_bundles = (len(items) + config.bundle_size - 1) // config.bundle_size
            for index, chunk in enumerate(chunked(items, config.bundle_size), start=1):
                plans.append(
                    BundlePlan(
                        bundle_type=BundleType.BOARD_GROUPED,
                        bundle_identifier=identifier,
                        bundle_number=index,
                        total_bundles=total_bundles,
                        clients=chunk,
                    )
                )
        return plans

    # Size-based bundling (default)
    total_bundles = (len(records) + config.bundle_size - 1) // config.bundle_size
    for index, chunk in enumerate(chunked(records, config.bundle_size), start=1):
        plans.append(
            BundlePlan(
                bundle_type=BundleType.SIZE_BASED,
                bundle_identifier=None,
                bundle_number=index,
                total_bundles=total_bundles,
                clients=chunk,
            )
        )
    return plans


def relative(path: Path, root: Path) -> str:
    """Convert path to string relative to root directory.

    Module-internal helper for manifest generation. Creates relative path strings
    for storing in JSON manifests, making paths portable across different base directories.

    Parameters
    ----------
    path : Path
        Absolute path to convert.
    root : Path
        Root directory to compute relative path from.

    Returns
    -------
    str
        Relative path as POSIX string.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def merge_pdf_files(pdf_paths: Sequence[Path], destination: Path) -> None:
    writer = PdfWriter()
    for pdf_path in pdf_paths:
        with pdf_path.open("rb") as stream:
            reader = PdfReader(stream)
            for page in reader.pages:
                writer.add_page(page)
    with destination.open("wb") as output_stream:
        writer.write(output_stream)


def write_bundle(
    config: BundleConfig,
    plan: BundlePlan,
    *,
    combined_dir: Path,
    metadata_dir: Path,
    artifact_path: Path,
) -> BundleResult:
    # Generate filename based on bundle type and identifiers
    if plan.bundle_type == BundleType.SCHOOL_GROUPED:
        identifier_slug = slugify(plan.bundle_identifier or "unknown")
        name = f"{config.language}_school_{identifier_slug}_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"
    elif plan.bundle_type == BundleType.BOARD_GROUPED:
        identifier_slug = slugify(plan.bundle_identifier or "unknown")
        name = f"{config.language}_board_{identifier_slug}_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"
    else:  # SIZE_BASED
        name = f"{config.language}_bundle_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"

    output_pdf = combined_dir / f"{name}.pdf"
    manifest_path = metadata_dir / f"{name}_manifest.json"

    merge_pdf_files([record.pdf_path for record in plan.clients], output_pdf)

    checksum = sha256(output_pdf.read_bytes()).hexdigest()
    total_pages = sum(record.page_count for record in plan.clients)

    manifest = {
        "run_id": config.run_id,
        "language": config.language,
        "bundle_type": plan.bundle_type.value,
        "bundle_identifier": plan.bundle_identifier,
        "bundle_number": plan.bundle_number,
        "total_bundles": plan.total_bundles,
        "bundle_size": config.bundle_size,
        "total_clients": len(plan.clients),
        "total_pages": total_pages,
        "sha256": checksum,
        "output_pdf": relative(output_pdf, config.output_dir),
        "clients": [
            {
                "sequence": record.sequence,
                "client_id": record.client_id,
                "full_name": " ".join(
                    filter(
                        None,
                        [
                            record.client["person"]["first_name"],
                            record.client["person"]["last_name"],
                        ],
                    )
                ).strip(),
                "school": record.client["school"]["name"],
                "board": record.client["board"]["name"],
                "pdf_path": relative(record.pdf_path, config.output_dir),
                "artifact_path": relative(artifact_path, config.output_dir),
                "pages": record.page_count,
            }
            for record in plan.clients
        ],
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LOG.info("Created %s (%s clients)", output_pdf.name, len(plan.clients))
    return BundleResult(
        pdf_path=output_pdf, manifest_path=manifest_path, bundle_plan=plan
    )


def bundle_pdfs(config: BundleConfig) -> List[BundleResult]:
    if config.bundle_size <= 0:
        LOG.info("Bundle size <= 0; skipping bundling step.")
        return []

    artifact_path = (
        config.output_dir / "artifacts" / f"preprocessed_clients_{config.run_id}.json"
    )
    if not artifact_path.exists():
        raise FileNotFoundError(f"Expected artifact at {artifact_path}")

    artifact = load_artifact(config.output_dir, config.run_id)
    if artifact.get("language") != config.language:
        raise ValueError(
            f"Artifact language {artifact.get('language')!r} does not match requested language {config.language!r}."
        )
    clients = build_client_lookup(artifact)

    records = build_pdf_records(config.output_dir, config.language, clients)
    if not records:
        LOG.info("No PDFs found for language %s; nothing to bundle.", config.language)
        return []

    log_path = config.output_dir / "logs" / f"preprocess_{config.run_id}.log"
    plans = plan_bundles(config, records, log_path)
    if not plans:
        LOG.info("No bundle plans produced; check bundle size and filters.")
        return []

    combined_dir = config.output_dir / "pdf_combined"
    combined_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir = config.output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    results: List[BundleResult] = []
    for plan in plans:
        results.append(
            write_bundle(
                config,
                plan,
                combined_dir=combined_dir,
                metadata_dir=metadata_dir,
                artifact_path=artifact_path,
            )
        )

    LOG.info("Generated %d bundle(s).", len(results))
    return results


if __name__ == "__main__":
    import sys

    print(
        "⚠️  Direct invocation: This module is typically executed via orchestrator.py.\n"
        "   Re-running a single step is valid when pipeline artifacts are retained on disk,\n"
        "   allowing you to skip earlier steps and regenerate output.\n"
        "   Note: Output will overwrite any previous files.\n"
        "\n"
        "   For typical usage, run: uv run viper <input> <language>\n",
        file=sys.stderr,
    )
    sys.exit(1)
