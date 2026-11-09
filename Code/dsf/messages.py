"""
Messages duetPrintGuard sends to its pages - the same scheme as duetLapse3

A Message is the English text (used in the log, and by the page as a fallback) with a code and values, so the page can
show it in its own language - see ui/src/locales ("server").  A Message is a str, so it can be used anywhere the text is.
Keep the English the same as in en.json.

An error reply with a Message: raise CodedHTTPException(status, message) - the reply is {"detail": text, "code": {...}}.
"""
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class Message(str):
    def __new__(cls, code, text, **params):
        message = super().__new__(cls, text)
        message.code = code
        message.params = params
        return message


def coded(text):
    """{code, params} for the page - None for plain text."""
    if isinstance(text, Message):
        return {'code': text.code, 'params': {k: str(v) for k, v in text.params.items()}}
    return None


def coded_errors(errors):
    """{field: {code, params}} for a dict of {field: message} - the fields with a Message."""
    return {field: coded(message) for field, message in errors.items() if coded(message)}


class CodedHTTPException(HTTPException):
    """An error reply whose detail is a Message."""

    def __init__(self, status_code, message):
        super().__init__(status_code=status_code, detail=str(message))
        self.message = message


async def coded_http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail, 'code': coded(exc.message)})
