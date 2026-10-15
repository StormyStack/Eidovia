from typing import List, Optional, Any
from fastapi import APIRouter, Depends, Query, status
from dependencies import require_admin, CurrentAdmin
from schemas import SupportTicketCreate, SupportTicketUpdate, SupportTicketResponse, WildcardTicketAnswer
from services.support_service import SupportService

router = APIRouter(prefix="/support", tags=["admin-support"])


@router.get("/tickets", response_model=List[SupportTicketResponse])
async def list_tickets(
    status: Optional[str] = Query(None, description="Filter by ticket status: open, in_progress, resolved"),
    priority: Optional[str] = Query(None, description="Filter by priority: low, medium, high"),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """List customer/student support tickets."""
    return await SupportService.list_tickets(status=status, priority=priority)


@router.post("/tickets", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: SupportTicketCreate,
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Create a support ticket or user inquiry manually."""
    return await SupportService.create_ticket(
        user_id=str(admin.user_id),
        username=admin.username,
        data=body,
    )


@router.patch("/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def update_ticket(
    ticket_id: str,
    body: SupportTicketUpdate,
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Update ticket resolution status or add administrative notes."""
    return await SupportService.update_ticket(ticket_id, body)


@router.post("/tickets/{ticket_id}/wildcards")
async def give_requested_wildcards(
    ticket_id: str,
    body: WildcardTicketAnswer,
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Answer a wildcard request: give the cards (to the learner's default) and mark the ticket resolved."""
    return await SupportService.give_wildcards(ticket_id, body.amount, admin.username, body.note, admin)
