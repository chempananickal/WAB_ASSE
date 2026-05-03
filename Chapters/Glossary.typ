#let glossary_group = "Glossary"
#let abbreviation_group = "Abbreviations"

#let all_glossary_entries = (
  local_alignment: (
    short: "local alignment",
    description: "An alignment strategy that searches for the best matching subsections of two sequences instead of forcing an end-to-end alignment.",
    group: glossary_group,
  ),
  warm_up_phase: (
    short: "warm-up phase",
    description: "The initial execution period in which a JIT-enabled runtime collects profiling information and may compile hot paths before reaching steady-state performance.",
    group: glossary_group,
  ),
  copy_and_patch: (
    short: "copy-and-patch",
    description: "A JIT compilation strategy where optimized versions of certain functions are written in a lower-level language and then dynamically patched into the interpreter at runtime.",
    group: glossary_group,
  ),
  jit: (
    short: "JIT",
    long: "Just-in-Time",
    group: abbreviation_group,
  ),
  sw: (
    short: "SW",
    long: "Smith-Waterman",
    group: abbreviation_group,
  ),
  pep: (
    short: "PEP",
    long: "Python Enhancement Proposal",
    group: abbreviation_group,
  ),
  gcc: (
    short: "GCC",
    long: "GNU Compiler Collection",
    group: abbreviation_group,
  ),
  msvc: (
    short: "MSVC",
    long: "Microsoft Visual C++",
    group: abbreviation_group,
  ),
  dsl: (
    short: "DSL",
    long: "Domain-Specific Language",
    group: abbreviation_group,
  ),
  ide: (
    short: "IDE",
    long: "Integrated Development Environment",
    group: abbreviation_group,
  ),
  ast: (
    short: "AST",
    long: "Abstract Syntax Tree",
    group: abbreviation_group,
  ),
)
