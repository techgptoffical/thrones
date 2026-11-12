"""Model runtime: a provider abstraction plus the llama.cpp implementation.

The rest of Thrones talks only to `ChatProvider` and `ModelManager`, so a new
backend (another engine, another process model) is a new provider class, not
an application rewrite.
"""
