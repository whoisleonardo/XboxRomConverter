# Perfis de execução para download otimizado

AGGRESSIVE = {
    "max_connections": 16,
    "max_parts": 16,
    "chunk_size": 8 * 1024 * 1024,  # 8 MiB
    "probe_timeout": 2.0,
    "retry_policy": 4,
    "backoff_strategy": "exponential_short",
}

SAFE = {
    "max_connections": 4,
    "max_parts": 2,
    "chunk_size": 2 * 1024 * 1024,  # 2 MiB
    "probe_timeout": 5.0,
    "retry_policy": 2,
    "backoff_strategy": "exponential_long",
}

PROFILES = {
    "aggressive": AGGRESSIVE,
    "safe": SAFE,
}

def get_profile(name: str):
    return PROFILES.get(name.lower(), SAFE)
