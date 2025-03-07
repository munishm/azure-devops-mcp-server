import os
import base64
import logging
from typing import Optional, Dict, List
from urllib.parse import quote
from dotenv import load_dotenv
import requests
from fastmcp import FastMCP

# -----------------------------------
# Setup Logging
# -----------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('azure_devops_mcp.log')  # Output to file
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------------
# Load Environment Variables
# -----------------------------------
load_dotenv()
ORGANIZATION = os.getenv("ORGANIZATION")
PROJECT = os.getenv("PROJECT")
BASE_URL = os.getenv("BASE_URL", "https://dev.azure.com")
API_VERSION = "7.2-preview"
PAT = os.getenv("AZURE_DEVOPS_PAT")

if not all([ORGANIZATION, PROJECT, PAT]):
    logger.error("Missing required environment variables: ORGANIZATION, PROJECT, or AZURE_DEVOPS_PAT")
    raise ValueError("Required environment variables are not set")

AZURE_DEVOPS_URL = f"{BASE_URL}/{ORGANIZATION}/{PROJECT}/_apis"
HEADERS = {
    "Authorization": f"Basic {base64.b64encode(f':{PAT}'.encode()).decode()}",
    "Content-Type": "application/json-patch+json",
}

# -----------------------------------
# MCP Server Initialization
# -----------------------------------
mcp = FastMCP("Azure DevOps Work Items Manager")

# -----------------------------------
# Helper Functions
# -----------------------------------
def _fetch_work_item_details(url: str) -> Dict:
    """Helper to fetch work item details from a given URL."""
    try:
        logger.debug(f"Fetching work item details from {url}")
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch work item details from {url}: {e}")
        raise

# -----------------------------------
# Resources
# -----------------------------------
@mcp.resource("workitems://recent")
def get_recent_work_items() -> str:
    """Get a list of recent work items using WIQL."""
    logger.info("Fetching recent work items")
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/wiql?api-version={API_VERSION}"
        query = {
            "query": "SELECT [System.Id], [System.Title], [System.State] FROM workitems WHERE [System.TeamProject] = @project ORDER BY [System.ChangedDate] DESC"
        }
        response = requests.post(url, json=query, headers=HEADERS)
        response.raise_for_status()
        
        work_items = response.json().get("workItems", [])
        if not work_items:
            logger.info("No recent work items found")
            return "No recent work items found"
        
        details: List[str] = []
        for item in work_items[:10]:
            item_data = _fetch_work_item_details(item["url"])
            title = item_data["fields"]["System.Title"]
            state = item_data["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        
        result = "\n".join(details)
        logger.info(f"Successfully fetched {len(details)} recent work items")
        return result
    except Exception as e:
        logger.error(f"Failed to fetch recent work items: {e}")
        return f"Error: {str(e)}"

@mcp.resource("workitems://{work_item_id}")
def get_work_item(work_item_id: str) -> str:
    """Retrieve a single work item by ID."""
    logger.info(f"Fetching work item {work_item_id}")
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        result = (
            f"ID: {data['id']}\n"
            f"Title: {data['fields']['System.Title']}\n"
            f"State: {data['fields']['System.State']}\n"
            f"Description: {data['fields'].get('System.Description', 'No description')}\n"
            f"URL: {data['url']}"
        )
        logger.info(f"Successfully fetched work item {work_item_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to fetch work item {work_item_id}: {e}")
        return f"Error: {str(e)}"

@mcp.resource("workitems://list/{ids}")
def list_work_items(ids: str) -> str:
    """List work items by comma-separated IDs."""
    logger.info(f"Listing work items for IDs: {ids}")
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems?ids={ids}&api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        if not data["value"]:
            logger.info("No work items found for provided IDs")
            return "No work items found"
        
        details: List[str] = []
        for item in data["value"]:
            title = item["fields"]["System.Title"]
            state = item["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        
        result = "\n".join(details)
        logger.info(f"Successfully listed {len(details)} work items")
        return result
    except Exception as e:
        logger.error(f"Failed to list work items: {e}")
        return f"Error: {str(e)}"

@mcp.resource("workitems://batch/{ids}")
def get_work_items_batch(ids: str) -> str:
    """Get multiple work items in a batch by comma-separated IDs."""
    logger.info(f"Fetching batch work items for IDs: {ids}")
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
            logger.info("No work items found in batch")
            return "No work items found"
        
        details: List[str] = []
        for item in data["value"]:
            title = item["fields"]["System.Title"]
            state = item["fields"]["System.State"]
            details.append(f"ID: {item['id']} | Title: {title} | State: {state}")
        
        result = "\n".join(details)
        logger.info(f"Successfully fetched {len(details)} batch work items")
        return result
    except Exception as e:
        logger.error(f"Failed to fetch batch work items: {e}")
        return f"Error: {str(e)}"

# -----------------------------------
# Tools
# -----------------------------------
@mcp.tool()
def create_work_item(type: str, title: str, description: str = "", parent_id: Optional[str] = None, story_points: Optional[float] = None) -> Dict:
    """Create a new work item (e.g., User Story, Task)."""
    logger.info(f"Creating work item: Type={type}, Title={title}")
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
        
        result = {"result": f"Work item created: ID {data['id']}", "id": data["id"], "url": data["url"]}
        logger.info(f"Work item created successfully: ID={data['id']}")
        return result
    except requests.exceptions.HTTPError as e:
        logger.error(f"Create work item failed with HTTP error: {e.response.text}")
        return {"error": f"HTTP Error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error(f"Create work item failed: {e}")
        return {"error": str(e)}

@mcp.tool()
def delete_work_item(work_item_id: str) -> Dict:
    """Delete a work item by ID."""
    logger.info(f"Deleting work item {work_item_id}")
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.delete(url, headers=HEADERS)
        response.raise_for_status()
        
        result = {"result": f"Work item {work_item_id} deleted successfully"}
        logger.info(f"Work item {work_item_id} deleted successfully")
        return result
    except Exception as e:
        logger.error(f"Delete work item {work_item_id} failed: {e}")
        return {"error": str(e)}

@mcp.tool()
def update_work_item(work_item_id: str, title: Optional[str] = None, description: Optional[str] = None, 
                     story_points: Optional[float] = None, state: Optional[str] = None) -> Dict:
    """Update a work item’s fields."""
    logger.info(f"Updating work item {work_item_id}")
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
            logger.warning(f"No fields provided to update for work item {work_item_id}")
            return {"error": "No fields provided to update"}
        
        response = requests.patch(url, json=body, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        result = {"result": f"Work item {work_item_id} updated", "url": data["url"]}
        logger.info(f"Work item {work_item_id} updated successfully")
        return result
    except Exception as e:
        logger.error(f"Update work item {work_item_id} failed: {e}")
        return {"error": str(e)}

# -----------------------------------
# Prompts
# -----------------------------------
@mcp.prompt()
def analyze_work_item(work_item_id: str) -> str:
    """Generate a prompt for analyzing a work item."""
    logger.info(f"Generating analysis prompt for work item {work_item_id}")
    try:
        url = f"{AZURE_DEVOPS_URL}/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        title = data["fields"]["System.Title"]
        state = data["fields"]["System.State"]
        description = data["fields"].get("System.Description", "No description")
        
        result = (
            f"Please analyze this Azure DevOps work item:\n"
            f"ID: {work_item_id}\n"
            f"Title: {title}\n"
            f"State: {state}\n"
            f"Description: {description}\n\n"
            f"What insights can you provide about its status and content?"
        )
        logger.info(f"Analysis prompt generated for work item {work_item_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to generate analysis prompt for work item {work_item_id}: {e}")
        return f"Error retrieving work item: {str(e)}"

@mcp.prompt()
def suggest_work_item_update(work_item_id: str, title: Optional[str] = None, description: Optional[str] = None, 
                             story_points: Optional[float] = None, state: Optional[str] = None) -> str:
    """Generate a prompt to suggest updating a work item."""
    logger.info(f"Generating update suggestion prompt for work item {work_item_id}")
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
        logger.info(f"No updates suggested for work item {work_item_id}")
        return "No updates suggested"
    
    updates_str = "\n".join(updates)
    result = (
        f"Please update this Azure DevOps work item:\n"
        f"ID: {work_item_id}\n"
        f"Suggested Updates:\n"
        f"{updates_str}\n\n"
        f"Proceed with these changes?"
    )
    logger.info(f"Update suggestion prompt generated for work item {work_item_id}")
    return result

# -----------------------------------
# Main Execution
# -----------------------------------
if __name__ == "__main__":
    logger.info("Starting Azure DevOps Work Items Manager MCP server")
    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.critical(f"MCP server failed to start: {e}")
        raise