#let body-font = "New Computer Modern"
#let display-font = "CMU Sans Serif"

#import "@preview/glossy:0.9.0": theme-basic

#let paper(body) = {
  set page(
    paper: "a4",
    margin: (
      top: 2.5cm,
      bottom: 2.5cm,
      left: 2.5cm,
      right: 2.5cm,
    ),
  )
  set text(lang: "en", font: body-font, size: 14pt)
  set par(justify: true, leading: 0.72em)
  set heading(numbering: "1.")
  show heading: set text(font: display-font)
  show heading: set block(below: 2em)

  body
}

#let unnumbered_heading(title) = heading(level: 1, numbering: none, outlined: true)[#title]

#let major_section(body) = [
  #pagebreak(weak: true)
  #body
]

#let unnumbered_section(title, body) = major_section([
  #unnumbered_heading(title)
  #body
])

#let numbered_section(body) = major_section(body)

#let theme-no-title = (
  section: (title, body) => body,
  group: theme-basic.group,
  entry: theme-basic.entry,
)

#let title_page(info) = [
  #set text(font: body-font)

  #align(left)[
    #image("Images/Cover/provadis-hochschule.pdf", height: 2.5cm)
  ]

  #v(1cm)

  #align(center)[
    #text(size: 16pt, weight: "bold", font: display-font)[#info.document_type]
    #v(0.5cm)
    #text(size: 16pt)[#info.university_name]
    #v(1cm)
    #text(size: 22pt, weight: "bold", font: display-font, costs: (hyphenation: 10000%))[#info.thesis_title]
    // #v(0.5cm)
    // #text(size: 16pt)[#info.thesis_subtitle]
    #v(2cm)
    #text(size: 12pt)[#info.author_name]
    #linebreak()
    #text(size: 12pt)[#info.author_email]
    #linebreak()
    #text(size: 12pt)[Matriculation Number: #info.matriculation_number]
    #v(2cm)
    #text(size: 12pt)[Department: #info.department_name]
    #linebreak()
    #text(size: 12pt)[Module: #info.module_name]
    #linebreak()
    #text(size: 12pt)[Reviewer: #info.reviewer_name]
    #v(2cm)
    #text(size: 12pt)[#info.submission_date.display("[day].[month].[year]")]
  ]

  #pagebreak()
]


#let ai_declaration_table(entries) = {
  show table.cell: set block(breakable: false)
  table(
    columns: (1.1fr, 2.4fr, 2fr),
    inset: 8pt,
    align: (left, left, left),
    table.header(
      [#text(font: display-font)[*System*]], [#text(font: display-font)[*Prompt*]], [#text(font: display-font)[*Usage*]]
    ),
    ..entries
      .map(entry => (
        [#text(size: 11pt)[#entry.system]],
        [#text(size: 11pt)[#entry.prompt]],
        [#text(size: 11pt)[#entry.usage]],
      ))
      .flatten(),
  )
}

#let declaration_text(info) = [
  I hereby confirm that I have personally and independently prepared the present work and have not used any sources or aids other than those specified. All passages taken verbatim or in substance from other sources are identified as such. The drawings, illustrations and tables in this work are created by me or have been provided with an appropriate source reference. This work has not been submitted by me to any other university in the same or similar form for the acquisition of an academic degree.

  #v(2cm)

  #grid(
    columns: (1fr, 1fr),
    column-gutter: 1cm,
    [Frankfurt, #info.submission_date.display("[day].[month].[year]")],
    [#box(width: 7.5cm, inset: 10pt, stroke: (bottom: 0.6pt))[]],
  )

  #align(right)[#text(size: 12pt)[#info.author_name]]
]
