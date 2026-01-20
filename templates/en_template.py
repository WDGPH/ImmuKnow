"""English Typst template renderer.

This module contains the English version of the immunization notice template. The
template generates a 2025 immunization notice in Typst format for dynamic PDF
rendering.

The template defines the notice layout, including client information, immunization
requirements, vaccine records, QR codes, and contact instructions. All placeholder
values (client data, dates, vaccines) are dynamically substituted during rendering.

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

#conf.header_info_cim("__LOGO_PATH__", 6cm, black, 16pt, "Request for Immunization Record")

#v(0.2cm)

#conf.client_info_tbl_en(equal_split: false, vline: false, client, client_id, font_size, "Childcare Centre", 81pt, border: false)

#v(0.3cm)

// Notice for immunizations
As of *#date* our files show that your child has not received the following immunization(s):  

#conf.client_immunization_list(immunizations_due)

Please review the Immunization Record on page 2 and update your child's record by using one of the following options:

1. By visiting #text(fill:conf.linkcolor)[#link("https://www.test-immunization.ca")]
2. By emailing #text(fill:conf.linkcolor)[#link("records@test-immunization.ca")]
3. By mailing a photocopy of your child's immunization record to Test Health, 123 Placeholder Street, Sample City, ON A1A 1A1
4. By Phone: 555-555-5555 ext. 1234

Please update Public Health and your childcare centre every time your child receives a vaccine. 

#grid(
  columns: (1fr, auto),
  gutter: 10pt,
  [*If you are choosing not to immunize your child*, a valid medical exemption or statement of conscience or religious belief must be submitted. Links to these forms can be located at #text(fill:conf.wdgteal)[#link("https://www.test-immunization.ca/exemptions")]. Please note this exemption is for childcare only and a new exemption will be required upon enrollment in elementary school.],
  [#if "qr_img" in client [
    #if "qr_url" in client [
      #link(client.qr_url)[#image(client.qr_img, width: 3cm)]
    ] else [
      #image(client.qr_img, width: 3cm)
    ]
  ]]
)

If there is an outbreak, children who are not adequately immunized may be excluded.

If you have any questions, please call 555-555-5555 ext. 1234.

  Sincerely, 

#conf.signature("__SIGNATURE_PATH__", "Dr. Jane Smith, MPH", "Associate Medical Officer of Health")

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
    #text(size: 20.5pt, fill: black)[*Immunization Record*]]
  
)

  #v(0.5cm)

  For your reference, the immunization(s) on file with Public Health are as follows:  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  End of immunization record ]
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
#conf.immunization-table(5, num_rows, received, diseases, 11pt, "en")
#end_of_immunization_notice()
"""


def render_notice(
    context: Mapping[str, str],
    *,
    logo_path: str,
    signature_path: str,
) -> str:
    """Render the Typst document for a single English notice.

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
