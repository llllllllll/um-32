import enum


STACK_SIZE = 2 ** 10


class Register(enum.IntEnum):
    # scratch registers
    ax = 0
    bx = 1
    cx = 2
    dx = 3

    # locals of the current function
    locals = 4

    # position independent code table; used to resolve static allocation
    # addresses to runtime addresses
    pic_table = 5

    # the array representing the call stack
    stack = 6

    # the current stack top index
    stack_top = 7
