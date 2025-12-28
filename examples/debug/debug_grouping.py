"""
Debug mixed tag optimization vs single bit optimization  
"""

import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import map_address_to_tag
from pyS7.requests import prepare_optimized_requests

def debug_mixed_vs_single():
    print("=== Single BIT tag ===")
    tags1 = [map_address_to_tag("DB1,X0.7")]
    requests1, groups1 = prepare_optimized_requests(tags1, max_pdu=240)
    print(f"Tags: {tags1}")
    print(f"Groups: {groups1}")
    for packed_tag, original_tags in groups1.items():
        print(f"Packed tag type: {packed_tag.data_type}")
    
    print("\n=== Mixed tags (different DBs) ===")
    tags2 = [map_address_to_tag("DB1,X0.1"), map_address_to_tag("DB2,I2")]
    requests2, groups2 = prepare_optimized_requests(tags2, max_pdu=240)
    print(f"Tags: {tags2}")
    print(f"Groups: {groups2}")
    for packed_tag, original_tags in groups2.items():
        print(f"Packed tag type: {packed_tag.data_type}")
    
    print("\n=== Multiple BIT tags same DB ===")
    tags3 = [map_address_to_tag("DB1,X0.1"), map_address_to_tag("DB1,X0.7")]
    requests3, groups3 = prepare_optimized_requests(tags3, max_pdu=240)
    print(f"Tags: {tags3}")
    print(f"Groups: {groups3}")
    for packed_tag, original_tags in groups3.items():
        print(f"Packed tag type: {packed_tag.data_type}")

if __name__ == "__main__":
    debug_mixed_vs_single()