"""Pydantic models used to validate Zoho API responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ZohoBaseModel(BaseModel):
    """Shared model config for Zoho payloads."""

    model_config = ConfigDict(extra="allow")


class ZohoContact(ZohoBaseModel):
    """Subset of contact fields that watcher code may read."""

    id: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None


class ZohoAssignee(ZohoBaseModel):
    """Subset of assignee fields used for pending snapshots."""

    id: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    name: Optional[str] = None
    emailId: Optional[str] = None


class ZohoProduct(ZohoBaseModel):
    """Subset of product object fields included in ticket payloads."""

    id: Optional[str] = None
    productName: Optional[str] = None
    name: Optional[str] = None


class ZohoTicket(ZohoBaseModel):
    """Ticket object returned by /api/v1/tickets/search."""

    id: Optional[str] = None
    ticketNumber: Optional[str] = None
    status: Optional[str] = None
    statusType: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    descriptionText: Optional[str] = None
    createdTime: Optional[str] = None
    webUrl: Optional[str] = None
    productName: Optional[str] = None
    product: Optional[ZohoProduct] = None
    assignee: Optional[ZohoAssignee] = None
    contact: Optional[ZohoContact] = None
    cf: Optional[Dict[str, Any]] = None


class ZohoTicketSearchResponse(ZohoBaseModel):
    """Top-level payload returned by Zoho ticket search."""

    data: Optional[List[ZohoTicket]] = None
    count: Optional[int] = None


class ZohoAccessTokenResponse(ZohoBaseModel):
    """Token payload returned by Zoho refresh-token exchange."""

    access_token: str
    api_domain: Optional[str] = None
    token_type: Optional[str] = None
    scope: Optional[str] = None
    expires_in: Optional[int] = None
    expires_in_sec: Optional[int] = None
