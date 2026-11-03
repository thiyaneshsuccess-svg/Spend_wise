"""Request dependencies.

``get_current_user`` is the single seam where identity enters the application.
Today it bootstraps one local user, because SpendWise is local-first and auth
lands in M7. When sessions arrive, only this function changes: every query
downstream already receives a ``user`` object and scopes by ``user.id``.

Building the seam now — rather than adding ``user_id`` later — is deliberate.
Retrofitting tenant isolation into an existing schema is how data leaks happen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_session

LOCAL_USER_EMAIL = "local@spendwise.app"

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(session: SessionDep) -> User:
    user = session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is not None:
        return user

    settings = get_settings()
    user = User(
        email=LOCAL_USER_EMAIL,
        display_name="Local User",
        currency=settings.currency,
        timezone=settings.timezone,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
