Version 4
SymbolType CELL
LINE Normal 16 16 16 24
LINE Normal 16 104 16 112
RECTANGLE Normal 4 24 28 104
LINE Normal 64 64 30 64
LINE Normal 30 64 40 58
LINE Normal 30 64 40 70
TEXT 16 64 Center 0 C
TEXT -4 20 Right 0 CW
LINE Normal -16 64 4 64
TEXT -12 56 Left 0 ctrl
WINDOW 0 72 16 Left 2
WINDOW 3 72 104 Left 2
SYMATTR Value R=100k L=0.1
SYMATTR Prefix X
SYMATTR SpiceModel pot_revlog_vc
SYMATTR ModelFile potentiometer.sub
SYMATTR Description Potentiometer, reverse log (C), rotation = V(CTRL) 0..1. Pins CCW W CW CTRL
PIN 16 112 NONE 8
PINATTR PinName CCW
PINATTR SpiceOrder 1
PIN 64 64 NONE 8
PINATTR PinName W
PINATTR SpiceOrder 2
PIN 16 16 NONE 8
PINATTR PinName CW
PINATTR SpiceOrder 3
PIN -16 64 NONE 8
PINATTR PinName CTRL
PINATTR SpiceOrder 4
