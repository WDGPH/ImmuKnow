#let notice = json(sys.inputs.at("data"))
#let template-version = "overdue_diseases_v1"
#let template-language = "fr"
// @immuknow-settings: settings/overdue_diseases_v1.fr.typ
#import "settings/overdue_diseases_v1.fr.typ": list-columns, history-diseases, history-ignore-agents, history-include-other, history-show-validity, history-min-rows, envelope-window, page-margins, body-font, body-size, logo-width, title-size, signature-width, signature-height, client-font-size, client-details, address-addressee
#import "lib/immuknow/lib.typ" as ik
// Shared project settings are edited by the playground layout selectors.
#let layout = ik.project-layout(json("layout-settings.json"), template-version + "." + template-language, window: envelope-window)
#ik.check-notice(notice, version: template-version, language: template-language)

// --- CCEYA NOTICE TEMPLATE (TEST VERSION) --- //
// Description: A typst template that dynamically generates CCEYA templates.
// NOTE: All contact details are placeholders for testing purposes only.
// ----------------------------------------- //

#import "conf.typ"
#import "presentation.typ" as presentation

#show: ik.notice-page.with(language: template-language, paper: layout.paper, margins: page-margins, font: body-font, font-size: body-size)
#show link: it => box(underline(it))

// Immunization Notice Section
#let immunization_notice(client, date) = block[

#v(0.2cm)

#ik.notice-header(logo: image(notice.logo_path, width: logo-width), logo-width: logo-width, title-size: title-size, title: "Demande de dossier d'immunisation")

#v(0.2cm)

#ik.client-block(notice, window: layout.window, font-size: client-font-size, details: client-details, addressee: address-addressee)

#v(0.3cm)

// Notice for immunizations
En date du *#date*, nos dossiers indiquent que votre enfant n'a pas reçu les immunisations suivantes :  

#set list(indent: 0.8cm)
#strong(ik.overdue-diseases(notice, columns: list-columns, labels: presentation.selected-labels()))

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

#ik.signature-block(signature: image(notice.signature_path, width: signature-width, height: signature-height, fit: "contain"), name: "Dr. Jane Smith, MPH", title: "Médecin hygiéniste adjoint")

  
]

#let vaccine_table_page() = block[
  
  #v(0.5cm)

  #ik.notice-header(logo: image(notice.logo_path, width: logo-width), logo-width: logo-width, title-size: 20.5pt, title: "Dossier d’immunisation")

  #v(0.5cm)

  Pour votre référence, les immunisations enregistrées auprès de la Santé publique sont les suivantes :  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  Fin du dossier d'immunisation ]

#let data = notice.client_data
#let date = presentation.long-date(notice.date_as_of, "fr", required: false)


#immunization_notice(data, date)
#pagebreak()
#vaccine_table_page()
#ik.immunization-history(notice, diseases: history-diseases, ignore-agents: history-ignore-agents, include-other: history-include-other, show-validity: history-show-validity, min-rows: history-min-rows, font-size: 10.6pt, labels: presentation.selected-labels())
#end_of_immunization_notice()
