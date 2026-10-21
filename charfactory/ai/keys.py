"""Chaves de API dos provedores, guardadas no Gerenciador de Credenciais do Windows (nunca no
config.json). Fora do Windows, ou sem chave guardada, vale a variável de ambiente do provedor
(ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY…)."""
from __future__ import annotations

import os
import sys

ENV = {"anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY",),
       "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "compatible": ("OPENAI_COMPATIBLE_API_KEY",)}
_memory: dict[str, str] = {}          # fora do Windows: só durante a sessão


def _target(provider: str) -> str:
    return f"CharFactory/{provider}"


def _credapi():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CREDENTIAL, adv


CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE = 1, 2


def _read(provider: str) -> str:
    if sys.platform != "win32":
        return _memory.get(provider, "")
    ctypes, CREDENTIAL, adv = _credapi()
    p = ctypes.POINTER(CREDENTIAL)()
    if not adv.CredReadW(_target(provider), CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return ""
    try:
        c = p.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
    finally:
        adv.CredFree(p)


def get(provider: str) -> str:
    try:
        key = _read(provider)
    except OSError:
        key = ""
    return key or next((os.environ[v] for v in ENV.get(provider, ()) if os.environ.get(v)), "")


def from_env(provider: str) -> bool:
    """A chave em uso vem de variável de ambiente (nada guardado)?"""
    try:
        return not _read(provider) and bool(get(provider))
    except OSError:
        return bool(get(provider))


def set(provider: str, key: str) -> None:  # noqa: A001
    key = key.strip()
    if not key:
        delete(provider)
        return
    if sys.platform != "win32":
        _memory[provider] = key
        return
    ctypes, CREDENTIAL, adv = _credapi()
    blob = key.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL(Type=CRED_TYPE_GENERIC, TargetName=_target(provider), CredentialBlobSize=len(blob),
                   CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                   Persist=CRED_PERSIST_LOCAL_MACHINE, UserName="api-key")
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error(), "CredWriteW failed")


def delete(provider: str) -> None:
    _memory.pop(provider, None)
    if sys.platform == "win32":
        _, _, adv = _credapi()
        adv.CredDeleteW(_target(provider), CRED_TYPE_GENERIC, 0)
