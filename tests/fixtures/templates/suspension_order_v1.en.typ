#import "settings.typ": *
#show: notice-style
#notice-page("Rendering fixture")[
  #immuknow.client-block(notice, window: envelope-window, font-size: client-font-size, details: client-details)
  As of #date_as_of
  #immuknow.overdue-diseases(notice, columns: 1, labels: presentation.selected-labels())
  #immuknow.link("https://example.org/records")[Records]
  #immuknow.qr-code(notice, ..qr)
  #immuknow.signature-block(name: "Fixture signer", title: "Rendering test")
]
