#import "info.typ": exposee_info
#import "template.typ": numbered_section, paper, theme-no-title, title_page, unnumbered_section
#import "@preview/glossy:0.9.0": glossary, init-glossary
#import "Chapters/Glossary.typ": all_glossary_entries
#import "Chapters/Exposee.typ": exposee_content

#show: init-glossary.with(all_glossary_entries)

#show: paper

#set page(numbering: "I")
#counter(page).update(1)

#title_page(exposee_info)

#numbered_section([
  #outline(title: [Contents])
])

// #unnumbered_section([Glossary], glossary(theme: theme-no-title, groups: ("Glossary",), show-all: true))

// #unnumbered_section([Abbreviations], glossary(
//   theme: theme-no-title,
//   groups: ("Abbreviations",),
//   show-all: true,
// ))

#set page(numbering: "1")
#counter(page).update(1)

#unnumbered_section([Exposé], exposee_content)

#set page(numbering: "i")
#counter(page).update(1)

#numbered_section([
  #bibliography("references.bib", title: [References], style: "ieee", full: true)
])
