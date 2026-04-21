from fastapi import FastAPI, HTTPException
from app.services.orbital_client import OrbitalClient
from app.core.credit_logic import calculate_text_credits
from app.schemas.usage import UsageResponse
import asyncio

app = FastAPI(
    title="Orbital Copilot Usage API",
    description="Calculates credit consumption for legal document queries.",
    version="1.0.0"
)

@app.get("/usage", response_model=UsageResponse)
async def get_usage():
    """
    Main endpoint to fetch current billing period data and calculate 
    credits based on report IDs or message text logic.
    """
    orbital = OrbitalClient()
    
    try:
        # 1. Fetch raw messages from the external storage API
        messages = await orbital.get_messages()

        # 2. Extract unique report IDs to batch requests (Performance Optimization)
        report_ids = {m["report_id"] for m in messages if m.get("report_id")}
        
        # 3. Fetch report details concurrently using asyncio
        # This prevents O(n) latency bottlenecks
        tasks = [orbital.get_report_data(rid) for rid in report_ids]
        report_results = await asyncio.gather(*tasks)
        
        # Map successful report fetches to their ID for O(1) lookup
        report_map = {rid: data for rid, data in zip(report_ids, report_results) if data}

        # 4. Process each message into the required JSON contract
        usage_output = []
        for msg in messages:
            report_id = msg.get("report_id")
            report_info = report_map.get(report_id)

            # Rule: If report exists and lookup didn't 404, use fixed cost
            if report_id and report_info:
                credits = float(report_info["credit_cost"])
                report_name = report_info["name"]
            else:
                # Rule: Fallback to text calculation (if no ID or if ID returned 404)
                credits = calculate_text_credits(msg.get("text", ""))
                report_name = None

            # Construct item matching the exact contract requirement
            item = {
                "id": msg["id"],
                "timestamp": msg["timestamp"],
                "credits": credits
            }
            # Omit report_name if it doesn't exist
            if report_name:
                item["report_name"] = report_name
                
            usage_output.append(item)

        return {"usage": usage_output}

    except Exception as e:
        # Production tip: In a real app, log the error here
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        # Ensure the HTTP client session is closed
        await orbital.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
