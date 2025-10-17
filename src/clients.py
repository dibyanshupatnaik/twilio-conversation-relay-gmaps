from __future__ import annotations

from functools import lru_cache

from openai import OpenAI
from twilio.rest import Client

from .settings import settings


@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache
def get_twilio_client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


openai_client = get_openai_client()
twilio_client = get_twilio_client()
