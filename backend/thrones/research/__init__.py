"""Online research: pluggable search, safe fetching, extraction, and the Deep Research pipeline.

Everything fetched from the web is treated as untrusted data. The model never
has tool access while it reads fetched pages, so text on a page cannot trigger
actions; it can only influence the wording of notes, which are then cited.
"""
