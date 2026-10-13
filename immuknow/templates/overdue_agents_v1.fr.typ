// @immuknow-settings: settings.typ
#import "settings.typ": *
#show: notice-style // Apply the layout and theme from Settings

// Page 1: the letter. Each if/else below chooses wording for the client or their parent
// over_16 is true for clients aged 16 or older.
#notice-page("Demande de dossier d'immunisation")[
#immuknow.client-block(
  notice,
  window: envelope-window,
  font-size: client-font-size,
  details: client-details,
  addressee: address-addressee,
) // Mailing address and client details
#v(0.3cm) // Space before the message

En date du *#date_as_of*, nos dossiers indiquent que #if notice.client_data.over_16 == true [vous n'avez] else if notice.client_data.over_16 == false [votre enfant n'a] else [la personne nommée n'a] pas reçu les immunisations suivantes :

#set list(indent: 0.8cm)
#strong(immuknow.overdue-agents(notice, columns: list-columns))

Veuillez examiner le dossier d'immunisation à la page 2 et mettre à jour #if notice.client_data.over_16 == true [votre dossier] else if notice.client_data.over_16 == false [le dossier de votre enfant] else [le dossier de la personne nommée] en utilisant l'une des options suivantes :

1. En visitant #link(records-url)
2. En envoyant un courriel à #link("mailto:" + records-email)[#records-email]
3. En envoyant par la poste une photocopie #if notice.client_data.over_16 == true [de votre dossier d'immunisation] else if notice.client_data.over_16 == false [du dossier d'immunisation de votre enfant] else [du dossier d'immunisation de la personne nommée] à #health-unit-name, #health-unit-address
4. Par téléphone : #health-unit-phone

Veuillez informer la Santé publique#if notice.client_data.over_16 == false [ et votre centre de garde d'enfants] chaque fois que #if notice.client_data.over_16 == true [vous recevez] else if notice.client_data.over_16 == false [votre enfant reçoit] else [la personne nommée reçoit] un vaccin.

#grid(
  columns: (1fr, auto),
  gutter: 10pt,
  [*Si vous choisissez de ne pas #if notice.client_data.over_16 == true [vous faire vacciner] else if notice.client_data.over_16 == false [immuniser votre enfant] else [immuniser la personne nommée]*, une exemption médicale valide ou une déclaration de conscience ou de croyance religieuse doit être remplie et soumise à la Santé publique. Les liens vers ces formulaires se trouvent à #link(exemptions-url). Veuillez noter que cette exemption est uniquement pour la garde d'enfants et qu'une nouvelle exemption sera requise lors de l'inscription à l'école primaire.],
  [#immuknow.qr-code(notice, ..qr)]
)

En cas d'éclosion, les enfants qui ne sont pas adéquatement immunisés peuvent être exclus du centre de garde d'enfants.

Si vous avez des questions sur #if notice.client_data.over_16 == true [vos vaccins] else if notice.client_data.over_16 == false [les vaccins de votre enfant] else [les vaccins de la personne nommée], veuillez appeler le #health-unit-phone pour parler à une infirmière de la Santé publique.

  Sincères salutations,

#immuknow.signature-block(
  signature: signature,
  name: signature-name,
  title: "Médecin hygiéniste adjoint",
)

]

#notice-page("Dossier d’immunisation")[
  Pour votre référence, les immunisations enregistrées auprès de la Santé publique sont les suivantes :

  #immunization-history()
  #align(center)[Fin du dossier d'immunisation]
]

// Privacy notice: edit wording and contact details here
#immuknow.privacy-notice[
  Les renseignements figurant dans cet avis ont été recueillis en vertu de la _Loi sur la protection et la promotion de la santé_, conformément à la _Loi sur l’accès à l’information municipale et la protection de la vie privée_ et à la _Loi sur la protection des renseignements personnels sur la santé_. Ces renseignements servent à la prestation de programmes et de services de santé publique, à l’administration de l’organisme ainsi qu’à la tenue de bases de données et de registres de santé et aux recherches connexes, dans le respect des exigences légales et réglementaires. Toute question concernant la gestion de ces renseignements doit être adressée au responsable de la protection de la vie privée au 1-800-555-0100, poste 1234, ou à privacy\@example.org.
]
