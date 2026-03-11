"""Pydantic models used to validate Zoho API responses (layperson style)."""  # Plain summary of this file.

from typing import Annotated, Any, Dict, List, Optional  # Keep type hints explicit and easy to read.

from pydantic import BaseModel, ConfigDict, StringConstraints  # Pydantic v2 building blocks for strict response validation.

# Shared constrained text type for required fields that must not be blank.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]  # Non-empty text after trimming spaces.


class ZohoBaseModel(BaseModel):  # Shared base class for all Zoho payload models.
    """Shared model config for Zoho payloads (kept simple)."""  # Brief class description.

    model_config = ConfigDict(extra="allow")  # Allow unknown keys so small API changes do not break us.


class ZohoContact(ZohoBaseModel):  # Contact details nested inside some ticket payloads.
    """Subset of contact fields that watcher code may read."""  # Brief class description.

    id:        Optional[str] = None  # Contact id text.
    firstName: Optional[str] = None  # Contact first name.
    lastName:  Optional[str] = None  # Contact last name.
    phone:     Optional[str] = None  # Contact phone number.
    mobile:    Optional[str] = None  # Contact mobile number.
    email:     Optional[str] = None  # Contact email address.


class ZohoAssignee(ZohoBaseModel):  # Agent/assignee details nested in ticket payloads.
    """Subset of assignee fields used for pending snapshots."""  # Brief class description.

    id:        Optional[str] = None  # Assignee id text.
    firstName: Optional[str] = None  # Assignee first name.
    lastName:  Optional[str] = None  # Assignee last name.
    name:      Optional[str] = None  # Assignee fallback full-name field.
    emailId:   Optional[str] = None  # Assignee email address.


class ZohoProduct(ZohoBaseModel):  # Product information nested in some ticket payloads.
    """Subset of product object fields included in ticket payloads."""  # Brief class description.

    id:          Optional[str] = None  # Product id text.
    productName: Optional[str] = None  # Product display name (common Zoho key).
    name:        Optional[str] = None  # Product display name (fallback key).


class ZohoTicket(ZohoBaseModel):  # One ticket row returned by Zoho search.
    """Ticket object returned by /api/v1/tickets/search."""  # Brief class description.

    id:              RequiredText             # REQUIRED: unique ticket id used for cooldown tracking and logs.
    ticketNumber:    RequiredText             # REQUIRED: human-friendly ticket number shown in notifications.
    status:          RequiredText             # REQUIRED: ticket status used by watcher filters.
    statusType:      RequiredText             # REQUIRED: status type used to detect unresolved/closed tickets.
    subject:         RequiredText             # REQUIRED: subject line used in matching and notification cards.
    createdTime:     RequiredText             # REQUIRED: creation timestamp used for age calculations.
    webUrl:          RequiredText             # REQUIRED: URL used by "Open Ticket" action in Teams cards.
    description:     Optional[str]            = None  # HTML/plain description text (optional fallback field).
    descriptionText: Optional[str]            = None  # Alternative plain-text description field.
    productName:     Optional[str]            = None  # Flat product name field when present.
    product:         Optional[ZohoProduct]    = None  # Nested product object when present.
    assignee:        Optional[ZohoAssignee]   = None  # Nested assignee object when present.
    contact:         Optional[ZohoContact]    = None  # Nested contact object when present.
    cf:              Optional[Dict[str, Any]] = None  # Custom-fields dictionary (`cf`) from Zoho.


class ZohoTicketSearchResponse(ZohoBaseModel):  # Top-level wrapper for ticket search responses.
    """Top-level payload returned by Zoho ticket search."""  # Brief class description.

    data:  List[ZohoTicket]  # REQUIRED: list of tickets returned by search endpoint (can be empty list).
    count: Optional[int] = None  # Optional total/count field from Zoho.


class ZohoAccessTokenResponse(ZohoBaseModel):  # Top-level wrapper for OAuth token responses.
    """Token payload returned by Zoho refresh-token exchange."""  # Brief class description.

    access_token:   RequiredText  # REQUIRED one-hour OAuth access token.
    api_domain:     Optional[str] = None  # Optional Zoho API domain hint.
    token_type:     Optional[str] = None  # Optional token type text.
    scope:          Optional[str] = None  # Optional granted scope text.
    expires_in:     Optional[int] = None  # Optional expiry value (seconds).
    expires_in_sec: Optional[int] = None  # Optional alternate expiry field.
