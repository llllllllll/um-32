UML Runtime Model
=================

WARNING: I wrote this on bus over about 6 hours, the code is actual trash right now.

Registers
---------

The UML language runtime uses the machine's eight registers in the following
way:

1. ``ax``: General purpose register.
2. ``bx``: General purpose register.
3. ``cx``: General purpose register.
4. ``dx``: General purpose register.
5. ``arguments``: Pointer to the arguments array passed to the current function.
6. ``pic_table``: Pointer to the array holding the position PIC table. More on
   this below.
7. ``call_context``: The function call context information.
8. ``locals``: The locals of the current function.

PIC Table
~~~~~~~~~

Arrays and functions are allocated at program launch so we don't know the
address at compile time. The PIC table is an array where each symbol or string
literal holds a fixed offset. At program launch, we allocate and initialize the
"statically" allocated objects and write the runtime address into the PIC
table.

Call Context
~~~~~~~~~~~~

The call context is an array which holds the call stack. The layout of this
array is: ``[stack_depth, stack_entries...]``. Each stack entry contains the
following fields:

1. Return Array: The array to return to.
2. Return Execution Finger: The execution finger to restore when returning.
3. Locals: The pointer to the locals array to restore.
4. Arguments: The pointer to the arguments array to restore.

Program Layout
--------------

Each function occupies a unique array. These arrays are initialized in the base
program. Once all of the static arrays are allocated and initialized, the
``main`` function is loaded with no argument.

Program arrays also occupy a unique array in the machine.
