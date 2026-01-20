"""French Typst template renderer.

This module contains the French version of the immunization notice template. The
template generates a 2025 immunization notice in Typst format for dynamic PDF
rendering.

The template defines the notice layout in French, including client information,
immunization requirements, vaccine records, QR codes, and contact instructions.
All placeholder values (client data, dates, vaccines) are dynamically substituted
during rendering.

Available placeholder variables include:
- client: Client data dict with person, school, board, contact info
- client_id: Unique client identifier
- immunizations_due: List of required vaccines
- qr_code: Optional QR code image path (if QR generation is enabled)
- date: Delivery/notice date
"""

from __future__ import annotations

from typing import Mapping

TEMPLATE_PREFIX = """// --- CCEYA NOTICE TEMPLATE (TEST VERSION) --- //
// Description: A typst template that dynamically generates CCEYA templates.
// NOTE: All contact details are placeholders for testing purposes only.
// Author: Kassy Raymond
// Date Created: 2025-06-25
// Date Last Updated: 2025-09-16
// ----------------------------------------- //

#import "/templates/conf.typ"

// General document formatting 
#set text(fill: black)
#set par(justify: false)
#set page("us-letter")

// Formatting links - prevent URLs from splitting across lines
#show link: it => box(underline(it))

// Font formatting
#set text(
  font: "FreeSans",
  size: 10pt
)

// Immunization Notice Section
#let immunization_notice(client, client_id, immunizations_due, date, font_size) = block[

#v(0.2cm)

#conf.header_info_cim("__LOGO_PATH__", 6cm, black, 16pt, "Demande de dossier d'immunisation")

#v(0.2cm)

#conf.client_info_tbl_fr(equal_split: false, vline: false, client, client_id, font_size, "Centre de garde d'enfants", 81pt, border: false)

#v(0.3cm)

// Notice for immunizations
En date du *#date*, nos dossiers indiquent que votre enfant n'a pas reçu les immunisations suivantes :  

#conf.client_immunization_list(immunizations_due)

Veuillez examiner le dossier d'immunisation à la page 2 et mettre à jour le dossier de votre enfant en utilisant l'une des options suivantes :

1. En visitant #text(fill:conf.linkcolor)[#link("https://www.test-immunization.ca")]
2. En envoyant un courriel à #text(fill:conf.linkcolor)[#link("records@test-immunization.ca")]
3. En envoyant par la poste une photocopie du dossier d'immunisation de votre enfant à Test Health, 123 Placeholder Street, Sample City, ON A1A 1A1
4. Par téléphone : 555-555-5555 poste 1234

Veuillez informer la Santé publique et votre centre de garde d'enfants chaque fois que votre enfant reçoit un vaccin. En gardant les vaccinations de votre enfant à jour, vous protégez non seulement sa santé, mais aussi la santé des autres enfants et du personnel du centre de garde d'enfants.  

#grid(
  columns: (1fr, auto),
  gutter: 10pt,
  [*Si vous choisissez de ne pas immuniser votre enfant*, une exemption médicale valide ou une déclaration de conscience ou de croyance religieuse doit être remplie et soumise à la Santé publique. Les liens vers ces formulaires se trouvent à #text(fill:conf.wdgteal)[#link("https://www.test-immunization.ca/exemptions")]. Veuillez noter que cette exemption est uniquement pour la garde d'enfants et qu'une nouvelle exemption sera requise lors de l'inscription à l'école primaire.],
  [#if "qr_img" in client [
    #if "qr_url" in client [
      #link(client.qr_url)[#image(client.qr_img, width: 3cm)]
    ] else [
      #image(client.qr_img, width: 3cm)
    ]
  ]]
)

En cas d'éclosion d'une maladie évitable par la vaccination, la Santé publique peut exiger que les enfants qui ne sont pas adéquatement immunisés (y compris ceux avec exemptions) soient exclus du centre de garde d'enfants jusqu'à la fin de l'éclosion. 

Si vous avez des questions sur les vaccins de votre enfant, veuillez appeler le 555-555-5555 poste 1234 pour parler à une infirmière de la Santé publique.

  Sincères salutations, 

#conf.signature("__SIGNATURE_PATH__", "Dr. Jane Smith, MPH", "Médecin hygiéniste adjoint")

// Invisible marker for layout validation
#box(width: 0pt, height: 0pt)[
  #text(size: 0.1pt, fill: white)[MARK_END_SIGNATURE_BLOCK]
]
  
]

#let vaccine_table_page(client_id) = block[
  
  #v(0.5cm)

  #grid(
  
  columns: (50%,50%), 
  gutter: 5%, 
  [#image("__LOGO_PATH__", width: 6cm)],
  [#set align(center + bottom)
    #text(size: 20.5pt, fill: black)[*Dossier d'immunisation*]]
  
)

  #v(0.5cm)

  Pour votre référence, les immunisations enregistrées auprès de la Santé publique sont les suivantes :  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  Fin du dossier d'immunisation ]
"""

DYNAMIC_BLOCK = """
#let client_row = __CLIENT_ROW__
#let data = __CLIENT_DATA__
#let vaccines_due = __VACCINES_DUE_STR__
#let vaccines_due_array = __VACCINES_DUE_ARRAY__
#let received = __RECEIVED__
#let num_rows = __NUM_ROWS__
#let diseases = __CHART_DISEASES_TRANSLATED__
#let date = data.date_data_cutoff

#set page(
  margin: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm),
  footer: align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
)

#immunization_notice(data, client_row, vaccines_due_array, date, 11pt)
#pagebreak()
#vaccine_table_page(client_row.at(0))
#conf.immunization-table(5, num_rows, received, diseases, 10.6pt, "fr")
#end_of_immunization_notice()
"""


def render_notice(
    context: Mapping[str, str],
    *,
    logo_path: str,
    signature_path: str,
) -> str:
    """Render the Typst document for a single French notice.

    Parameters
    ----------
    context : Mapping[str, str]
        Dictionary containing template placeholder values. Must include:
        - client_row: Row identifier
        - client_data: Client information dict
        - vaccines_due_str: Formatted string of vaccines due
        - vaccines_due_array: Array of vaccines due
        - received: Received vaccine data
        - num_rows: Number of table rows
        - chart_diseases_translated: Translated disease names for chart columns

    logo_path : str
        Absolute path to logo image file
    signature_path : str
        Absolute path to signature image file

    Returns
    -------
    str
        Rendered Typst template with all placeholders replaced

    Raises
    ------
    KeyError
        If any required context keys are missing
    """
    required_keys = (
        "client_row",
        "client_data",
        "vaccines_due_str",
        "vaccines_due_array",
        "received",
        "num_rows",
        "chart_diseases_translated",
    )
    missing = [key for key in required_keys if key not in context]
    if missing:
        missing_keys = ", ".join(missing)
        raise KeyError(f"Missing context keys: {missing_keys}")

    prefix = TEMPLATE_PREFIX.replace("__LOGO_PATH__", logo_path).replace(
        "__SIGNATURE_PATH__", signature_path
    )

    dynamic = (
        DYNAMIC_BLOCK.replace("__CLIENT_ROW__", context["client_row"])
        .replace("__CLIENT_DATA__", context["client_data"])
        .replace("__VACCINES_DUE_STR__", context["vaccines_due_str"])
        .replace("__VACCINES_DUE_ARRAY__", context["vaccines_due_array"])
        .replace("__RECEIVED__", context["received"])
        .replace("__NUM_ROWS__", context["num_rows"])
        .replace("__CHART_DISEASES_TRANSLATED__", context["chart_diseases_translated"])
    )
    return prefix + dynamic
