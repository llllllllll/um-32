from functools import singledispatch
from itertools import chain
import sys

from . import ast
from . import instructions as instrs
from .immutable import immutable
from .runtime_constants import Register


def _static_allocations_without_literal_arrays(nodes):
    for n, node in enumerate(nodes):
        if ((isinstance(node, ast.Global) and node.type == 'array') or
                isinstance(node, ast.FunctionDef)):
            yield node, n


class OccupiedRegister:
    def __init__(self, underlying_register, allocator):
        self._underlying_register = underlying_register
        self._allocator = allocator

    def release(self):
        self._allocator._given_out.pop()
        self._allocator._registers.append(self._underlying_register)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.release()


class RegisterAllocator:
    def __init__(self):
        self._registers = [Register.ax, Register.bx, Register.cx, Register.dx]
        self._given_out = []

    def _format_given_out(self):
        return '\n  '.join(
            f'{n}: {file}:{line}'
            for n, (file, line) in enumerate(self._given_out, 1)
        )

    def occupy(self):
        try:
            underlying = self._registers.pop()
        except IndexError:
            raise ValueError(
                f'failed to allocate a new register: the registers were given'
                f' out at:\n  {self._format_given_out()}',
            )

        frame = sys._getframe(2)
        self._given_out.append((frame.f_code.co_filename, frame.f_lineno))
        return OccupiedRegister(underlying, self)


class Context(immutable):
    __slots__ = (
        'static_allocations',
        'registers',
        'locals',
        'arguments',
    )

    def __init__(self,
                 static_allocations,
                 registers=None,
                 locals=None,
                 arguments=None):
        if registers is None:
            registers = RegisterAllocator()

        self.static_allocations = static_allocations
        self.registers = registers
        self.locals = locals
        self.arguments = arguments

    def static_address(self, node):
        return self.static_allocations.setdefault(
            node,
            len(self.static_allocations),
        )

    def immediate(self, register, value):
        return instrs.Immediate(register, value, self.registers)


@singledispatch
def compile_node(node, ctx):
    raise NotImplementedError(
        f'cannot compile node of type {type(node).__name__}',
    )


@compile_node.register(ast.FunctionDef)
def _compile_function_def(node, ctx):
    locals_ = {l: n for n, l in enumerate(node.locals)}
    arguments = {arg: n for n, arg in enumerate(node.args)}
    ctx = ctx.update(
        locals=locals_,
        arguments=arguments,
    )

    for subnode in node.body:
        yield from compile_node(subnode, ctx)

    if node.name == 'main':
        yield instrs.Halt()


@singledispatch
def compute_into_register(node, ctx):
    raise NotImplementedError(
        f'cannot compute node of type {type(node).__name__}: {node!r}',
    )


@compute_into_register.register(ast.Local)
def _compute_local(node, ctx):
    out = ctx.registers.occupy()
    address = ctx.locals[node]
    yield ctx.immediate(out, address)
    yield instrs.ArrayIndex(
        out,
        Register.locals,
        out,
    )
    return out


@compute_into_register.register(ast.Argument)
def _compute_argument(node, ctx):
    out = ctx.registers.occupy()
    address = ctx.arguments[node]
    yield ctx.immediate(out, address)
    yield instrs.ArrayIndex(
        out,
        Register.arguments,
        out,
    )
    return out


@compute_into_register.register(ast.Global)
def _compute_global(node, ctx):
    out = ctx.registers.occupy()

    if node.type == 'uint':
        yield ctx.immediate(out, node.value)
    else:
        yield ctx.immediate(out, ctx.static_address(node))

    return out


@compute_into_register.register(ast.UIntLiteral)
def _compute_uint_literal(node, ctx):
    out = ctx.registers.occupy()
    yield ctx.immediate(out, node.value)
    return out


@compute_into_register.register(ast.ArrayLiteral)
def _compute_array_literal(node, ctx):
    out = ctx.registers.occupy()
    yield ctx.immediate(out, ctx.static_address(node))
    return out


@compile_node.register(ast.BuiltinCall)
def _builtin_call(node, ctx):
    if node.name == 'putchar':
        with (yield from compute_into_register(node.args[0], ctx)) as arg:
            yield instrs.Output(arg)
    else:
        raise NotImplementedError(
            f'no implementation for built-in {node.name!r}',
        )


@compute_into_register.register(ast.BinOp)
def _binop(node, ctx):
    lhs = (yield from compute_into_register(node.lhs, ctx))
    with (yield from compute_into_register(node.rhs, ctx)) as rhs:
        if node.op == '+':
            yield instrs.Addition(lhs, lhs, rhs)
        elif node.op == '*':
            yield instrs.Multiplication(lhs, lhs, rhs)
        elif node.op == '/':
            yield instrs.Division(lhs, lhs, rhs)
        else:
            raise NotImplementedError(f'op {node.op} not supported')

    return lhs


@compile_node.register(ast.Assignment)
def _assignment(node, ctx):
    if isinstance(node.lhs, ast.Local):
        address_map = ctx.locals
        array_register = Register.locals
    else:
        address_map = ctx.arguments
        array_register = Register.arguments

    with (yield from compute_into_register(node.rhs, ctx)) as rhs:
        address = address_map[node.lhs]
        with ctx.registers.occupy() as address_register:
            yield ctx.immediate(address_register, address)
            yield instrs.ArrayAmmendment(
                array_register,
                address_register,
                rhs,
            )


def _write_functions(ctx, function_bodies):

    def inner_write_functions():
        main = None

        for address, (name, instructions) in function_bodies.items():
            raw_instructions = [
                instr.raw_instruction for instr in instructions
            ]
            array = ctx.registers.occupy()
            yield instrs.Allocation(array, len(raw_instructions))
            for raw_instruction in raw_instructions:
                with ctx.registers.occupy() as imm:
                    yield ctx.immediate(imm, raw_instruction)

            if name == 'main':
                main = array
            else:
                array.release()

        return main

    main = yield from inner_write_functions()
    if main is None:
        raise SyntaxError('no main function')

    with ctx.registers.occupy() as imm:
        yield ctx.immediate(imm, 0)
        yield instrs.LoadProgram(main, imm)


def compile_ast(nodes):
    static_allocations = dict(
        _static_allocations_without_literal_arrays(nodes),
    )

    ctx = Context(static_allocations)

    function_bodies = {}
    for node in nodes:
        if isinstance(node, ast.FunctionDef):
            function_bodies[static_allocations[node]] = (
                node.name,
                list(
                    chain.from_iterable(
                        instr.low_level_instructions()
                        for instr in compile_node(node, ctx)
                    ),
                ),
            )

    return b''.join(
        ll.raw_instruction.to_bytes(4, 'big')
        for instr in _write_functions(ctx, function_bodies)
        for ll in instr.low_level_instructions()
    )
