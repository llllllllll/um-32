from operator import index

from .runtime_constants import Register


class Address:
    def __init__(self, value=None):
        self.value = value

    def __index__(self):
        value = self.value
        if value is None:
            raise ValueError('address was not set')

        return value


def set_bits(n, start, count, value):
    """Set the bits in ``out`` from [start,start + count) to value.

    Parameters
    ----------
    n : int
        The int to set the bits of.
    start : int
        The start bit to set.
    count : int
        The number of bits to set.
    value : int
        The bitpattern to set.

    Returns
    -------
    set : int
        ``n`` with the bits set.
    """
    mask = ~(((1 << count) - 1) << start)
    return (n & mask) | (value << start)


class Instruction:
    def __init__(self, a=0, b=0, c=0):
        self.a = a
        self.b = b
        self.c = c

    @property
    def raw_instruction(self):
        instruction = set_bits(0, 28, 4, self.opcode)
        instruction = set_bits(instruction, 6, 3, index(self.a))
        instruction = set_bits(instruction, 3, 3, index(self.b))
        instruction = set_bits(instruction, 0, 3, index(self.c))
        return instruction

    def low_level_instructions(self):
        yield self

    def __repr__(self):
        return f'{type(self).__name__}(a={self.a}, b={self.b}, c={self.c})'


class ConditionalMove(Instruction):
    opcode = 0


class ArrayIndex(Instruction):
    opcode = 1


class ArrayAmmendment(Instruction):
    opcode = 2


class Addition(Instruction):
    opcode = 3


class Multiplication(Instruction):
    opcode = 4


class Division(Instruction):
    opcode = 5


class NotAnd(Instruction):
    opcode = 6


class Halt(Instruction):
    opcode = 7

    def __init__(self):
        super().__init__(0, 0, 0)


class Allocation(Instruction):
    opcode = 8

    def __init__(self, result, size):
        super().__init__(0, result, size)


class Abandonment(Instruction):
    opcode = 9

    def __init__(self, register):
        super().__init__(0, 0, register)


class Output(Instruction):
    opcode = 10

    def __init__(self, register):
        super().__init__(0, 0, register)


class Input(Instruction):
    opcode = 11


class LoadProgram(Instruction):
    opcode = 12

    def __init__(self, program, ip):
        super().__init__(0, program, ip)


class Orthography(Instruction):
    opcode = 13
    max_value = 2 ** 25 - 1

    def __init__(self, register, value):
        if value > self.max_value:
            raise ValueError(
                f'cannot store an immediate larger'
                f' than {self.max_value}: {value}',
            )

        self.register = register
        self.value = value

    @property
    def raw_instruction(self):
        instruction = set_bits(0, 28, 4, self.opcode)
        instruction = set_bits(instruction, 25, 3, index(self.register))
        instruction = set_bits(instruction, 0, 25, index(self.value))
        return instruction

    def __repr__(self):
        return f'{type(self).__name__}({self.register}, {self.value})'


class IRInstruction(object):
    def low_level_instructions(self):
        for instr in self.instructions:
            yield from instr.low_level_instructions()


class Immediate(IRInstruction):
    def __init__(self, register, value, register_allocator):
        self.register = register
        self.value = value
        self.allocator = register_allocator

    def low_level_instructions(self):
        register_allocator = self.allocator
        register = self.register
        value = index(self.value)

        quot, rem = divmod(value, Orthography.max_value)
        if quot:
            yield Orthography(register, quot)
            with register_allocator.occupy() as r:
                yield Orthography(r, Orthography.max_value)
                yield Multiplication(register, r, register)

            if rem:
                with register_allocator.occupy() as r:
                    yield Orthography(r, rem)
                    yield Addition(register, r, register)
        else:
            yield Orthography(register, rem)


class Push(IRInstruction):
    def __init__(self, register, register_allocator):
        self.register = register
        self.allocator = register_allocator

    def low_level_instructions(self):
        yield ArrayAmmendment(
            Register.stack,
            Register.stack_top,
            self.register,
        )

        register_allocator = self.allocator
        with register_allocator.occupy() as imm:
            yield from Immediate(
                imm,
                1,
                register_allocator,
            ).low_level_instructions()
            yield Addition(Register.stack_top, Register.stack_top, imm)


class Pop(IRInstruction):
    def __init__(self, register, register_allocator):
        self.register = register
        self.allocator = register_allocator

    def low_level_instructions(self):
        register_allocator = self.allocator
        with register_allocator.occupy() as imm:
            yield from Immediate(
                imm,
                -1 % 2 ** 32,
                register_allocator,
            ).low_level_instructions()
            yield Addition(Register.stack_top, Register.stack_top, imm)

        yield ArrayIndex(self.register, Register.stack, Register.stack_top)
