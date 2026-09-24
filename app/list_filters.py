"""Remember each list page's last query conditions in the session (REQ-036).

A list page visited with query parameters stores them; a later visit without
any query parameters (e.g. from the nav bar or a "back to list" link) is
redirected to the stored conditions. Submitting the filter form with empty
values stores empty values, which effectively clears the remembered state.
"""

from flask import redirect, request, session, url_for

SESSION_PREFIX = "list_filters:"


def restore_or_remember(fields):
    """Return a redirect to the remembered conditions, or None to render normally."""
    key = SESSION_PREFIX + request.endpoint
    if request.args:
        session[key] = {f: request.args[f] for f in fields if f in request.args}
        return None
    saved = session.get(key)
    if saved and any(saved.values()):
        return redirect(url_for(request.endpoint, **saved))
    return None


def clear_all():
    for key in [k for k in session if k.startswith(SESSION_PREFIX)]:
        session.pop(key)
