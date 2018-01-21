import enum


MAX_STACK_DEPTH = 1000
STACK_ENTRY_POINTERS = 4

@enum.unique
class CallContext(enum.IntEnum):
    stack_depth = 0
    stack_start = 1


class Register(enum.IntEnum):
    ax = 0
    bx = 1
    cx = 2
    dx = 3
    arguments = 4
    pic_table = 5
    call_context = 6
    locals = 7
