import ast
import inspect
import sys
from typing import List


class Visit(ast.NodeVisitor):
    def __init__(self):
        self.scope = []  # type: List[str]

    def at_global_scope(self):
        return not self.scope

    def generic_visit(self, node: ast.AST):
        raise Exception(node)

    def recurse(self, node: ast.AST):
        for child in ast.iter_child_nodes(node):
            yield from self.visit(child)

    def visit_Module(self, node: ast.Module):
        yield '/* module */'
        yield from self.doc_body(node)

    def doc_body(self, node):
        fiddled = list(node.body)
        possible_docstring = fiddled[0]
        if isinstance(possible_docstring, ast.Expr) and \
                isinstance(possible_docstring.value, ast.Str):
            fiddled.pop(0)
            docstring = inspect.cleandoc(possible_docstring.value.s)
            yield '\n'.join('/// {}'.format(x) for x in docstring.split('\n')) + '\n'

        for item in fiddled:
            yield from self.visit(item)

    def visit_Expr(self, node: ast.Expr):
        yield '/* expr */'
        yield from self.recurse(node)
        yield ';\n'

    def visit_Str(self, node: ast.Str):
        yield rust_str(node.s)

    def visit_Import(self, node: ast.Import):
        for name in node.names:
            yield 'use {};\n'.format(strip_alias(name))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for mod in node.names:
            yield 'use {}::{};\n'.format(node.module.replace('.', '::'), strip_alias(mod.name))

    def visit_Assign(self, node: ast.Assign):
        if self.at_global_scope():
            yield 'const'
        if len(node.targets) == 1:
            yield from self.visit(node.targets[0])
        else:
            yield '('
            for item in node.targets:
                yield from self.visit(item)
                yield ','
            yield ')'

        if self.at_global_scope():
            yield ': Unknown'
        yield ' = '
        yield from self.visit(node.value)
        yield ';\n'

    def visit_Store(self, node: ast.Store):
        yield '/* store */'

    def visit_Name(self, node: ast.Name):
        # yield '/* name */'
        yield node.id

    def visit_Call(self, node: ast.Call):
        yield '/* call */'
        yield from self.visit(node.func)
        yield '('
        for arg in node.args:
            yield from self.visit(arg)
            yield ','
        yield ')'

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        yield 'unimplemented!(' + rust_str(ast.dump(node)) + ')'

    def visit_ListComp(self, node: ast.GeneratorExp):
        yield 'unimplemented!(' + rust_str(ast.dump(node)) + ')'

    def visit_SetComp(self, node: ast.GeneratorExp):
        yield 'unimplemented!(' + rust_str(ast.dump(node)) + ')'

    def visit_DictComp(self, node: ast.GeneratorExp):
        yield 'unimplemented!(' + rust_str(ast.dump(node)) + ')'

    def visit_ClassDef(self, node: ast.ClassDef):
        yield 'impl ' + node.name + '{\n'
        yield from self.doc_body(node)
        yield '}\n'

    def visit_Tuple(self, node: ast.Tuple):
        yield '&['
        for element in node.elts:
            yield from self.visit(element)
            yield ','
        yield ']'

    def visit_BinOp(self, node: ast.BinOp):
        if isinstance(node.op, ast.Mod):
            yield 'format!('
            yield from self.visit(node.left)
            yield from self.visit(node.right)
            yield ')'
            return

        yield from self.visit(node.left)
        yield from self.visit(node.op)
        yield from self.visit(node.right)

    def visit_Add(self, node: ast.Add):
        yield '+'

    def visit_Sub(self, node: ast.Add):
        yield '-'

    def visit_Not(self, node: ast.Not):
        yield '!'

    def visit_BitOr(self, node: ast.Not):
        yield '|'

    def visit_BitAnd(self, node: ast.Not):
        yield '&'

    def visit_IsNot(self, node: ast.IsNot):
        yield '/* is not */ !='

    def visit_And(self, node: ast.And):
        yield ' && '

    def visit_Or(self, node: ast.Or):
        yield ' || '

    def visit_Eq(self, node: ast.NotEq):
        yield ' == '

    def visit_Is(self, node: ast.NotEq):
        yield ' /* is */ == '

    def visit_NotEq(self, node: ast.NotEq):
        yield ' != '

    def visit_USub(self, node: ast.USub):
        yield '-'

    def visit_Gt(self, node):
        yield '>'

    def visit_Lt(self, node):
        yield '<'

    def visit_LtE(self, node):
        yield '<='

    def visit_GtE(self, node):
        yield '>='

    def visit_FunctionDef(self, node: ast.FunctionDef):
        yield 'fn'
        yield node.name
        assert isinstance(node.args, ast.arguments)
        yield from self.visit(node.args)
        if node.returns:
            yield ' -> '
            yield from self.visit(node.returns)
        yield '{\n'
        self.scope.append('method')
        yield from self.doc_body(node)
        self.scope.pop()
        yield '}'

    def visit_arguments(self, node: ast.arguments):
        assert not node.vararg
        assert not node.kwonlyargs
        # assert not node.defaults
        yield '/* TODO: unimplemented: defaults */'
        assert not node.kwarg
        assert not node.kw_defaults

        yield '('
        for arg in node.args:
            assert isinstance(arg, ast.arg)
            yield from self.visit(arg)
            yield ','
        yield ')'

    def visit_arg(self, node: ast.arg):
        if node.arg == 'self':
            yield '&self'
        else:
            yield node.arg

    def visit_Attribute(self, node: ast.Attribute):
        yield from self.visit(node.value)
        yield '.'
        yield node.attr

    def visit_List(self, node: ast.List):
        if 0 == len(node.elts):
            yield 'Vec::new()'
            return
        yield 'vec!('
        for item in node.elts:
            yield from self.visit(item)
            yield ', '
        yield ')'

    def visit_Dict(self, node: ast.Dict):
        if 0 == len(node.keys):
            yield 'HashMap::new()'
            return

        yield 'hashmap!(\n'
        for i in range(len(node.keys)):
            yield from self.visit(node.keys[i])
            yield ' => '
            yield from self.visit(node.values[i])
            yield ',\n'
        yield ')'

    def visit_Try(self, node: ast.Try):
        yield 'if /* try */ {'
        for item in node.body:
            yield from self.visit(item)
        yield '} else {\n'
        yield 'unimplemented!("multilple handlers:");\n'
        for handler in node.handlers:
            yield from self.visit(handler)
        yield '}\n\n'

        assert not node.orelse

        for item in node.finalbody:
            yield from self.visit(item)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        yield '/* '
        yield from self.visit(node.type)
        yield ' */'
        for item in node.body:
            yield from self.visit(item)

    def visit_Subscript(self, node: ast.Subscript):
        yield from self.visit(node.value)
        yield '['
        yield from self.visit(node.slice)
        yield ']'

    def visit_Index(self, node: ast.Index):
        yield from self.recurse(node)

    def visit_If(self, node: ast.If):
        yield 'if '
        yield from self.visit(node.test)
        yield '{ \n'
        for item in node.body:
            yield from self.visit(item)
        if node.orelse:
            yield '} else {'
            for item in node.orelse:
                yield from self.visit(item)

        yield '}\n\n'

    def visit_IfExp(self, node: ast.IfExp):
        yield 'if'
        yield from self.visit(node.test)
        yield '{'
        yield from self.visit(node.body)
        yield '} else {'
        yield from self.visit(node.orelse)
        yield '}'

    def visit_Return(self, node: ast.Return):
        yield 'return'
        if node.value:
            yield from self.visit(node.value)
        yield ';\n'

    def visit_Continue(self, node: ast.Continue):
        yield 'continue;\n'

    def visit_Break(self, node: ast.Break):
        yield 'break;\n'

    def visit_For(self, node: ast.For):
        yield 'for'
        yield from self.visit(node.target)
        yield 'in'
        yield from self.visit(node.iter)
        yield '{\n'
        for item in node.body:
            yield from self.visit(item)
        yield '}\n'

    def visit_Compare(self, node: ast.Compare):
        assert 1 == len(node.ops)

        if isinstance(node.ops[0], ast.In) or isinstance(node.ops[0], ast.NotIn):
            assert 1 == len(node.comparators)
            if isinstance(node.ops[0], ast.NotIn):
                yield '!'
            yield from self.visit(node.comparators[0])
            yield '.contains_key('
            yield from self.visit(node.left)
            yield ')'
            return

        assert 1 == len(node.comparators)
        yield from self.visit(node.left)
        yield from self.visit(node.ops[0])
        yield from self.visit(node.comparators[0])

    def visit_NameConstant(self, node: ast.NameConstant):
        yield repr(node.value)

    def visit_BoolOp(self, node: ast.BoolOp):
        it = iter(node.values)
        yield from self.visit(next(it))
        for item in it:
            yield from self.visit(node.op)
            yield from self.visit(item)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        yield from self.visit(node.op)
        yield from self.visit(node.operand)

    def visit_Lambda(self, node: ast.Lambda):
        yield '|'
        yield from self.visit(node.args)
        yield '| '
        yield from self.visit(node.body)

    def visit_Raise(self, node: ast.Raise):
        yield '/* raise */ return Err('
        yield from self.visit(node.exc)
        yield ')'

    def visit_Assert(self, node: ast.Assert):
        yield 'assert!('
        yield from self.visit(node.test)
        yield ')'

    def visit_Num(self, node: ast.Num):
        yield repr(node.n)

    def visit_With(self, node: ast.With):
        yield '{/* <with block> */\n'
        for item in node.items:
            yield from self.visit(item)
        yield '\n/* <-> */\n'

        for item in node.body:
            yield from self.visit(item)

        yield '}/* </with block> */\n\n'

    def visit_withitem(self, node: ast.withitem):
        yield from self.visit(node.optional_vars)
        yield ' = '
        yield from self.visit(node.context_expr)

    def visit_Set(self, node: ast.Set):
        yield 'hashset!('
        for val in node.elts:
            yield from self.visit(val)
            yield ', '
        yield ')'

    def visit_AugAssign(self, node: ast.AugAssign):
        yield from self.visit(node.target)
        yield from self.visit(node.op)
        yield '='
        yield from self.visit(node.value)
        yield ';'

    def visit_While(self, node: ast.While):
        yield 'while '
        yield from self.visit(node.test)
        yield '{\n'
        for item in node.body:
            yield from self.visit(item)
        yield '}\n'

        assert not node.orelse

    def visit_Slice(self, node: ast.Slice):
        assert not node.step
        if node.lower:
            yield from self.visit(node.lower)
        yield '..'
        if node.upper:
            yield from self.visit(node.upper)

    def visit_Delete(self, node: ast.Delete):
        yield 'unimplemented!(' + rust_str(ast.dump(node)) + ')'


def strip_alias(thing) -> str:
    if hasattr(thing, 'name'):
        return thing.name
    return thing


def rust_str(some_str):
    return '"{}"'.format(some_str.encode('unicode_escape').replace(b'"', b'\\"').decode('utf-8'))


def main():
    source = sys.argv[1]
    with open(source) as f:
        a = ast.parse(f.read(), source)

    for item in Visit().visit(a):
        print(item, end=' ')


if __name__ == '__main__':
    main()
