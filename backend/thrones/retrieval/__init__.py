"""Local document ingestion and retrieval (SQLite FTS5 / BM25).

Retrieved passages are supplied to the model as quoted context with their
source labels. They are never described as knowledge the model already has.
"""
