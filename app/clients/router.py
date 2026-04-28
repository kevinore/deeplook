from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, assert_client_owner, get_current_user
from app.dependencies import get_db
from app.models.schemas import ClientCreateRequest, ClientResponse, ClientUpdateRequest
from app.repositories.client_repo import ClientRepository

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("", response_model=ClientResponse, status_code=201)
async def create_client(
    body: ClientCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ClientResponse:
    repo = ClientRepository(db)
    existing = await repo.get_by_email(str(body.email))
    if existing:
        raise HTTPException(status_code=409, detail="A client with this email already exists.")
    client = await repo.create(
        name=body.name,
        email=str(body.email),
        phone=body.phone,
        business_name=body.business_name,
        business_type=body.business_type,
        business_identifiers=body.business_identifiers,
        average_transaction_value=body.average_transaction_value,
        clerk_user_id=user.user_id,
    )
    await db.commit()
    return ClientResponse.model_validate(client)


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[ClientResponse]:
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    return [ClientResponse.model_validate(c) for c in clients]


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ClientResponse:
    client = await assert_client_owner(str(client_id), user, db)
    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    body: ClientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ClientResponse:
    await assert_client_owner(str(client_id), user, db)
    updates = body.model_dump(exclude_none=True)
    client = await ClientRepository(db).update(str(client_id), **updates)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    await db.commit()
    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    await assert_client_owner(str(client_id), user, db)
    success = await ClientRepository(db).soft_delete(str(client_id))
    if not success:
        raise HTTPException(status_code=404, detail="Client not found.")
    await db.commit()
