import ast

from . import instructions as instrs
from .runtime_constants import Register, MAX_STACK_DEPTH, STACK_ENTRY_POINTERS
from .static_allocation import (
    AllocationType,
    Literal,
    Symbol,
    build_static_allocation_table,
)


def _compile_ir(body):
    """Compile the intermediate instructions directly to bytecode.
    """
    return b''.join(
        llinstr.bytes
        for instr in body
        for llinstr in instr.low_level_instructions()
    )


def _current_ip(body):
    return sum(
        1
        for instr in body
        for llinstr in instr.low_level_instructions()
    )


class _FunctionCompiler(ast.NodeVisitor):
    class _LocalsCounter(ast.NodeVisitor):
        def __init__(self):
            self._count = 0

        def count(self, node):
            self.visit(node)
            return self._count

        def visit_Name(self, node):
            self._count += isinstance(node.ctx, ast.Store)

    def __init__(self, body, static_allocation_table):
        self._static_allocation_table = static_allocation_table

        self._body = body
        self._locals = {}

        self._unique_id = 0

    def _new_local(self, type_):
        name = f'.{self._unique_id}'
        self._unique_id += 1
        addr = len(self._locals)
        self._locals[name] = (addr, type_)
        return addr

    def _get_local(self, name, type_):
        return self._locals.setdefault(name, (len(self._locals), type_))[0]

    def visit_FunctionDef(self, node):
        body = self._body

        locals_count = self._LocalsCounter().count(node)
        if locals_count:
            body.append(instrs.Allocation(Register.locals, len(self._locals)))

        self.generic_visit(node)

        if node.name == 'main':
            body.append(instrs.Halt())
        else:
            body.extend((
                instrs.Abandonment(Register.locals),
                instrs.Return(),
            ))

    _builtin = {}

    def _putchar(self, args):
        if len(args) != 1:
            raise SyntaxError('putchar takes exactly 1 argument')

        arg, = args

        body = self._body
        if isinstance(arg, ast.Num):
            body.append(instrs.Immediate(Register.ax, arg.n))
        elif isinstance(arg, ast.Str):
            if len(arg.s) != 1:
                raise SyntaxError('putchar only takes length-1 strings')
            body.append(instrs.Immediate(Register.ax, ord(arg.s)))
        elif isinstance(arg, ast.Name):
            if arg.id in self._locals:
                body.extend((
                    instrs.Immediate(Register.ax, self._locals[arg.id][0]),
                    instrs.ArrayIndex(
                        Register.ax,
                        Register.locals,
                        Register.ax,
                    ),
                ))
                if self._locals[arg.id][1] == AllocationType.str:
                    body.extend((
                        instrs.Immediate(Register.bx, 1),
                        instrs.ArrayIndex(
                            Register.ax,
                            Register.ax,
                            Register.bx,
                        ),
                    ))
            elif Symbol(arg.id) in self._static_allocation_table:
                addr, type_, _ = self._static_allocation_table[Symbol(arg.id)]
                if type_ != AllocationType.uint:
                    raise SyntaxError(f'{arg.id} is not a uint')
                body.append(instrs.ReadSymbol(Register.ax, addr))
            else:
                raise SyntaxError('unknown argument')

        body.append(instrs.Output(Register.ax))

    _builtin['putchar'] = _putchar

    def visit_Call(self, node):
        if node.keywords:
            raise SyntaxError('no keyword arguments')

        if (isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == 'um'):
            self._builtin[node.func.attr](self, node.args)
        else:
            raise NotImplementedError('can only call builtins')

    def visit_For(self, node):
        if not isinstance(node.target, ast.Name):
            raise SyntaxError('iteration variable must be a name')
        if not isinstance(node.iter, ast.Name):
            raise SyntaxError('can only loop over a variable')

        loop_index_addr = self._new_local(AllocationType.uint)
        loop_remaining_addr = self._new_local(AllocationType.uint)

        loop_variable_addr = self._get_local(
            node.target.id,
            AllocationType.uint,
        )
        loop_iterator_addr = self._get_local(
            node.iter.id,
            AllocationType.uint,
        )

        end_address = instrs.PlaceholderInt()

        body = self._body
        body.extend((
            # read the loop iterator into dx and the length into cx
            instrs.Immediate(Register.dx, loop_iterator_addr),
            instrs.ArrayIndex(
                Register.dx,
                Register.locals,
                Register.dx,
            ),
            instrs.Immediate(Register.cx, 0),
            instrs.ArrayIndex(
                Register.cx,
                Register.dx,
                Register.cx,
            ),

            # save the loop progress
            instrs.Immediate(Register.ax, loop_remaining_addr),
            instrs.ArrayAmmendment(
                Register.locals,
                Register.ax,
                Register.cx,
            ),

            instrs.Immediate(Register.ax, loop_index_addr),
            # start at 1 because the length is at 0
            instrs.Immediate(Register.bx, 1),
            instrs.ArrayAmmendment(
                Register.locals,
                Register.ax,
                Register.bx,
            ),
        ))
        start_address = _current_ip(body)
        body.extend((
            instrs.JumpIfFalse(
                Register.ax,
                end_address,
                start_address,
                Register.cx,
            ),
            instrs.Output(Register.ax),
            instrs.ArrayIndex(
                Register.ax,
                Register.dx,
                Register.bx,
            ),

            instrs.Immediate(Register.bx, loop_variable_addr),
            instrs.ArrayAmmendment(
                Register.locals,
                Register.bx,
                Register.ax,
            ),
        ))

        self.generic_visit(node)

        body.extend((
            # load the loop iterator into dx
            instrs.Immediate(Register.dx, loop_iterator_addr),
            instrs.ArrayIndex(
                Register.dx,
                Register.locals,
                Register.dx,
            ),

            # load the remaining into cx
            instrs.Immediate(Register.bx, loop_remaining_addr),
            instrs.ArrayIndex(
                Register.cx,
                Register.locals,
                Register.bx,
            ),
            # decrement the progress
            instrs.SubImmediate(Register.cx, 1, Register.ax),
            instrs.ArrayAmmendment(
                Register.locals,
                Register.bx,
                Register.cx,
            ),

            # load the current index into bx
            instrs.Immediate(Register.ax, loop_index_addr),
            instrs.ArrayIndex(
                Register.bx,
                Register.locals,
                Register.ax,
            ),
            instrs.AddImmediate(Register.bx, 1, Register.ax),
            instrs.Immediate(Register.ax, loop_index_addr),
            instrs.ArrayAmmendment(
                Register.locals,
                Register.ax,
                Register.bx,
            ),

            instrs.Jump(start_address),
        ))
        end_address.value = _current_ip(body)

    def visit_Assign(self, node):
        body = self._body

        if (isinstance(node.value, ast.Num) and
            not (isinstance(node.value.n, int) and
                 0 >= node.value.n >= 2 ** 32 - 1)):
            body.append(instrs.Immediate(Register.cx, node.value.n))
            type_ = AllocationType.uint
        elif isinstance(node.value, ast.Str):
            entry = self._static_allocation_table[Literal(node.value.s)]
            body.append(instrs.ReadSymbol(Register.cx, entry[0]))
            type_ = AllocationType.str
        else:
            raise SyntaxError('invalid rvalue: {node.value!r}')

        for target in node.targets:
            if not isinstance(target, ast.Name):
                raise SyntaxError(f'invalid lvalue: {target!r}')

            address = self._get_local(target.id, type_)
            body.extend((
                instrs.Immediate(Register.bx, address),
                instrs.ArrayAmmendment(
                    Register.locals,
                    Register.bx,
                    Register.cx,
                ),
            ))


def _compile_function(node, static_allocation_table):
    body = []
    _FunctionCompiler(body, static_allocation_table).visit(node)
    return body


def _fill_pic_table(address):
    """Fill in pic_table address with the value of ``Register.arguments`.
    """
    yield instrs.Immediate(Register.bx, address)
    yield instrs.ArrayAmmendment(
        Register.pic_table,
        Register.bx,
        Register.arguments,
    )


def _allocate_list(address, value, static_allocation_table):
    yield instrs.Immediate(Register.bx, len(value) + 4)
    yield instrs.Allocation(Register.arguments, Register.bx)
    yield instrs.Immediate(Register.bx, 0)
    yield instrs.Immediate(Register.cx, len(value))
    yield instrs.ArrayAmmendment(Register.arguments, Register.bx, Register.cx)

    for n, c in enumerate(value):
        yield instrs.Immediate(Register.bx, n + 1)
        yield instrs.Immediate(Register.cx, c)
        yield instrs.ArrayAmmendment(
            Register.arguments,
            Register.bx,
            Register.cx,
        )

    yield from _fill_pic_table(address)


def _allocate_uint(address, value, static_allocation_table):
    yield instrs.Immediate(Register.bx, 4)
    yield instrs.Allocation(Register.arguments, Register.bx)
    yield instrs.Immediate(Register.cx, value)
    yield instrs.Immediate(Register.bx, 0)
    yield instrs.ArrayAmmendment(Register.arguments, Register.bx, Register.cx)

    yield from _fill_pic_table(address)


def _sliding_instructions(bytecode):
    for n in range(len(bytecode) // 4):
        yield int.from_bytes(bytecode[n * 4:n * 4 + 4], 'big')


def _allocate_function(address, value, static_allocation_table):
    body = []
    _FunctionCompiler(body, static_allocation_table).visit(value)

    bytecode = _compile_ir(body)
    instructions = list(_sliding_instructions(bytecode))

    yield instrs.Immediate(Register.bx, len(instructions))
    yield instrs.Allocation(Register.arguments, Register.bx)

    for n, instruction in enumerate(instructions):
        yield instrs.Immediate(Register.ax, n)
        yield instrs.Immediate(Register.dx, instruction)
        yield instrs.ArrayAmmendment(
            Register.arguments,
            Register.ax,
            Register.dx,
        )

    yield from _fill_pic_table(address)


_static_allocation_functions = {
    AllocationType.str: _allocate_list,
    AllocationType.uint: _allocate_uint,
    AllocationType.function: _allocate_function,
}


class CompilationError(Exception):
    def __init__(self, msg):
        self._msg = msg

    def __str__(self):
        return self._msg


def compile(source):
    tree = ast.parse(source)

    static_allocation_table = build_static_allocation_table(tree)

    items = sorted(static_allocation_table.items(), key=lambda t: t[1][0])

    program_body = [
        instrs.Immediate(Register.ax, len(items)),
        instrs.Allocation(Register.pic_table, Register.ax),
        instrs.Immediate(
            Register.ax,
            MAX_STACK_DEPTH *
            STACK_ENTRY_POINTERS +
            1,
        ),
        instrs.Allocation(Register.call_context, Register.ax),
    ]

    for key, (address, type_, value) in items:
        program_body.extend(
            _static_allocation_functions[type_](
                address,
                value,
                static_allocation_table,
            ),
        )

    try:
        main_address = static_allocation_table[Symbol('main')][0]
    except KeyError:
        raise CompilationError('no main function')

    program_body.extend((
        instrs.ReadSymbol(Register.ax, main_address),
        instrs.Immediate(Register.bx, 0),
        instrs.LoadProgram(Register.ax, Register.bx),
    ))

    return _compile_ir(program_body)
