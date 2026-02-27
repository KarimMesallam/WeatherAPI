#!/usr/bin/env python3
"""Verify FES2022 installation and test tide computation."""
import sys
import time
sys.path.insert(0, '/var/www/dahab-api')

from app.tides_fes2022 import verify_fes2022_installation, compute_tides_fes2022

def main():
    print("=== FES2022 Installation Check ===\n")

    status = verify_fes2022_installation()

    print(f"Cache file: {status['cache_file']}")
    print(f"Cache exists: {status['cache_exists']}")
    print(f"Constituents: {status.get('constituents_count', 0)}")

    if status.get('latitude'):
        print(f"Location: ({status['latitude']}, {status['longitude']})")

    if status['ready']:
        print("\n✓ FES2022 is ready!")
        print("\nTesting tide computation...")

        start = time.time()
        result = compute_tides_fes2022()
        elapsed = time.time() - start

        if result:
            print(f"✓ Success: {len(result)} values in {elapsed:.2f}s")
            print(f"  Range: {min(result)} to {max(result)} cm")
            print(f"  First 6 hours: {result[:6]}")
        else:
            print("✗ Computation failed - check logs")
            return 1
    else:
        print("\n✗ FES2022 not ready")
        print("\nTo set up FES2022:")
        print("  1. Download data: ./download_fes2022.sh")
        print("  2. Extract constants: python3 extract_fes2022_constants.py")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
