from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select

from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models import User, UserSettings
from app.models.sharing import FriendRequest, Friendship, ShareAudit, SharePermission
from app.services.storage import lock_owner
from app.sharing_schemas import ShareFlags

NAMES = tuple(ShareFlags.model_fields)
FLAGS = {name: 1 << index for index, name in enumerate(NAMES)}
REQUEST_AGE = timedelta(days=30)
COOLDOWN = timedelta(minutes=10)


def hidden():
    return ApiError(404, "shared_not_found", "内容不存在或当前不可访问。")


def person(user):
    return {"public_id": user.public_id, "nickname": user.nickname}


def peer(db, public_id, required=True):
    user = db.scalar(select(User).where(User.public_id == public_id, User.is_active.is_(True)))
    if user is None and required:
        raise hidden()
    return user


def pair(a, b):
    return (a, b) if a < b else (b, a)


def for_pair(model, a, b):
    low, high = pair(a, b)
    return select(model).where(model.low_id == low, model.high_id == high)


def grant_view(row):
    flags = row.flags if row else 0
    return dict(permissions={name: bool(flags & bit) for name, bit in FLAGS.items()},
                version=row.version if row else 0, history_scope=row.history_scope if flags else "today",
                history_start=row.history_start if flags else None, granted_at=row.granted_at if flags else None)


def direction(db, relationship_id, owner, viewer):
    return db.scalar(select(SharePermission).where(SharePermission.friendship_id == relationship_id,
                                                   SharePermission.owner_id == owner, SharePermission.viewer_id == viewer))


def relation(db, owner, public_id):
    other = peer(db, public_id)
    match = db.scalar(for_pair(Friendship, owner, other.id))
    if match is None:
        raise hidden()
    return match, other


def relationship_view(match, other, outgoing, incoming):
    return dict(relationship_id=match.id, person=person(other), outgoing=grant_view(outgoing), incoming=grant_view(incoming))


def sharing(db, owner, public_id):
    match, other = relation(db, owner, public_id)
    return relationship_view(match, other, direction(db, match.id, owner, other.id), direction(db, match.id, other.id, owner))


def listing(db, owner):
    joined = db.execute(select(Friendship, User).join(User, or_(
        and_(Friendship.low_id == owner.id, User.id == Friendship.high_id),
        and_(Friendship.high_id == owner.id, User.id == Friendship.low_id),
    )).where(User.is_active.is_(True)).order_by(Friendship.created_at.desc(), Friendship.id)).all()
    grants = {}
    if joined:
        rows = db.scalars(select(SharePermission).where(SharePermission.friendship_id.in_([rel.id for rel, _ in joined])))
        grants = {(row.friendship_id, row.owner_id, row.viewer_id): row for row in rows}
    return dict(me=person(owner), items=[
        relationship_view(rel, other, grants.get((rel.id, owner.id, other.id)), grants.get((rel.id, other.id, owner.id)))
        for rel, other in joined
    ])


def request_view(row, actor, other):
    return dict(id=row.id, person=person(other), direction="outgoing" if row.sender_id == actor else "incoming",
                status=row.status, created_at=row.created_at)


def requests(db, actor):
    return [request_view(row, actor, other) for row, other in db.execute(select(FriendRequest, User).join(User, or_(
        and_(FriendRequest.sender_id == actor, User.id == FriendRequest.recipient_id),
        and_(FriendRequest.recipient_id == actor, User.id == FriendRequest.sender_id),
    )).where(User.is_active.is_(True), FriendRequest.created_at > utcnow() - REQUEST_AGE)
        .order_by(FriendRequest.created_at.desc(), FriendRequest.id).limit(100))]


def send(db, actor, public_id):
    lock_owner(db, actor)
    other = peer(db, public_id)
    if actor == other.id:
        raise ApiError(422, "friend_self", "不能向自己发送好友申请。")
    now = utcnow()
    db.execute(delete(FriendRequest).where(FriendRequest.created_at <= now - REQUEST_AGE))
    if db.scalar(for_pair(Friendship, actor, other.id)):
        raise ApiError(409, "already_friends", "你们已经是饭搭子。")
    previous = db.scalar(for_pair(FriendRequest, actor, other.id))
    if previous and previous.status == "pending":
        return request_view(previous, actor, other)
    if previous and previous.status == "rejected" and previous.sender_id == actor and previous.updated_at > now - COOLDOWN:
        raise ApiError(429, "friend_request_cooldown", "这项申请暂时无法再次发送，请稍后再试。")
    count = db.scalar(select(func.count()).select_from(FriendRequest).where(
        FriendRequest.sender_id == actor, FriendRequest.status == "pending",
    ))
    if count >= 20:
        raise ApiError(429, "friend_requests_pending", "还有多项申请等待处理。")
    if previous:
        db.delete(previous)
        db.flush()
    low, high = pair(actor, other.id)
    request = FriendRequest(id=str(uuid4()), low_id=low, high_id=high, sender_id=actor, recipient_id=other.id,
                            created_at=now, updated_at=now)
    db.add(request)
    db.flush()
    result = request_view(request, actor, other)
    db.commit()
    return result


def respond(db, actor, request_id, status):
    lock_owner(db, actor)
    now = utcnow()
    request = db.get(FriendRequest, request_id)
    if request is None or request.created_at <= now - REQUEST_AGE:
        raise hidden()
    permitted = request.sender_id if status == "cancelled" else request.recipient_id
    if permitted != actor:
        raise hidden()
    other = db.get(User, request.recipient_id if permitted == request.sender_id else request.sender_id)
    if other is None or not other.is_active:
        raise hidden()
    if request.status == status:
        return request_view(request, actor, other)
    if request.status != "pending":
        raise ApiError(409, "friend_request_resolved", "这项申请已处理。")
    request.status = status
    request.responded_at = request.updated_at = now
    if status == "accepted" and not db.scalar(for_pair(Friendship, actor, other.id)):
        db.add(Friendship(id=str(uuid4()), low_id=request.low_id, high_id=request.high_id, created_at=now))
    result = request_view(request, actor, other)
    db.commit()
    return result


def audit(db, actor, other, event, now):
    db.add(ShareAudit(id=str(uuid4()), actor_id=actor, peer_id=other, event=event, created_at=now))
    db.flush()
    recent = select(ShareAudit.id).where(ShareAudit.actor_id == actor).order_by(
        ShareAudit.created_at.desc(), ShareAudit.id.desc()).limit(100)
    db.execute(delete(ShareAudit).where(or_(
        ShareAudit.created_at < now - timedelta(days=90),
        and_(ShareAudit.actor_id == actor, ShareAudit.id.not_in(recent)),
    )))


def remove(db, actor, public_id, relationship_id):
    lock_owner(db, actor)
    other = peer(db, public_id, required=False)
    match = db.scalar(for_pair(Friendship, actor, other.id)) if other else None
    if match is None:
        return
    if match.id != relationship_id:
        raise hidden()
    db.delete(match)
    audit(db, actor, other.id, "friend_removed", utcnow())
    db.commit()


def normalize_flags(flags):
    if not flags.records:
        flags.calories = flags.nutrition = flags.notes = False
    if not flags.records and not flags.catalog:
        flags.names = flags.photos = flags.stickers = flags.history = False
    return sum(FLAGS[key] for key, value in flags.model_dump().items() if value)


def update_grant(db, actor, public_id, relationship_id, version, permissions, scope=None, confirmed_start=None):
    lock_owner(db, actor)
    match, other = relation(db, actor, public_id)
    if match.id != relationship_id:
        raise hidden()
    stored = direction(db, match.id, actor, other.id)
    if (stored.version if stored else 0) != version:
        raise ApiError(409, "sharing_version_conflict", "共享设置已在其他位置修改，请重新读取。")
    flags = normalize_flags(permissions)
    if scope not in (None, "today") and not flags & FLAGS["history"]:
        raise ApiError(422, "history_requires_permission", "扩大历史范围前请先开启历史记录。")
    if not flags and not stored:
        return relationship_view(match, other, None, direction(db, match.id, other.id, actor))

    now = utcnow()
    old_flags = stored.flags if stored else 0
    old_scope, old_start = (stored.history_scope, stored.history_start) if stored else ("today", None)
    settings = db.get(UserSettings, actor)
    today = now.astimezone(ZoneInfo(settings.timezone if settings else "Asia/Shanghai")).date()
    next_scope = scope or (old_scope if old_flags and flags & FLAGS["history"] else "today")
    start = old_start
    if not flags:
        next_scope, start = "today", None
    elif not old_flags or scope is not None or next_scope != old_scope:
        start = None if next_scope == "all" else today - timedelta(days={"today": 0, "week": 6, "month": 29}[next_scope])
    elif flags & ~old_flags and (start is None or start < today) and confirmed_start != (start or "all"):
        raise ApiError(422, "history_choice_required", "新增权限会开放过去的记录，请确认历史起点或选择仅从今天开始。")

    if not stored:
        stored = SharePermission(friendship_id=match.id, owner_id=actor, viewer_id=other.id, version=0)
        db.add(stored)
    if (flags, next_scope, start) != (old_flags, old_scope, old_start):
        if flags & ~old_flags:
            audit(db, actor, other.id, "enabled", now)
        if old_flags & ~flags:
            audit(db, actor, other.id, "disabled" if flags else "stopped", now)
        if (next_scope, start) != (old_scope, old_start) and flags:
            audit(db, actor, other.id, "history_changed", now)
        stored.flags, stored.history_scope, stored.history_start = flags, next_scope, start
        stored.granted_at = (stored.granted_at or now) if flags else None
        stored.updated_at, stored.version = now, stored.version + 1
    result = relationship_view(match, other, stored, direction(db, match.id, other.id, actor))
    db.commit()
    return result
