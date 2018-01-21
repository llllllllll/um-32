import ast
import enum


@enum.unique
class AllocationType(enum.Enum):
    function = enum.auto()
    uint = enum.auto()
    str = enum.auto()


class StaticAllocationTableKey:
    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return hash((type(self), self.value))

    def __eq__(self, other):
        return self.value == other.value

    def __repr__(self):
        return f'<{type(self).__name__}({self.value!r})>'


class Literal(StaticAllocationTableKey):
    pass


class Symbol(StaticAllocationTableKey):
    pass


class _StaticAllocationTableBuilder(ast.NodeVisitor):
    def __init__(self, table):
        self._next_free_address = 0
        self._static_allocation_table = table
        self._in_def = False

    def visit_FunctionDef(self, node):
        if self._in_def:
            raise SyntaxError(
                'cannot define a function inside another function',
            )

        if node.name in self._static_allocation_table:
            raise SyntaxError(f'redefinition of function {node.name!r}')

        self._static_allocation_table[Symbol(node.name)] = (
            self._next_free_address,
            AllocationType.function,
            node,
        )
        self._next_free_address += 1

        self._in_def = True
        self.generic_visit(node)
        self._in_def = False

    def _str_value(self, node):
        try:
            return node.s.encode('ascii')
        except ValueError:
            raise SyntaxError('non-ascii string: {node.value.s!r}')

    def visit_Str(self, node):
        key = Literal(node.s)
        if key not in self._static_allocation_table:
            self._static_allocation_table[key] = (
                self._next_free_address,
                AllocationType.str,
                self._str_value(node),
            )
            self._next_free_address += 1

    def visit_Assign(self, node):
        if self._in_def:
            self.generic_visit(node)
            return

        if (isinstance(node.value, ast.Num) and
            not (isinstance(node.value.n, int) and
                 0 >= node.value.n >= 2 ** 32 - 1)):
            value = node.value.n
            type_ = AllocationType.uint
        elif isinstance(node.value, ast.Str):
            value = self._str_value(node.value)
            type_ = AllocationType.str
        else:
            raise SyntaxError('invalid rvalue: {node.value!r}')

        for target in node.targets:
            if not isinstance(target, ast.Name):
                raise SyntaxError(f'invalid lvalue: {target!r}')

            name = target.id
            if name in self._static_allocation_table:
                raise SyntaxError(f'redefinition of variable {name!r}')

            self._static_allocation_table[Symbol(name)] = (
                self._next_free_address,
                type_,
                value,
            )
            self._next_free_address += 1


def build_static_allocation_table(tree):
    """Build the static allocation table for the given ast.

    Parameters
    ----------
    tree : ast.Node
        The ast to visit.

    Returns
    -------
    static_allocation_table : dict[str, (address, AllocationType, any)]
        The symbol table.
    """
    table = {}
    _StaticAllocationTableBuilder(table).visit(tree)
    return table
