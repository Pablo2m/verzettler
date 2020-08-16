#!/usr/bin/env python3

# std
from abc import ABC, abstractmethod
from typing import Optional, Iterable
from pathlib import PurePath, Path
import os.path

# ours
from verzettler.zettelkasten import Zettelkasten
from verzettler.note import Note
from verzettler.markdown_reader import MarkdownReader


class NoteTransformer(ABC):
    """ Takes a note and transforms underlying markdown file
    """

    @abstractmethod
    def transform(self, note: Note) -> str:
        pass

    def transform_write(self, note: Note, path: Optional[PurePath] = None):
        if path:
            path = Path(path)
        else:
            path = note.path
        transformed = self.transform(note)
        with path.open("w") as outf:
            outf.write(transformed)


def identity(arg):
    return arg


# todo: split up
class DefaultTransformer(NoteTransformer):
    def __init__(self, zk: Zettelkasten, tag_transformer=identity):
        self.zk = zk
        self.tag_transformer = tag_transformer

    @staticmethod
    def _format_tags(tags: Iterable[str]) -> str:
        """

        >>> DefaultTransformer._format_tags(["tag1", "tag2"]).strip()
        'Tags: #tag1 #tag2'
        """
        return (
            "Tags: " + " ".join("#" + tag for tag in sorted(list(tags))) + "\n"
        )

    def _format_link(self, note: Note, zid: str) -> str:
        if zid in self.zk:
            rel_path = Path(
                os.path.relpath(str(self.zk[zid].path), str(note.path.parent))
            )
            link_title = self.zk[zid].title
            return f'[[{zid}]] [{link_title}]({rel_path} "autogen")'
        else:
            return f"[[{zid}]]"

    def transform(self, note: Note) -> str:
        out_lines = []

        md_reader = MarkdownReader.from_file(note.path)
        for i, md_line in enumerate(md_reader.lines):
            remove_line = False

            # Fixing
            if md_line.is_code_block and "tags: " in md_line.text.lower():
                if i >= 1 and not md_reader.lines[i - 1].text.strip():
                    out_lines = out_lines[:-1]
                continue

            # Change style of headers
            if (
                i > 1
                and not md_line.is_code_block
                and md_line.text.startswith("===")
                and md_reader.lines[i - 1].text.strip()
            ):
                out_lines = out_lines[:-1]
                md_line.text = "# " + md_reader.lines[i - 1].text
            if (
                i > 1
                and not md_line.is_code_block
                and md_line.text.startswith("---")
                and md_reader.lines[i - 1].text.strip()
            ):
                out_lines = out_lines[:-1]
                md_line.text = "## " + md_reader.lines[i - 1].text

            # Modifying tags if haven't been given before
            if not note.tags:
                if (
                    i >= 1
                    and md_reader.lines[i - 1].text.startswith("# ")
                    and not md_line.is_code_block
                ):
                    tags = self.tag_transformer(set())
                    if tags:
                        out_lines.extend(
                            ["\n", self._format_tags(tags),]
                        )

            # Modifying tags if already given
            if "tags: " in md_line.text.lower() and not md_line.is_code_block:
                tags = self.tag_transformer(note._read_tags(md_line.text))
                if not tags:
                    # Remove line
                    continue
                md_line.text = self._format_tags(tags)

            # Replacing/extending links

            # Remove old autogenerated links
            md_line.text = Note.autogen_link_regex.sub("", md_line.text)

            # Add new links
            links = Note.id_link_regex_no_group.findall(md_line.text)
            for link in links:
                zid = Note.id_regex.findall(link)
                assert len(zid) == 1
                zid = zid[0]
                new_links = self._format_link(note, zid)
                md_line.text = md_line.text.replace(link, new_links)

            # Remove old backlinks section
            if (
                len(md_line.current_section) == 2
                and md_line.current_section[-1].lower() == "backlinks"
            ):
                remove_line = True

            # Add lines
            if not remove_line:
                out_lines.append(md_line.text)

            # Add new blacklinks section to file
            if md_line.is_last_line:
                backlinks = self.zk.get_backlinks(note.nid)
                if backlinks:
                    if len(out_lines) >= 1 and out_lines[-1] == "\n":
                        pass
                    elif len(out_lines) >= 1 and out_lines[-1].endswith("\n"):
                        out_lines.extend(["\n"])
                    elif len(out_lines) >= 1 and not out_lines[-1].endswith(
                        "\n"
                    ):
                        out_lines.extend(["\n", "\n"])
                    out_lines.extend(["## Backlinks\n", "\n"])
                    for backlink in sorted(list(backlinks)):
                        out_lines.append(
                            f"* {self._format_link(note, backlink)}\n"
                        )

        return "".join(out_lines)
