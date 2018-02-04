from functools import singledispatch, partial
from itertools import chain
import sys

from . import ast
from . import instructions as instrs
from .immutable import immutable
from .runtime_constants import Register, STACK_SIZE


def _static_allocations_without_literal_arrays(nodes):
    for n, node in enumerate(nodes):
        if ((isinstance(node, ast.Global) and node.type == 'array') or
                isinstance(node, ast.FunctionDef)):
            yield node, n


class OccupiedRegister:
    def __init__(self, underlying_register, allocator):
        self._underlying_register = underlying_register
        self._allocator = allocator

    def __index__(self):
        return self._underlying_register

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

        frame = sys._getframe(1)
        self._given_out.append((frame.f_code.co_filename, frame.f_lineno))
        return OccupiedRegister(underlying, self)


class Context(immutable):
    __slots__ = (
        'static_allocations',
        'registers',
        'locals',
        'current_array_address',
    )

    def __init__(self,
                 static_allocations,
                 registers=None,
                 locals=None,
                 current_array_address=None):
        if registers is None:
            registers = RegisterAllocator()

        self.static_allocations = static_allocations
        self.registers = registers
        self.locals = locals
        self.current_array_address = current_array_address

    def static_address(self, node):
        return self.static_allocations.setdefault(
            node,
            len(self.static_allocations),
        )

    def immediate(self, register, value):
        return instrs.Immediate(register, value, self.registers)

    def push(self, register):
        return instrs.Push(register, self.registers)

    def pop(self, register):
        return instrs.Pop(register, self.registers)


@singledispatch
def compile_node(node, ctx):
    raise NotImplementedError(
        f'cannot compile node of type {type(node).__name__}',
    )


@compile_node.register(ast.FunctionDef)
def _compile_function_def(node, ctx):
    locals_ = {l: n for n, l in enumerate(chain(node.args, node.locals))}
    ctx = ctx.update(
        locals=locals_,
        current_array_address=ctx.static_allocations[node],
    )

    with ctx.registers.occupy() as imm:
        yield ctx.immediate(imm, len(node.locals) + len(node.args))
        yield instrs.Allocation(Register.locals, imm)

    if node.args:
        with ctx.registers.occupy() as return_address:
            yield ctx.pop(return_address)

            for n in range(len(node.args)):
                with ctx.registers.occupy() as arg:
                    yield ctx.pop(arg)
                    with ctx.registers.occupy() as ix:
                        yield ctx.immediate(ix, n)

                        yield instrs.ArrayAmmendment(Register.locals, ix, arg)

            yield ctx.push(return_address)

    for subnode in node.body:
        yield from compile_node(subnode, ctx)

    yield instrs.Abandonment(Register.locals)

    if node.name == 'main':
        yield instrs.Halt()
    else:
        with ctx.registers.occupy() as return_array, \
                ctx.registers.occupy() as return_address:
            yield ctx.pop(return_address)
            yield ctx.pop(return_array)

            # restore locals
            yield ctx.pop(Register.locals)

            yield instrs.LoadProgram(return_array, return_address)


@compile_node.register(ast.Call)
def _compile_call(node, ctx):
    return _call(False, node, ctx)


def _call(expr, node, ctx):
    assert not (node.type == 'void' and expr), (
        'cannot use void call in expression'
    )

    # save the current locals
    yield ctx.push(Register.locals)

    with ctx.registers.occupy() as current_address:
        yield ctx.immediate(current_address, ctx.current_array_address)
        yield instrs.ArrayIndex(
            current_address,
            Register.pic_table,
            current_address,
        )
        yield ctx.push(current_address)

    # compute args rtl so that TOS is args[0] when we are done
    for arg in reversed(node.args):
        with (yield from compute_into_register(arg, ctx)) as r:
            yield ctx.push(r)

    with ctx.registers.occupy() as call_addr:
        function_address = ctx.static_allocations[ast.FunctionDef(
            node.function,
            (),
            (),
            (),
            node.type,
        )]
        yield ctx.immediate(call_addr, function_address)
        ret_address = (
            yield instrs.ArrayIndex(call_addr, Register.pic_table, call_addr)
        )

        with ctx.registers.occupy() as imm:
            # use an orthography instead of immediate to ensure a fixed size
            # between the address and the place to resume
            yield instrs.Orthography(imm, ret_address + 6)
            yield ctx.push(imm)

            yield instrs.Orthography(imm, 0)
            yield instrs.LoadProgram(call_addr, imm)

    if not expr:
        return None

    out = ctx.registers.occupy()

    # we store the return value in the stack array at index 0
    yield ctx.immediate(out, 0)
    yield instrs.ArrayIndex(out, Register.stack, out)

    return out


@compile_node.register(ast.Return)
def _compile_return(node, ctx):
    if node.value is None:
        return

    with (yield from compute_into_register(node.value, ctx)) as r, \
            ctx.registers.occupy() as imm:
        # we store return values in the stack array at index 0
        yield ctx.immediate(imm, 0)
        yield instrs.ArrayAmmendment(Register.stack, imm, r)


@singledispatch
def compute_into_register(node, ctx):
    raise NotImplementedError(
        f'cannot compute node of type {type(node).__name__}: {node!r}',
    )


@compute_into_register.register(ast.Call)
def _compute_call(node, ctx):
    return _call(True, node, ctx)


@compute_into_register.register(ast.Local)
@compute_into_register.register(ast.Argument)
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


@compute_into_register.register(ast.Global)
def _compute_global(node, ctx):
    out = ctx.registers.occupy()

    if node.type == 'uint':
        yield ctx.immediate(out, node.value.value)
    else:
        yield ctx.immediate(out, ctx.static_address(node))
        yield instrs.ArrayIndex(out, Register.pic_table, out)

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
    yield instrs.ArrayIndex(out, Register.pic_table, out)
    return out


@compute_into_register.register(ast.BuiltinCall)
def _compute_builtin_call(node, ctx):
    assert node.type != 'void', 'cannot compute void function'

    try:
        f = _builtins[node.name]
    except KeyError:
        raise NotImplementedError(
            f'no implementation for built-in {node.name!r}',
        )

    return f(True, node, ctx)


_builtins = {}


def builtin(f=None, name=None):
    if f is None:
        return partial(builtin, name=name)

    _builtins[name if name is not None else f.__name__] = f
    return f


@builtin
def putchar(expr, node, ctx):
    with (yield from compute_into_register(node.args[0], ctx)) as arg:
        yield instrs.Output(arg)


@builtin(name='exit')
def _exit(expr, node, ctx):
    yield instrs.Halt()


@builtin(name='len')
def _len(expr, node, ctx):
    if not expr:
        return

    out = yield from compute_into_register(node.args[0], ctx)
    with ctx.registers.occupy() as zero:
        yield ctx.immediate(zero, 0)
        yield instrs.ArrayIndex(out, out, zero)

    return out


@builtin
def alloc(expr, node, ctx):
    if not expr:
        # ugh, you can't address this so wtf?
        return

    out = yield from compute_into_register(node.args[0], ctx)
    yield instrs.Allocation(out, out)
    return out


@builtin
def free(expr, node, ctx):
    with (yield from compute_into_register(node.args[0], ctx)) as r:
        yield instrs.Abandonment(r)


@compile_node.register(ast.BuiltinCall)
def _builtin_call(node, ctx):
    try:
        f = _builtins[node.name]
    except KeyError:
        raise NotImplementedError(
            f'no implementation for built-in {node.name!r}',
        )

    return f(False, node, ctx)


@compute_into_register.register(ast.Subscript)
def _compute_subscript(node, ctx):
    if isinstance(node.index, (ast.Global, ast.UIntLiteral)):
        out = yield from compute_into_register(node.array, ctx)
        with ctx.registers.occupy() as ix:
            # add 1 to move past the size
            yield ctx.immediate(ix, node.index.value + 1)
            yield instrs.ArrayIndex(out, out, ix)
    else:
        with (yield from compute_into_register(node.index, ctx)) as ix:
            with ctx.registers.occupy() as imm:
                # add one to move past the size
                yield ctx.immediate(imm, 1)
                yield instrs.Addition(ix, ix, imm)

            out = yield from compute_into_register(node.array, ctx)
            yield instrs.ArrayIndex(out, out, ix)

    return out


@compute_into_register.register(ast.BinOp)
def _binop(node, ctx):
    lhs = yield from compute_into_register(node.lhs, ctx)
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


def _assign_name(node, ctx):
    with (yield from compute_into_register(node.rhs, ctx)) as rhs:
        address = ctx.locals[node.lhs]
        with ctx.registers.occupy() as address_register:
            yield ctx.immediate(address_register, address)
            yield instrs.ArrayAmmendment(
                Register.locals,
                address_register,
                rhs,
            )


def _assign_subscript(node, ctx):
    if isinstance(node.lhs.index, (ast.Global, ast.UIntLiteral)):
        with (yield from compute_into_register(node.lhs.array, ctx)) as arr, \
                ctx.registers.occupy() as ix:
            # add 1 to move past the size
            yield ctx.immediate(ix, node.lhs.index.value + 1)
            with (yield from compute_into_register(node.rhs, ctx)) as rhs:
                yield instrs.ArrayAmmendment(arr, ix, rhs)

    else:
        with (yield from compute_into_register(node.lhs.array, ctx)) as arr, \
                (yield from compute_into_register(node.lhs.index, ctx)) as ix:
            with ctx.registers.occupy() as imm:
                # add 1 to move past the size
                yield ctx.immediate(1)
                yield instrs.Addition(ix, ix, imm)
            with (yield from compute_into_register(node.rhs, ctx)) as rhs:
                yield instrs.ArrayAmmendment(arr, ix, rhs)



@compile_node.register(ast.Assignment)
def _assignment(node, ctx):
    if isinstance(node.lhs, ast.Subscript):
        return _assign_subscript(node, ctx)

    return _assign_name(node, ctx)


def _write_static_allocations(ctx, static_allocations, function_bodies):
    with ctx.registers.occupy() as imm:
        yield ctx.immediate(imm, len(static_allocations))
        yield instrs.Allocation(Register.pic_table, imm)

    with ctx.registers.occupy() as imm:
        yield ctx.immediate(imm, STACK_SIZE)
        yield instrs.Allocation(Register.stack, imm)

    # the stack top is 1 because we store the return at index 0
    yield ctx.immediate(Register.stack_top, 1)

    def inner_write_static_allocations():
        main = None

        for node, address in static_allocations.items():
            if isinstance(node, ast.FunctionDef):
                data = [
                    instr.raw_instruction for instr in function_bodies[node]
                ]
                alloc_size = len(data)
                offset = 0
            else:
                data = node.value
                alloc_size = len(data) + 1  # we store the size inline
                offset = 1

            array = ctx.registers.occupy()
            with ctx.registers.occupy() as size_reg:
                yield ctx.immediate(size_reg, alloc_size)
                yield instrs.Allocation(array, size_reg)

            if not isinstance(node, ast.FunctionDef):
                with ctx.registers.occupy() as imm:
                    yield ctx.immediate(imm, len(data))
                    with ctx.registers.occupy() as ix:
                        yield ctx.immediate(ix, 0)
                        yield instrs.ArrayAmmendment(
                            array,
                            ix,
                            imm,
                        )

            for n, raw_instruction in enumerate(data, offset):
                with ctx.registers.occupy() as imm:
                    yield ctx.immediate(imm, raw_instruction)
                    with ctx.registers.occupy() as ix:
                        yield ctx.immediate(ix, n)
                        yield instrs.ArrayAmmendment(
                            array,
                            ix,
                            imm,
                        )

            with ctx.registers.occupy() as ix:
                yield ctx.immediate(ix, address)
                yield instrs.ArrayAmmendment(Register.pic_table, ix, array)

            if isinstance(node, ast.FunctionDef) and node.name == 'main':
                main = array
            else:
                array.release()

        return main

    main = yield from inner_write_static_allocations()
    if main is None:
        raise SyntaxError('no main function')

    with ctx.registers.occupy() as imm:
        yield ctx.immediate(imm, 0)
        yield instrs.LoadProgram(main, imm)


def _ll_instrs(it):
    ip = 0

    for llinstr in next(it).low_level_instructions():
        ip += 1
        yield llinstr

    while True:
        try:
            ir = it.send(ip)
        except StopIteration:
            return

        for llinstr in ir.low_level_instructions():
            ip += 1
            yield llinstr


def compile_ast(nodes):
    static_allocations = dict(
        _static_allocations_without_literal_arrays(nodes),
    )

    ctx = Context(static_allocations)

    function_bodies = {}
    for node in nodes:
        if isinstance(node, ast.FunctionDef):
            function_bodies[node] = list(_ll_instrs(compile_node(node, ctx)))

    return b''.join(
        ll.raw_instruction.to_bytes(4, 'big')
        for ll in _ll_instrs(_write_static_allocations(
            ctx,
            static_allocations,
            function_bodies,
        ))
    )
