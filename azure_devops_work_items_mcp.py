import os
from dotenv import load_dotenv
import requests
import base64
import logging
from urllib.parse import quote
from fastmcp import FastMCP

# Load environment variables
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Azure DevOps API setup
ORGANIZATION = os.getenv("ORGANIZATION")
PROJECT = os.getenv("PROJECT")
BASE_URL = os.getenv("BASE_URL")
API_VERSION = "7.2-preview"
PAT = os.getenv("AZURE_DEVOPS_PAT")
AZURE_DEVOPS_URL = f"{BASE_URL}/{ORGANIZATION}/{PROJECT}/_apis"

# Authentication header
auth_token = base64.b64encode(f":{PAT}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {auth_token}",
    "Content-Type": "application/json-patch+json",
}

# Initialize MCP server
mcp = FastMCP("Azure DevOps Work Items Manager")

# Resource: Get recent work items
@mcp.resource("workitems://recent")
def get_recent_work_items() -> str:
    """Get a list of recent work items using WIQL"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/wiql?api-version={API_VERSION}"
        query = {
            "query": "SELECT [System.Id], [System.Title], [System.State] FROM workitems WHERE [System.TeamProject] = @project ORDER BY [System.ChangedDate] DESC"
        }
        response = requests.post(url, json=query, headers=HEADERS)
        response.raise_for_status()
        
        work_items = response.json().get("workItems", [])
        if not work_items:
            return "No recent work items found"
        
        details = []
        for item in work_items[:10]:
            item_url = item["url"]
            item_response = requests.get(item_url, headers=HEADERS)
            item_data = item_response.json()
            title = item_data["fields"]["System.Title"]
            state = item_data["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        return "\n".join(details)
    except Exception as e:
        logger.error(f"Failed to fetch recent work items: {e}")
        return f"Error: {str(e)}"

# Tool: Create a work item
@mcp.tool()
def create_work_item(type: str, title: str, description: str = "", parent_id: str = None, story_points: float = None) -> dict:
    """Create a new work item (e.g., User Story, Task)"""
    try:
        encoded_type = quote(type)
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/${encoded_type}?api-version={API_VERSION}"
        body = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description or ""},
        ]
        
        if story_points and type.lower() == "user story":
            body.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints", "value": story_points})
        
        if parent_id:
            body.append({
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"{AZURE_DEVOPS_URL}/wit/workitems/{parent_id}"
                }
            })
        
        response = requests.post(url, json=body, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return {"result": f"Work item created: ID {data['id']}", "id": data["id"], "url": data["url"]}
    except requests.exceptions.HTTPError as e:
        logger.error(f"Create work item failed: {e.response.text}")
        return {"error": f"HTTP Error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error(f"Create work item failed: {e}")
        return {"error": str(e)}

# Tool: Delete a work item
@mcp.tool()
def delete_work_item(work_item_id: str) -> dict:
    """Delete a work item by ID"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.delete(url, headers=HEADERS)
        response.raise_for_status()
        return {"result": f"Work item {work_item_id} deleted successfully"}
    except Exception as e:
        logger.error(f"Delete work item failed: {e}")
        return {"error": str(e)}

# Resource: Get a work item
@mcp.resource("workitems://{work_item_id}")
def get_work_item(work_item_id: str) -> str:
    """Retrieve a single work item by ID"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return f"ID: {data['id']}\nTitle: {data['fields']['System.Title']}\nState: {data['fields']['System.State']}\nDescription: {data['fields'].get('System.Description', 'No description')}\nURL: {data['url']}"
    except Exception as e:
        logger.error(f"Get work item failed: {e}")
        return f"Error: {str(e)}"

# Resource: List work items
@mcp.resource("workitems://list/{ids}")
def list_work_items(ids: str) -> str:
    """List work items by comma-separated IDs"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems?ids={ids}&api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if not data["value"]:
            return "No work items found"
        
        details = []
        for item in data["value"]:
            title = item["fields"]["System.Title"]
            state = item["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        return "\n".join(details)
    except Exception as e:
        logger.error(f"List work items failed: {e}")
        return f"Error: {str(e)}"

# Tool: Update a work item
@mcp.tool()
def update_work_item(work_item_id: str, title: str = None, description: str = None, story_points: float = None, state: str = None) -> dict:
    """Update a work item’s fields"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        body = []
        
        if title:
            body.append({"op": "add", "path": "/fields/System.Title", "value": title})
        if description:
            body.append({"op": "add", "path": "/fields/System.Description", "value": description})
        if story_points:
            body.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints", "value": story_points})
        if state:
            body.append({"op": "add", "path": "/fields/System.State", "value": state})
        
        if not body:
            return {"error": "No fields provided to update"}
        
        response = requests.patch(url, json=body, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return {"result": f"Work item {work_item_id} updated", "url": data["url"]}
    except Exception as e:
        logger.error(f"Update work item failed: {e}")
        return {"error": str(e)}

# Resource: Batch get work items
@mcp.resource("workitems://batch/{ids}")
def get_work_items_batch(ids: str) -> str:
    """Get multiple work items in a batch by comma-separated IDs"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitemsbatch?api-version={API_VERSION}"
        body = {
            "ids": [int(id.strip()) for id in ids.split(",")],
            "fields": ["System.Id", "System.Title", "System.State"]
        }
        response = requests.post(url, json=body, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if not data["value"]:
            return "No work items found"
        
        details = []
        for item in data["value"]:
            title = item["fields"]["System.Title"]
            state = item["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        return "\n".join(details)
    except Exception as e:
        logger.error(f"Batch get work items failed: {e}")
        return f"Error: {str(e)}"

# Prompt: Analyze a work item
@mcp.prompt()
def analyze_work_item(work_item_id: str) -> str:
    """Generate a prompt for analyzing a work item"""
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        title = data["fields"]["System.Title"]
        state = data["fields"]["System.State"]
        description = data["fields"].get("System.Description", "No description")
        
        return f"""Please analyze this Azure DevOps work item:
ID: {work_item_id}
Title: {title}
State: {state}
Description: {description}

What insights can you provide about its status and content?"""
    except Exception as e:
        logger.error(f"Analyze work item failed: {e}")
        return f"Error retrieving work item: {str(e)}"

# Prompt: Suggest updating a work item
@mcp.prompt()
def suggest_work_item_update(work_item_id: str, title: str = None, description: str = None, story_points: float = None, state: str = None) -> str:
    """Generate a prompt to suggest updating a work item"""
    updates = []
    if title:
        updates.append(f"Title: {title}")
    if description:
        updates.append(f"Description: {description}")
    if story_points:
        updates.append(f"Story Points: {story_points}")
    if state:
        updates.append(f"State: {state}")
    
    if not updates:
        return "No updates suggested"
    
    updates_str = "\n".join(updates)  # Join outside the f-string
    return f"""Please update this Azure DevOps work item:
ID: {work_item_id}
Suggested Updates:
{updates_str}

Proceed with these changes?"""

# Run the MCP server
if __name__ == "__main__":
    print("Running Azure DevOps Work Items Manager...")
    mcp.run(transport='stdio')