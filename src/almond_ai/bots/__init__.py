"""Multi-bot session layer: bot definitions, per-bot sessions, storage.

Sits alongside `almond_ai.agents` (the older, single global "current
agent" concept, kept for `/agent` command backward compatibility) rather
than replacing it. Every bot session still shares one model provider --
see `almond_ai.bots.sessions.SessionManager`.
"""
