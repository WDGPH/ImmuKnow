"""Generate per-client Typst notices from the normalized preprocessing artifact.

This module consumes the JSON artifact emitted by ``preprocess.py`` and generates
per-client Typst templates for notice rendering.

**Input Contract:**
- Reads preprocessed artifact JSON (created by preprocess step)
- Assumes artifact contains valid client records with all required fields
- Assumes language validation already occurred at CLI entry point

**Output Contract:**
- Writes per-client Typst template files to output/artifacts/typst/
- Returns list of successfully generated .typ file paths
- All clients must succeed; fails immediately on first error (critical feature)

**Error Handling:**
- Client data errors raise immediately (cannot produce incomplete output)
- Infrastructure errors (missing paths) raise immediately
- Invalid language enum raises immediately (should never occur if upstream validates)
- No per-client recovery; fail-fast approach ensures deterministic output

**Validation Contract:**

What this module validates:
- Artifact language matches all client languages (fail-fast if mismatch)

What this module assumes (validated upstream):
- Artifact file exists and is valid JSON (validated by read_artifact())
- Language code is valid (validated at CLI by argparse choices)
- Client records have all required fields (validated by preprocessing step)
- File paths exist (output_dir, logo_path, signature_path)

Functions with special validation notes:
- render_notice(): Calls Language.from_string() on client.language to convert
  string to enum; this adds a second validation layer (redundant but safe)
- get_language_renderer(): Assumes language enum is valid; no defensive check
  (language validated upstream via CLI choices + Language.from_string())
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from .config_loader import load_config
from .data_models import (
    ArtifactPayload,
    ClientRecord,
)
from .enums import Language
from .preprocess import format_iso_date_for_language
from .translation_helpers import display_label
from .utils import deserialize_client_record

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_template_module(template_dir: Path, language_code: str):
    """Dynamically load a template module from specified directory.

    Loads a language-specific template module at runtime from a custom directory.
    This enables PHU-specific template customization without code changes.

    **Validation Contract:**
    - Template file must exist at {template_dir}/{language_code}_template.py
    - Module must define render_notice() function
    - Raises immediately if file missing or render_notice() not found

    Parameters
    ----------
    template_dir : Path
        Directory containing template modules (e.g., templates/ or phu_templates/my_phu/)
    language_code : str
        Two-character ISO language code (e.g., "en", "fr")

    Returns
    -------
    module
        Loaded Python module with render_notice() function

    Raises
    ------
    FileNotFoundError
        If template file doesn't exist at expected path
    ImportError
        If module cannot be loaded
    AttributeError
        If module doesn't define render_notice() function

    Examples
    --------
    >>> module = load_template_module(Path("templates"), "en")
    >>> module.render_notice(context, logo_path="/logo.png", signature_path="/sig.png")
    """
    module_name = f"{language_code}_template"
    module_path = template_dir / f"{module_name}.py"

    # Validate file exists
    if not module_path.exists():
        raise FileNotFoundError(
            f"Template module not found: {module_path}. "
            f"Expected {module_name}.py in {template_dir}"
        )

    # Load module dynamically
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load template module: {module_path}")

    module = importlib.util.module_from_spec(spec)

    # Register in sys.modules to prevent duplicate loads
    sys.modules[f"_dynamic_{module_name}"] = module
    spec.loader.exec_module(module)

    # Validate render_notice() exists
    if not hasattr(module, "render_notice"):
        raise AttributeError(
            f"Template module {module_name} must define render_notice() function. "
            f"Check {module_path} and ensure it implements the required interface."
        )

    return module


def build_language_renderers(template_dir: Path) -> dict:
    """Build renderer dictionary from templates in specified directory.

    Discovers and loads all available language template modules from the given directory,
    building a mapping of language codes to their render_notice functions.

    **Validation Contract:**
    - Only languages with corresponding template files are included
    - Each available template must have valid render_notice() function
    - Raises immediately if any template file exists but is invalid
    - Does NOT require all Language enum values to be present
    - Later validation ensures requested language is available when needed

    Parameters
    ----------
    template_dir : Path
        Directory containing language template modules

    Returns
    -------
    dict
        Mapping of language codes (str) to render_notice functions (callable)
        Format: {"en": <function>, "fr": <function>, ...}
        May contain subset of all languages; only includes available templates

    Raises
    ------
    AttributeError
        If a template file exists but doesn't define render_notice()

    Examples
    --------
    >>> renderers = build_language_renderers(Path("templates"))
    >>> renderers["en"](context, logo_path="/logo.png", signature_path="/sig.png")

    >>> # PHU providing only English
    >>> renderers = build_language_renderers(Path("phu_templates/my_phu"))
    >>> renderers  # May only contain {"en": <function>}
    """
    renderers = {}
    for lang in Language:
        module_path = template_dir / f"{lang.value}_template.py"
        # Only load if template file exists
        if module_path.exists():
            module = load_template_module(template_dir, lang.value)
            renderers[lang.value] = module.render_notice
    return renderers


def get_language_renderer(language: Language, renderers: dict):
    """Get template renderer for given language from provided renderer dict.

    Maps Language enum values to their corresponding template rendering functions
    from a dynamically-built renderer dictionary. This provides a single dispatch
    point for template selection with runtime-configurable template sources.

    **Validation Contract:** Assumes language is a valid Language enum (validated
    upstream at CLI entry point via argparse choices, and again by Language.from_string()
    before calling this function). Checks that language is available in renderers dict;
    raises with helpful error if template for requested language is not available.

    Parameters
    ----------
    language : Language
        Language enum value (guaranteed to be valid from Language enum).
    renderers : dict
        Mapping of language codes to render_notice functions, built by
        build_language_renderers(). May only contain subset of all languages.

    Returns
    -------
    callable
        Template rendering function for the language.

    Raises
    ------
    FileNotFoundError
        If requested language template is not available in renderers dict.
        Provides helpful message listing available languages.

    Examples
    --------
    >>> renderers = build_language_renderers(Path("templates"))
    >>> renderer = get_language_renderer(Language.ENGLISH, renderers)
    >>> # renderer is now the render_notice function from en_template
    """
    if language.value not in renderers:
        available = ", ".join(sorted(renderers.keys())) if renderers else "none"
        raise FileNotFoundError(
            f"Template not available for language: {language.value}\n"
            f"Available languages: {available}\n"
            f"Ensure your template directory contains {language.value}_template.py"
        )
    return renderers[language.value]


def read_artifact(path: Path) -> ArtifactPayload:
    """Read and deserialize the preprocessed artifact JSON.

    **Input Contract:** Assumes artifact was created by preprocessing step and
    contains valid client records. Does not validate client schema; relies on
    preprocessing to have ensured data quality.

    Parameters
    ----------
    path : Path
        Path to the preprocessed artifact JSON file.

    Returns
    -------
    ArtifactPayload
        Parsed artifact with clients and metadata.

    Raises
    ------
    FileNotFoundError
        If artifact file does not exist.
    json.JSONDecodeError
        If artifact is not valid JSON.
    KeyError
        If artifact is missing required fields.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Preprocessed artifact not found: {path}. "
            "Ensure preprocessing step has completed."
        )

    try:
        payload_dict = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Preprocessed artifact is not valid JSON: {path}") from exc

    clients = []

    for client_dict in payload_dict["clients"]:
        client = deserialize_client_record(client_dict)
        clients.append(client)

    return ArtifactPayload(
        run_id=payload_dict["run_id"],
        language=payload_dict["language"],
        clients=clients,
        warnings=payload_dict.get("warnings", []),
        created_at=payload_dict.get("created_at", ""),
        total_clients=payload_dict.get("total_clients", len(clients)),
    )


def escape_string(value: str) -> str:
    """Escape special characters in a string for Typst template output.

    Module-internal helper for to_typ_value(). Escapes backslashes, quotes,
    and newlines to ensure the string can be safely embedded in a Typst template.

    Parameters
    ----------
    value : str
        String to escape.

    Returns
    -------
    str
        Escaped string safe for Typst embedding.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def to_typ_value(value) -> str:
    """Convert a Python value to its Typst template representation.

    Module-internal helper for building template contexts. Handles strings
    (with escaping), booleans, None, numbers, sequences (tuples), and mappings
    (dicts) by converting them to Typst syntax.

    Parameters
    ----------
    value : Any
        Python value to convert.

    Returns
    -------
    str
        Typst-compatible representation of the value.

    Raises
    ------
    TypeError
        If value type is not supported.

    Examples
    --------
    >>> to_typ_value("hello")
    '"hello"'
    >>> to_typ_value(True)
    'true'
    >>> to_typ_value([1, 2, 3])
    '(1, 2, 3)'
    """
    if isinstance(value, str):
        return f'"{escape_string(value)}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "none"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [to_typ_value(item) for item in value]
        if len(items) == 1:
            inner = f"{items[0]},"
        else:
            inner = ", ".join(items)
        return f"({inner})"
    if isinstance(value, Mapping):
        items = ", ".join(f"{key}: {to_typ_value(val)}" for key, val in value.items())
        return f"({items})"
    raise TypeError(f"Unsupported value type for Typst conversion: {type(value)!r}")


def load_and_translate_chart_diseases(language: str) -> List[str]:
    """Load and translate the chart disease list from configuration.

    Loads chart_diseases_header from config/parameters.yaml and translates each
    disease name to the target language using the diseases_chart translation domain.
    This ensures chart column headers match the configured set of diseases and are
    properly localized.

    Parameters
    ----------
    language : str
        Language code (e.g., "en", "fr").

    Returns
    -------
    List[str]
        List of translated disease names in order.
    """
    config = load_config()
    chart_diseases_header = config.get("chart_diseases_header", [])

    translated_diseases: List[str] = []
    for disease in chart_diseases_header:
        label = display_label("diseases_chart", disease, language, strict=False)
        translated_diseases.append(label)

    return translated_diseases


def build_template_context(
    client: ClientRecord, qr_output_dir: Path | None = None
) -> Dict[str, str]:
    """Build template context from client data.

    Translates disease names in vaccines_due_list and received records to
    localized display strings using the configured translation files.
    Also loads and translates the chart disease header list from configuration.
    Formats the notice date_data_cutoff with locale-aware formatting using Babel.

    Parameters
    ----------
    client : ClientRecord
        Client record with all required fields.
    qr_output_dir : Path, optional
        Directory containing QR code PNG files.

    Returns
    -------
    Dict[str, str]
        Template context with translated disease names and formatted date.
    """
    config = load_config()
    preprocess_cfg: Dict[str, object] = config.get("preprocess", {})
    show_validity_markers = bool(
        preprocess_cfg.get("show_validity_markers", False)
    )

    # Load and format date_data_cutoff for the client's language
    date_data_cutoff_iso = config.get("date_data_cutoff")
    if date_data_cutoff_iso:
        date_data_cutoff_formatted = format_iso_date_for_language(
            date_data_cutoff_iso, client.language
        )
    else:
        date_data_cutoff_formatted = ""

    client_data = {
        "name": " ".join(
            filter(None, [client.person["first_name"], client.person["last_name"]])
        ).strip(),
        "address": client.contact["street"],
        "city": client.contact["city"],
        "postal_code": client.contact["postal_code"],
        "date_of_birth": client.person["date_of_birth_display"],
        "school": client.school["name"],
        "date_data_cutoff": date_data_cutoff_formatted,
        "over_16": client.person["over_16"]
    }

    # Check if QR code PNG exists from prior generation step
    if qr_output_dir:
        qr_filename = f"qr_code_{client.sequence}_{client.client_id}.png"
        qr_path = qr_output_dir / qr_filename
        if qr_path.exists():
            client_data["qr_img"] = to_root_relative(qr_path)

            # Also include QR URL (payload) if available
            if client.qr and client.qr.get("payload"):
                client_data["qr_url"] = client.qr["payload"]

    # If qr payload is present but no qr_output_dir, still include it
    # (may occur if QR generation is disabled but qr payload exists in artifact)
    if client.qr and client.qr.get("payload") and "qr_url" not in client_data:
        client_data["qr_url"] = client.qr["payload"]

    # Load and translate chart disease header
    chart_diseases_translated = load_and_translate_chart_diseases(client.language)

    # Translate vaccines_due_list to display labels
    vaccines_due_array_translated: List[str] = []
    if client.vaccines_due_list:
        for disease in client.vaccines_due_list:
            label = display_label(
                "diseases_overdue", disease, client.language, strict=False
            )
            vaccines_due_array_translated.append(label)

    # Translate vaccines_due string
    vaccines_due_str_translated = (
        ", ".join(vaccines_due_array_translated)
        if vaccines_due_array_translated
        else ""
    )

    # Translate received records' diseases
    received_translated: List[Dict[str, object]] = []
    if client.received:
        for record in client.received:
            translated_record = dict(record)
            # Translate diseases field (not vaccine)
            if "diseases" in translated_record and isinstance(
                translated_record["diseases"], list
            ):
                translated_diseases = []
                for disease in translated_record["diseases"]:
                    label = display_label(
                        "diseases_chart", disease, client.language, strict=False
                    )
                    translated_diseases.append(label)
                translated_record["diseases"] = translated_diseases
            received_translated.append(translated_record)

    return {
        "client_row": to_typ_value([client.client_id]),
        "client_data": to_typ_value(client_data),
        "vaccines_due_str": to_typ_value(vaccines_due_str_translated),
        "vaccines_due_array": to_typ_value(vaccines_due_array_translated),
        "received": to_typ_value(received_translated),
        "num_rows": str(len(received_translated)),
        "chart_diseases_translated": to_typ_value(chart_diseases_translated),
        "show_validity_markers": to_typ_value(show_validity_markers),
    }


def to_root_relative(path: Path) -> str:
    """Convert absolute path to project-root-relative Typst path reference.

    Module-internal helper for template rendering. Converts absolute file paths
    to paths relative to the project root, formatted for Typst's import resolution.
    If path is outside project root (e.g., custom assets), returns absolute path.

    Parameters
    ----------
    path : Path
        Absolute path to convert.

    Returns
    -------
    str
        Path string like "/artifacts/qr_codes/code.png" (relative to project root)
        or absolute path if outside project root.

    Raises
    ------
    ValueError
        If path cannot be resolved (defensive guard, should not occur in practice).
    """
    absolute = path.resolve()
    try:
        relative = absolute.relative_to(ROOT_DIR)
        return "/" + relative.as_posix()
    except ValueError:
        # Path is outside project root (e.g., custom template assets)
        # Return as absolute path string for Typst
        return str(absolute)


def render_notice(
    client: ClientRecord,
    *,
    output_dir: Path,
    logo: Path,
    signature: Path,
    renderers: dict,
    qr_output_dir: Path | None = None,
) -> str:
    """Render a Typst notice for a single client using provided renderers.

    Parameters
    ----------
    client : ClientRecord
        Client record with all required fields
    output_dir : Path
        Output directory (used for path resolution)
    logo : Path
        Path to logo image file
    signature : Path
        Path to signature image file
    renderers : dict
        Language code to render_notice function mapping from build_language_renderers()
    qr_output_dir : Path, optional
        Directory containing QR code PNG files

    Returns
    -------
    str
        Rendered Typst template content
    """
    language = Language.from_string(client.language)
    renderer = get_language_renderer(language, renderers)
    context = build_template_context(client, qr_output_dir)
    return renderer(
        context,
        logo_path=to_root_relative(logo),
        signature_path=to_root_relative(signature),
    )


def generate_typst_files(
    payload: ArtifactPayload,
    output_dir: Path,
    logo_path: Path,
    signature_path: Path,
    template_dir: Path,
) -> List[Path]:
    """Generate Typst template files for all clients in payload.

    Parameters
    ----------
    payload : ArtifactPayload
        Preprocessed client data with metadata
    output_dir : Path
        Directory to write Typst files
    logo_path : Path
        Path to logo image
    signature_path : Path
        Path to signature image
    template_dir : Path
        Directory containing language template modules

    Returns
    -------
    List[Path]
        List of generated .typ file paths
    """
    # Build renderers from specified template directory
    renderers = build_language_renderers(template_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    qr_output_dir = output_dir / "qr_codes"
    typst_output_dir = output_dir / "typst"
    typst_output_dir.mkdir(parents=True, exist_ok=True)
    files: List[Path] = []
    language = payload.language
    for client in payload.clients:
        if client.language != language:
            raise ValueError(
                f"Client {client.client_id} language {client.language!r} does not match artifact language {language!r}."
            )
        typst_content = render_notice(
            client,
            output_dir=output_dir,
            logo=logo_path,
            signature=signature_path,
            renderers=renderers,
            qr_output_dir=qr_output_dir,
        )
        filename = f"{language}_notice_{client.sequence}_{client.client_id}.typ"
        file_path = typst_output_dir / filename
        file_path.write_text(typst_content, encoding="utf-8")
        files.append(file_path)
        LOG.info("Wrote %s", file_path)
    return files


def main(
    artifact_path: Path,
    output_dir: Path,
    logo_path: Path,
    signature_path: Path,
    template_dir: Path,
) -> List[Path]:
    """Main entry point for Typst notice generation.

    Parameters
    ----------
    artifact_path : Path
        Path to the preprocessed JSON artifact.
    output_dir : Path
        Directory to write Typst files.
    logo_path : Path
        Path to the logo image.
    signature_path : Path
        Path to the signature image.
    template_dir : Path
        Directory containing language template modules.

    Returns
    -------
    List[Path]
        List of generated Typst file paths.
    """
    payload = read_artifact(artifact_path)
    generated = generate_typst_files(
        payload,
        output_dir,
        logo_path,
        signature_path,
        template_dir,
    )
    print(
        f"Generated {len(generated)} Typst files in {output_dir} for language {payload.language}"
    )
    return generated


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
