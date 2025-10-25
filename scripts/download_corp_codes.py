#!/usr/bin/env python3
"""DART corp_code.xml 다운로드 및 파싱 스크립트.

DART API에서 기업 고유번호(corp_code) 목록을 다운로드하고
ticker ↔ corp_code 매핑 테이블에 저장합니다.

Requirements:
- DART_API_KEY in .env file
"""

import os
import sys
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import httpx
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal, test_connection
from models import CorpCodeMap

load_dotenv()

DART_API_KEY = os.getenv("DART_API_KEY")
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DATA_DIR = project_root / "data" / "dart"


def print_header(title: str):
    """Print formatted header."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + f" {title:^66} " + "║")
    print("╚" + "═" * 68 + "╝")
    print()


def print_section(title: str):
    """Print section separator."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def download_corp_codes(api_key: str) -> Path:
    """Download corp_code.xml from DART API.

    Args:
        api_key: DART API key

    Returns:
        Path to extracted XML file

    Raises:
        Exception if download fails
    """
    print_section("Step 1: Downloading corp_code.xml from DART")

    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = DATA_DIR / "corpCode.zip"
    xml_path = DATA_DIR / "CORPCODE.xml"

    # Download ZIP file
    params = {"crtfc_key": api_key}

    try:
        print(f"Downloading from: {CORP_CODE_URL}")
        print(f"API Key: {api_key[:10]}..." if api_key else "No API key provided")

        with httpx.Client(timeout=60.0) as client:
            response = client.get(CORP_CODE_URL, params=params)
            response.raise_for_status()

            # Save ZIP file
            with open(zip_path, "wb") as f:
                f.write(response.content)

            print(f"✅ Downloaded: {zip_path} ({len(response.content):,} bytes)")

        # Extract ZIP file
        print("\nExtracting ZIP file...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(DATA_DIR)

        print(f"✅ Extracted: {xml_path}")

        # Clean up ZIP file
        zip_path.unlink()

        return xml_path

    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text[:200]}")
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


def parse_corp_codes(xml_path: Path) -> list:
    """Parse CORPCODE.xml and extract company information.

    Args:
        xml_path: Path to CORPCODE.xml

    Returns:
        List of corp code dictionaries
    """
    print_section("Step 2: Parsing CORPCODE.xml")

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        corp_codes = []

        for corp in root.findall("list"):
            corp_code = corp.find("corp_code").text if corp.find("corp_code") is not None else None
            corp_name = corp.find("corp_name").text if corp.find("corp_name") is not None else None
            stock_code = corp.find("stock_code").text if corp.find("stock_code") is not None else None
            modify_date = corp.find("modify_date").text if corp.find("modify_date") is not None else None

            # Only include companies with stock codes (상장사만)
            if stock_code and stock_code.strip():
                corp_codes.append({
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code.strip(),  # This is the ticker
                    "modify_date": modify_date
                })

        print(f"✅ Parsed {len(corp_codes):,} listed companies from XML")

        # Show sample
        print("\nSample corp codes (first 5):")
        print(f"{'Corp Code':<10} {'Stock Code':<10} {'Corp Name':<30}")
        print("-" * 70)
        for corp in corp_codes[:5]:
            print(f"{corp['corp_code']:<10} {corp['stock_code']:<10} {corp['corp_name']:<30}")

        return corp_codes

    except Exception as e:
        print(f"❌ Error parsing XML: {e}")
        raise


def save_to_database(corp_codes: list) -> int:
    """Save corp codes to database.

    Args:
        corp_codes: List of corp code dictionaries

    Returns:
        Number of records saved
    """
    print_section("Step 3: Saving to Database")

    db = SessionLocal()
    saved_count = 0
    updated_count = 0

    try:
        for corp in corp_codes:
            try:
                # Check if already exists
                existing = db.query(CorpCodeMap).filter_by(
                    ticker=corp["stock_code"]
                ).first()

                if existing:
                    # Update existing record
                    existing.corp_code = corp["corp_code"]
                    existing.corp_name = corp["corp_name"]
                    existing.modify_date = corp["modify_date"]
                    updated_count += 1
                else:
                    # Create new record
                    new_corp = CorpCodeMap(
                        ticker=corp["stock_code"],
                        corp_code=corp["corp_code"],
                        corp_name=corp["corp_name"],
                        stock_name=corp["corp_name"],  # Use same as corp_name initially
                        modify_date=corp["modify_date"]
                    )
                    db.add(new_corp)
                    saved_count += 1

                # Commit every 100 records
                if (saved_count + updated_count) % 100 == 0:
                    db.commit()
                    print(f"Progress: {saved_count + updated_count:,} / {len(corp_codes):,}")

            except Exception as e:
                print(f"⚠️  Error saving {corp['stock_code']}: {e}")
                db.rollback()
                continue

        # Final commit
        db.commit()

        print(f"\n✅ Database save complete:")
        print(f"   - New records: {saved_count:,}")
        print(f"   - Updated records: {updated_count:,}")
        print(f"   - Total: {saved_count + updated_count:,}")

        return saved_count + updated_count

    except Exception as e:
        print(f"❌ Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def verify_mapping() -> None:
    """Verify corp_code_map table contents."""
    print_section("Step 4: Verifying Database")

    db = SessionLocal()

    try:
        total = db.query(CorpCodeMap).count()
        print(f"Total corp codes in database: {total:,}")

        # Show sample
        samples = db.query(CorpCodeMap).limit(10).all()

        print(f"\nSample mappings (first 10):")
        print(f"{'Ticker':<10} {'Corp Code':<10} {'Corp Name':<30}")
        print("-" * 70)
        for corp in samples:
            print(f"{corp.ticker:<10} {corp.corp_code:<10} {corp.corp_name:<30}")

    finally:
        db.close()


def main():
    """메인 함수."""
    print_header("DART Corp Code Download & Mapping")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check API key
    if not DART_API_KEY:
        print("\n" + "=" * 70)
        print("⚠️  DART_API_KEY not found in .env file!")
        print("=" * 70)
        print("\nPlease get your free API key from:")
        print("https://opendart.fss.or.kr/")
        print("\nThen add it to your .env file:")
        print("DART_API_KEY=your_api_key_here")
        print("\nSee docs/DART_API_SETUP.md for detailed instructions.")
        print("=" * 70)
        sys.exit(1)

    # Test database connection
    if not test_connection():
        print("\n❌ Database connection failed!")
        sys.exit(1)

    try:
        # Step 1: Download corp_code.xml
        xml_path = download_corp_codes(DART_API_KEY)

        # Step 2: Parse XML
        corp_codes = parse_corp_codes(xml_path)

        # Step 3: Save to database
        saved_count = save_to_database(corp_codes)

        # Step 4: Verify
        verify_mapping()

        # Success summary
        print("\n" + "=" * 70)
        print("✅ Corp code mapping completed successfully!")
        print("=" * 70)
        print(f"\nTotal companies mapped: {saved_count:,}")
        print("\nNext steps:")
        print("  1. Verify data in TablePlus: corp_code_map table")
        print("  2. Run financial statement collection script")
        print("\n" + "=" * 70)

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Error occurred:")
        print("=" * 70)
        print(str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
