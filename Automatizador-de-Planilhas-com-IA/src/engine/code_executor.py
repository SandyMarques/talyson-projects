"""Executor isolado de código Pandas gerado por LLM.

Modelo de segurança — defesa em profundidade, na ordem em que cada camada atua:

1. **Análise estática por AST** (`CodeSafetyValidator`): rejeita imports não permitidos,
   acesso a atributos dunder, e chamadas a `eval`/`exec`/`open`/`getattr`/`compile`/
   `__import__` e às funções de I/O do pandas. Diferente da blocklist por regex da versão
   anterior, a AST não pode ser enganada por concatenação de strings, `chr()` ou `%s`.
2. **Isolamento de processo** (`_SandboxRunner`): o código NUNCA executa no processo da
   aplicação. Roda em um subprocesso com diretório de trabalho temporário vazio, `PYTHONPATH`
   neutralizado (só o caminho das bibliotecas numéricas é repassado) e sem nenhuma variável
   de ambiente da aplicação — a API key não existe dentro do sandbox.
3. **Builtins restritos**: sem `open`, `eval`, `exec`, `compile`, `__import__`, `input`,
   `breakpoint`, sem introspecção.
4. **Audit hook** (`sys.addaudithook`): barreira de runtime que bloqueia rede
   (`socket.*`), criação de processos (`subprocess.*`, `os.system`, `os.exec*`, `os.fork`,
   `os.spawn*`), `ctypes`, `shutil`, escrita/remoção no sistema de arquivos e imports fora
   da lista. Cobre inclusive caminhos que a AST não previu, como `pd.io.common.os`.
5. **Limites de recurso**: timeout de parede sempre aplicado; em POSIX também
   `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE` e `RLIMIT_NPROC`. Em Windows, o vetor de
   execução/rede é coberto pelo audit hook e a parada pelo timeout; limites de memória por
   processo dependem de Job Object do SO e não são aplicados (documentado no README).
6. **Entrada imutável**: os DataFrames são serializados em JSON para o subprocesso, então o
   código gerado não tem como mutar o estado da aplicação — só devolver dados novos.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple, Union

import pandas as pd

#: Format string que tenta alcançar atributo via dunder, ex.: `'{0.__class__.__subclasses__}'`.
#: Isso permite escalada sem nenhum ponto no código-fonte, então é barrado na AST. O padrão
#: exige o ponto antes do dunder, então chaves de dicionário legítimas (`f"{d['__init__']}"`)
#: continuam permitidas.
_FORMAT_COM_DUNDER = re.compile(r"\{[^{}]*\.\s*__[A-Za-z0-9_]*__[^{}]*\}")


def _fingerprint(frame: pd.DataFrame) -> str:
    """Hash estável do conteúdo, usado para detectar mutação in-place real de `df`.

    Vive no processo PAI (não no código do sandbox) porque é ele quem decide se o fallback
    "o código mutou `df`" é legítimo.
    """
    import hashlib

    estrutura = (tuple(str(c) for c in frame.columns), tuple(str(d) for d in frame.dtypes))
    try:
        conteudo = frame.to_json(orient="records", date_format="iso", default_handler=str)
    except (ValueError, TypeError):
        conteudo = repr(frame.to_dict("list"))
    return hashlib.sha256((repr(estrutura) + conteudo).encode("utf-8", "replace")).hexdigest()


# ---------------------------------------------------------------------------------------
# Análise estática (AST)
# ---------------------------------------------------------------------------------------

class CodeSafetyError(ValueError):
    """Violação de política de segurança detectada na análise estática."""


class CodeSafetyValidator:
    """Valida código Python gerado por LLM por meio de allow-list de AST."""

    #: Módulos que o código gerado pode importar.
    ALLOWED_IMPORTS: FrozenSet[str] = frozenset(
        {"pandas", "numpy", "datetime", "math", "statistics", "re", "json"}
    )

    #: Nomes de builtins que o código gerado pode chamar diretamente.
    ALLOWED_CALL_NAMES: FrozenSet[str] = frozenset(
        {
            "abs",
            "all",
            "any",
            "bool",
            "callable",
            "chr",
            "dict",
            "divmod",
            "enumerate",
            "filter",
            "float",
            "format",
            "frozenset",
            "hash",
            "hex",
            "int",
            "isinstance",
            "issubclass",
            "iter",
            "len",
            "list",
            "map",
            "max",
            "min",
            "next",
            "oct",
            "ord",
            "pow",
            "print",
            "range",
            "repr",
            "round",
            "set",
            "slice",
            "sorted",
            "str",
            "sum",
            "tuple",
            "type",
            "zip",
        }
    )

    #: Nomes que jamais podem aparecer, nem como chamada nem como referência.
    FORBIDDEN_NAMES: FrozenSet[str] = frozenset(
        {
            "__builtins__",
            "breakpoint",
            "compile",
            "delattr",
            "dir",
            "eval",
            "exec",
            "exit",
            "getattr",
            "globals",
            "help",
            "input",
            "locals",
            "memoryview",
            "open",
            "quit",
            "setattr",
            "vars",
            "__import__",
        }
    )

    #: Atributos proibidos — travam a escalada clássica por introspecção.
    FORBIDDEN_ATTRIBUTES: FrozenSet[str] = frozenset(
        {
            "cr_frame",
            "f_back",
            "f_builtins",
            "f_code",
            "f_globals",
            "f_locals",
            "func_code",
            "func_globals",
            "gi_frame",
            "im_class",
            "im_func",
            "tb_frame",
        }
    )

    #: Métodos perigosos por nome, em qualquer objeto (`x.system(...)`, `x.popen(...)`).
    FORBIDDEN_CALL_ATTRIBUTES: FrozenSet[str] = frozenset(
        {
            "chmod",
            "chown",
            "connect",
            "dump",
            "dumps",
            "execl",
            "execle",
            "execlp",
            "execv",
            "execve",
            "fork",
            "getenv",
            "getoutput",
            "getstatusoutput",
            "import_module",
            "load",
            "loads",
            "makedirs",
            "mkdir",
            "open",
            "popen",
            "putenv",
            "read_bytes",
            "read_text",
            "reload",
            "remove",
            "removedirs",
            "rename",
            "renames",
            "rmdir",
            "rmtree",
            "send",
            "sendall",
            "spawnl",
            "spawnv",
            "startfile",
            "system",
            "to_clipboard",
            "to_csv",
            "to_excel",
            "to_feather",
            "to_gbq",
            "to_hdf",
            "to_json",
            "to_latex",
            "to_markdown",
            "to_orc",
            "to_parquet",
            "to_pickle",
            "to_sql",
            "to_stata",
            "unlink",
            "urlopen",
            "walk",
            "write",
            "write_bytes",
            "write_lines",
            "write_text",
            "writelines",
        }
    )

    #: Leitura de arquivo/BD do pandas — vetor de leitura arbitrária do disco.
    FORBIDDEN_PANDAS_IO: FrozenSet[str] = frozenset(
        {
            "ExcelFile",
            "ExcelWriter",
            "HDFStore",
            "read_clipboard",
            "read_csv",
            "read_excel",
            "read_feather",
            "read_fwf",
            "read_gbq",
            "read_hdf",
            "read_html",
            "read_json",
            "read_orc",
            "read_parquet",
            "read_pickle",
            "read_sas",
            "read_spss",
            "read_sql",
            "read_sql_query",
            "read_sql_table",
            "read_stata",
            "read_table",
            "read_xml",
        }
    )

    #: Nomes reservados: módulos e entradas do sandbox. Filtrados da coleta de nomes locais.
    RESERVED_NAMES: FrozenSet[str] = frozenset(
        {"pd", "pandas", "np", "numpy", "datetime", "math", "re", "json",
         "df", "dfs", "df_result", "dfs_result"}
    )

    #: Subconjunto que o código NÃO pode reatribuir: são as entradas (módulos e abas).
    #: `df_result`/`dfs_result` ficam de fora porque atribuí-los é justamente o contrato.
    READONLY_NAMES: FrozenSet[str] = frozenset(
        {"pd", "pandas", "np", "numpy", "datetime", "math", "re", "json", "df", "dfs"}
    )

    def __init__(self) -> None:
        self._local_names: FrozenSet[str] = frozenset()

    # -- API pública -------------------------------------------------------------------

    def check(self, code: str) -> Tuple[bool, Optional[str]]:
        """Retorna `(True, None)` se o código é aceitável, senão `(False, motivo)`."""
        if not code or not code.strip():
            return False, "Nenhum código foi gerado para execução."

        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            return False, f"O código gerado não é Python válido: {exc}"

        self._local_names = self._collect_defined_names(tree)
        violations: List[str] = []
        for node in ast.walk(tree):
            violations.extend(self._inspect(node))
        if violations:
            unique = list(dict.fromkeys(violations))
            return False, "; ".join(unique)
        return True, None

    def validate(self, code: str) -> None:
        """Como `check`, mas levanta `CodeSafetyError`."""
        is_safe, message = self.check(code)
        if not is_safe:
            raise CodeSafetyError(message or "Código bloqueado pela política de segurança.")

    # -- Verificações ------------------------------------------------------------------

    def _inspect(self, node: ast.AST) -> List[str]:
        violations: List[str] = []

        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in self.ALLOWED_IMPORTS:
                    violations.append(
                        f"import de '{alias.name}' não é permitido "
                        f"(permitidos: {', '.join(sorted(self.ALLOWED_IMPORTS))})"
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.level:
                violations.append("imports relativos não são permitidos")
            else:
                module = (node.module or "").split(".")[0]
                if module not in self.ALLOWED_IMPORTS:
                    violations.append(f"import de '{node.module}' não é permitido")

        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                violations.append(f"acesso ao atributo '{node.attr}' não é permitido")
            elif node.attr in self.FORBIDDEN_ATTRIBUTES:
                violations.append(f"acesso ao atributo '{node.attr}' não é permitido")

        elif isinstance(node, ast.Name):
            if node.id in self.FORBIDDEN_NAMES:
                violations.append(f"uso de '{node.id}' não é permitido")

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _FORMAT_COM_DUNDER.search(node.value):
                violations.append(
                    "acesso a atributo dunder via format string não é permitido "
                    f"({node.value.strip()[:60]!r})"
                )

        elif isinstance(node, ast.Call):
            violations.extend(self._inspect_call(node))

        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets: List[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                for name in self._target_names(target):
                    if name in self.READONLY_NAMES:
                        violations.append(
                            f"reatribuir '{name}' não é permitido: é uma entrada do sandbox "
                            "(módulo ou aba). Devolva o resultado em 'df_result' (DataFrame) "
                            "ou 'dfs_result' (dicionário de abas)"
                        )

        return violations

    def _inspect_call(self, node: ast.Call) -> List[str]:
        func = node.func

        if isinstance(func, ast.Name):
            if func.id in self.FORBIDDEN_NAMES:
                return [f"chamada a '{func.id}()' não é permitido"]
            if func.id not in self.ALLOWED_CALL_NAMES and func.id not in self._local_names:
                return [f"chamada à função desconhecida '{func.id}()' não é permitida"]
            return []

        if not isinstance(func, ast.Attribute):
            return []

        violations: List[str] = []
        if func.attr in self.FORBIDDEN_CALL_ATTRIBUTES:
            violations.append(f"chamada a '.{func.attr}()' não é permitida")
        if func.attr in self.FORBIDDEN_PANDAS_IO:
            violations.append(f"chamada a leitura/escrita de arquivo '.{func.attr}()' não é permitida")
        if isinstance(func.value, ast.Name) and func.value.id in {"pd", "pandas"}:
            if func.attr in self.FORBIDDEN_PANDAS_IO:
                violations.append(f"'pd.{func.attr}()' não é permitido")
        return violations

    @staticmethod
    def _collect_defined_names(tree: ast.AST) -> FrozenSet[str]:
        """Nomes de funções/variáveis definidos pelo próprio snippet.

        Os nomes reservados (módulos e entradas do sandbox) são filtrados: se entrassem aqui,
        seriam injetados no escopo local e sobrescreveriam `pd`/`np`/`dfs`, quebrando o código.
        """
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(CodeSafetyValidator._target_names(target))
            elif isinstance(node, ast.AnnAssign):
                names.update(CodeSafetyValidator._target_names(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                names.update(CodeSafetyValidator._target_names(node.target))
            elif isinstance(node, ast.comprehension):
                names.update(CodeSafetyValidator._target_names(node.target))
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                names.update(CodeSafetyValidator._target_names(node.optional_vars))
            elif isinstance(node, ast.Lambda):
                for arg in node.args.args:
                    names.add(arg.arg)
            elif isinstance(node, ast.arguments):
                for arg in list(node.args) + list(node.kwonlyargs) + list(node.posonlyargs):
                    names.add(arg.arg)
        return frozenset(names - CodeSafetyValidator.RESERVED_NAMES)

    @staticmethod
    def _target_names(target: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                names.update(CodeSafetyValidator._target_names(element))
        return names


# ---------------------------------------------------------------------------------------
# Código executado no subprocesso isolado
# ---------------------------------------------------------------------------------------

#: Programa do subprocesso: recebe o payload por stdin, executa em ambiente restrito e
#: devolve JSON por stdout. Vive aqui (e não em arquivo separado) para que o sandbox tenha
#: um único artefato auditável.
SANDBOX_CHILD_CODE = r'''
import builtins
import json
import os
import sys

payload = json.loads(sys.stdin.read())

# --- 1. ambiente e diretorio ---------------------------------------------------------------
os.environ.clear()   # nenhuma variavel da aplicacao (API keys) existe dentro do sandbox
os.chdir(payload["workdir"])

for extra_path in payload["extra_paths"]:
    # append (nao insert): a stdlib precisa ter precedencia. Ha ambientes com modulos
    # obsoletos na user-site (ex.: uuid.py de Python 2) que, prependidos, sombreiam a stdlib.
    if extra_path and extra_path not in sys.path:
        sys.path.append(extra_path)

# --- 2. limites de recurso (POSIX; em Windows vale audit hook + timeout) --------------------
try:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (payload["cpu_seconds"], payload["cpu_seconds"] + 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if payload.get("enforce_memory_limit"):
        resource.setrlimit(resource.RLIMIT_AS, (payload["memory_bytes"], payload["memory_bytes"]))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except (ValueError, OSError):
        pass
except ImportError:
    pass
except (ValueError, OSError):
    pass

# --- 3. bibliotecas -------------------------------------------------------------------------
# IMPORTANTE: as bibliotecas sao carregadas ANTES de instalar o audit hook. numpy, pandas e
# pyarrow carregam bibliotecas nativas via `ctypes.dlopen` e consultam o registro/paths
# durante o proprio import; com o hook ativo elas nem carregariam. O hook passa a valer para
# TODO o codigo gerado, que e o que importa isolar.
import contextlib
import datetime as datetime_module
import io
import math
import re
import traceback
import types

import numpy as np
import pandas as pd

_PANDAS_BLOCKED = (
    "ExcelFile", "ExcelWriter", "HDFStore", "eval", "get_option", "option_context",
    "read_clipboard", "read_csv", "read_excel", "read_feather", "read_fwf", "read_gbq",
    "read_hdf", "read_html", "read_json", "read_orc", "read_parquet", "read_pickle",
    "read_sas", "read_spss", "read_sql", "read_sql_query", "read_sql_table", "read_stata",
    "read_table", "read_xml", "set_option", "show_versions", "test",
    "to_clipboard", "to_csv", "to_excel", "to_feather", "to_gbq", "to_hdf", "to_json",
    "to_latex", "to_markdown", "to_orc", "to_parquet", "to_pickle", "to_sql", "to_stata",
)
_NUMPY_BLOCKED = (
    "ctypeslib", "distutils", "f2py", "fromfile", "fromregex", "genfromtxt", "load",
    "loads", "loadtxt", "memmap", "save", "savetxt", "savez", "savez_compressed", "testing",
)


def _make_facade(module, blocked, module_name):
    """Namespace somente-leitura com as APIs seguras do modulo.

    Devolve um SimpleNamespace (e NAO um dict): o codigo gerado usa acesso por atributo
    (`pd.to_datetime(...)`, `np.where(...)`), e atributo nao resolve em dict.
    """
    facade = {"__name__": module_name}
    for name in dir(module):
        if name.startswith("_") or name in blocked:
            continue
        try:
            facade[name] = getattr(module, name)
        except Exception:
            continue
    return types.SimpleNamespace(**facade)


safe_pd = _make_facade(pd, _PANDAS_BLOCKED, "pandas")
safe_np = _make_facade(np, _NUMPY_BLOCKED, "numpy")

# --- 5. audit hook: barreira de runtime -------------------------------------------------------
# Instalado AGORA, depois das bibliotecas carregarem. Dali em diante vale para todo o codigo
# gerado: bloqueia rede, criacao de processos, escalada por ctypes, modulos de IO perigosos e
# escrita no sistema de arquivos. Cobre vias que a analise estatica nao previu, como
# `pd.io.common.os`.
BLOCKED_PREFIXES = (
    "ctypes.", "ftplib.", "http.client.", "os.chmod", "os.chown", "os.exec", "os.fork",
    "os.kill", "os.link", "os.listdir", "os.mkdir", "os.putenv", "os.remove", "os.rename",
    "os.rmdir", "os.scandir", "os.spawn", "os.symlink", "os.system", "os.truncate",
    "os.unlink", "os.utime", "os.walk", "shutil.", "smtplib.", "socket.", "subprocess.",
    "urllib.Request", "winreg.",
)
#: Modulos bloqueados na barreira de runtime (vias alternativas, ex.: pd.io.common.os).
BLOCKED_MODULE_IMPORTS = (
    "subprocess", "shutil", "multiprocessing", "webbrowser", "winreg", "pty",
)
#: Trechos de caminho liberados para LEITURA (carga de modulos). Escrita nunca e liberada.
ALLOWED_READ_SNIPPETS = (
    "site-packages", "lib\\", "lib/", "python3", "python31", "libpython",
    ".pyd", ".so", ".dll", ".py", ".pyc", ".zip",
)


def _audit(event, args):
    """Bloqueia processo, rede, ctypes, escrita em disco e modulos de IO."""
    for prefix in BLOCKED_PREFIXES:
        if event.startswith(prefix):
            raise PermissionError("operacao bloqueada no sandbox: %s" % event)

    if event in ("open", "os.open"):
        target = args[0] if args else ""
        if isinstance(target, bytes):
            target = target.decode("utf-8", "ignore")
        elif not isinstance(target, str):
            return  # descritor ja aberto ou objeto sem caminho
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            raise PermissionError("escrita em disco bloqueada no sandbox: %r" % (target,))
        if any(snippet in target.lower() for snippet in ALLOWED_READ_SNIPPETS):
            return
        raise PermissionError("leitura de arquivo bloqueada no sandbox: %r" % (target,))

    if event == "import":
        root = str(args[0]).split(".")[0].lstrip("_") if args else ""
        if root in BLOCKED_MODULE_IMPORTS:
            raise PermissionError("modulo %r bloqueado no sandbox" % (args[0] if args else "",))


sys.addaudithook(_audit)

# --- 6. builtins restritos --------------------------------------------------------------------
_BUILTIN_NAMES = (
    "ArithmeticError", "AttributeError", "BaseException", "Exception", "Ellipsis", "False",
    "FloatingPointError", "IndexError", "KeyError", "LookupError", "NameError",
    "None", "NotImplemented", "NotImplementedError", "OSError", "OverflowError",
    "PermissionError", "RuntimeError", "StopIteration", "True", "TypeError",
    "UnicodeDecodeError", "UnicodeEncodeError", "UnicodeError", "ValueError",
    "ZeroDivisionError", "__build_class__", "abs", "all", "any", "bool", "bytes",
    "callable", "chr", "classmethod", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "getattr", "hasattr", "hash", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "object", "oct",
    "ord", "pow", "print", "property", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "zip",
)

safe_builtins = {}
for _name in _BUILTIN_NAMES:
    if hasattr(builtins, _name):
        safe_builtins[_name] = getattr(builtins, _name)

# --- protecao contra traversal por format string -----------------------------------------------
# `'{0.__class__.__bases__[0].__subclasses__}'.format(df)` alcanca atributos internos SEM usar um
# unico ponto no codigo-fonte, entao a analise estatica nao ve nada e o `format()` builtin nao
# intercepta (o ataque usa o metodo do proprio literal). A defesa efetiva e desarmar o
# `string.Formatter`: nenhuma resolucao de campo pode conter dunder.
# Formatação legitima (`'{}'`, `'{:.2f}'`, `'{0}'`, `'{nome}'`) continua funcionando, porque
# `get_field` e o ponto unico por onde TODA formatacao passa.
import string as _string

_FORMATTER_BASE = _string.Formatter


class _FormatterRestrito(_FORMATTER_BASE):
    """Formatter sem resolucao de atributos dunder em campos."""

    def get_field(self, field_name, args, kwargs):
        for componente in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(field_name)):
            if componente.startswith("__") and componente.endswith("__"):
                raise PermissionError(
                    "acesso a atributo dunder via format string bloqueado no sandbox: %r"
                    % (field_name,)
                )
        return super().get_field(field_name, args, kwargs)


_FORMATTER_RESTRITO = _FormatterRestrito()


def _format_seguro(value, spec=""):
    """Builtin `format()`, implementado via `Formatter.vformat`.

    Chamar `format(value, spec)` direto não passa pelo `get_field` restrito, e é justamente
    ali que a checagem de dunder acontece. `vformat` é o caminho que exercita o Formatter.
    """
    return _FORMATTER_RESTRITO.vformat("{:" + spec + "}", (value,), {})


safe_builtins["format"] = _format_seguro

# Nota de projeto: `str` é imutável, então não é possível substituir `str.format` em runtime
# (TypeError: cannot set 'format' attribute of immutable type 'str'). A defesa contra a
# escalada por format string fica integralmente na AST (`_FORMAT_COM_DUNDER`), que é onde ela
# funciona melhor: rejeita o literal `'{0.__class__}'` sem nenhum falso-positivo em código
# legítimo. O `format()` builtin continua com o Formatter restrito como segunda camada.


def _fingerprint(frame):
    """Hash estavel do conteudo, para detectar mutacao in-place real de df."""
    import hashlib

    estrutura = (tuple(str(c) for c in frame.columns), tuple(str(d) for d in frame.dtypes))
    try:
        conteudo = frame.to_json(orient="records", date_format="iso", default_handler=str)
    except (ValueError, TypeError):
        conteudo = repr(frame.to_dict("list"))
    return hashlib.sha256((repr(estrutura) + conteudo).encode("utf-8", "replace")).hexdigest()

# --- 6. escopo e execucao --------------------------------------------------------------------
dfs = {}
for _sheet_name, _sheet_payload in payload["sheets"].items():
    dfs[_sheet_name] = pd.DataFrame.from_records(
        _sheet_payload["records"], columns=_sheet_payload["columns"]
    )

if not dfs:
    raise ValueError("Nenhuma aba fornecida para o sandbox.")

_first_sheet = list(dfs.keys())[0]
dfs[_first_sheet] = dfs[_first_sheet].copy(deep=True)
local_scope = {}

stdout_buffer = io.StringIO()
# Os dois escopos sao separados de proposito: nomes definidos pelo codigo gerado ficam em
# `local_scope` e nao sobrescrevem os modulos expostos aqui. A chave `__builtins__` precisa
# existir nos DOIS dicionarios — o CPython le os builtins do escopo local quando
# globals e locals sao distintos, e sem ela qualquer chamada a len/print falha.
global_scope = {
    "__builtins__": safe_builtins,
    "__name__": "__main__",
    "pd": safe_pd,
    "pandas": safe_pd,
    "np": safe_np,
    "numpy": safe_np,
    "datetime": datetime_module,
    "math": math,
    "re": re,
    "json": json,
    "dfs": dfs,
    "df": dfs[_first_sheet],
    "df_result": None,
    "dfs_result": None,
}
local_scope = dict(global_scope)

try:
    with contextlib.redirect_stdout(stdout_buffer):
        exec(compile(payload["code"], "<codigo_gerado>", "exec"), global_scope, local_scope)
except BaseException as exc:
    result = {
        "success": False,
        "error": "%s: %s" % (type(exc).__name__, exc),
        "traceback": traceback.format_exc()[-4000:],
        "stdout": stdout_buffer.getvalue()[-4000:],
    }
else:
    df_res = local_scope.get("df_result")
    dfs_res = local_scope.get("dfs_result")

    normalized = {}
    if isinstance(dfs_res, dict):
        for key, value in dfs_res.items():
            if isinstance(value, pd.Series):
                normalized[str(key)] = value.to_frame()
            elif isinstance(value, pd.DataFrame):
                normalized[str(key)] = value

    if df_res is None and normalized:
        df_res = list(normalized.values())[0]

    if df_res is None:
        candidate = local_scope.get("df")
        if isinstance(candidate, pd.DataFrame):
            # Fallback apenas para mutacao in-place REAL: se `df` continua igual ao que
            # entrou, o codigo nao produziu nada e devolver-lo mascararia o erro
            # (ex.: `x = 42` "teria sucesso" retornando a planilha de entrada).
            if _fingerprint(candidate) != payload["df_fingerprint"]:
                df_res = candidate

    if isinstance(df_res, pd.Series):
        df_res = df_res.to_frame()

    if not isinstance(df_res, pd.DataFrame):
        result = {
            "success": False,
            "error": (
                "O código executou, mas nem `df_result` nem `dfs_result` retornaram um "
                "pandas DataFrame válido."
            ),
            "stdout": stdout_buffer.getvalue()[-4000:],
        }
    else:
        result = {
            "success": True,
            "df_result": df_res,
            "dfs_result": normalized or {"Resultado": df_res},
            "stdout": stdout_buffer.getvalue()[-4000:],
        }

# --- 7. serializacao de saida ------------------------------------------------------------------
def _encode_frame(frame):
    safe = frame.copy()
    for column in safe.columns:
        if isinstance(safe[column].dtype, pd.CategoricalDtype):
            safe[column] = safe[column].astype(object)
    safe.columns = [str(c) for c in safe.columns]
    safe = safe.where(pd.notna(safe), None)
    return {
        "__dataframe__": True,
        "columns": [str(c) for c in safe.columns],
        "records": json.loads(safe.to_json(orient="records", date_format="iso", force_ascii=False, default_handler=str)),
    }


try:
    out = {"success": bool(result.get("success")), "stdout": result.get("stdout", "")}
    if out["success"]:
        out["df_result"] = _encode_frame(result["df_result"])
        out["dfs_result"] = {name: _encode_frame(frame) for name, frame in result["dfs_result"].items()}
    else:
        out["error"] = result.get("error")
        out["traceback"] = result.get("traceback")
except Exception as _erro_serializacao:
    out = {
        "success": False,
        "error": "Falha ao serializar o resultado do sandbox: %s: %s"
        % (type(_erro_serializacao).__name__, _erro_serializacao),
        "traceback": traceback.format_exc()[-2000:],
    }

sys.stdout.write(json.dumps(out, ensure_ascii=False))
sys.stdout.flush()
'''


# ---------------------------------------------------------------------------------------
# Runner do subprocesso
# ---------------------------------------------------------------------------------------


@dataclass
class SandboxLimits:
    """Limites de recurso do subprocesso isolado."""

    wall_timeout_seconds: float = 20.0
    cpu_seconds: int = 15
    #: Aplica RLIMIT_AS? Desligado por padrao: o OpenBLAS embutido no numpy reserva espaco de
    #: endereco por thread e, sob RLIMIT_AS, aborta a importacao com "Memory allocation still
    #: failed after 10 retries" — ou seja, o limite quebra o sandbox em vez de protege-lo.
    #: A protecao real contra planilhas gigantes e `max_cells`, aplicado ANTES de executar.
    #: Em deploy conteinerizado, o limite de memoria deve vir do runtime (Docker --memory).
    enforce_memory_limit: bool = False
    memory_bytes: int = 6 * 1024 * 1024 * 1024  # 6 GiB, usado so se enforce_memory_limit
    max_output_bytes: int = 64 * 1024 * 1024
    max_cells: int = 5_000_000


class SandboxTimeoutError(RuntimeError):
    """O código excedeu o tempo limite de execução."""


class _SandboxRunner:
    """Executa o código gerado em um subprocesso Python isolado."""

    def __init__(self, limits: Optional[SandboxLimits] = None) -> None:
        self.limits = limits or SandboxLimits()

    def run(self, code: str, sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        workdir = tempfile.mkdtemp(prefix="pandas_sandbox_")
        try:
            payload = {
                "code": code,
                "sheets": {name: self._encode_frame(frame) for name, frame in sheets.items()},
                "df_fingerprint": _fingerprint(next(iter(sheets.values()))),
                "cpu_seconds": self.limits.cpu_seconds,
                "memory_bytes": self.limits.memory_bytes,
                "enforce_memory_limit": self.limits.enforce_memory_limit,
                "workdir": workdir,
                "extra_paths": self._library_paths(),
            }
            return self._spawn(payload)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # -- Internos ----------------------------------------------------------------------

    @staticmethod
    def _library_paths() -> List[str]:
        """Caminhos de bibliotecas a repassar ao subprocesso (sem repassar PYTHONPATH)."""
        import site

        raw_candidates: List[str] = []
        try:
            raw_candidates.append(site.getusersitepackages())
        except Exception:  # noqa: BLE001
            pass
        try:
            raw_candidates.extend(site.getsitepackages())
        except Exception:  # noqa: BLE001
            pass
        raw_candidates.append(str(os.path.dirname(os.__file__)))

        candidates: List[str] = []
        for candidate in raw_candidates:
            if candidate and os.path.isdir(candidate) and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _encode_frame(frame: pd.DataFrame) -> Dict[str, Any]:
        """Serializa um DataFrame para JSON de forma estável e independente dos dtypes."""
        safe = frame.copy()
        for column in safe.columns:
            if isinstance(safe[column].dtype, pd.CategoricalDtype):
                safe[column] = safe[column].astype(object)
        safe.columns = [str(c) for c in safe.columns]
        records = json.loads(
            safe.to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
                default_handler=str,
            )
        )
        return {"columns": [str(c) for c in safe.columns], "records": records}

    def _spawn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "",
            "HOME": payload["workdir"],
            "TMPDIR": payload["workdir"],
            "TEMP": payload["workdir"],
            "TMP": payload["workdir"],
        }
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-c", SANDBOX_CHILD_CODE],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.limits.wall_timeout_seconds,
                env=env,
                cwd=payload["workdir"],
                creationflags=creationflags,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxTimeoutError(
                f"O código excedeu o limite de {self.limits.wall_timeout_seconds:.0f}s "
                "e foi interrompido pelo sandbox."
            ) from exc

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        if len(stdout.encode("utf-8", "ignore")) > self.limits.max_output_bytes:
            return {
                "success": False,
                "error": "O resultado gerado excedeu o tamanho máximo permitido pelo sandbox.",
            }

        if not stdout.strip():
            return {
                "success": False,
                "error": "O sandbox não produziu resultado.",
                "traceback": (stderr.strip() or None) and stderr.strip()[-6000:],
            }

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Resposta inválida do sandbox (saída não-JSON).",
                "traceback": (stderr or stdout).strip()[-2000:],
            }


# ---------------------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """Resultado da execução de um bloco de código de manipulação."""

    success: bool
    df_result: Optional[pd.DataFrame] = None
    dfs_result: Optional[Dict[str, pd.DataFrame]] = None
    executed_code: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None
    stdout: str = ""
    execution_time_ms: float = 0.0
    columns_added: List[str] = field(default_factory=list)
    columns_removed: List[str] = field(default_factory=list)
    rows_delta: int = 0
    #: Avisos não fatais (abas descartadas, limites atingidos).
    warnings: List[str] = field(default_factory=list)


class SafeCodeExecutor:
    """Fachada do executor isolado de código gerado por LLM.

    Mantém a assinatura histórica (`execute(code, data)`) e delega ao subprocesso isolado.
    """

    def __init__(self, limits: Optional[SandboxLimits] = None) -> None:
        self.limits = limits or SandboxLimits()
        self.validator = CodeSafetyValidator()
        self.runner = _SandboxRunner(self.limits)

    # -- Validação estática ------------------------------------------------------------

    @classmethod
    def validate_code_safety(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Valida o código por allow-list de AST (compatível com a API anterior)."""
        return CodeSafetyValidator().check(code)

    # -- Execução ----------------------------------------------------------------------

    def execute(
        self,
        code: str,
        input_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    ) -> ExecutionResult:
        """Valida e executa o código no sandbox isolado e devolve o resultado."""
        sheets = self._normalize_input(input_data)
        if not sheets:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error="Nenhuma aba ou tabela foi fornecida para execução.",
            )

        first_frame = next(iter(sheets.values()))
        original_columns = {str(c) for c in first_frame.columns}
        original_rows = len(first_frame)

        is_safe, safety_message = self.validator.check(code)
        if not is_safe:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=f"Código bloqueado pela política de segurança: {safety_message}",
                traceback=safety_message,
            )

        total_cells = sum(int(frame.shape[0]) * int(frame.shape[1]) for frame in sheets.values())
        if total_cells > self.limits.max_cells:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=(
                    f"A planilha tem {total_cells} células, acima do limite de "
                    f"{self.limits.max_cells} do sandbox. Reduza o volume de dados."
                ),
            )

        start_time = time.perf_counter()
        try:
            raw = self.runner.run(code, sheets)
        except SandboxTimeoutError as exc:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=str(exc),
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - falha de infraestrutura do sandbox
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=f"Falha ao executar o sandbox isolado: {exc}",
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if not raw.get("success"):
            error = str(raw.get("error") or "Erro desconhecido no sandbox.")
            lowered = error.lower()
            if "bloquead" in lowered or "permissionerror" in lowered:
                error = f"Código bloqueado pelo sandbox de segurança: {error}"
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=error,
                traceback=raw.get("traceback"),
                stdout=raw.get("stdout", "") or "",
                execution_time_ms=elapsed_ms,
            )

        df_result = self._decode_frame(raw.get("df_result"))
        dfs_result: Dict[str, pd.DataFrame] = {}
        for name, frame_payload in (raw.get("dfs_result") or {}).items():
            decoded = self._decode_frame(frame_payload)
            if decoded is not None:
                dfs_result[str(name)] = decoded

        if df_result is None and dfs_result:
            df_result = next(iter(dfs_result.values()))

        if df_result is None:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error="O código executou, mas não retornou um DataFrame válido.",
                stdout=raw.get("stdout", "") or "",
                execution_time_ms=elapsed_ms,
            )

        new_columns = {str(c) for c in df_result.columns}

        return ExecutionResult(
            success=True,
            df_result=df_result,
            dfs_result=dfs_result or {"Resultado": df_result},
            executed_code=code,
            stdout=raw.get("stdout", "") or "",
            execution_time_ms=elapsed_ms,
            columns_added=sorted(new_columns - original_columns),
            columns_removed=sorted(original_columns - new_columns),
            rows_delta=len(df_result) - original_rows,
        )

    # -- Conversão ---------------------------------------------------------------------

    @staticmethod
    def _normalize_input(
        input_data: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    ) -> Dict[str, pd.DataFrame]:
        if input_data is None:
            return {}
        if isinstance(input_data, pd.DataFrame):
            return {"Planilha": input_data}
        if isinstance(input_data, dict):
            return {
                str(name): frame
                for name, frame in input_data.items()
                if isinstance(frame, pd.DataFrame)
            }
        return {}

    @staticmethod
    def _decode_frame(payload: Any) -> Optional[pd.DataFrame]:
        if not isinstance(payload, dict) or not payload.get("__dataframe__"):
            return None
        columns = payload.get("columns") or []
        records = payload.get("records") or []
        try:
            return pd.DataFrame.from_records(records, columns=columns)
        except Exception:  # noqa: BLE001
            return None
