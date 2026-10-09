#let notice = json(sys.inputs.at("data"))
#let template-version = "overdue_agents_v1"
#let template-language = "fr"
#import "lib/immuknow/lib.typ" as ik
#ik.check-notice(notice, version: template-version, language: template-language)
#assert(notice.overdue_agents.len() > 0, message: "This overdue template requires vaccine agent data")

// --- CCEYA NOTICE TEMPLATE (TEST VERSION) --- //
// Description: A typst template that dynamically generates CCEYA templates.
// NOTE: All contact details are placeholders for testing purposes only.
// ----------------------------------------- //

#import "/templates/conf.typ"
#import "/templates/presentation.typ" as presentation

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
#set text(lang: "fr", region: "CA")

// Immunization Notice Section
#let immunization_notice(client, client_id, immunizations_due, date, font_size) = block[

#v(0.2cm)

#conf.header_info_cim(notice.logo_path, 6cm, black, 16pt, "Demande de dossier d'immunisation")

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

Veuillez informer la Santé publique et votre centre de garde d'enfants chaque fois que votre enfant reçoit un vaccin.

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

En cas d'éclosion, les enfants qui ne sont pas adéquatement immunisés peuvent être exclus du centre de garde d'enfants.

Si vous avez des questions sur les vaccins de votre enfant, veuillez appeler le 555-555-5555 poste 1234 pour parler à une infirmière de la Santé publique.

  Sincères salutations, 

#conf.signature(notice.signature_path, "Dr. Jane Smith, MPH", "Médecin hygiéniste adjoint")

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
  [#image(notice.logo_path, width: 6cm)],
  [#set align(center + bottom)
    #text(size: 20.5pt, fill: black)[*Dossier d'immunisation*]]
  
)

  #v(0.5cm)

  Pour votre référence, les immunisations enregistrées auprès de la Santé publique sont les suivantes :  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  Fin du dossier d'immunisation ]

#let client_row = notice.client_id
#let data = notice.client_data
#let vaccines_due_array = notice.overdue_agents
#let received = notice.received
#let diseases = notice.chart_diseases
#let show_validity_markers = notice.show_validity_markers
#let date = presentation.long-date(notice.date_as_of, "fr", required: false)

#set page(
  margin: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm),
  footer: align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
)

#immunization_notice(data, client_row, vaccines_due_array, date, 11pt)
#pagebreak()
#vaccine_table_page(client_row)
#conf.immunization-table(5, received, diseases, 10.6pt, "fr", show_validity_markers)
#end_of_immunization_notice()
