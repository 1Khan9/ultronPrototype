;; Tree-sitter symbol query for C.
;; Adapted from aider/queries/tree-sitter-language-pack/c-tags.scm.
;; aider is licensed under Apache License 2.0; see THIRD_PARTY_NOTICES.md.
;; Note: defs only; pygments lexer backfills refs in tree_sitter_tags.

(struct_specifier name: (type_identifier) @name.definition.class body:(_)) @definition.class

(declaration type: (union_specifier name: (type_identifier) @name.definition.class)) @definition.class

(function_declarator declarator: (identifier) @name.definition.function) @definition.function

(type_definition declarator: (type_identifier) @name.definition.type) @definition.type

(enum_specifier name: (type_identifier) @name.definition.type) @definition.type
