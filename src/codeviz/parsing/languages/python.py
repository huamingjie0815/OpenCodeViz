from __future__ import annotations

from tree_sitter_python import language as python_language

from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseImport, ParseInheritance, ParseResult
from codeviz.parsing.tree_sitter_parser import TreeSitterSourceParser


class PythonParser(TreeSitterSourceParser):
    def __init__(self) -> None:
        super().__init__(python_language())

    def parse_file(self, file_path: str, content: str, language: str) -> ParseResult:
        tree = self.parse_bytes(content)
        result = ParseResult()
        self._walk(tree.root_node, file_path, content, result, [])
        return result

    def _walk(
        self,
        node,
        file_path: str,
        content: str,
        result: ParseResult,
        parents: list[str],
    ) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            local_id = f"class:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(
                ParseEntity(
                    local_id=local_id,
                    name=self.node_text(name_node, content),
                    kind="class",
                    file_path=file_path,
                    start_line=self.line_number(node),
                    end_line=node.end_point[0] + 1,
                    signature=self.node_text(node, content).splitlines()[0],
                    language="python",
                )
            )
            for child in node.named_children:
                if child.type == "argument_list":
                    for base in child.named_children:
                        result.inheritance.append(
                            ParseInheritance(
                                source_entity_local_id=local_id,
                                target_name=self.node_text(base, content),
                                relation_type="extends",
                                line=self.line_number(base),
                            )
                        )
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            kind = "method" if parents else "function"
            local_id = f"{kind}:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(
                ParseEntity(
                    local_id=local_id,
                    name=self.node_text(name_node, content),
                    kind=kind,
                    file_path=file_path,
                    start_line=self.line_number(node),
                    end_line=node.end_point[0] + 1,
                    signature=self.node_text(node, content).splitlines()[0],
                    parent_local_id=parents[-1] if parents else "",
                    language="python",
                )
            )
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module_path = self.node_text(module_node, content) if module_node is not None else ""
            for child in node.named_children:
                if module_node is not None and child.id == module_node.id:
                    continue
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is None:
                        continue
                    imported_name = self.node_text(name_node, content)
                    local_name = self.node_text(alias_node, content) if alias_node is not None else imported_name
                    result.imports.append(
                        ParseImport(
                            module_path=module_path,
                            import_kind="named",
                            imported_name=imported_name,
                            local_name=local_name,
                            line=self.line_number(node),
                        )
                    )
                elif child.type == "dotted_name":
                    imported_name = self.node_text(child, content)
                    result.imports.append(
                        ParseImport(
                            module_path=module_path,
                            import_kind="named",
                            imported_name=imported_name,
                            local_name=imported_name,
                            line=self.line_number(node),
                        )
                    )

        if node.type == "call" and parents:
            function_node = node.child_by_field_name("function")
            if function_node is not None:
                text = self.node_text(function_node, content)
                if "." in text:
                    qualifier, callee_name = text.rsplit(".", 1)
                else:
                    qualifier, callee_name = "", text
                result.call_sites.append(
                    ParseCallSite(
                        source_entity_local_id=parents[-1],
                        callee_name=callee_name,
                        callee_qualifier=qualifier,
                        line=self.line_number(node),
                    )
                )

        if node.type == "argument_list":
            return

        for child in node.named_children:
            self._walk(child, file_path, content, result, parents)
