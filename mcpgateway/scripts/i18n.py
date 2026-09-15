"""Extract, merge, and compile gettext catalogs for ContextForge.

The script depends on the standard library only, so translation builds work
with the runtime dependencies and no Babel install.

Commands:
    extract   Scan Python modules and Jinja2 templates, write messages.pot.
    update    Merge messages.pot into each catalog, keeping existing
              translations and adding new entries as untranslated.
    compile   Write messages.mo beside each messages.po.
    all       Run extract, update, then compile.

Usage:
    python -m mcpgateway.scripts.i18n all
    python -m mcpgateway.scripts.i18n extract
    python -m mcpgateway.scripts.i18n update
    python -m mcpgateway.scripts.i18n compile
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
TRANSLATIONS_DIR = PACKAGE_DIR / "translations"
TEMPLATES_DIR = PACKAGE_DIR / "templates"
DOMAIN = "messages"

# Messages that are structural or too short to translate meaningfully.
SKIP_MESSAGES = frozenset({""})

_PY_CALL = re.compile(r"(?<![\w.])(?:_|gettext)\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")
_PY_NGETTEXT = re.compile(r"(?<![\w.])ngettext\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*,\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")
_PY_PROTOCOL = re.compile(r"(?<![\w.])protocol_gettext\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")
#: Module-level string constants, for messages such as
#: '_ACCESS_DENIED_MSG = "Access denied"' that are translated by reference.
_CONSTANT_ASSIGNMENT = re.compile(r"^(_*[A-Z][A-Z0-9_]*)\s*=\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*$", re.MULTILINE)
#: Calls that translate a module-level constant instead of a literal.
_PY_CALL_IDENT = re.compile(r"(?<![\w.])(?:_|gettext|protocol_gettext)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]")
_JINJA_TRANS = re.compile(r"\{%-?\s*trans\s*%\}(.*?)\{%-?\s*endtrans\s*%\}", re.DOTALL)


@dataclass
class Entry:
    """One catalog entry.

    Attributes:
        msgid: Source message, written in English.
        msgstr: Translated message for the singular form.
        msgctxt: Optional disambiguating context.
        msgid_plural: Optional source plural form.
        msgstr_plural: Translations keyed by plural form index.
        references: Source locations that use the message.
        flags: gettext flags such as 'fuzzy'.
        obsolete: True when the message is no longer present in the source.
    """

    msgid: str
    msgstr: str = ""
    msgctxt: str | None = None
    msgid_plural: str | None = None
    msgstr_plural: dict[int, str] = field(default_factory=dict)
    references: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    obsolete: bool = False

    @property
    def key(self) -> tuple[str | None, str, str | None]:
        """Return the identity of this entry.

        Returns:
            Tuple of context, singular source message, and plural source message.
        """
        return (self.msgctxt, self.msgid, self.msgid_plural)


def _unescape(literal: str) -> str:
    """Decode a gettext string literal.

    Args:
        literal: Quoted literal as it appears in a .po file.

    Returns:
        The decoded string.
    """
    text = literal[1:-1]
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(text):
            break
        escape = text[index]
        index += 1
        mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}
        out.append(mapping.get(escape, escape))
    return "".join(out)


def _escape(text: str) -> str:
    """Encode a string as a gettext literal body.

    Args:
        text: Raw string.

    Returns:
        Escaped string without surrounding quotes.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def parse_po(text: str) -> list[Entry]:
    """Parse gettext catalog text into entries.

    Args:
        text: Contents of a .po file.

    Returns:
        Parsed entries in file order.
    """
    entries: list[Entry] = []
    current: Entry | None = None
    target = "msgid"
    plural_index = 0
    obsolete = False

    def flush() -> None:
        """Append the entry under construction."""
        nonlocal current
        if current is not None and (current.msgid or current.msgctxt or current.msgstr or current.msgstr_plural):
            entries.append(current)
        current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#~"):
            obsolete = True
            line = line[2:].strip()
            if not line:
                continue
        elif line.startswith("#"):
            flush()
            continue

        if line.startswith("msgctxt "):
            flush()
            current = Entry(msgid="", msgctxt=_unescape(line[len("msgctxt ") :]), obsolete=obsolete)
            target = "msgctxt"
            continue

        if line.startswith("msgid_plural "):
            if current is not None:
                current.msgid_plural = _unescape(line[len("msgid_plural ") :])
            target = "msgid_plural"
            continue

        if line.startswith("msgid "):
            if current is None or current.msgid or current.msgstr or target not in {"msgctxt", "msgid"}:
                flush()
                current = Entry(msgid="", obsolete=obsolete)
            current.msgid = _unescape(line[len("msgid ") :])
            target = "msgid"
            continue

        plural_match = re.match(r"msgstr\[(\d+)\] (.*)$", line)
        if plural_match:
            if current is not None:
                current.msgstr_plural[int(plural_match.group(1))] = _unescape(plural_match.group(2))
            target = "msgstr_plural"
            plural_index = int(plural_match.group(1))
            continue

        if line.startswith("msgstr "):
            if current is not None:
                current.msgstr = _unescape(line[len("msgstr ") :])
            target = "msgstr"
            plural_index = 0
            continue

        if line.startswith('"'):
            value = _unescape(line)
            if current is None:
                current = Entry(msgid="", obsolete=obsolete)
            if target in {"msgctxt"}:
                current.msgctxt = (current.msgctxt or "") + value
            elif target in {"msgid"}:
                current.msgid += value
            elif target == "msgid_plural":
                current.msgid_plural = (current.msgid_plural or "") + value
            elif target == "msgstr_plural":
                current.msgstr_plural[plural_index] = current.msgstr_plural.get(plural_index, "") + value
            else:
                current.msgstr += value
            continue

    flush()
    return entries


def render_po(entries: list[Entry], header: str) -> str:
    """Render entries as gettext catalog text.

    Args:
        entries: Entries to render.
        header: Catalog header block, including the trailing newline marker.

    Returns:
        Text ready to write to a .po file.
    """
    lines: list[str] = ['msgid ""', f'msgstr "{_escape(header)}"', ""]

    for entry in sorted(entries, key=lambda item: (item.msgctxt or "", item.msgid)):
        if entry.obsolete:
            continue
        if entry.references:
            lines.append("#: " + " ".join(sorted(set(entry.references))))
        if entry.flags:
            lines.append("#, " + ", ".join(sorted(set(entry.flags))))
        if entry.msgctxt:
            lines.append(f'msgctxt "{_escape(entry.msgctxt)}"')
        lines.append(f'msgid "{_escape(entry.msgid)}"')
        if entry.msgid_plural:
            lines.append(f'msgid_plural "{_escape(entry.msgid_plural)}"')
            if entry.msgstr_plural:
                for index in sorted(entry.msgstr_plural):
                    lines.append(f'msgstr[{index}] "{_escape(entry.msgstr_plural[index])}"')
            else:
                lines.append('msgstr[0] ""')
        else:
            lines.append(f'msgstr "{_escape(entry.msgstr)}"')
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def extract_messages() -> list[Entry]:
    """Scan Python modules and Jinja2 templates for translatable messages.

    Returns:
        Entries with their source references, ordered by first occurrence.
    """
    found: dict[tuple[str | None, str, str | None], Entry] = {}

    def record(msgid: str, reference: str, plural: str | None = None) -> None:
        """Add a message to the extraction result.

        Args:
            msgid: Source singular message.
            reference: File and line where the message appears.
            plural: Optional source plural message.
        """
        if msgid in SKIP_MESSAGES:
            return
        key = (None, msgid, plural)
        entry = found.get(key)
        if entry is None:
            entry = Entry(msgid=msgid, msgid_plural=plural)
            found[key] = entry
        if reference not in entry.references:
            entry.references.append(reference)

    def scan_code(path: Path) -> None:
        """Scan a Python or JavaScript source file for translated messages.

        Args:
            path: Source file to scan.
        """
        relative = path.relative_to(PACKAGE_DIR.parent)
        text = path.read_text(encoding="utf-8")
        constants = {match.group(1): _unescape(match.group(2)) for match in _CONSTANT_ASSIGNMENT.finditer(text)}
        for number, line in enumerate(text.splitlines(), start=1):
            reference = f"{relative}:{number}"
            for match in _PY_NGETTEXT.finditer(line):
                record(_unescape(match.group(1)), reference, _unescape(match.group(2)))
            for match in _PY_PROTOCOL.finditer(line):
                record(_unescape(match.group(1)), reference)
            for match in _PY_CALL.finditer(line):
                record(_unescape(match.group(1)), reference)
            for match in _PY_CALL_IDENT.finditer(line):
                value = constants.get(match.group(1))
                if value:
                    record(value, reference)

    python_files = sorted(path for path in PACKAGE_DIR.rglob("*.py") if "translations" not in path.parts)
    for path in python_files:
        scan_code(path)

    # The Admin UI ships its own JavaScript bundle; it uses the same underscore
    # call convention so one catalog serves templates and client code.
    admin_ui_dir = PACKAGE_DIR / "admin_ui"
    if admin_ui_dir.exists():
        for path in sorted(admin_ui_dir.rglob("*.js")):
            scan_code(path)

    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        relative = path.relative_to(PACKAGE_DIR.parent)
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            reference = f"{relative}:{number}"
            for match in _PY_CALL.finditer(line):
                record(_unescape(match.group(1)), reference)
        for match in _JINJA_TRANS.finditer(text):
            message = match.group(1).strip()
            if message and "{{" not in message and "{%" not in message:
                record(message, f"{relative}:trans")

    return sorted(found.values(), key=lambda item: item.msgid)


def compile_catalog(po_path: Path, mo_path: Path) -> int:
    """Compile a .po catalog into a binary .mo catalog.

    Args:
        po_path: Source .po file.
        mo_path: Destination .mo file.

    Returns:
        Number of translated entries written.
    """
    entries = [entry for entry in parse_po(po_path.read_text(encoding="utf-8")) if not entry.obsolete]
    catalog: list[tuple[bytes, bytes]] = []

    for entry in entries:
        if entry.msgid == "":
            header = entry.msgstr
            if header:
                catalog.append((b"", header.encode("utf-8")))
            continue

        key = f"{entry.msgctxt}\x04{entry.msgid}" if entry.msgctxt else entry.msgid
        if entry.msgid_plural:
            forms = entry.msgstr_plural
            if not forms:
                continue
            value = "\0".join(forms[index] for index in sorted(forms))
            catalog.append(((key + "\0" + entry.msgid_plural).encode("utf-8"), value.encode("utf-8")))
        elif entry.msgstr:
            catalog.append((key.encode("utf-8"), entry.msgstr.encode("utf-8")))

    catalog.sort(key=lambda item: item[0])

    count = len(catalog)
    keys = b""
    values = b""
    offsets: list[tuple[int, int, int, int]] = []
    for key, value in catalog:
        offsets.append((len(key), len(keys), len(value), len(values)))
        keys += key + b"\0"
        values += value + b"\0"

    key_table_offset = 7 * 4
    value_table_offset = key_table_offset + count * 8
    # Keys and values form two consecutive blocks after the tables, so a value
    # offset is relative to the key block end, not to the key block start.
    key_base = value_table_offset + count * 8
    value_base = key_base + len(keys)

    output = bytearray()
    output += struct.pack("<7I", 0x950412DE, 0, count, key_table_offset, value_table_offset, 0, 0)
    for key_length, key_offset, _value_length, _value_offset in offsets:
        output += struct.pack("<2I", key_length, key_base + key_offset)
    for _key_length, _key_offset, value_length, value_offset in offsets:
        output += struct.pack("<2I", value_length, value_base + value_offset)
    output += keys
    output += values

    mo_path.parent.mkdir(parents=True, exist_ok=True)
    mo_path.write_bytes(bytes(output))
    return count


def merge_catalog(po_path: Path, extracted: list[Entry], header: str) -> tuple[int, int]:
    """Merge extracted messages into an existing catalog.

    Existing translations are preserved. New messages are added untranslated.
    Messages no longer present in the source keep their translation and are
    written only when already translated, so translators can spot them.

    Args:
        po_path: Catalog to update. It is created when absent.
        extracted: Messages found in the source tree.
        header: Header block to use when the catalog does not exist yet.

    Returns:
        Tuple of added messages and total messages.
    """
    existing: dict[tuple[str | None, str, str | None], Entry] = {}
    if po_path.exists():
        for entry in parse_po(po_path.read_text(encoding="utf-8")):
            if entry.msgid:
                existing[entry.key] = entry

    added = 0
    merged: list[Entry] = []
    for entry in extracted:
        previous = existing.get(entry.key)
        if previous is None:
            added += 1
            merged.append(entry)
            continue
        previous.references = entry.references
        merged.append(previous)

    known = {entry.key for entry in merged}
    for key, entry in existing.items():
        if key not in known and entry.msgstr:
            entry.obsolete = True
            merged.append(entry)

    po_path.parent.mkdir(parents=True, exist_ok=True)
    po_path.write_text(render_po(merged, header), encoding="utf-8")
    return added, len(merged)


def default_header(locale: str, plural_forms: str) -> str:
    """Build the standard catalog header.

    Args:
        locale: Locale code, for example 'zh-CN'.
        plural_forms: Value of the Plural-Forms header for this locale.

    Returns:
        Header block value.
    """
    return (
        "Project-Id-Version: ContextForge\n"
        "Report-Msgid-Bugs-To: \n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {locale}\n"
        f"Plural-Forms: {plural_forms}\n"
    )


def read_po_header(po_path: Path) -> str | None:
    """Return the existing catalog header, when the file exists.

    Args:
        po_path: Catalog path.

    Returns:
        The header value, or None when the catalog is absent or has no header.
    """
    if not po_path.exists():
        return None
    for entry in parse_po(po_path.read_text(encoding="utf-8")):
        if entry.msgid == "" and entry.msgstr:
            return entry.msgstr
    return None


def locale_plural_forms(locale: str) -> str:
    """Return the Plural-Forms header for a locale.

    Args:
        locale: Locale code.

    Returns:
        The Plural-Forms value.
    """
    if locale.lower().startswith("zh"):
        return "nplurals=1; plural=0;"
    return "nplurals=2; plural=(n != 1);"


def catalog_path(locale: str) -> Path:
    """Return the .po path for a locale.

    Args:
        locale: Locale code using an underscore, for example 'zh_CN'.

    Returns:
        Path to the catalog file.
    """
    return TRANSLATIONS_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"


def existing_locales() -> list[str]:
    """List locales that already have a catalog directory.

    Returns:
        Locale directory names in sorted order.
    """
    if not TRANSLATIONS_DIR.exists():
        return []
    return sorted(path.name for path in TRANSLATIONS_DIR.iterdir() if (path / "LC_MESSAGES").is_dir())


def command_extract(pot_path: Path) -> int:
    """Run the extract command.

    Args:
        pot_path: Path of the template catalog to write.

    Returns:
        Process exit code.
    """
    entries = extract_messages()
    pot_path.parent.mkdir(parents=True, exist_ok=True)
    pot_path.write_text(render_po(entries, default_header("en", locale_plural_forms("en"))), encoding="utf-8")
    print(f"Extracted {len(entries)} messages to {pot_path}")
    return 0


def command_update(pot_path: Path, locales: list[str]) -> int:
    """Run the update command.

    Args:
        pot_path: Template catalog holding the current messages.
        locales: Locale directory names to update.

    Returns:
        Process exit code.
    """
    if not pot_path.exists():
        print(f"Template catalog not found: {pot_path}. Run 'extract' first.", file=sys.stderr)
        return 1
    extracted = [entry for entry in parse_po(pot_path.read_text(encoding="utf-8")) if entry.msgid]
    for locale in locales:
        po_path = catalog_path(locale)
        header = read_po_header(po_path) or default_header(locale, locale_plural_forms(locale))
        added, total = merge_catalog(po_path, extracted, header)
        print(f"{locale}: {added} new, {total} total ({po_path})")
    return 0


def command_compile(locales: list[str]) -> int:
    """Run the compile command.

    Args:
        locales: Locale directory names to compile.

    Returns:
        Process exit code.
    """
    for locale in locales:
        po_path = catalog_path(locale)
        if not po_path.exists():
            print(f"Skip {locale}: {po_path} not found", file=sys.stderr)
            continue
        mo_path = po_path.with_suffix(".mo")
        count = compile_catalog(po_path, mo_path)
        print(f"{locale}: compiled {count} entries to {mo_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: Argument list. Defaults to sys.argv[1:].

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Manage ContextForge translation catalogs.")
    parser.add_argument("command", choices=["extract", "update", "compile", "all"])
    parser.add_argument("--locale", action="append", dest="locales", help="Locale directory to process, for example zh_CN. Repeatable.")
    args = parser.parse_args(argv)

    pot_path = TRANSLATIONS_DIR / f"{DOMAIN}.pot"
    locales = args.locales or existing_locales()

    if args.command == "extract":
        return command_extract(pot_path)
    if args.command == "update":
        return command_update(pot_path, locales)
    if args.command == "compile":
        return command_compile(locales)

    command_extract(pot_path)
    status = command_update(pot_path, locales)
    if status != 0:
        return status
    return command_compile(locales)


if __name__ == "__main__":
    raise SystemExit(main())
