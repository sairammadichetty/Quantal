import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_usage_endpoint_structure():
    """
    Test that the /usage endpoint returns the correct JSON structure
    and the 200 OK status code.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/usage")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check "usage" key exists
    assert "usage" in data
    assert isinstance(data["usage"], list)
    
    # Check structure of the first item if list is not empty
    if len(data["usage"]) > 0:
        item = data["usage"][0]
        assert "id" in item
        assert "timestamp" in item
        assert "credits" in item
        # Ensure credits is a number (float or int)
        assert isinstance(item["credits"], (int, float))

@pytest.mark.asyncio
async def test_contract_compliance():
    """
    Verify that report_name is omitted (not null) when it doesn't exist.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/usage")
    
    data = response.json()
    for item in data["usage"]:
        # The prompt strictly says: "otherwise this field should be omitted"
        # This check ensures we don't have {"report_name": null}
        if "report_name" in item:
            assert item["report_name"] is not None
