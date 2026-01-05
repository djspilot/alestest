import sqlite3
import os
from typing import List
from .models import HoleFeature, MatchedFeature

class DatabaseManager:
    def __init__(self, db_path="manufacturing_data.db"):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def initialize_schema(self, schema_path):
        """Initialize the database with the schema if tables don't exist."""
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
            
        with open(schema_path, 'r') as f:
            schema = f.read()
            
        self.connect()
        try:
            self.conn.executescript(schema)
            self.conn.commit()
        finally:
            self.close()

    def save_analysis_results(self, part_name: str, holes: List[HoleFeature], matches: List[MatchedFeature], is_turned: bool):
        """Save the analysis results to the database."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            
            # 1. Insert Part
            # Determine part type
            part_type = "Turned Part" if is_turned else "Prismatic Part"
            
            cursor.execute("""
                INSERT INTO Parts (
                    PartNumber, Revision, PartType, ConfidenceScore, ManualReviewRequired
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                part_name, 
                "A", # Default revision
                part_type, 
                0.95, # Placeholder confidence
                0 # Default manual review
            ))
            
            part_id = cursor.lastrowid
            
            # 2. Insert Holes
            for hole in holes:
                # Check if this hole has a match in the matches list
                # This is a simplistic matching based on diameter for demonstration
                # In reality, you'd pass matched objects directly or have IDs
                match = next((m for m in matches if abs(m.step_value - hole.diameter) < 0.001), None)
                
                source = "STEP"
                upper = 0.0
                lower = 0.0
                
                if match:
                    source = "BOTH"
                    upper = match.tolerance_upper
                    lower = match.tolerance_lower
                
                cursor.execute("""
                    INSERT INTO Holes (
                        PartID, HoleType, DiameterNominal, DiameterUpperDev, DiameterLowerDev,
                        PositionX, PositionY, PositionZ, Depth, DataSource
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    part_id, 
                    "Cylindrical", 
                    hole.diameter, 
                    upper, 
                    lower,
                    hole.position[0], 
                    hole.position[1], 
                    hole.position[2],
                    hole.depth, 
                    source
                ))
                
            self.conn.commit()
            # print(f"Successfully saved results for part '{part_name}' (ID: {part_id}) to database.")
            return part_id
            
        except Exception as e:
            print(f"Error saving to database: {e}")
            self.conn.rollback()
            raise
        finally:
            self.close()
