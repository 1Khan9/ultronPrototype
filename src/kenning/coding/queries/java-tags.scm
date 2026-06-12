;; Tree-sitter symbol query for Java.
;; Adapted from aider/queries/tree-sitter-language-pack/java-tags.scm.
;; aider is licensed under Apache License 2.0; see THIRD_PARTY_NOTICES.md.

(class_declaration
  name: (identifier) @name.definition.class) @definition.class

(method_declaration
  name: (identifier) @name.definition.method) @definition.method

(method_invocation
  name: (identifier) @name.reference.method
  arguments: (argument_list) @reference.call)

(interface_declaration
  name: (identifier) @name.definition.interface) @definition.interface

(type_list
  (type_identifier) @name.reference.interface) @reference.implementation

(object_creation_expression
  type: (type_identifier) @name.reference.class) @reference.class

(superclass (type_identifier) @name.reference.class) @reference.class
