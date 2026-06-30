"""
app/api/rate_limiter.py
-----------------------
slowapi instance for rate limiting endpoints.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
