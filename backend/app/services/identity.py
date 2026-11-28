from datetime import timedelta
from hmac import compare_digest, digest
from secrets import randbelow, token_urlsafe
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.core.security import token_hash
from app.models.identity import EmailChallenge, Invitation


def invalid_code():
    return ApiError(400, "email_code_invalid", "验证码无效或已过期，请检查后重试。")


def begin(db):
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def sign(settings, *parts):
    return digest(settings.email_code_secret.get_secret_value().encode(), "\x00".join(parts).encode(), "sha256").hex()


def code_digest(settings, row, code):
    return sign(settings, "code", row.id, row.purpose, row.mail_scope, row.owner_id or "",
                row.expires_at.isoformat(timespec="microseconds"), code)


def issue(db, settings, mailer, email, purpose, address, owner=None):
    if mailer is None:
        raise ApiError(503, "email_disabled", "邮箱验证暂未开放。")
    begin(db)
    now = utcnow()
    mail_scope, ip_scope = sign(settings, "email", email), sign(settings, "ip", address)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour = now - timedelta(hours=1)
    daily, per_mail, per_ip, recent = db.execute(select(
        func.count().filter(EmailChallenge.created_at >= day),
        func.count().filter(EmailChallenge.created_at >= hour, EmailChallenge.mail_scope == mail_scope),
        func.count().filter(EmailChallenge.created_at >= hour, EmailChallenge.ip_scope == ip_scope),
        func.count().filter(EmailChallenge.created_at > now - timedelta(seconds=60),
                            EmailChallenge.mail_scope == mail_scope),
    ).where(EmailChallenge.created_at >= min(day, hour))).one()
    if daily >= settings.email_daily_limit or per_mail >= 5 or per_ip >= 12 or recent:
        raise ApiError(429, "email_send_limit", "发送请求过于频繁，请稍后重试。", {"Retry-After": "60"})
    db.execute(delete(EmailChallenge).where(EmailChallenge.created_at < now - timedelta(days=2)))
    db.execute(update(EmailChallenge).where(
        EmailChallenge.mail_scope == mail_scope, EmailChallenge.purpose == purpose,
        EmailChallenge.owner_id == owner, EmailChallenge.consumed_at.is_(None),
    ).values(consumed_at=now))
    code = f"{randbelow(1_000_000):06d}"
    row = EmailChallenge(id=str(uuid4()), owner_id=owner, mail_scope=mail_scope, ip_scope=ip_scope, purpose=purpose,
                         attempts=0, created_at=now, expires_at=now + timedelta(minutes=5))
    row.digest = code_digest(settings, row, code)
    db.add(row)
    db.commit()
    try:
        mailer.send(email, purpose, code)
    except Exception:
        raise ApiError(503, "email_delivery_failed", "邮件暂时无法发送，请稍后重试。") from None
    db.execute(update(EmailChallenge).where(EmailChallenge.id == row.id).values(delivered_at=utcnow()))
    db.commit()
    return {"request_id": row.id, "expires_in": 300, "resend_after": 60}


def consume(db, settings, identifier, email, purpose, code, owner=None):
    if settings.email_mode == "disabled":
        raise invalid_code()
    begin(db)
    row = db.get(EmailChallenge, str(identifier))
    now = utcnow()
    expected_mail = sign(settings, "email", email)
    if (row is None or row.purpose != purpose or row.owner_id != owner or row.consumed_at is not None
            or row.delivered_at is None or row.expires_at <= now or row.attempts >= 5
            or not compare_digest(row.mail_scope, expected_mail)):
        raise invalid_code()
    if not compare_digest(row.digest, code_digest(settings, row, code)):
        row.attempts += 1
        db.commit()
        raise invalid_code()
    row.consumed_at = now


def spend_invitation(db, token):
    if not token:
        return False
    result = db.execute(update(Invitation).where(
        Invitation.digest == token_hash(token), Invitation.expires_at > utcnow(),
        Invitation.revoked_at.is_(None), Invitation.remaining > 0,
    ).values(remaining=Invitation.remaining - 1))
    return result.rowcount == 1


def create_invitation(db, count, hours):
    token = token_urlsafe(32)
    db.add(Invitation(digest=token_hash(token), remaining=count, expires_at=utcnow() + timedelta(hours=hours)))
    db.commit()
    return token
