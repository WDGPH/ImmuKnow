"""Bundle the expected notice PDFs by size, school, or board.

The render-job manifest supplies the complete compiled cohort. Each merged PDF
has a matching audit manifest; missing notices and merge failures halt this step.
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
from .generate_notices import read_render_jobs

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@dataclass(frozen=True)
class BundleConfig:
    """Configuration for PDF bundling operation.

    Attributes
    ----------
    output_dir : Path
        Root output directory containing pipeline artifacts
    bundle_size : int
        Maximum number of clients per bundle (0 disables bundling)
    bundle_strategy : BundleStrategy
        Strategy for grouping PDFs into bundles
    run_id : str
        Pipeline run identifier
    """

    output_dir: Path
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


def bundle_pdfs_with_config(
    output_dir: Path,
    run_id: str,
    config_path: Path | None = None,
) -> List[BundleResult]:
    """Bundle PDFs using configuration from parameters.yaml.

    Parameters
    ----------
    output_dir : Path
        Root output directory containing pipeline artifacts.
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
        bundle_size=bundle_size,
        bundle_strategy=bundle_strategy,
        run_id=run_id,
    )

    return bundle_pdfs(config_obj)


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
    languages = sorted({record.client["language"] for record in plan.clients})
    prefix = languages[0] if len(languages) == 1 else "notices"
    if plan.bundle_type == BundleType.SCHOOL_GROUPED:
        identifier_slug = slugify(plan.bundle_identifier or "unknown")
        name = f"{prefix}_school_{identifier_slug}_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"
    elif plan.bundle_type == BundleType.BOARD_GROUPED:
        identifier_slug = slugify(plan.bundle_identifier or "unknown")
        name = f"{prefix}_board_{identifier_slug}_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"
    else:  # SIZE_BASED
        name = f"{prefix}_bundle_{plan.bundle_number:03d}_of_{plan.total_bundles:03d}"

    output_pdf = combined_dir / f"{name}.pdf"
    manifest_path = metadata_dir / f"{name}_manifest.json"

    merge_pdf_files([record.pdf_path for record in plan.clients], output_pdf)

    checksum = sha256(output_pdf.read_bytes()).hexdigest()
    total_pages = sum(record.page_count for record in plan.clients)

    manifest = {
        "run_id": config.run_id,
        "language": languages[0] if len(languages) == 1 else None,
        "languages": languages,
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
    artifact = load_artifact(config.output_dir, config.run_id)
    clients = build_client_lookup(artifact)
    jobs = read_render_jobs(config.output_dir / "artifacts", require_compiled=True)
    if {(job.sequence, job.client_id) for job in jobs} != set(clients):
        raise ValueError("Render jobs do not match the canonical cohort")
    records = [
        PdfRecord(
            sequence=job.sequence,
            client_id=job.client_id,
            pdf_path=job.pdf,
            page_count=len(PdfReader(job.pdf).pages),
            client=clients[(job.sequence, job.client_id)],
        )
        for job in jobs
    ]
    if not records:
        LOG.info("The cohort is empty; nothing to bundle.")
        return []

    log_path = config.output_dir / "logs" / f"preprocess_{config.run_id}.log"
    plans = plan_bundles(config, records, log_path)
    planned = [record.pdf_path for plan in plans for record in plan.clients]
    if len(planned) != len(records) or set(planned) != {
        record.pdf_path for record in records
    }:
        raise ValueError("Bundle plans must include every expected notice exactly once")

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
