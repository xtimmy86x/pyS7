"""
Example demonstrating WSTRING (Wide String) data type usage.

WSTRING is used for Unicode strings in S7 PLCs and uses UTF-16 encoding.
Each character takes 2 bytes, compared to STRING which uses 1 byte per character (ASCII).

WSTRING structure:
- Byte 0: Maximum length (in characters, not bytes)
- Byte 1: Current length (in characters, not bytes)
- Bytes 2+: UTF-16 BE encoded string data (2 bytes per character)
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client

# PLC connection details
PLC_IP = "192.168.100.230"
RACK = 0
SLOT = 1

client = S7Client(address=PLC_IP, rack=RACK, slot=SLOT)

try:
    client.connect()
    print(f"✓ Connected to PLC at {PLC_IP}")
    
    # ===== READING WSTRING =====
    print("\n" + "="*70)
    print("Reading WSTRING from PLC")
    print("="*70)
    
    # Read a WSTRING with max length 20 characters at DB1, offset 566
    # Format: DB<number>,WS<offset>.<max_length>
    wstring_tags = [
        "DB1,WS566.20",   # test_wstring: WSTRING at byte 566, max 20 chars
        "DB1,WS1078.50",  # test_wstring2: WSTRING at byte 1078, max 50 chars
    ]
    
    try:
        # Read each WSTRING individually to avoid response parsing issues
        values = []
        for tag in wstring_tags:
            result = client.read([tag])
            values.append(result[0])
        for tag, value in zip(wstring_tags, values):
            print(f"  {tag}: '{value}' (length: {len(value)} chars)")
    except Exception as e:
        print(f"  Error reading WSTRING: {e}")
    
    # ===== WRITING WSTRING =====
    print("\n" + "="*70)
    print("Writing WSTRING to PLC")
    print("="*70)
    
    # Write Unicode strings to PLC
    wstring_write_tags = [
        "DB1,WS566.20",   # test_wstring: WSTRING at byte 566, max 20 chars
        "DB1,WS1078.50",  # test_wstring2: WSTRING at byte 1078, max 50 chars
    ]
    
    wstring_values = [
        "Hello 世界! \U0001F30D",  # Unicode with emoji and Chinese (15 chars)
        "Ελληνικά Кириллица",      # Greek and Cyrillic (18 chars)
    ]
    
    try:
        # Write each WSTRING individually
        for tag, value in zip(wstring_write_tags, wstring_values):
            client.write([tag], [value])
        print(f"  ✓ Successfully wrote WSTRING values")
        
        # Read back to verify
        readback = []
        for tag in wstring_write_tags:
            result = client.read([tag])
            readback.append(result[0])
        for tag, written, readback_val in zip(wstring_write_tags, wstring_values, readback):
            match = "✓" if written == readback_val else "✗"
            print(f"  {match} {tag}: wrote '{written}', read '{readback_val}'")
            
    except Exception as e:
        print(f"  Error writing WSTRING: {e}")
    
    # ===== WSTRING vs STRING COMPARISON =====
    print("\n" + "="*70)
    print("WSTRING vs STRING Comparison")
    print("="*70)
    
    print("\nSTRING (ASCII, 1 byte per char):")
    print("  - Max length: 254 characters")
    print("  - Encoding: ASCII (7-bit, characters 0-127)")
    print("  - Size: length + 2 bytes (header)")
    print("  - Use for: English text, simple data")
    print("  - Address format: DB<n>,S<offset>.<length>")
    
    print("\nWSTRING (Unicode, 2 bytes per char):")
    print("  - Max length: 254 characters")
    print("  - Encoding: UTF-16 BE (supports all Unicode)")
    print("  - Size: (length × 2) + 2 bytes (header)")
    print("  - Use for: International text, emojis, special characters")
    print("  - Address format: DB<n>,WS<offset>.<length>")
    
    print("\nExample sizes:")
    print("  STRING[10]:  12 bytes (10 chars + 2 byte header)")
    print("  WSTRING[10]: 22 bytes (10 chars × 2 + 2 byte header)")
    
    # ===== PRACTICAL EXAMPLES =====
    print("\n" + "="*70)
    print("Practical Examples")
    print("="*70)
    
    # Example 1: Product names with international characters
    print("\n1. International product names:")
    product_tags = [
        "DB5,WS0.30",
        "DB5,WS64.30",
        "DB5,WS128.30",
    ]
    
    product_names = [
        "Café Müller",           # German umlauts
        "Hôtel du Château",      # French accents
        "Tokyo 東京 Station",     # Japanese
    ]
    
    try:
        client.write(product_tags, product_names)
        readback = client.read(product_tags)
        print("  Product names:")
        for name in readback:
            print(f"    - {name}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Example 2: Using S7Tag objects for more control
    print("\n2. Using S7Tag objects:")
    from pyS7.tag import S7Tag
    from pyS7.constants import MemoryArea, DataType
    
    wstring_tag = S7Tag(
        memory_area=MemoryArea.DB,
        db_number=1,
        data_type=DataType.WSTRING,
        start=566,         # Byte offset in DB (test_wstring)
        bit_offset=0,
        length=20          # Maximum character count
    )
    
    try:
        # Write with tag object
        test_value = "Test WSTRING 测试"
        client.write([wstring_tag], [test_value])
        
        # Read with tag object
        result = client.read([wstring_tag])
        print(f"  Wrote: '{test_value}'")
        print(f"  Read:  '{result[0]}'")
        print(f"  Match: {result[0] == test_value}")
        print(f"  Tag size: {wstring_tag.size()} bytes")  # (20 × 2) + 4 = 44 bytes
        
    except Exception as e:
        print(f"  Error: {e}")
    
finally:
    client.disconnect()
    print("\n✓ Disconnected from PLC")

print("\n" + "="*70)
print("Notes:")
print("="*70)
print("- WSTRING is available in S7-1200/1500 PLCs")
print("- Older PLCs (S7-300/400) may not support WSTRING")
print("- UTF-16 BE (Big Endian) is the standard encoding for S7 WSTRINGs")
print("- Maximum WSTRING length is 254 characters (not bytes!)")
print("- Each character takes 2 bytes, so WSTRING[254] = 510 bytes + 2 byte header = 512 bytes")
