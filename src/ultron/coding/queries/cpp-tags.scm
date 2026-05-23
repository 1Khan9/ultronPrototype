;; Tree-sitter symbol query for C++.
;; Adapted from aider/queries/tree-sitter-language-pack/cpp-tags.scm.
;; aider is licensed under Apache License 2.0; see THIRD_PARTY_NOTICES.md.
;; Note: defs only; pygments lexer backfills refs in tree_sitter_tags.

(struct_specifier name: (type_identifier) @name.definition.class body:(_)) @definition.class

(declaration type: (union_specifier name: (type_identifier) @name.definition.class)) @definition.class

(function_declarator declarator: (identifier) @name.definition.function) @definition.function

(function_declarator declarator: (field_identifier) @name.definition.function) @definition.function

(function_declarator declarator: (qualified_identifier scope: (namespace_identifier) @local.scope name: (identifier) @name.definition.method)) @definition.method

(type_definition declarator: (type_identifier) @name.definition.type) @definition.type

(enum_specifier name: (type_identifier) @name.definition.type) @definition.type

(class_specifier name: (type_identifier) @name.definition.class) @definition.class
