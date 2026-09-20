Version 4
SymbolType CELL
LINE Normal 16 16 16 24
LINE Normal 16 104 16 112
RECTANGLE Normal 4 24 28 104
CIRCLE Normal -8 36 40 92
LINE Normal -32 64 -24 64
LINE Normal -24 48 -4 58
LINE Normal -4 58 -12 58
LINE Normal -4 58 -9 51
LINE Normal -24 72 -4 82
LINE Normal -4 82 -12 82
LINE Normal -4 82 -9 75
LINE Normal -24 48 -24 72
TEXT -28 40 Right 0 lux
WINDOW 0 48 24 Left 2
WINDOW 3 48 104 Left 2
SYMATTR Value R10=14.14k gamma=0.6 Rdark=10Meg tau=21.09m ka=0.8336 kLH=1.2 hist=1
SYMATTR Prefix X
SYMATTR SpiceModel ldr
SYMATTR ModelFile ldr.sub
SYMATTR Description CdS LDR, R = R10 (E/10 lux)^-gamma with attack/decay and light history. Pins A B L (V(L) = lux)
PIN 16 16 NONE 8
PINATTR PinName A
PINATTR SpiceOrder 1
PIN 16 112 NONE 8
PINATTR PinName B
PINATTR SpiceOrder 2
PIN -32 64 NONE 8
PINATTR PinName L
PINATTR SpiceOrder 3
