"""
Debug the optimized request generation
"""

import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import map_address_to_tag
from pyS7.requests import prepare_optimized_requests

def debug_optimization():
    print("=== Address Parsing ===")
    # Parse the address
    tag = map_address_to_tag("DB1,X0.7")
    print(f"Original tag: {tag}")
    print(f"  start: {tag.start}")
    print(f"  bit_offset: {tag.bit_offset}")
    print(f"  data_type: {tag.data_type}")
    print(f"  length: {tag.length}")
    
    print("\n=== Optimization Process ===")
    # See what happens during optimization
    tags = [tag]
    requests, groups = prepare_optimized_requests(tags, max_pdu=240)
    
    print(f"Number of request groups: {len(requests)}")
    print(f"Request tags: {requests}")
    print(f"Groups mapping: {groups}")
    
    # Check what packed tags were created
    for packed_tag, original_tags in groups.items():
        print(f"\nPacked tag: {packed_tag}")
        print(f"  start: {packed_tag.start}")
        print(f"  bit_offset: {packed_tag.bit_offset}")  
        print(f"  data_type: {packed_tag.data_type}")
        print(f"  length: {packed_tag.length}")
        print(f"  Contains original tags: {original_tags}")

if __name__ == "__main__":
    debug_optimization()