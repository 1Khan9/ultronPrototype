;; Tree-sitter symbol query for Python.
;; Adapted from aider/queries/tree-sitter-language-pack/python-tags.scm.
;; aider is licensed under Apache License 2.0; see THIRD_PARTY_NOTICES.md.

(module (expression_statement (assignment left: (identifier) @name.definition.constant) @definition.constant))

(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
      (identifier) @name.reference.call
      (attribute
        attribute: (identifier) @name.reference.call)
  ]) @reference.call
