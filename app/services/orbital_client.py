import httpx
import asyncio
from typing import Dict, Optional, Any

BASE_URL = "https://windows.net"

class OrbitalClient:
    def __init__(self):
        # In production, you'd manage this via a FastAPI lifespan for connection pooling
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_messages(self) -> list:
        """Fetches all messages for the current billing period."""
        url = f"{BASE_URL}/messages/current-period"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def get_report_data(self, report_id: int) -> Optional[Dict[str, Any]]:
        """Fetches name and cost for a single report. Handles 404 gracefully."""
        url = f"{BASE_URL}/reports/{report_id}"
        response = await self.client.get(url)
        
        if response.status_code == 404:
            return None # Triggers the "fall back" rule in the logic
            
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
