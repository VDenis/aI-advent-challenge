"""Support service tools for ticket management and FAQ search."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from progect_assistant.assistant.core.registry import Tool, ToolContext


def _load_support_data(filename: str, project_root: str) -> Dict[str, Any]:
    """Load JSON data from support directory."""
    path = Path(project_root) / "progect_assistant" / "support" / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}


def _save_support_data(filename: str, data: Dict[str, Any], project_root: str) -> None:
    """Save JSON data to support directory."""
    path = Path(project_root) / "progect_assistant" / "support" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_ticket_id(project_root: str) -> str:
    """Generate next ticket ID based on existing tickets."""
    config_data = _load_support_data("config.json", project_root)
    prefix = config_data.get("ticket_id_prefix", "TICKET")

    data = _load_support_data("tickets.json", project_root)
    tickets = data.get("tickets", [])

    max_id = 0
    for ticket in tickets:
        ticket_id = ticket.get("ticket_id", "")
        if ticket_id.startswith(prefix):
            try:
                num = int(ticket_id.split("-")[1])
                max_id = max(max_id, num)
            except (IndexError, ValueError):
                pass

    return f"{prefix}-{max_id + 1:03d}"


class SearchFAQTool(Tool):
    """Search FAQ entries using keyword matching."""

    name = "search_faq"
    description = "Search FAQ entries for answers to common questions."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "default": 3, "description": "Number of results to return"},
        },
        "required": ["query"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        query = params.get("query", "")
        top_k = int(params.get("top_k", 3))

        # Load FAQ data
        data = _load_support_data("faq.json", context.project_root)
        faqs = data.get("faqs", [])

        # Simple keyword matching
        results = []
        query_lower = query.lower()
        for faq in faqs:
            keywords = faq.get("keywords", [])
            question = faq.get("question", "").lower()
            answer = faq.get("answer", "").lower()

            score = 0.0
            if query_lower in question:
                score += 1.0
            if query_lower in answer:
                score += 0.5
            for keyword in keywords:
                if query_lower in keyword.lower():
                    score += 0.3

            if score > 0:
                results.append({
                    "id": faq.get("id"),
                    "category": faq.get("category"),
                    "question": faq.get("question"),
                    "answer": faq.get("answer"),
                    "score": round(score, 2),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"query": query, "count": len(results), "results": results[:top_k]}


class GetTicketTool(Tool):
    """Retrieve ticket details by ID."""

    name = "get_ticket"
    description = "Get detailed information about a support ticket."
    parameters_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "Ticket ID (e.g., TICKET-001)"},
        },
        "required": ["ticket_id"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        ticket_id = params.get("ticket_id", "")
        data = _load_support_data("tickets.json", context.project_root)
        tickets = data.get("tickets", [])

        for ticket in tickets:
            if ticket.get("ticket_id") == ticket_id:
                return {"ticket": ticket}

        return {"error": f"Ticket {ticket_id} not found"}


class CreateTicketTool(Tool):
    """Create a new support ticket."""

    name = "create_ticket"
    description = "Create a new support ticket for a user."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
            "subject": {"type": "string", "description": "Ticket subject"},
            "description": {"type": "string", "description": "Detailed problem description"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "medium",
                "description": "Ticket priority",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Tags for categorizing the ticket",
            },
        },
        "required": ["user_id", "subject", "description"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        ticket_id = _generate_ticket_id(context.project_root)
        now = datetime.utcnow().isoformat() + "Z"

        ticket = {
            "ticket_id": ticket_id,
            "user_id": params.get("user_id"),
            "status": "open",
            "priority": params.get("priority", "medium"),
            "subject": params.get("subject"),
            "description": params.get("description"),
            "created_at": now,
            "updated_at": now,
            "resolved_at": None,
            "tags": params.get("tags", []),
            "comments": [],
            "resolution": None,
            "similar_tickets": [],
        }

        # Load and update tickets
        data = _load_support_data("tickets.json", context.project_root)
        if "tickets" not in data:
            data["tickets"] = []
        data["tickets"].append(ticket)
        _save_support_data("tickets.json", data, context.project_root)

        return {"ticket": ticket, "message": f"Created ticket {ticket_id}"}


class UpdateTicketTool(Tool):
    """Update ticket status and add comments."""

    name = "update_ticket"
    description = "Update ticket status or add a comment to a ticket."
    parameters_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "Ticket ID"},
            "status": {
                "type": "string",
                "enum": ["open", "in-progress", "resolved", "closed"],
                "description": "New ticket status",
            },
            "comment": {"type": "string", "description": "Comment text to add"},
            "comment_author": {"type": "string", "default": "support", "description": "Comment author"},
            "resolution": {"type": "string", "description": "Resolution description if closing"},
        },
        "required": ["ticket_id"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        ticket_id = params.get("ticket_id", "")
        new_status = params.get("status")
        comment_text = params.get("comment")
        resolution = params.get("resolution")

        data = _load_support_data("tickets.json", context.project_root)
        tickets = data.get("tickets", [])

        ticket = None
        for t in tickets:
            if t.get("ticket_id") == ticket_id:
                ticket = t
                break

        if not ticket:
            return {"error": f"Ticket {ticket_id} not found"}

        now = datetime.utcnow().isoformat() + "Z"
        ticket["updated_at"] = now

        # Update status
        if new_status:
            ticket["status"] = new_status
            if new_status in ("resolved", "closed"):
                ticket["resolved_at"] = now

        # Add comment
        if comment_text:
            comment_id = f"comment-{len(ticket.get('comments', [])) + 1:03d}"
            comment = {
                "comment_id": comment_id,
                "author": params.get("comment_author", "support"),
                "text": comment_text,
                "created_at": now,
            }
            if "comments" not in ticket:
                ticket["comments"] = []
            ticket["comments"].append(comment)

        # Set resolution
        if resolution:
            ticket["resolution"] = resolution

        _save_support_data("tickets.json", data, context.project_root)
        return {"ticket": ticket, "message": f"Updated ticket {ticket_id}"}


class SearchTicketsTool(Tool):
    """Search tickets by query, status, or tags."""

    name = "search_tickets"
    description = "Search support tickets by text, status, or tags."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text search query"},
            "status": {
                "type": "string",
                "enum": ["open", "in-progress", "resolved", "closed"],
                "description": "Filter by status",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by tags",
            },
            "user_id": {"type": "string", "description": "Filter by user ID"},
        },
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        query = params.get("query", "").lower()
        status_filter = params.get("status")
        tag_filters = params.get("tags", [])
        user_filter = params.get("user_id")

        data = _load_support_data("tickets.json", context.project_root)
        tickets = data.get("tickets", [])

        results = []
        for ticket in tickets:
            # Apply filters
            if status_filter and ticket.get("status") != status_filter:
                continue
            if user_filter and ticket.get("user_id") != user_filter:
                continue
            if tag_filters:
                ticket_tags = ticket.get("tags", [])
                if not any(tag in ticket_tags for tag in tag_filters):
                    continue

            # Text search
            if query:
                subject = ticket.get("subject", "").lower()
                description = ticket.get("description", "").lower()
                if query not in subject and query not in description:
                    continue

            results.append({
                "ticket_id": ticket.get("ticket_id"),
                "user_id": ticket.get("user_id"),
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "subject": ticket.get("subject"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
            })

        return {"filters": params, "count": len(results), "tickets": results}


class GetUserContextTool(Tool):
    """Get user profile and ticket history."""

    name = "get_user_context"
    description = "Retrieve user profile and their support ticket history."
    parameters_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
        },
        "required": ["user_id"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        user_id = params.get("user_id", "")

        # Load user data
        users_data = _load_support_data("users.json", context.project_root)
        users = users_data.get("users", [])

        user = None
        for u in users:
            if u.get("user_id") == user_id:
                user = u
                break

        if not user:
            return {"error": f"User {user_id} not found"}

        # Load user's tickets
        tickets_data = _load_support_data("tickets.json", context.project_root)
        tickets = tickets_data.get("tickets", [])

        user_tickets = [
            {
                "ticket_id": t.get("ticket_id"),
                "status": t.get("status"),
                "subject": t.get("subject"),
                "created_at": t.get("created_at"),
            }
            for t in tickets
            if t.get("user_id") == user_id
        ]

        return {
            "user": user,
            "tickets": user_tickets,
            "ticket_count": len(user_tickets),
        }


class FindSimilarTicketsTool(Tool):
    """Find similar resolved tickets using keyword matching."""

    name = "find_similar_tickets"
    description = "Find similar resolved tickets that might help solve current issue."
    parameters_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Problem description"},
            "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
        },
        "required": ["description"],
    }

    def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        description = params.get("description", "")
        top_k = int(params.get("top_k", 5))

        # Load tickets
        data = _load_support_data("tickets.json", context.project_root)
        tickets = data.get("tickets", [])

        # Filter resolved tickets
        resolved = [t for t in tickets if t.get("status") in ("resolved", "closed")]

        # Simple similarity: keyword matching
        query_words = set(description.lower().split())
        results = []

        for ticket in resolved:
            subject = ticket.get("subject", "").lower()
            desc = ticket.get("description", "").lower()

            ticket_words = set((subject + " " + desc).split())
            common_words = query_words & ticket_words
            score = len(common_words) / max(len(query_words), 1)

            if score > 0.1:
                results.append({
                    "ticket_id": ticket.get("ticket_id"),
                    "subject": ticket.get("subject"),
                    "description": ticket.get("description")[:200] + "...",
                    "resolution": ticket.get("resolution"),
                    "score": round(score, 2),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"description": description, "count": len(results), "results": results[:top_k]}
