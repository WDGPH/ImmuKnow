# Run from a scratch folder prepared as described in the documentation guide.
# Six fictional clients, real execution, normal playback speed.
Output notice-demo.gif
Require immuknow
Set Shell bash
Set Width 1200
Set Height 600
Set FontSize 19
Set FontFamily "FreeMono"
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
Type "# Create notices for six fictional clients"
Enter
Type "immuknow run clients.csv --notice-assignments notices.json --templates project/templates --config project/config --output runs"
Enter
Wait+Line /\$$/
Sleep 1500ms
Type "ls runs/*/"
Enter
Wait+Line /\$$/
Sleep 2s
Type "# Open report.html to review findings and notices."
Enter
Sleep 3s
