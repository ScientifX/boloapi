"""
UPDATED HOME PAGE ROUTE FOR app.py

Replace your existing "/" route with this updated version.
This maintains the FBI API data fetch while using the new template.
"""

@app.get("/", response_class=HTMLResponse)
@limiter.limit(rate_max)
async def root(request: Request):
    """
    Homepage - accessible by all roles (PUBLIC and above)
    Shows live FBI data statistics, features, pricing, and use cases
    """
    # Public endpoint - no authentication required
    current_role = get_current_role(request)  # For session-based testing
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(FBI_API_URL, params={"page": 1})
            response.raise_for_status()
            data = response.json()
            total = data.get("total", "N/A")
        except Exception:
            total = "5,200+"  # Fallback if FBI API is unavailable
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total": total,
            "current_role": current_role.value,  # For testing display
        }
    )
