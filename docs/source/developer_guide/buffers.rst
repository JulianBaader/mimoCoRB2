Buffers
=======

.. automodule:: mimocorb2.mimo_buffer


Token Handeling
---------------

.. tikz::

    \usetikzlibrary{shapes.geometric}
    \tikzstyle{queue} = [rectangle, minimum width=3cm, minimum height=1cm, text centered, draw=black]
    \tikzstyle{interface} = [ellipse, minimum width=3cm, minimum height=1cm,text centered, draw=black]
    \tikzstyle{arrow} = [thick,->,>=stealth]



    \node (empty_queue) [queue] at (0,2) {Empty Slots};
    \node (observer) [interface] at (0,0) {Observer};
    \node (filled_queue) [queue] at (0,-2) {Filled Slots};
    \node (reader) [interface] at (-4,0) {Reader};
    \node (writer) [interface] at (4,0) {Writer};


    \draw [arrow] (reader) to[out=90, in=180] (empty_queue);
    \draw [arrow] (empty_queue) to[out=0, in=90] (writer);
    \draw [arrow] (writer) to[out=270, in=0] (filled_queue);
    \draw [arrow] (filled_queue) to[out=180, in=270] (reader);

    \draw [arrow] (filled_queue) to[out=180, in=180] (observer);
    \draw [arrow] (observer) to[out=0, in=0] (filled_queue);