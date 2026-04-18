from __future__ import annotations

from tree_sitter_javascript import language as javascript_language

from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseExport, ParseImport, ParseInheritance, ParseResult
from codeviz.parsing.tree_sitter_parser import TreeSitterSourceParser


class JavaScriptParser(TreeSitterSourceParser):
    def __init__(self) -> None:
        super().__init__(javascript_language())

    def parse_file(self, file_path: str, content: str, language: str) -> ParseResult:
        tree = self.parse_bytes(content)
        result = ParseResult()
        self._walk(tree.root_node, file_path, content, language, result, [])
        return result

    def _walk(
        self,
        node,
        file_path: str,
        content: str,
        language: str,
        result: ParseResult,
        parents: list[str],
    ) -> None:
        if node.type == "export_statement":
            export_text = self.node_text(node, content)
            if export_text.startswith("export default "):
                child = next(
                    (
                        item
                        for item in node.named_children
                        if item.type in {"function_declaration", "class_declaration", "identifier"}
                    ),
                    None,
                )
                if child is not None:
                    if child.type == "identifier":
                        local_name = self.node_text(child, content)
                    else:
                        name_node = next(
                            (
                                item
                                for item in child.named_children
                                if item.type in {"identifier", "type_identifier", "property_identifier"}
                            ),
                            None,
                        )
                        local_name = self.node_text(name_node, content) if name_node is not None else ""
                    if local_name:
                        result.exports.append(
                            ParseExport(
                                export_name="default",
                                local_name=local_name,
                                line=self.line_number(node),
                            )
                        )
            for child in node.named_children:
                self._walk(child, file_path, content, language, result, parents)
            return

        if node.type == "function_declaration":
            name_node = next((child for child in node.named_children if child.type in {"identifier", "property_identifier"}), None)
            if name_node is None:
                return
            exported = node.parent is not None and node.parent.type == "export_statement"
            local_id = f"function:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(
                ParseEntity(
                    local_id=local_id,
                    name=self.node_text(name_node, content),
                    kind="function",
                    file_path=file_path,
                    start_line=self.line_number(node),
                    end_line=node.end_point[0] + 1,
                    signature=self.node_text(node, content).splitlines()[0],
                    exported=exported,
                    language=language,
                )
            )
            for child in node.named_children:
                self._walk(child, file_path, content, language, result, parents + [local_id])
            return

        if node.type == "class_declaration":
            name_node = next((child for child in node.named_children if child.type in {"type_identifier", "identifier"}), None)
            if name_node is None:
                return
            exported = node.parent is not None and node.parent.type == "export_statement"
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
                    exported=exported,
                    language=language,
                )
            )
            for child in node.named_children:
                if child.type == "class_heritage":
                    for nested in child.named_children:
                        relation_type = ""
                        if nested.type == "extends_clause":
                            relation_type = "extends"
                        elif nested.type == "implements_clause":
                            relation_type = "implements"
                        if not relation_type:
                            continue
                        targets = [
                            item
                            for item in nested.named_children
                            if item.type in {"identifier", "type_identifier"}
                        ]
                        for target in targets:
                            result.inheritance.append(
                                ParseInheritance(
                                    source_entity_local_id=local_id,
                                    target_name=self.node_text(target, content),
                                    relation_type=relation_type,
                                    line=self.line_number(target),
                                )
                            )
            for child in node.named_children:
                self._walk(child, file_path, content, language, result, parents + [local_id])
            return

        if node.type == "method_definition" and parents:
            name_node = next((child for child in node.named_children if child.type == "property_identifier"), None)
            if name_node is None:
                return
            local_id = f"method:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(
                ParseEntity(
                    local_id=local_id,
                    name=self.node_text(name_node, content),
                    kind="method",
                    file_path=file_path,
                    start_line=self.line_number(node),
                    end_line=node.end_point[0] + 1,
                    signature=self.node_text(node, content).splitlines()[0],
                    parent_local_id=parents[-1],
                    language=language,
                )
            )
            for child in node.named_children:
                self._walk(child, file_path, content, language, result, parents + [local_id])
            return

        if node.type == "import_statement":
            module_node = next((child for child in node.named_children if child.type == "string"), None)
            module_path = self.node_text(module_node, content).strip("\"'") if module_node is not None else ""
            clause_node = next((child for child in node.named_children if child.type == "import_clause"), None)
            if clause_node is None:
                return
            clause_children = list(clause_node.named_children)
            if len(clause_children) == 1 and clause_children[0].type == "identifier":
                result.imports.append(
                    ParseImport(
                        module_path=module_path,
                        import_kind="default",
                        imported_name="default",
                        local_name=self.node_text(clause_children[0], content),
                        line=self.line_number(node),
                    )
                )
                return
            if len(clause_children) == 1 and clause_children[0].type == "namespace_import":
                name_node = next((child for child in clause_children[0].named_children if child.type == "identifier"), None)
                if name_node is not None:
                    result.imports.append(
                        ParseImport(
                            module_path=module_path,
                            import_kind="namespace",
                            imported_name="*",
                            local_name=self.node_text(name_node, content),
                            line=self.line_number(node),
                        )
                    )
                return
            named_node = next((child for child in clause_children if child.type == "named_imports"), None)
            if named_node is not None:
                for child in named_node.named_children:
                    if child.type != "import_specifier":
                        continue
                    names = [item for item in child.named_children if item.type in {"identifier", "property_identifier"}]
                    if not names:
                        continue
                    imported_name = self.node_text(names[0], content)
                    local_name = self.node_text(names[-1], content)
                    result.imports.append(
                        ParseImport(
                            module_path=module_path,
                            import_kind="named",
                            imported_name=imported_name,
                            local_name=local_name,
                            line=self.line_number(node),
                        )
                    )

        if node.type == "call_expression" and parents:
            function_node = node.child_by_field_name("function")
            if function_node is None and node.named_children:
                function_node = node.named_children[0]
            if function_node is not None:
                if function_node.type == "member_expression":
                    parts = [self.node_text(item, content) for item in function_node.named_children if item.type in {"identifier", "property_identifier", "this"}]
                    if len(parts) >= 2:
                        qualifier = parts[0]
                        callee_name = parts[-1]
                    else:
                        qualifier = ""
                        callee_name = self.node_text(function_node, content)
                else:
                    qualifier = ""
                    callee_name = self.node_text(function_node, content)
                result.call_sites.append(
                    ParseCallSite(
                        source_entity_local_id=parents[-1],
                        callee_name=callee_name,
                        callee_qualifier=qualifier,
                        line=self.line_number(node),
                    )
                )

        for child in node.named_children:
            self._walk(child, file_path, content, language, result, parents)
