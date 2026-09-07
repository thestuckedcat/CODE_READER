# Design

One subprocess parses one translation unit using its normalized compilation
command. Compiler facts are accepted only when Clang reports no error diagnostic.
