Version 4
SymbolType CELL
RECTANGLE Normal 16 40 32 88
LINE Normal 32 40 64 8
LINE Normal 64 8 64 120
LINE Normal 64 120 32 88
LINE Normal 0 32 16 32
LINE Normal 16 32 16 40
LINE Normal 0 96 16 96
LINE Normal 16 96 16 88
TEXT 4 24 Left 0 +
WINDOW 0 72 32 Left 2
WINDOW 3 72 96 Left 2
SYMATTR Value Re=6.4 Fs=80 Qms=5 Qes=1 Le=0.7m n=0.7
SYMATTR Prefix X
SYMATTR SpiceModel speaker
SYMATTR ModelFile speaker.sub
SYMATTR Description Loudspeaker impedance from Thiele-Small parameters. Pins P N
PIN 0 32 NONE 8
PINATTR PinName P
PINATTR SpiceOrder 1
PIN 0 96 NONE 8
PINATTR PinName N
PINATTR SpiceOrder 2
