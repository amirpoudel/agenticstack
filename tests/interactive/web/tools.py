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
import logging
from typing import Any

logger = logging.getLogger(__name__)

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
                    "description": "Listing intent: sale or rent. Map user phrase 'buy' to 'sale'.",
                },
                "location": {"type": "string", "description": "City or area name"},
                "maxPrice": {"type": "number", "description": "Max price in NPR"},
                "minBedrooms": {"type": "integer", "description": "Min bedrooms"},
            },
            "required": [],
        },
        "required": [],
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
        "slug": "house-sale-kathmandu-006",
        "title": "Affordable 2BHK House in Kapan",
        "propertyType": "house",
        "listingType": "sale",
        "location": "Kapan, Kathmandu",
        "price": 9_500_000,
        "bedrooms": 2,
        "area": "3.5 aana",
        "description": "Budget-friendly house suitable for small families.",
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
    {
        "slug": "house-sale-lalitpur-007",
        "title": "Family 3BHK House in Imadol",
        "propertyType": "house",
        "listingType": "sale",
        "location": "Imadol, Lalitpur",
        "price": 12_500_000,
        "bedrooms": 3,
        "area": "4 aana",
        "description": "Well-maintained family house near schools and market.",
    },
    {
        "slug": "apartment-sale-kathmandu-008",
        "title": "Compact 2BHK Apartment in New Baneshwor",
        "propertyType": "apartment",
        "listingType": "sale",
        "location": "New Baneshwor, Kathmandu",
        "price": 8_800_000,
        "bedrooms": 2,
        "area": "980 sqft",
        "description": "Affordable apartment close to offices and transport.",
    },
    {
        "slug": "house-rent-lalitpur-009",
        "title": "2.5 Storey House for Rent in Bhaisepati",
        "propertyType": "house",
        "listingType": "rent",
        "location": "Bhaisepati, Lalitpur",
        "price": 65_000,
        "bedrooms": 4,
        "area": "6 aana",
        "description": "Spacious rental house with parking and terrace.",
    },
    {
        "slug": "land-sale-bhaktapur-010",
        "title": "Residential Land in Suryabinayak",
        "propertyType": "land",
        "listingType": "sale",
        "location": "Suryabinayak, Bhaktapur",
        "price": 6_500_000,
        "bedrooms": 0,
        "area": "2.5 aana",
        "description": "Road-access land plot suitable for a small house.",
    },
    {
        "slug": "commercial-rent-kathmandu-011",
        "title": "Street-front Shop Space in Putalisadak",
        "propertyType": "commercial",
        "listingType": "rent",
        "location": "Putalisadak, Kathmandu",
        "price": 90_000,
        "bedrooms": 0,
        "area": "550 sqft",
        "description": "High-footfall retail space ideal for showroom or office.",
    },
    {
        "slug": "house-sale-bhaktapur-012",
        "title": "Traditional Style 3BHK House in Madhyapur",
        "propertyType": "house",
        "listingType": "sale",
        "location": "Madhyapur Thimi, Bhaktapur",
        "price": 9_900_000,
        "bedrooms": 3,
        "area": "3.75 aana",
        "description": "Move-in-ready home with easy access to ring road.",
    },
    {
        "slug": "apartment-rent-kathmandu-013",
        "title": "Modern 1BHK Apartment in Lazimpat",
        "propertyType": "apartment",
        "listingType": "rent",
        "location": "Lazimpat, Kathmandu",
        "price": 38_000,
        "bedrooms": 1,
        "area": "620 sqft",
        "description": "Bright and modern apartment suitable for professionals.",
    },
    {
        "slug": "house-sale-pokhara-014",
        "title": "Lake-view 4BHK House in Pokhara",
        "propertyType": "house",
        "listingType": "sale",
        "location": "Lakeside, Pokhara",
        "price": 18_000_000,
        "bedrooms": 4,
        "area": "7 aana",
        "description": "Premium house with mountain and lake views.",
    },
    {
        "slug": "land-sale-kathmandu-015",
        "title": "Corner Plot in Budhanilkantha",
        "propertyType": "land",
        "listingType": "sale",
        "location": "Budhanilkantha, Kathmandu",
        "price": 11_000_000,
        "bedrooms": 0,
        "area": "5 aana",
        "description": "Peaceful residential plot in a growing neighborhood.",
    },
]


# ── Mock executor (per-user shortlist state) ──────────────────────────────────

_shortlists: dict[str, list] = {}


def _normalize_listing_type(value: Any) -> str:
    logger.info("[test-tools] _normalize_listing_type value=%s", value)
    raw = str(value or "").strip().lower()
    mapping = {
        "buy": "sale",
        "buy sale": "sale",
        "buy/sale": "sale",
        "for sale": "sale",
        "sale": "sale",
        "rent": "rent",
        "rent in": "rent",
        "rent out": "rent",
        "rent-in": "rent",
        "rent-out": "rent",
        "rental": "rent",
        "lease": "rent",
    }
    normalized = mapping.get(raw, raw)
    logger.info("[test-tools] _normalize_listing_type normalized=%s", normalized)
    return normalized


def _normalize_property_type(value: Any) -> str:
    logger.info("[test-tools] _normalize_property_type value=%s", value)
    raw = str(value or "").strip().lower()
    mapping = {
        "house": "house",
        "home": "house",
        "villa": "house",
        "land": "land",
        "plot": "land",
        "apartment": "apartment",
        "apartments": "apartment",
        "flat": "apartment",
        "flats": "apartment",
        "aparment": "apartment",
        "appt": "apartment",
        "commercial": "commercial",
        "office": "commercial",
        "shop": "commercial",
        "commercial space": "commercial",
    }
    normalized = mapping.get(raw, raw)
    logger.info("[test-tools] _normalize_property_type normalized=%s", normalized)
    return normalized


def _normalize_location(value: Any) -> str:
    logger.info("[test-tools] _normalize_location value=%s", value)
    text = str(value or "").strip().lower()
    aliases = {
        "kathamandu": "kathmandu",
        "katmandu": "kathmandu",
        "ktm": "kathmandu",
    }
    for src, dst in aliases.items():
        text = text.replace(src, dst)
    logger.info("[test-tools] _normalize_location normalized=%s", text)
    return text


def execute_tool(name: str, args: dict, user_id: str) -> str:
    """Execute a mock tool call and return a JSON string result.

    This runs inside the test client — AgenticStack only decides *when* and
    *with what args* to call a tool. Execution always lives here.
    """
    logger.info("[test-tools] execute_tool name=%s user_id=%s args=%s", name, user_id, args)
    sl = _shortlists.setdefault(user_id, [])

    if name == "search_properties":
        ptype = _normalize_property_type(args.get("propertyType"))
        ltype = _normalize_listing_type(args.get("listingType"))
        loc = _normalize_location(args.get("location"))
        max_p = args.get("maxPrice")
        min_b = args.get("minBedrooms") or 0
        results = [
            p for p in MOCK_PROPERTIES
            if (not ptype or p["propertyType"] == ptype)
            and (not ltype or p["listingType"] == ltype)
            and (not loc or loc in _normalize_location(p["location"]))
            and (max_p is None or p["price"] <= max_p)
            and p["bedrooms"] >= min_b
        ]
        logger.info(
            "[test-tools] search_properties filters propertyType=%s listingType=%s location=%s maxPrice=%s minBedrooms=%s found=%s",
            ptype,
            ltype,
            loc,
            max_p,
            min_b,
            len(results),
        )
        return json.dumps({"found": len(results), "properties": results})

    if name == "get_property_details":
        slug = args.get("slug", "")
        prop = next((p for p in MOCK_PROPERTIES if p["slug"] == slug), None)
        logger.info("[test-tools] get_property_details slug=%s found=%s", slug, bool(prop))
        return json.dumps(prop if prop else {"error": f"Not found: {slug}"})

    if name == "shortlist_property":
        slug = args.get("slug", "")
        note = args.get("note", "")
        if not any(s["slug"] == slug for s in sl):
            sl.append({"slug": slug, "note": note})
        logger.info("[test-tools] shortlist_property slug=%s total=%s", slug, len(sl))
        return json.dumps({"shortlisted": slug, "total": len(sl)})

    if name == "get_shortlist":
        logger.info("[test-tools] get_shortlist total=%s", len(sl))
        return json.dumps({"shortlist": sl, "total": len(sl)})

    logger.info("[test-tools] unknown tool name=%s", name)
    return json.dumps({"error": f"Unknown tool: {name}"})
