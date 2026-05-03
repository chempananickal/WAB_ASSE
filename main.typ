#import "info.typ": wab_info
#import "template.typ": (
  ai_declaration_table, declaration_text, numbered_section, paper, theme-no-title, title_page, unnumbered_section,
)
#import "@preview/glossy:0.9.0": glossary, init-glossary
#import "Chapters/Glossary.typ": all_glossary_entries
#import "Chapters/Abstract.typ": abstract_content
#import "Chapters/01_Introduction.typ": introduction_content
#import "Chapters/02_Methods.typ": methods_content
#import "Chapters/03_Results.typ": results_content
#import "Chapters/04_Discussion.typ": discussion_content
#import "Chapters/05_Conclusion.typ": conclusion_content
#import "Chapters/AI_Declaration.typ": ai_declaration_entries, ai_declaration_intro

#show: init-glossary.with(all_glossary_entries)

#show: paper


#title_page(wab_info)

#set page(numbering: "I")
#counter(page).update(2)
#unnumbered_section([Abstract], abstract_content)

#numbered_section([
  #outline(title: [Contents])
])

#unnumbered_section([List of Figures], outline(
  title: none,
  target: figure.where(kind: image),
))

#unnumbered_section([List of Tables], outline(
  title: none,
  target: figure.where(kind: table),
))

#unnumbered_section([Glossary], glossary(
  theme: theme-no-title,
  groups: ("Glossary",),
))

#unnumbered_section([Abbreviations], glossary(
  theme: theme-no-title,
  groups: ("Abbreviations",),
))

#set page(numbering: "1")
#counter(page).update(1)

#numbered_section(introduction_content)

#numbered_section(methods_content)

#numbered_section(results_content)

#numbered_section(discussion_content)

#numbered_section(conclusion_content)

#pagebreak()
#set page(numbering: "i")
#counter(page).update(1)

#numbered_section([
  #bibliography("references.bib", title: [References], style: "american-medical-association")
])

#unnumbered_section([AI Declaration], [
  #ai_declaration_intro
  #v(0.8cm)
  #ai_declaration_table(ai_declaration_entries)
])

#unnumbered_section([Declaration of Authorship], declaration_text(wab_info))
