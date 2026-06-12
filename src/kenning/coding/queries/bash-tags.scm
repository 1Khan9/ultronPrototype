;; Tree-sitter symbol query for Bash.
;; Adapted from aider/queries/tree-sitter-language-pack/bash-tags.scm.
;; aider is licensed under Apache License 2.0; see THIRD_PARTY_NOTICES.md.

(function_definition
  name: (word) @name.definition.function) @definition.function

(variable_assignment
  name: (variable_name) @name.definition.variable) @definition.variable

(command
  name: (command_name) @name.reference.call) @reference.call
