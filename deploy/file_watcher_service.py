"""File watcher service for ALES ERP integration.

This service monitors a configured folder for new STEP files,
analyzes them automatically, and exports results to XML format
compatible with ALES ERP system.

Usage:
    # Normal operation (watches folder continuously)
    python file_watcher_service.py

    # Test mode (analyze single file and exit)
    python file_watcher_service.py --test --file path/to/file.step

Configuration:
    Set environment variables in .env file:
    - WATCHED_FOLDER: Folder to monitor (e.g., G:\\ALES\\Offerte-ALES)
    - LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
    - ENABLE_UNFOLD: Enable FreeCAD unfold (True/False, default: True)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path (deploy/ is one level below project root)
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from manufacturing_pipeline.reporting.xml_exporter import export_to_xml


# Load environment variables
load_dotenv()

# Configuration from environment
WATCHED_FOLDER = os.getenv('WATCHED_FOLDER', r'G:\ALES\Offerte-ALES')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
ENABLE_UNFOLD = os.getenv('ENABLE_UNFOLD', 'True').lower() == 'true'

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_watcher_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class STEPFileHandler(FileSystemEventHandler):
    """Handler for STEP file creation events."""

    def __init__(self):
        self.processing = set()  # Track files being processed to avoid duplicates
        super().__init__()

    def on_created(self, event):
        """Called when a file is created in the watched folder."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process STEP files
        if file_path.suffix.lower() not in ['.step', '.stp']:
            return

        # Avoid processing the same file twice
        if str(file_path) in self.processing:
            logger.debug(f"File already being processed: {file_path}")
            return

        logger.info(f"New STEP file detected: {file_path}")

        # Add to processing set
        self.processing.add(str(file_path))

        try:
            # Process the file
            self._process_step_file(file_path)
        finally:
            # Remove from processing set
            self.processing.discard(str(file_path))

    def _process_step_file(self, file_path: Path):
        """Process a STEP file and export results to XML.

        Args:
            file_path: Path to the STEP file
        """
        # Extract offertenr from folder name
        # Example: G:\ALES\Offerte-ALES\2026\20260312\part.step
        # → offertenr = "20260312"
        folder = file_path.parent
        offertenr = folder.name

        # Log file path
        log_path = folder / f"STEP_{offertenr}.log"

        # Write start log
        logger.info(f"Processing: {file_path} (Offertenr: {offertenr})")
        log_content = f"STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_content += f"File: {file_path.name}\n"
        log_path.write_text(log_content, encoding='utf-8')

        try:
            # Wait a moment to ensure file is fully written
            time.sleep(1)

            # Analyze using the pipeline
            result = analyze_step_file(str(file_path))

            # Export to XML
            xml_path = folder / f"STEP_{offertenr}.xml"
            export_to_xml(result, xml_path, part_name=offertenr)

            # Update log with success
            log_content += f"COMPLETED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            log_content += f"XML: {xml_path.name}\n"
            log_content += f"Category: {result.get('category', 'N/A')}\n"
            log_content += f"Thickness: {result.get('thickness', 'N/A')} mm\n"
            log_content += f"Holes: {result.get('production', {}).get('holes_total', 0)}\n"
            log_content += f"Bends: {result.get('production', {}).get('bends_total', 0)}\n"

            log_path.write_text(log_content, encoding='utf-8')

            logger.info(f"Successfully processed: {file_path.name} → {xml_path.name}")

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}", exc_info=True)

            # Update log with error
            log_content += f"ERROR: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            log_content += f"Message: {str(e)}\n"
            log_path.write_text(log_content, encoding='utf-8')


def analyze_step_file(file_path: str) -> dict:
    """Analyze a STEP file and return results.

    This is a wrapper around the existing run.py analysis logic.

    Args:
        file_path: Path to STEP file

    Returns:
        Analysis result dict
    """
    from manufacturing_pipeline.scripts.aag_analyzer import analyze_with_aag
    from manufacturing_pipeline.analysis.part_analyzer import PartAnalyzer

    logger.debug(f"Running AAG analysis on: {file_path}")

    # Run AAG analysis (topology-based feature recognition)
    result = analyze_with_aag(
        file_path,
        enable_unfold=ENABLE_UNFOLD,
        verbose=False
    )

    # Add part classification
    analyzer = PartAnalyzer()
    category, part_type, reasoning = analyzer.classify_part(result)

    result['category'] = category
    result['part_type'] = part_type
    result['file'] = Path(file_path).name
    result['success'] = True

    return result


def main():
    """Main entry point for file watcher service."""
    parser = argparse.ArgumentParser(description="ALES ERP File Watcher Service")
    parser.add_argument('--test', action='store_true', help="Test mode (single file)")
    parser.add_argument('--file', type=str, help="STEP file to process in test mode")

    args = parser.parse_args()

    if args.test:
        # Test mode: analyze single file
        if not args.file:
            logger.error("--file required in test mode")
            sys.exit(1)

        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

        logger.info(f"Test mode: analyzing {file_path}")

        handler = STEPFileHandler()
        handler._process_step_file(file_path)

        logger.info("Test complete")
        return

    # Normal operation: watch folder
    logger.info(f"Starting file watcher service")
    logger.info(f"Watching folder: {WATCHED_FOLDER}")
    logger.info(f"Unfold enabled: {ENABLE_UNFOLD}")

    # Create watched folder if it doesn't exist
    Path(WATCHED_FOLDER).mkdir(parents=True, exist_ok=True)

    # Create event handler and observer
    event_handler = STEPFileHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCHED_FOLDER, recursive=True)

    # Start watching
    observer.start()
    logger.info("File watcher service started. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping file watcher service...")
        observer.stop()

    observer.join()
    logger.info("File watcher service stopped")


if __name__ == '__main__':
    main()
