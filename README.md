# Simple Typst Template

This template provides two Typst entry points:

- main.typ for the full WAB
- exposee.typ for the exposé

The shared metadata lives in info.typ, and the shared layout helpers live in template.typ.

Both documents use the same title page layout. The only document-specific change is the document type field defined in the imported metadata.

To compile the documents:

- typst compile main.typ main.pdf
- typst compile exposee.typ exposee.pdf
