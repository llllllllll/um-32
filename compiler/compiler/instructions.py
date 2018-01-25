from operator import index

from .runtime_constants import Register, CallContext, STACK_ENTRY_POINTERS


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


def _get_register_int(r):
    try:
        return r._underlying_register
    except AttributeError:
        return r


class Instruction:
    def __init__(self, a=0, b=0, c=0):
        self.a = _get_register_int(a)
        self.b = _get_register_int(b)
        self.c = _get_register_int(c)

    @property
    def raw_instruction(self):
        instruction = set_bits(0, 28, 4, self.opcode)
        instruction = set_bits(instruction, 6, 3, index(self.a))
        instruction = set_bits(instruction, 3, 3, index(self.b))
        instruction = set_bits(instruction, 0, 3, index(self.c))
        return instruction.to_bytes(4, 'big')

    def instructions(self):
        yield self.raw_instruction

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
        return instruction.to_bytes(4, 'big')

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
        register = self.register
        value = self.value

        if value <= Orthography.max_value:
            yield Orthography(register, value)

        else:
            with self.allocator.occupy() as acc:
                yield Orthography(register, Orthography.max_value)
                value -= Orthography.max_value
                while value > Orthography.max_value:
                    yield Orthography(acc, Orthography.max_value)
                    yield Addition(register, register, acc)
                    value -= Orthography.max_value

                if value:
                    yield Orthography(acc, value)
                    yield Addition(register, register, acc)


class AddImmediate(IRInstruction):
    def __init__(self, register, literal, accumulator_register):
        self.instructions = (
            Immediate(accumulator_register, literal),
            Addition(register, register, accumulator_register),
        )


class SubImmediate(IRInstruction):
    def __init__(self, register, literal, accumulator_register):
        self.instructions = (
            Immediate(
                accumulator_register,
                (~literal + 1 + (1 << 32)) % (1 << 32),
            ),
            Addition(register, register, accumulator_register),
        )


class MultiplyImmediate(IRInstruction):
    def __init__(self, register, literal, accumulator_register):
        self.instructions = (
            Immediate(accumulator_register, literal),
            Multiplication(register, register, accumulator_register),
        )


class DivideImmediate(IRInstruction):
    def __init__(self, register, literal, accumulator_register):
        self.instructions = (
            Immediate(accumulator_register, literal),
            Division(register, register, accumulator_register),
        )


class AmmendImmediate(IRInstruction):
    def __init__(self, array, index, value):
        self.instructions = (
            Immediate(Register.ax, array),
            Immediate(Register.bx, index),
            Immediate(Register.cx, value),

            ArrayAmmendment(Register.ax, Register.bx, Register.cx),
        )


class Call(IRInstruction):
    def __init__(self, arguments, return_function, current_ip):
        self.instructions = (
            Immediate(Register.bx, CallContext.stack_depth),
            Immediate(Register.cx, 1),
            Addition(Register.ax, Register.bx, Register.cx),
            ArrayAmmendment(
                Register.call_context,
                CallContext.stack_depth,
                Register.ax,
            ),

            # write the return address to the call stack
            MultiplyImmediate(Register.bx, STACK_ENTRY_POINTERS, Register.cx),
            # add 17 because that is how many instructions a call takes
            Immediate(Register.cx, current_ip + 17),
            ArrayAmmendment(
                Register.call_context,
                Register.bx,
                Register.cx,
            ),

            AddImmediate(Register.bx, 1, Register.cx),
            Immediate(Register.cx, return_function),
            ArrayAmmendment(
                Register.call_context,
                Register.bx,
                Register.cx,
            ),

            AddImmediate(Register.bx, 1, Register.dx),
            ArrayAmmendment(
                Register.call_context,
                Register.bx,
                Register.locals,
            ),

            AddImmediate(Register.bx, 1, Register.dx),
            ArrayAmmendment(
                Register.call_context,
                Register.bx,
                Register.arguments,
            ),

            # fill the registers for the jump
            Immediate(Register.arguments, arguments),

            Immediate(Register.ax, 0),
            LoadProgram(Register.cx, Register.ax)
        )


class Return(IRInstruction):
    def __init__(self, allocator):
        self.instructions = (
            Immediate(Register.ax, CallContext.stack_depth),
            ArrayIndex(Register.bx, Register.call_context, Register.ax),

            UnconditionalMove(Register.cx, Register.bx, Register.dx),
            SubImmediate(Register.bx, 1, Register.dx),

            ArrayAmmendment(
                Register.call_context,
                Register.ax,
                Register.bx,
            ),

            MultiplyImmediate(Register.cx, STACK_ENTRY_POINTERS, Register.dx),

            ArrayIndex(
                Register.cx,
                Register.call_context,
                Register.cx,
            ),

            SubImmediate(Register.cx, 1, Register.dx),
            ArrayIndex(
                Register.locals,
                Register.call_context,
                Register.cx,
            ),

            SubImmediate(Register.cx, 1, Register.dx),
            ArrayIndex(
                Register.bx,
                Register.call_context,
                Register.cx,
            ),

            SubImmediate(Register.cx, 1, Register.dx),
            ArrayIndex(
                Register.ax,
                Register.call_context,
                Register.cx,
            ),

            LoadProgram(Register.ax, Register.bx),
        )


class Jump(IRInstruction):
    def __init__(self, ip):
        self.instructions = (
            Immediate(Register.ax, 0),
            Immediate(Register.bx, ip),
            LoadProgram(Register.ax, Register.bx),
        )


class JumpIfTrue(IRInstruction):
    def __init__(self, condition_register, ip, current_ip, tmp_register):
        self.instructions = (
            # add 4 to current ip to jump past the load
            Immediate(tmp_register, current_ip + 4),
            ConditionalMove(tmp_register, ip, condition_register),
            Immediate(Register.bx, 0),
            LoadProgram(Register.bx, tmp_register),
        )


class JumpIfFalse(IRInstruction):
    def __init__(self, condition_register, ip, current_ip, tmp_register):
        self.instructions = (
            # add 4 to current ip to jump past the load
            Immediate(tmp_register, ip + 4),
            ConditionalMove(tmp_register, current_ip, condition_register),
            Immediate(Register.bx, 0),
            LoadProgram(Register.bx, tmp_register),
        )


class ReadSymbol(IRInstruction):
    def __init__(self, register, pic_address):
        self.instructions = (
            Immediate(Register.ax, pic_address),
            ArrayIndex(register, Register.pic_table, Register.ax),
        )


class UnconditionalMove(IRInstruction):
    def __init__(self, a, b, true_register):
        self.instructions = (
            Immediate(true_register, 1),
            ConditionalMove(a, b, true_register),
        )
