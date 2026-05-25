"""
Tool schemas and mock executor for the interactive test client.

Layout:
  TOOL_SCHEMAS  — JSON Schema definitions sent to AgenticStack at registration.
  MOCK_DATA     — In-memory dataset used by the mock executor.
  execute_tool  — Simulates the real service logic (runs in the test client,
                  NOT in AgenticStack).

To add a new tool:
  1. Append its schema to TOOL_SCHEMAS (or define a new list for a different app).
  2. Add a branch in execute_tool() for the new tool name.
  3. Add any mock data it needs to MOCK_DATA.
"""

import json
from typing import Any

# ── Tool schemas (sent to AgenticStack on app registration) ───────────────────

PROPERTY_TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_properties",
        "description": "Search for properties matching criteria.",
        "parameters": {
            "type": "object",
            "properties": {
                "propertyType": {
                    "type": "string",
                    "enum": ["house", "apartment", "land", "commercial"],
                    "description": "Type of property",
                },
                "listingType": {
                    "type": "string",
                    "enum": ["sale", "rent"],
                    "description": "Buy or rent",
                },
                "location": {"type": "string", "description": "City or area name"},
                "maxPrice": {"type": "number", "description": "Max price in NPR"},
                "minBedrooms": {"type": "integer", "description": "Min bedrooms"},
            },
            "required": ["propertyType", "listingType"],
        },
        "required": ["propertyType", "listingType"],
    },
    {
        "name": "get_property_details",
        "description": "Get full details of a specific property by its slug.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Property slug"},
            },
            "required": ["slug"],
        },
        "required": ["slug"],
    },
    {
        "name": "shortlist_property",
        "description": "Save a property to the user shortlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Property slug"},
                "note": {"type": "string", "description": "Optional note"},
            },
            "required": ["slug"],
        },
        "required": ["slug"],
    },
    {
        "name": "get_shortlist",
        "description": "Retrieve the user shortlisted properties.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "required": [],
    },
]


# ── Mock data ─────────────────────────────────────────────────────────────────

MOCK_PROPERTIES: list[dict[str, Any]] = [
    {
        "slug": "modern-house-kathmandu-001",
        "title": "Modern 4BHK House in Baluwatar",
        "propertyType": "house",
        "listingType": "sale",
        "location": "Baluwatar, Kathmandu",
        "price": 35_000_000,
        "bedrooms": 4,
        "area": "12 aana",
        "description": "Newly built modern house with parking and garden.",
    },
    {
        "slug": "apartment-rent-patan-002",
        "title": "2BHK Apartment for Rent in Patan",
        "propertyType": "apartment",
        "listingType": "rent",
        "location": "Patan, Lalitpur",
        "price": 25_000,
        "bedrooms": 2,
        "area": "900 sqft",
        "description": "Fully furnished apartment near Patan Dhoka.",
    },
    {
        "slug": "house-rent-thamel-003",
        "title": "3BHK House for Rent in Thamel",
        "propertyType": "house",
        "listingType": "rent",
        "location": "Thamel, Kathmandu",
        "price": 45_000,
        "bedrooms": 3,
        "area": "10 aana",
        "description": "Spacious house in tourist hub with roof terrace.",
    },
    {
        "slug": "land-pokhara-004",
        "title": "Ropani Land in Lakeside Pokhara",
        "propertyType": "land",
        "listingType": "sale",
        "location": "Lakeside, Pokhara",
        "price": 8_000_000,
        "bedrooms": 0,
        "area": "4 ropani",
        "description": "Prime land plot close to Fewa Lake.",
    },
    {
        "slug": "apartment-sale-lalitpur-005",
        "title": "Luxury 3BHK Apartment in Lalitpur",
        "propertyType": "apartment",
        "listingType": "sale",
        "location": "Sanepa, Lalitpur",
        "price": 22_000_000,
        "bedrooms": 3,
        "area": "1400 sqft",
        "description": "High-rise apartment with city views and gym.",
    },
]


# ── Mock executor (per-user shortlist state) ──────────────────────────────────

_shortlists: dict[str, list] = {}


def execute_tool(name: str, args: dict, user_id: str) -> str:
    """Execute a mock tool call and return a JSON string result.

    This runs inside the test client — AgenticStack only decides *when* and
    *with what args* to call a tool. Execution always lives here.
    """
    sl = _shortlists.setdefault(user_id, [])

    if name == "search_properties":
        ptype = (args.get("propertyType") or "").lower()
        ltype = (args.get("listingType") or "").lower()
        loc   = (args.get("location") or "").lower()
        max_p = args.get("maxPrice")
        min_b = args.get("minBedrooms") or 0
        results = [
            p for p in MOCK_PROPERTIES
            if (not ptype or p["propertyType"] == ptype)
            and (not ltype or p["listingType"] == ltype)
            and (not loc   or loc in p["location"].lower())
            and (max_p is None or p["price"] <= max_p)
            and p["bedrooms"] >= min_b
        ]
        return json.dumps({"found": len(results), "properties": results})

    if name == "get_property_details":
        slug = args.get("slug", "")
        prop = next((p for p in MOCK_PROPERTIES if p["slug"] == slug), None)
        return json.dumps(prop if prop else {"error": f"Not found: {slug}"})

    if name == "shortlist_property":
        slug = args.get("slug", "")
        note = args.get("note", "")
        if not any(s["slug"] == slug for s in sl):
            sl.append({"slug": slug, "note": note})
        return json.dumps({"shortlisted": slug, "total": len(sl)})

    if name == "get_shortlist":
        return json.dumps({"shortlist": sl, "total": len(sl)})

    return json.dumps({"error": f"Unknown tool: {name}"})
