UML Runtime Model
=================

Registers
---------

The UML language runtime uses the machine's eight registers in the following
way:

1. ``ax``: General purpose register.
2. ``bx``: General purpose register.
3. ``cx``: General purpose register.
4. ``dx``: General purpose register.
5. ``locals``: Pointer to the array holding the current function's locals.
6. ``pic_table``: Pointer to the array holding the position PIC table. More on
   this below.
7. ``stack``: Pointer to the array holding the stack.
8. ``stack_top``: The index of the next free spot in the stack.

PIC Table
~~~~~~~~~

Arrays and functions are allocated at program launch so we don't know the
address at compile time. The PIC table is an array where each symbol or string
literal holds a fixed offset. At program launch, we allocate and initialize the
"statically" allocated objects and write the runtime address into the PIC
table.

Stack
~~~~~

At program launch, we allocate a large scratch array to use as a stack. The
address of this array is stored in the ``stack`` register. The stack gets used
in cases where the four general purpose registers are not enough to evaluate an
expression. The stack is also used to maintain the function call stack. When
calling a function, we push the pointer to our current locals, then the runtime
address of the current function's array. After the array, we push each argument
in right-to-left order. Finally, we push the execution finger value to pass when
returning to the calling function.

Program Layout
--------------

Each function occupies a unique array. These arrays are initialized in the base
program along with any global arrays or array literals. Once all of the static
arrays are allocated and initialized, the ``main`` function is loaded with no
arguments.

Data
----

Arrays
~~~~~~

Array objects are laid out as a UM-32 array with the first element being the
size of the array, and the remaining elements being the data. This means that
``operator[]`` needs to increment the index by one to address the data, but we
can get the size in constant time.

UInts
~~~~~

A ``uint`` fills a single UM-32 platter.

Builtin Functions
-----------------

All builtin functions are prefixed with ``um.`` to distinguish them from regular
function calls.

``um.alloc(size: uint) -> array``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Allocate a new array of the given size.

``um.free(arr: array) -> void``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Free the given array. The argument must be an array created with ``alloc``

``um.len(arr: array) -> uint``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Return the length of an array.

``um.putchar(c: uint) -> void``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Print the given uint as an ascii character.

``um.exit() -> void``
~~~~~~~~~~~~~~~~~~~~~

Terminate the program.
