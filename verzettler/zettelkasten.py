#!/usr/bin/env python3

# std
import os
from abc import ABC, abstractmethod
from typing import List, Union, Optional, Iterable, Set
from pathlib import Path, PurePath

# 3rd
from colour import Color

# ours
from verzettler.zettel import Zettel
from verzettler.log import logger


class ColorPicker(ABC):

    @abstractmethod
    def pick(self, zettel: Zettel):
        pass


class CategoryColorPicker(ColorPicker):

    def __init__(
            self,
            zettelkasten: "Zettelkasten",
            colors: Optional[List[str]] = None
    ):

        self.zettelkasten = zettelkasten
        if colors is None:
            colors = [
                "#8dd3c7",
                "#ffffb3",
                "#bebada",
                "#fb8072",
                "#80b1d3",
                "#fdb462",
                "#b3de69",
                "#fccde5",
                "#d9d9d9",
                "#bc80bd",
                "#ccebc5",
                "#ffed6f",
            ]

        self.category2color = {
            c: colors[i % len(colors)]
            for i, c in enumerate(self.zettelkasten.categories)
        }

    def pick(self, zettel: Zettel):
        categories = [t for t in zettel.tags if t.startswith("c_")]
        if len(categories) != 1:
            # unfortunately vis.js doesn't support multiple colors
            return "white"
        else:
            return ":".join([self.category2color[c] for c in categories])


class ConstantColorPicker(ColorPicker):

    def __init__(self, color= "#8dd3c7"):
        self.color = color

    def pick(self, zettel: Zettel):
        return self.color


class DepthColorPicker(ColorPicker):

    def __init__(self, zettelkasten: "Zettelkasten", start_color="#f67280", end_color="#fff7f8"):
        zettelkasten._update_depths()
        self.colors = list(
            Color(start_color).range_to(Color(end_color), zettelkasten.depth)
        )

    def pick(self, zettel: Zettel) -> str:
        if zettel.depth:
            return self.colors[zettel.depth-1]
        else:
            return self.colors[0]


class Zettelkasten(object):

    def __init__(self, zettels: Optional[List[Zettel]] = None):
        self.zid2zettel = {}

        if zettels is not None:
            self.add_zettels(zettels)

        self._finalized = False

    # Properties
    # =========================================================================

    @property
    def zettels(self):
        return list(self.zid2zettel.values())

    @property
    def tags(self) -> Set[str]:
        tags = set()
        for z in self.zettels:
            tags |= z.tags
        return tags

    @property
    def categories(self) -> Set[str]:
        return set(t for t in self.tags if t.startswith("c_"))

    @property
    def depth(self) -> int:
        maxdepth = 0
        for z in self.zettels:
            if z.depth is not None:
                maxdepth = max(z.depth, maxdepth)
        return maxdepth

    # Help functions
    # =========================================================================

    def _update_backlinks(self):
        # Reset
        for zettel in self.zettels:
            zettel.backlinks = set()
        # Add
        for zettel in self.zettels:
            for linked_zid in zettel.links:
                try:
                    self.zid2zettel[linked_zid].backlinks.add(zettel.zid)
                except KeyError:
                    logger.error(f"Could not find zettel with ZID {linked_zid}")

    def _update_depths(self, mother="00000000000000", mother_depth=0):
        try:
            mother = self.zid2zettel[mother]
        except KeyError:
            logger.error(f"Could not find zettel with ZID {mother}")
            return
        if mother.depth is not None:
            return
        mother.depth = mother_depth
        for daughter in mother.links:
            self._update_depths(
                mother=daughter,
                mother_depth=mother_depth+1
            )
            try:
                self.zid2zettel[daughter].depth = mother_depth + 1
            except KeyError:
                logger.error(f"Could not find zettel with ZID {daughter}")

    # Getting things
    # =========================================================================

    def get_by_path(self, path: Union[str, PurePath]) -> Zettel:
        path = Path(path)
        # fixme
        res = [z for z in self.zettels if z.path.name == path.name]
        assert len(res) == 1, (path.name, res)
        return res[0]

    # Extending collection
    # =========================================================================

    def add_zettels(self, zettels: Iterable[Zettel]) -> None:
        self._finalized = False
        for zettel in zettels:
            zettel.zettelkasten = self
            self.zid2zettel[zettel.zid] = zettel

    def add_zettels_from_directory(
            self,
            directory: Union[PurePath, str]
    ) -> None:
        self._finalized = False
        directory = Path(directory)
        for root, dirs, files in os.walk(str(directory), topdown=True):
            dirs[:] = [d for d in dirs if d not in [".git"]]
            self.add_zettels(
                [
                    Zettel(Path(root) / file)
                    for file in files
                    if file.endswith(".md")
                ]
            )

    def finalize(self):
        self._update_backlinks()
        self._update_depths()
        self._finalized = True

    # MISC
    # =========================================================================

    def transform_all(self, **kwargs) -> None:
        if not self._finalized:
            self.finalize()
        for zettel in self.zettels:
            zettel.transform_file(**kwargs)

    def dot_graph(self, color_picker: Optional[ColorPicker] = None) -> str:
        if not self._finalized:
            self.finalize()
        lines = [
            "digraph zettelkasten {",
            "\tnode [shape=box];"
        ]

        if color_picker is None:
            color_picker = DepthColorPicker(self)

        drawn_links = []
        for zettel in self.zettels:
            lines.append(
                f'\t{zettel.zid} ['
                f'label="{zettel.title} ({zettel.depth})" '
                f'labelURL="file://{zettel.path.resolve()}" '
                f'color={color_picker.pick(zettel)}'
                f'];'
            )
            for link in zettel.links:
                if link not in self:
                    logger.error(f"Didn't find zettel with zid {link}.")
                    continue
                if (zettel.zid, link) in drawn_links:
                    continue
                if zettel.zid not in self.zid2zettel[link].links:
                    lines.append(f"\t{zettel.zid} -> {link} [color=black];")
                    drawn_links.append((zettel.zid, link))
                else:
                    lines.append(f"\t{zettel.zid} -> {link} [color=black dir=both];")
                    drawn_links.extend(
                        [(zettel.zid, link), (link, zettel.zid)]
                    )

        lines.append("}")
        return "\n".join(lines)

    def stats_string(self) -> str:
        lines = [
            f"Total number of notes: {len(self.zid2zettel)}",
            f"Total number of tags: {len(self.tags)}",
        ]
        return "\n".join(lines)


    # Magic
    # =========================================================================

    # todo: provide get method that allows to only warn if not found or something
    def __getitem__(self, item):
        return self.zid2zettel[item]

    def __contains__(self, item):
        return item in self.zid2zettel

    def __repr__(self):
        return f"Zettelkasten({len(self.zid2zettel)})"
