from functools import partial
import sys

from . import ast
from . import instructions as instrs
from .runtime_constants import Register


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


class FunctionCompiler:
    _hooks = {}

    def _compiles(type_, function, hooks=_hooks):
        hooks[type_] = function
        return function

    compiles = partial(_compiles)
    del _compiles

    def __init__(self):
        self.registers = RegisterAllocator()

    def compute_into_register(self, node):
        out = self.registers.occupy()

        if isinstance(node, ast.Local):
            address = self._locals_address[node.name]
            self.body.extend((
                instrs.Immediate(out, address),
                instrs.ArrayIndex(
                        out,
                        Register.locals,
                        out,
                ),
            ))
        elif isinstance(node, ast.Global):
            if node.type == 'uint':
                self.body.append(instrs.Immediate(out, node.value))
            else:
                self.body.append(
                    instrs.Immediate(
                        out,
                        self.array_address[node.value],
                    ),
                )
        else:
            raise AssertionError(
                f'cannot compute {type(node).__name__} nodes into registers',
            )

        return out

    @compiles(ast.Assignment)  # noqa
    def _(self, node):
        if isinstance(node.lhs, ast.Local):
            address_map = self._local_address
            array_register = Register.locals
        else:
            address_map = self._argument_address
            array_register = Register.arguments

        with self.compute_in_register(node.rhs) as rhs_register:
            address = address_map[node.lhs]
            with self.registers.occupy() as address_register:
                self.body.extend((
                    instrs.Immediate(address_register, address),
                    instrs.ArrayAmmendment(
                        array_register,
                        address_register,
                        rhs_register,
                    ),
                ))

    @compiles(ast.BuiltinCall)  # noqa
    def _(self, node):
        if node.name == 'putchar':
            with self.compute_in_register(node.args[0]) as arg_register:
                self.body.append(instrs.Output(arg_register))
        else:
            raise NotImplementedError(
                f'no implementation for built-in {node.name!r}',
            )
