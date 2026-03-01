import httpx
from config import settings

PRIORITY_LABELS = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}

CREATE_ISSUE_MUTATION = """
mutation CreateIssue($title: String!, $description: String, $teamId: String!, $priority: Int) {
  issueCreate(input: {
    title: $title
    description: $description
    teamId: $teamId
    priority: $priority
  }) {
    success
    issue {
      id
      identifier
      title
      url
      priority
    }
  }
}
"""


async def create_ticket(
    title: str,
    description: str = "",
    priority: int = 3,
) -> dict:
    """
    Creates a Linear ticket via direct GraphQL API call.
    Returns {success, identifier, title, url, priority_label} or {success: False, error: "..."}.
    """
    headers = {
        "Authorization": settings.linear_api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "query": CREATE_ISSUE_MUTATION,
        "variables": {
            "title": title,
            "description": description,
            "teamId": settings.linear_team_id,
            "priority": priority,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("data", {}).get("issueCreate", {})
            if not result.get("success"):
                errors = data.get("errors", [{"message": "Unknown error"}])
                return {"success": False, "error": errors[0].get("message", str(errors))}

            issue = result["issue"]
            return {
                "success": True,
                "identifier": issue["identifier"],
                "title": issue["title"],
                "url": issue["url"],
                "priority_label": PRIORITY_LABELS.get(issue.get("priority", 3), "Normal"),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
