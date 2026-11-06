# Run from a scratch folder prepared as described in the documentation guide.
# Six fictional clients, real execution, normal playback speed.
Output notice-demo.gif
Require immuknow
Set Shell bash
Set Width 1000
Set Height 760
Set FontSize 24
Set FontFamily "DejaVu Sans Mono"
Set Theme "Catppuccin Frappe"
Set Padding 24
Set WindowBar Colorful
Set BorderRadius 12
Set Framerate 8
Set TypingSpeed 18ms
Set PlaybackSpeed 1
Set CursorBlink false
Hide
Type "export PS1='$ '; clear"
Enter
Sleep 500ms
Show
Type "immuknow run clients.csv --notices notices.json"
Enter
Wait+Line /\$$/
Sleep 7s
