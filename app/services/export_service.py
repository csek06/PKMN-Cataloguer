"""CSV export service for collection data."""

import csv
import io
import logging
from datetime import datetime
from typing import List, Dict, Any

from sqlmodel import Session, select, text
from fastapi.responses import StreamingResponse

from app.db import engine
from app.models import Card, CollectionEntry, PriceSnapshot

logger = logging.getLogger(__name__)


class ExportService:
    """Handles CSV export of collection data."""
    
    def __init__(self):
        self.engine = engine
    
    def export_collection_csv(self) -> StreamingResponse:
        """Export collection to CSV format."""
        try:
            # Get collection data
            collection_data = self._get_collection_data()
            
            # Generate CSV content
            csv_content = self._generate_csv_content(collection_data)
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pokemon_collection_{timestamp}.csv"
            
            # Create streaming response
            response = StreamingResponse(
                io.StringIO(csv_content),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
            logger.info(f"Generated CSV export: {filename} ({len(collection_data)} cards)")
            return response
            
        except Exception as e:
            logger.error(f"Error exporting collection to CSV: {e}")
            raise
    
    def _get_collection_data(self) -> List[Dict[str, Any]]:
        """Get collection data with all relevant information."""
        with Session(self.engine) as session:
            # Query collection entries with card data and latest prices
            query = """
                SELECT 
                    c.name,
                    c.set_name,
                    c.number,
                    c.rarity,
                    pcl.notes as variant,
                    ce.condition,
                    ce.qty,
                    ce.purchase_price_cents,
                    ce.notes as collection_notes,
                    ce.created_at,
                    ce.updated_at,
                    c.hp,
                    c.types,
                    c.artist,
                    c.flavor_text,
                    ps.ungraded_cents,
                    ps.psa9_cents,
                    ps.psa10_cents,
                    ps.bgs10_cents,
                    ps.as_of_date as price_date
                FROM collectionentry ce
                JOIN card c ON ce.card_id = c.id
                LEFT JOIN pricechartinglink pcl ON c.id = pcl.card_id
                LEFT JOIN (
                    SELECT 
                        card_id,
                        ungraded_cents,
                        psa9_cents,
                        psa10_cents,
                        bgs10_cents,
                        as_of_date,
                        ROW_NUMBER() OVER (PARTITION BY card_id ORDER BY as_of_date DESC) as rn
                    FROM pricesnapshot
                ) ps ON c.id = ps.card_id AND ps.rn = 1
                ORDER BY c.name, c.set_name
            """
            
            result = session.exec(text(query))
            rows = result.fetchall()
            
            collection_data = []
            for row in rows:
                # Convert cents to dollars
                purchase_price = row.purchase_price_cents / 100 if row.purchase_price_cents else None
                ungraded_price = row.ungraded_cents / 100 if row.ungraded_cents else None
                psa9_price = row.psa9_cents / 100 if row.psa9_cents else None
                psa10_price = row.psa10_cents / 100 if row.psa10_cents else None
                bgs10_price = row.bgs10_cents / 100 if row.bgs10_cents else None
                
                # Parse types JSON if available
                types_str = ""
                if row.types:
                    try:
                        import json
                        types_list = json.loads(row.types) if isinstance(row.types, str) else row.types
                        types_str = ", ".join(types_list) if types_list else ""
                    except:
                        types_str = str(row.types) if row.types else ""
                
                collection_data.append({
                    "Card Name": row.name or "",
                    "Set Name": row.set_name or "",
                    "Card Number": row.number or "",
                    "Rarity": row.rarity or "",
                    "Variant": row.variant or "",
                    "Condition": row.condition or "",
                    "Quantity": row.qty or 0,
                    "Purchase Price": f"${purchase_price:.2f}" if purchase_price else "",
                    "Current Ungraded Price": f"${ungraded_price:.2f}" if ungraded_price else "",
                    "Current PSA 9 Price": f"${psa9_price:.2f}" if psa9_price else "",
                    "Current PSA 10 Price": f"${psa10_price:.2f}" if psa10_price else "",
                    "Current BGS 10 Price": f"${bgs10_price:.2f}" if bgs10_price else "",
                    "Price Date": row.price_date.strftime("%Y-%m-%d") if row.price_date else "",
                    "HP": row.hp or "",
                    "Types": types_str,
                    "Artist": row.artist or "",
                    "Flavor Text": row.flavor_text or "",
                    "Collection Notes": row.collection_notes or "",
                    "Date Added": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
                    "Last Updated": row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if row.updated_at else ""
                })
            
            return collection_data
    
    def _generate_csv_content(self, data: List[Dict[str, Any]]) -> str:
        """Generate CSV content from collection data."""
        if not data:
            return "No collection data to export"
        
        # Create CSV content
        output = io.StringIO()
        
        # Define column order
        fieldnames = [
            "Card Name",
            "Set Name", 
            "Card Number",
            "Rarity",
            "Variant",
            "Condition",
            "Quantity",
            "Purchase Price",
            "Current Ungraded Price",
            "Current PSA 9 Price",
            "Current PSA 10 Price",
            "Current BGS 10 Price",
            "Price Date",
            "HP",
            "Types",
            "Artist",
            "Flavor Text",
            "Collection Notes",
            "Date Added",
            "Last Updated"
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue()
    
    def get_export_stats(self) -> Dict[str, Any]:
        """Get statistics about exportable data."""
        try:
            with Session(self.engine) as session:
                # Count total collection entries
                total_entries = session.exec(
                    select(CollectionEntry.id).select_from(CollectionEntry)
                ).fetchall()
                
                # Count unique cards
                unique_cards = session.exec(
                    select(Card.id).select_from(Card)
                    .join(CollectionEntry, Card.id == CollectionEntry.card_id)
                    .distinct()
                ).fetchall()
                
                # Count entries with pricing data
                entries_with_prices = session.exec(
                    select(CollectionEntry.id).select_from(CollectionEntry)
                    .join(Card, CollectionEntry.card_id == Card.id)
                    .join(PriceSnapshot, Card.id == PriceSnapshot.card_id)
                    .distinct()
                ).fetchall()
                
                return {
                    "total_entries": len(total_entries),
                    "unique_cards": len(unique_cards),
                    "entries_with_pricing": len(entries_with_prices),
                    "pricing_coverage": round(len(entries_with_prices) / len(total_entries) * 100, 1) if total_entries else 0
                }
                
        except Exception as e:
            logger.error(f"Error getting export stats: {e}")
            return {
                "total_entries": 0,
                "unique_cards": 0,
                "entries_with_pricing": 0,
                "pricing_coverage": 0,
                "error": str(e)
            }
