from __future__ import annotations

from typing import Dict, List

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Restaurant Recommendations</title>
  <link rel="stylesheet" href="/static/dashboard.css" />
</head>
<body>
  <main>
    <h1>Restaurant Recommendations</h1>
    <p class="subtitle">Here are the places we found for your last call.</p>
    {content}
  </main>
</body>
</html>
"""


def render_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return HTML_TEMPLATE.format(content="<p>No restaurants were stored.</p>")

    cards: List[str] = []
    for place in results:
        travel_block = ""
        travel = place.get("travel") or {}
        if travel.get("duration_text") or travel.get("distance_text"):
            travel_parts = [
                travel.get("duration_text", ""),
                travel.get("distance_text", ""),
            ]
            travel_block = f"<p class='travel'>{' · '.join(part for part in travel_parts if part)}</p>"

        card = f"""
        <article class="card">
          <h2>{place.get('name', 'Unknown')}</h2>
          <p class="address">{place.get('address', 'Address unavailable')}</p>
          <p class="meta">
            <span>⭐ {place.get('rating', 'N/A')}</span>
            <span>Reviews: {place.get('user_rating_count', 0)}</span>
            <span>{place.get('price_level') or 'Price N/A'}</span>
          </p>
          {travel_block}
        </article>
        """
        cards.append(card)

    section = "<section class='grid'>" + "\n".join(cards) + "</section>"
    return HTML_TEMPLATE.format(content=section)
