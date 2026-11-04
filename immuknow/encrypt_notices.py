"""Make optional individual encrypted copies without changing original notices."""

from __future__ import annotations

from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from multiprocessing import get_context
from collections.abc import Callable, Iterable
from pypdf.errors import PdfReadError

from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError
from pypdf.generic import DictionaryObject

from .client_placeholders import (
    CLIENT_PLACEHOLDERS,
    build_client_context,
    extract_template_fields,
    validate_and_format_template,
)
from .data_models import ClientRecord


def encrypt_notice(
    client: ClientRecord, source: Path, destination: Path, settings: dict
) -> dict[str, str | int]:
    """Publish a verified AES-256 revision 6 copy and return its encryption settings.

    Unavailable referenced facts cannot become an empty or partially guessed
    password. No exception includes the expanded password. The orchestrator
    records the actual outcome and continues independent clients.
    """
    if source.resolve() == destination.resolve():
        raise ValueError("Encrypted output must be separate from the original")
    context = build_client_context(client)
    template = settings.get("password", {}).get(
        "template", "{date_of_birth_iso_compact}"
    )
    try:
        fields = extract_template_fields(template)
        password = validate_and_format_template(
            template, context, allowed_fields=CLIENT_PLACEHOLDERS
        )
    except (KeyError, ValueError):
        raise ValueError(
            "Invalid password template; check allowed fields and formatting"
        ) from None
    missing = sorted(field for field in fields if not context.get(field, "").strip())
    if missing:
        raise ValueError("Password facts are unavailable: " + ", ".join(missing))
    if not password.strip():
        raise ValueError("Password must not be empty")

    reader = PdfReader(source)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    try:
        writer.encrypt(
            user_password=password, owner_password=password, algorithm="AES-256"
        )
    except DependencyError:
        raise ValueError(
            "PDF encryption is unavailable. Reinstall ImmuKnow with its required dependencies."
        ) from None
    except ValueError:
        raise ValueError(
            "The password cannot be used for PDF encryption. Check the password settings."
        ) from None
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".partial.pdf")
    try:
        with partial.open("wb") as stream:
            writer.write(stream)
        encrypted = PdfReader(partial)
        if (
            not encrypted.is_encrypted
            or encrypted.decrypt("")
            or not encrypted.decrypt(password)
        ):
            raise ValueError("Encrypted output could not be verified")
        details = encrypted.trailer["/Encrypt"]
        if (
            not isinstance(details, DictionaryObject)
            or details.get("/Filter") != "/Standard"
            or details.get("/V") != 5
            or details.get("/R") != 6
            or details.get("/Length") != 256
            or details.get("/StmF") != "/StdCF"
            or details.get("/StrF") != "/StdCF"
            or details.get("/CF", {}).get("/StdCF", {}).get("/CFM") != "/AESV3"
        ):
            raise ValueError(
                "Encrypted output does not use the required AES-256 settings"
            )
        if len(encrypted.pages) != len(reader.pages):
            raise ValueError("Encrypted output page count differs from the original")
        partial.replace(destination)
        return {"algorithm": "AES-256", "revision": 6, "key_bits": 256}
    finally:
        partial.unlink(missing_ok=True)


def encrypt_many(
    tasks: Iterable[tuple[ClientRecord, Path, Path]],
    settings: dict,
    workers: int,
    incorporate: Callable[[ClientRecord, Path, dict | None, Exception | None], None],
) -> None:
    """Encrypt bounded work and incorporate submitted outcomes before returning."""

    def reduced(client: ClientRecord) -> ClientRecord:
        return ClientRecord(
            sequence=client.sequence,
            client_id=client.client_id,
            language=client.language,
            person=client.person,
            school=client.school,
            board=client.board,
            contact=client.contact,
            overdue_diseases=[],
            overdue_agents=[],
            metadata={},
        )

    expected = (OSError, ValueError, PdfReadError)
    if workers == 1:
        for client, source, destination in tasks:
            try:
                result = encrypt_notice(client, source, destination, settings)
            except expected as exc:
                incorporate(client, destination, None, exc)
            else:
                incorporate(client, destination, result, None)
        return

    iterator = iter(tasks)
    pending = {}
    failure: BaseException | None = None
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))

    def submit_one() -> bool:
        try:
            client, source, destination = next(iterator)
        except StopIteration:
            return False
        future = executor.submit(
            encrypt_notice, reduced(client), source, destination, settings
        )
        pending[future] = (client, destination)
        return True

    def collect(future) -> None:
        nonlocal failure
        client, destination = pending.pop(future)
        try:
            result = future.result()
        except expected as exc:
            try:
                incorporate(client, destination, None, exc)
            except BaseException as callback_error:
                if failure is None:
                    failure = callback_error
        except BaseException as exc:
            if failure is None:
                failure = exc
        else:
            try:
                incorporate(client, destination, result, None)
            except BaseException as exc:
                if failure is None:
                    failure = exc

    try:
        for _ in range(workers):
            if not submit_one():
                break
        while pending and failure is None:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                collect(future)
            if failure is None:
                for _ in range(len(completed)):
                    if not submit_one():
                        break
    except BaseException as exc:
        failure = failure or exc
    finally:
        # Wait for every submitted job before the run lock can be released.
        executor.shutdown(wait=True)
        for future in list(pending):
            collect(future)
    if failure is not None:
        raise failure
