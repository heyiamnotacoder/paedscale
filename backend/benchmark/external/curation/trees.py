"""Where each drug's external-validation files live (PROTOCOL.md, Amendment 19 §4).

The primary dataset (Amendments 1-18) and the extension set are separate trees with the same
layout, so curating or scoring the extension cannot touch the frozen primary record. A drug
belongs to the extension when the extension set file lists it as included.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

EXTERNAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class Tree:
    """One dataset's folders: the search snapshot, the abstracts (gitignored), the pass and
    final records, the frozen dataset files, the outputs, and the file of engine inputs."""
    name: str
    search: str
    abstracts: str
    extraction: str
    dataset: str
    output: str
    inputs: str

    @classmethod
    def at(cls, name: str, root: str, inputs: str, output: str) -> "Tree":
        return cls(name, os.path.join(root, "search"), os.path.join(root, "abstracts"),
                   os.path.join(root, "extraction"), os.path.join(root, "dataset"), output, inputs)

    @property
    def final(self) -> str:
        return os.path.join(self.extraction, "final")

    @property
    def adjudication_log(self) -> str:
        return os.path.join(self.extraction, "adjudication.json")

    @property
    def authors(self) -> str:
        return os.path.join(self.dataset, "authors.json")

    def engine_inputs(self) -> dict:
        """{drug: inputs} with fe and the non-renal enzyme, as the scorer reads them."""
        with open(self.inputs, encoding="utf-8") as f:
            return json.load(f)["drugs"]


EXTENSION_ROOT = os.path.join(EXTERNAL, "extension")
PRIMARY = Tree.at("primary", EXTERNAL, os.path.join(os.path.dirname(EXTERNAL), "reference_set.json"),
                  os.path.join(EXTERNAL, "output"))
EXTENSION = Tree.at("extension", EXTENSION_ROOT, os.path.join(EXTENSION_ROOT, "extension_set.json"),
                    os.path.join(EXTERNAL, "output", "extension"))


def by_name(name: str) -> Tree:
    """`primary` or `extension`, looked up at call time."""
    return {"primary": PRIMARY, "extension": EXTENSION}[name]


def extension_drugs() -> list[str]:
    return sorted(k for k, d in EXTENSION.engine_inputs().items() if d.get("included"))


def tree_of(drug: str) -> Tree:
    return EXTENSION if drug in extension_drugs() else PRIMARY
