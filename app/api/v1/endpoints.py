@app.get("/usage", response_model=UsageResponse)
async def get_usage():
    orbital = OrbitalClient()
    try:
        # 1. Get messages first
        messages = await orbital.get_messages()

        # 2. Extract unique report IDs to avoid redundant API calls
        report_ids = {m["report_id"] for m in messages if m.get("report_id")}
        
        # 3. Fetch all report details CONCURRENTLY
        tasks = [orbital.get_report_data(rid) for rid in report_ids]
        report_results = await asyncio.gather(*tasks)
        
        # Map IDs to their details for easy lookup
        report_map = {rid: data for rid, data in zip(report_ids, report_results) if data}

        # 4. Final calculation loop
        usage_data = []
        for msg in messages:
            report_id = msg.get("report_id")
            report_info = report_map.get(report_id)

            if report_id and report_info:
                # Use fixed report cost
                credits = report_info["credit_cost"]
                report_name = report_info["name"]
            else:
                # FALLBACK: Use the complex credit_logic function from previous step
                credits = calculate_text_credits(msg["text"])
                report_name = None

            # Build the specific JSON contract
            item = {"id": msg["id"], "timestamp": msg["timestamp"], "credits": credits}
            if report_name:
                item["report_name"] = report_name
            usage_data.append(item)

        return {"usage": usage_data}
    finally:
        await orbital.close()
