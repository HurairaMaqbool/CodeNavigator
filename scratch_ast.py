# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

from tree_sitter import Language, Parser
import tree_sitter_python

lang = Language(tree_sitter_python.language())
parser = Parser(lang)

tree = parser.parse(b"from math import sqrt, pi")
root = tree.root_node
stmt = root.named_children[0]
print("stmt type:", stmt.type)
print("module_name node:", getattr(stmt.child_by_field_name("module_name"), "text", None))
for c in stmt.named_children:
    print("child:", c.type, c.text, "==", c)
