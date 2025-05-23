import logging
from typing import Union

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic.error_wrappers import ErrorWrapper, ValidationError
from sqlalchemy.exc import IntegrityError

from dispatch.auth.permissions import PermissionsDependency, SensitiveProjectActionPermission
from dispatch.auth.service import CurrentUser
from dispatch.database.core import DbSession
from dispatch.database.service import CommonParameters, search_filter_sort_paginate
from dispatch.exceptions import ExistsError
from dispatch.models import OrganizationSlug, PrimaryKey
from dispatch.project import service as project_service
from dispatch.rate_limiter import limiter
from dispatch.signal import service as signal_service

from .models import (
    SignalCreate,
    SignalEngagementCreate,
    SignalEngagementPagination,
    SignalEngagementRead,
    SignalEngagementUpdate,
    SignalFilterCreate,
    SignalFilterPagination,
    SignalFilterRead,
    SignalFilterUpdate,
    SignalInstanceCreate,
    SignalInstancePagination,
    SignalInstanceRead,
    SignalPagination,
    SignalRead,
    SignalStats,
    SignalUpdate,
)
from .service import (
    create,
    create_signal_engagement,
    create_signal_filter,
    delete,
    delete_signal_filter,
    get,
    get_by_primary_or_external_id,
    get_signal_stats,
    get_signal_engagement,
    get_signal_filter,
    update,
    update_signal_engagement,
    update_signal_filter,
)

router = APIRouter()

log = logging.getLogger(__name__)


@router.get("/instances", response_model=SignalInstancePagination)
def get_signal_instances(common: CommonParameters):
    """Gets all signal instances."""
    return search_filter_sort_paginate(model="SignalInstance", **common)


@router.post("/instances", response_model=SignalInstanceRead)
@limiter.limit("1000/minute")
def create_signal_instance(
    db_session: DbSession,
    organization: OrganizationSlug,
    signal_instance_in: SignalInstanceCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
):
    """Creates a new signal instance."""
    # TODO this should be refactored to use the signal service
    project = project_service.get_by_name_or_default(
        db_session=db_session, project_in=signal_instance_in.project
    )

    if not signal_instance_in.signal:
        # we try to get the signal definition by external id or variant
        external_id = signal_instance_in.raw.get("externalId")
        variant = signal_instance_in.raw.get("variant")
        signal_definition = signal_service.get_by_variant_or_external_id(
            db_session=db_session,
            project_id=project.id,
            external_id=external_id,
            variant=variant,
        )

    if not signal_definition:
        # we get the default signal definition
        signal_definition = signal_service.get_default(
            db_session=db_session,
            project_id=project.id,
        )
        msg = f"Default signal definition used for signal instance with external id {external_id} or variant {variant}."
        log.warn(msg)

    if not signal_definition:
        msg = f"No signal definition could be found by external id {external_id} or variant {variant}, and no default exists."
        log.warn(msg)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": msg}],
        ) from None

    signal_instance_in.signal = signal_definition

    try:
        signal_instance = signal_service.create_instance(
            db_session=db_session, signal_instance_in=signal_instance_in
        )
    except IntegrityError:
        msg = f"A signal instance with this id already exists. Id: {signal_instance_in.raw.get('id')}. Variant: {signal_instance_in.raw.get('variant')}"
        log.warn(msg)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[{"msg": msg}],
        ) from None

    return signal_instance


@router.get("/filters", response_model=SignalFilterPagination)
def get_signal_filters(common: CommonParameters):
    """Gets all signal filters."""
    return search_filter_sort_paginate(model="SignalFilter", **common)


@router.get("/engagements", response_model=SignalEngagementPagination)
def get_signal_engagements(common: CommonParameters):
    """Gets all signal engagements."""
    return search_filter_sort_paginate(model="SignalEngagement", **common)


@router.get("/engagements/{engagement_id}", response_model=SignalEngagementRead)
def get_engagement(
    db_session: DbSession,
    signal_engagement_id: PrimaryKey,
):
    """Gets a signal engagement by its id."""
    engagement = get_signal_engagement(
        db_session=db_session, signal_engagement_id=signal_engagement_id
    )
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal engagement with this id does not exist."}],
        )
    return engagement


@router.post("/engagements", response_model=SignalEngagementRead)
def create_engagement(
    db_session: DbSession,
    signal_engagement_in: SignalEngagementCreate,
    current_user: CurrentUser,
):
    """Creates a new signal engagement."""
    try:
        return create_signal_engagement(
            db_session=db_session, creator=current_user, signal_engagement_in=signal_engagement_in
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[{"msg": "A signal engagement with this name already exists."}],
        ) from None


@router.put(
    "/engagements/{signal_engagement_id}",
    response_model=SignalEngagementRead,
    dependencies=[Depends(PermissionsDependency([SensitiveProjectActionPermission]))],
)
def update_engagement(
    db_session: DbSession,
    signal_engagement_id: PrimaryKey,
    signal_engagement_in: SignalEngagementUpdate,
):
    """Updates an existing signal engagement."""
    signal_engagement = get_signal_engagement(
        db_session=db_session, signal_engagement_id=signal_engagement_id
    )
    if not signal_engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal engagement with this id does not exist."}],
        )

    try:
        signal_engagement = update_signal_engagement(
            db_session=db_session,
            signal_engagement=signal_engagement,
            signal_engagement_in=signal_engagement_in,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[{"msg": "A signal engagement with this name already exists."}],
        ) from None

    return signal_engagement


@router.post("/filters", response_model=SignalFilterRead)
def create_filter(
    db_session: DbSession,
    signal_filter_in: SignalFilterCreate,
    current_user: CurrentUser,
):
    """Creates a new signal filter."""
    try:
        return create_signal_filter(
            db_session=db_session, creator=current_user, signal_filter_in=signal_filter_in
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[{"msg": "A signal filter with this name already exists."}],
        ) from None


@router.put(
    "/filters/{signal_filter_id}",
    response_model=SignalFilterRead,
    dependencies=[Depends(PermissionsDependency([SensitiveProjectActionPermission]))],
)
def update_filter(
    db_session: DbSession,
    signal_filter_id: PrimaryKey,
    signal_filter_in: SignalFilterUpdate,
):
    """Updates an existing signal filter."""
    signal_filter = get_signal_filter(db_session=db_session, signal_filter_id=signal_filter_id)
    if not signal_filter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal filter with this id does not exist."}],
        )

    try:
        signal_filter = update_signal_filter(
            db_session=db_session, signal_filter=signal_filter, signal_filter_in=signal_filter_in
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[{"msg": "A signal filter with this name already exists."}],
        ) from None

    return signal_filter


@router.delete(
    "/filters/{signal_filter_id}",
    response_model=None,
    dependencies=[Depends(PermissionsDependency([SensitiveProjectActionPermission]))],
)
def delete_filter(db_session: DbSession, signal_filter_id: PrimaryKey):
    """Deletes a signal filter."""
    signal_filter = get(db_session=db_session, signal_filter_id=signal_filter_id)
    if not signal_filter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal filter with this id does not exist."}],
        )
    delete_signal_filter(db_session=db_session, signal_filter_id=signal_filter_id)


@router.get("", response_model=SignalPagination)
def get_signals(common: CommonParameters):
    """Gets all signal definitions."""
    return search_filter_sort_paginate(model="Signal", **common)


@router.get("/stats", response_model=SignalStats)
def return_signal_stats(
    db_session: DbSession,
    entity_value: str = Query(..., description="The name of the entity"),
    entity_type_id: int = Query(..., description="The ID of the entity type"),
    num_days: int = Query(None, description="The number of days to look back"),
):
    """Gets signal statistics given a named entity and entity type id."""
    signal_data = get_signal_stats(
        db_session=db_session,
        entity_value=entity_value,
        entity_type_id=entity_type_id,
        num_days=num_days,
    )
    return signal_data


@router.get("/{signal_id}/stats", response_model=SignalStats)
def return_single_signal_stats(
    db_session: DbSession,
    signal_id: Union[str, PrimaryKey],
    entity_value: str = Query(..., description="The name of the entity"),
    entity_type_id: int = Query(..., description="The ID of the entity type"),
    num_days: int = Query(None, description="The number of days to look back"),
):
    """Gets signal statistics for a specific signal given a named entity and entity type id."""
    signal = get_by_primary_or_external_id(db_session=db_session, signal_id=signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal with this id does not exist."}],
        )

    signal_data = get_signal_stats(
        db_session=db_session,
        entity_value=entity_value,
        entity_type_id=entity_type_id,
        signal_id=signal.id,
        num_days=num_days,
    )
    return signal_data


@router.get("/{signal_id}", response_model=SignalRead)
def get_signal(db_session: DbSession, signal_id: Union[str, PrimaryKey]):
    """Gets a signal by its id."""
    signal = get_by_primary_or_external_id(db_session=db_session, signal_id=signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal with this id does not exist."}],
        )
    return signal


@router.post("", response_model=SignalRead)
def create_signal(db_session: DbSession, signal_in: SignalCreate, current_user: CurrentUser):
    """Creates a new signal."""
    return create(db_session=db_session, signal_in=signal_in, user=current_user)


@router.put(
    "/{signal_id}",
    response_model=SignalRead,
    dependencies=[Depends(PermissionsDependency([SensitiveProjectActionPermission]))],
)
def update_signal(
    db_session: DbSession,
    signal_id: Union[str, PrimaryKey],
    signal_in: SignalUpdate,
    current_user: CurrentUser,
):
    """Updates an existing signal."""
    signal = get_by_primary_or_external_id(db_session=db_session, signal_id=signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal with this id does not exist."}],
        )

    try:
        signal = update(
            db_session=db_session, signal=signal, signal_in=signal_in, user=current_user
        )
    except IntegrityError:
        raise ValidationError(
            [ErrorWrapper(ExistsError(msg="A signal with this name already exists."), loc="name")],
            model=SignalUpdate,
        ) from None

    return signal


@router.delete(
    "/{signal_id}",
    response_model=None,
    dependencies=[Depends(PermissionsDependency([SensitiveProjectActionPermission]))],
)
def delete_signal(db_session: DbSession, signal_id: Union[str, PrimaryKey]):
    """Deletes a signal."""
    signal = get_by_primary_or_external_id(db_session=db_session, signal_id=signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[{"msg": "A signal with this id does not exist."}],
        )
    delete(db_session=db_session, signal_id=signal.id)
